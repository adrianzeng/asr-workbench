"""Model download: pure standard library, resumable, checksum-verified.

The manifest (models_manifest.json) is the only source of truth for file names,
sizes, SHA-256 digests and pinned revisions. Nothing here imports server.py,
so the downloader can also be used by a standalone repair script.
"""
from __future__ import annotations

import errno
import hashlib
import json
import os
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / "models_manifest.json"
CHUNK = 1 << 20                      # 1 MiB heap buffer (never stack-allocate 4 GB)
READ_TIMEOUT = 60.0                  # per-read idle timeout
MAX_ATTEMPTS = 3

DEFAULT_TEMPLATE = (
    "https://modelscope.cn/models/{owner}/{repo}/resolve/{revision}/{file}"
)


def load_manifest() -> dict:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def model_dir(data_root: Path, model_id: str) -> Path:
    """Where OneAsr expects the weights: {data-root}/models/<install dir>/."""
    entry = load_manifest()["models"][model_id]
    return Path(data_root) / "models" / entry["dir"]


def file_url(entry: dict, file: dict, cfg: dict) -> str:
    """Two sources: the pinned ModelScope template, or a flat custom mirror.

    A custom mirror is laid out as {base}/{install-dir}/{file-path}; this is the
    single configurable hook for a future netdisk / object-storage mirror.
    """
    source = str(cfg.get("download_source", "modelscope")).strip().lower()
    if source == "custom":
        base = str(cfg.get("download_base_url", "")).strip().rstrip("/")
        if not base:
            raise ValueError("下载源选了 custom，但没填 download_base_url")
        return f"{base}/{entry['dir']}/{file['path']}"
    template = str(cfg.get("download_url_template") or DEFAULT_TEMPLATE)
    return template.format(
        owner=entry["owner"],
        repo=entry["repo"],
        revision=file["revision"],
        file=file["path"],
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(CHUNK)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def file_is_ready(path: Path, size: int, sha256: str) -> bool:
    try:
        if path.stat().st_size != size:
            return False
    except OSError:
        return False
    return sha256_file(path) == sha256


def retry_backoff(attempt: int) -> float:
    return min(2 ** attempt, 30)


def preflight_disk(target_dir: Path, total_bytes: int) -> tuple[bool, str]:
    """Peak disk use is roughly .part + finished file, so ask for 1.1x."""
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
        free = shutil.disk_usage(target_dir).free
    except OSError as exc:
        return False, f"无法检查磁盘空间：{exc}"
    need = int(total_bytes * 1.1)
    if free < need:
        return False, (
            f"磁盘空间不够：还需要约 {need / 1024**3:.1f} GB，"
            f"当前可用 {free / 1024**3:.1f} GB。"
            "可以清理磁盘，或把整个文件夹搬到 D 盘（不用重装、不用重下）。"
        )
    return True, ""


def _classify_os_error(exc: OSError) -> str:
    if getattr(exc, "errno", None) in (errno.ENOSPC, errno.EDQUOT):
        return "disk_full"
    return "network"


def download_one(
    url: str,
    target: Path,
    size: int,
    sha256: str,
    on_progress: Callable[[int], None],
    cancel,
    attempts: int = MAX_ATTEMPTS,
) -> str:
    """Download one file. Returns 'ok' or 'error:<kind>:<detail>'.

    on_progress receives the *absolute* bytes already present for this file,
    not a delta, so a discarded .part retry cannot inflate the overall total.
    """
    if file_is_ready(target, size, sha256):
        on_progress(size)
        return "ok"

    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    last_kind, last_detail = "unknown", ""

    for attempt in range(attempts):
        if cancel.is_set():
            return "error:cancelled:已取消"

        existing = part.stat().st_size if part.exists() else 0
        if existing > size:
            part.unlink(missing_ok=True)
            existing = 0

        headers = {"User-Agent": "ASR-Workbench/1.1"}
        mode = "wb"
        if existing:
            headers["Range"] = f"bytes={existing}-"
            mode = "ab"
        else:
            part.unlink(missing_ok=True)

        try:
            request = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(request, timeout=READ_TIMEOUT) as response:
                status = getattr(response, "status", 200)
                # A 200 to a Range request means the server ignored it; 416
                # means our .part is stale. In both cases start this file over.
                if existing and status != 206:
                    part.unlink(missing_ok=True)
                    existing = 0
                    mode = "wb"
                    on_progress(0)

                with open(part, mode) as handle:
                    while True:
                        if cancel.is_set():
                            return "error:cancelled:已取消"
                        chunk = response.read(CHUNK)
                        if not chunk:
                            break
                        handle.write(chunk)
                        existing += len(chunk)
                        on_progress(existing)

            if part.stat().st_size != size:
                last_kind = "network"
                last_detail = f"文件大小不符（{part.stat().st_size} / {size}）"
                part.unlink(missing_ok=True)
                on_progress(0)
                time.sleep(retry_backoff(attempt))
                continue

            if sha256_file(part) != sha256:
                last_kind = "sha256_mismatch"
                last_detail = "校验没过，已丢弃重下"
                part.unlink(missing_ok=True)
                on_progress(0)
                time.sleep(retry_backoff(attempt))
                continue

            os.replace(part, target)
            on_progress(size)
            return "ok"

        except urllib.error.HTTPError as exc:
            if exc.code == 416:
                part.unlink(missing_ok=True)
                on_progress(0)
                continue
            if 400 <= exc.code < 500 and exc.code not in (408, 429):
                return f"error:http_4xx:HTTP {exc.code}"
            last_kind, last_detail = "network", f"HTTP {exc.code}"
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            reason = str(getattr(exc, "reason", exc))
            last_kind = "offline" if "getaddrinfo" in reason or "Name or service" in reason else "network"
            last_detail = reason[:200]
        except OSError as exc:
            kind = _classify_os_error(exc)
            if kind == "disk_full":
                return "error:disk_full:磁盘写满了，已下的部分会留着"
            last_kind, last_detail = kind, str(exc)[:200]

        time.sleep(retry_backoff(attempt))

    return f"error:{last_kind}:{last_detail or '重试多次仍未成功'}"
