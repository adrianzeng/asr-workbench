"""Model readiness + background download state machine.

Mirrors jobs.JobManager: an injected config loader/saver (no circular import),
a single daemon thread, a lock-protected snapshot, and terminal state reported
ONLY through snapshot() — progress callbacks never emit a completion event.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable

import downloader

ROOT = Path(__file__).resolve().parent
DEFAULT_MODELS = ("0.6b", "ctc")

ERROR_MESSAGES = {
    "network": "网络不太稳，已经重试过几次。检查网络后点「重试」，已经下好的不会丢。",
    "offline": "现在连不上网。连上 WiFi 后点「重试」，已经下好的不会丢。",
    "disk_full": "磁盘写满了。清理一下空间，或把整个文件夹搬到 D 盘（不用重装、不用重下）。",
    "sha256_mismatch": "下载的文件校验没过，已经自动丢弃重下；再试一次通常就好了。",
    "http_4xx": "下载地址返回了错误，可能是镜像地址填错了。检查「高级设置」里的下载源。",
    "cancelled": "已停止，下好的部分留着，下次接着下。",
    "unknown": "下载没成功，点「重试」再试一次，已经下好的不会丢。",
}


def _blank() -> dict:
    return {
        "state": "idle",            # idle|checking|downloading|verifying|completed|failed|cancelled
        "models": [],
        "phase": "",
        "current_model": "",
        "current_file": "",
        "file_index": 0,
        "file_count": 0,
        "downloaded_bytes": 0,
        "total_bytes": 0,
        "percent": 0.0,
        "speed_bytes_per_sec": 0,
        "eta_seconds": 0,
        "started_at": 0.0,
        "finished_at": 0.0,
        "files": [],
        "error": "",
        "error_kind": "",
        "retries": 0,
        "activated": False,
        "message": "",
    }


class ModelManager:
    def __init__(self, config_loader: Callable[[], dict],
                 config_saver: Callable[[dict], None], root: Path = ROOT):
        self._config_loader = config_loader
        self._config_saver = config_saver
        self._root = Path(root)
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._state = _blank()
        # path -> (mtime_ns, size, ready); hashing 4 GB on every page load is
        # far too slow, so reuse the verdict until the file actually changes.
        self._ready_cache: dict[str, tuple[int, int, bool]] = {}

    # ——— paths ———
    def _data_root(self, cfg: dict) -> Path:
        value = str(cfg.get("oneasr_data_root") or "./runtime/oneasr")
        path = Path(value)
        return path if path.is_absolute() else (self._root / path).resolve()

    def _cli_path(self, cfg: dict) -> Path:
        value = str(cfg.get("oneasr_cli") or "")
        path = Path(value)
        return path if path.is_absolute() else (self._root / path)

    # ——— readiness ———
    def _ready(self, path: Path, size: int, digest: str) -> bool:
        try:
            stat = path.stat()
        except OSError:
            return False
        key = str(path)
        cached = self._ready_cache.get(key)
        if cached and cached[0] == stat.st_mtime_ns and cached[1] == stat.st_size:
            return cached[2]
        ok = stat.st_size == size and downloader.sha256_file(path) == digest
        self._ready_cache[key] = (stat.st_mtime_ns, stat.st_size, ok)
        return ok

    def _cli_status(self, cfg: dict) -> tuple[bool, bool, str]:
        """(cli_ok, can_start, reason) — a purely local check, never networked."""
        cli = self._cli_path(cfg)
        if not cli.is_file():
            return False, False, "没找到听写程序，请确认安装包已完整解压"
        try:
            run = subprocess.run(
                [str(cli), "status", "--json", "--data-root", str(self._data_root(cfg))],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=30,
            )
            data = json.loads(run.stdout)
            state = data.get("can_start", {})
            return True, bool(state.get("ok")), str(state.get("reason") or "")
        except Exception as exc:
            return True, False, f"没能读取听写程序状态：{exc}"

    def check(self) -> dict:
        cfg = self._config_loader()
        manifest = downloader.load_manifest()
        data_root = self._data_root(cfg)
        models = []
        for model_id, entry in manifest["models"].items():
            folder = data_root / "models" / entry["dir"]
            ready_files = 0
            downloaded = 0
            for file in entry["files"]:
                target = folder / file["path"]
                if self._ready(target, file["size"], file["sha256"]):
                    ready_files += 1
                    downloaded += file["size"]
                else:
                    part = target.with_name(target.name + ".part")
                    if part.exists():
                        downloaded += min(part.stat().st_size, file["size"])
            ready = ready_files == len(entry["files"])
            models.append({
                "id": model_id,
                "label": entry["label"],
                "dir": entry["dir"],
                "ready": ready,
                "ready_files": ready_files,
                "file_count": len(entry["files"]),
                "size_bytes": entry["total_bytes"],
                "downloaded_bytes": downloaded,
                "remaining_bytes": max(0, entry["total_bytes"] - downloaded),
                "need_download": not ready,
            })

        cli_ok, can_start, reason = self._cli_status(cfg)
        by_id = {m["id"]: m for m in models}
        base_ready = all(by_id[k]["ready"] for k in DEFAULT_MODELS if k in by_id)
        needs_setup = not (cli_ok and base_ready)
        needed = sum(m["size_bytes"] - m["downloaded_bytes"]
                     for m in models if m["id"] in DEFAULT_MODELS and not m["ready"])
        try:
            free = shutil.disk_usage(data_root).free
        except OSError:
            free = 0

        if not cli_ok:
            message = reason
        elif not base_ready:
            message = "第一次使用，需要下载约 2.8 GB 的听写模型。只此一次，之后断网也能用。"
        elif not can_start:
            message = reason or "听写程序还没准备好，请点「重新检查」。"
        else:
            message = "环境就绪，可以直接开始转文字。"
        return {
            "models": models,
            "can_start": can_start,
            "cli_ok": cli_ok,
            "cli_error": reason,
            "needs_setup": needs_setup,
            "models_root": str(data_root / "models"),
            "estimated_total_bytes": needed,
            "disk_free_bytes": free,
            "disk_needed_bytes": int(needed * 1.1),
            "message": message,
        }

    # ——— download ———
    def snapshot(self) -> dict:
        with self._lock:
            out = dict(self._state)
            out["files"] = [dict(item) for item in self._state["files"]]
            out["models"] = list(self._state["models"])
            return out

    def start(self, model_ids: list[str], activate: bool = False) -> tuple[dict | None, str]:
        manifest = downloader.load_manifest()
        ids = [str(x) for x in model_ids]
        if not ids:
            return None, "还没有选要下载的模型"
        if any(x not in manifest["models"] for x in ids):
            return None, "有不认识的模型名"
        with self._lock:
            if self._state["state"] in ("checking", "downloading", "verifying"):
                return None, "已经有一批在下载了，等它结束或先点「停止」"

        cfg = self._config_loader()
        data_root = self._data_root(cfg)
        tasks = []
        files_state = []
        for model_id in ids:
            entry = manifest["models"][model_id]
            folder = data_root / "models" / entry["dir"]
            for file in entry["files"]:
                target = folder / file["path"]
                is_ready = self._ready(target, file["size"], file["sha256"])
                url = "" if is_ready else downloader.file_url(entry, file, cfg)
                tasks.append((model_id, entry, file, target, url, is_ready))
                files_state.append({
                    "model": model_id,
                    "path": file["path"],
                    "size": file["size"],
                    "done_bytes": file["size"] if is_ready else 0,
                    "state": "skipped" if is_ready else "pending",
                })

        total = sum(t[2]["size"] for t in tasks)
        pending = sum(t[2]["size"] for t in tasks if not t[5])
        ok, why = downloader.preflight_disk(data_root, pending)
        if not ok:
            return None, why

        with self._lock:
            self._state = _blank()
            self._state.update({
                "state": "downloading",
                "models": ids,
                "file_count": len(tasks),
                "total_bytes": total,
                "downloaded_bytes": sum(f["done_bytes"] for f in files_state),
                "files": files_state,
                "started_at": time.time(),
                "message": "正在下载模型，可以先去忙别的；别关黑色窗口。",
            })
            self._state["percent"] = (
                self._state["downloaded_bytes"] / total * 100 if total else 0
            )
        self._cancel.clear()
        threading.Thread(target=self._run, args=(tasks, activate), daemon=True).start()
        return self.snapshot(), ""

    def cancel(self) -> bool:
        with self._lock:
            if self._state["state"] not in ("checking", "downloading", "verifying"):
                return False
        self._cancel.set()
        return True

    def _on_progress(self, index: int, done: int) -> None:
        with self._lock:
            state = self._state
            state["files"][index]["done_bytes"] = done
            state["downloaded_bytes"] = sum(f["done_bytes"] for f in state["files"])
            total = state["total_bytes"] or 1
            state["percent"] = round(state["downloaded_bytes"] / total * 100, 1)
            now = time.monotonic()
            last = getattr(self, "_tick", None)
            if last is None or now - last[0] >= 0.35:
                if last:
                    elapsed = now - last[0]
                    state["speed_bytes_per_sec"] = max(
                        0, int((state["downloaded_bytes"] - last[1]) / elapsed)
                    )
                    speed = state["speed_bytes_per_sec"]
                    state["eta_seconds"] = (
                        int((total - state["downloaded_bytes"]) / speed) if speed else 0
                    )
                self._tick = (now, state["downloaded_bytes"])

    def _run(self, tasks: list, activate: bool) -> None:
        self._tick = None
        failed = False
        for index, (model_id, entry, file, target, url, is_ready) in enumerate(tasks):
            if self._cancel.is_set():
                break
            if is_ready:
                continue
            with self._lock:
                self._state["phase"] = "downloading"
                self._state["current_model"] = entry["dir"]
                self._state["current_file"] = file["path"]
                self._state["file_index"] = index + 1
                self._state["files"][index]["state"] = "downloading"
                self._state["retries"] = 0

            result = downloader.download_one(
                url, target, file["size"], file["sha256"],
                lambda done, i=index: self._on_progress(i, done),
                self._cancel,
            )
            if result == "ok":
                with self._lock:
                    self._state["files"][index]["state"] = "done"
                self._ready_cache.pop(str(target), None)
                continue

            parts = result.split(":", 2)
            kind = parts[1] if len(parts) > 1 else "unknown"
            detail = parts[2] if len(parts) > 2 else ""
            with self._lock:
                self._state["files"][index]["state"] = "error"
                self._state["error_kind"] = kind
                self._state["error"] = detail
            failed = True
            break

        with self._lock:
            state = self._state
            if self._cancel.is_set():
                state["state"] = "cancelled"
                state["error_kind"] = "cancelled"
                state["message"] = ERROR_MESSAGES["cancelled"]
            elif failed:
                state["state"] = "failed"
                state["message"] = ERROR_MESSAGES.get(state["error_kind"], ERROR_MESSAGES["unknown"])
            else:
                state["state"] = "completed"
                state["phase"] = "completed"
                state["percent"] = 100.0
                state["eta_seconds"] = 0
                state["message"] = "模型准备好了，正在打开工作台…"
                if activate and state["models"]:
                    chosen = state["models"][-1]
                    if chosen in ("0.6b", "1.7b"):
                        cfg = self._config_loader()
                        cfg["asr_model"] = chosen
                        self._config_saver(cfg)
                        state["activated"] = True
            state["finished_at"] = time.time()
            state["current_file"] = ""
            state["phase"] = state["state"]
