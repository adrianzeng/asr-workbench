#!/usr/bin/env python3
"""ASR Workbench - a tiny, dependency-free local backend.

Serves the web UI and runs ffmpeg + OneAsr CLI on files placed in the inbox.
All external paths come from config.json; nothing here is tied to a
particular machine, note-taking app, or knowledge base.
"""

from __future__ import annotations

import json
import mimetypes
import shutil
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
CONFIG_PATH = ROOT / "config.json"
EXAMPLE_PATH = ROOT / "config.example.json"

MEDIA_SUFFIXES = frozenset(
    ".wav .mp3 .flac .m4a .aac .ogg .opus .wma "
    ".mp4 .mkv .mov .webm .avi .flv .ts .m4v .mpeg .mpg .wmv .3gp".split()
)

DEFAULTS = {
    "ffmpeg": "ffmpeg",
    "oneasr_cli": "",
    "oneasr_data_root": "",
    "inbox_dir": "./inbox",
    "output_dir": "./output",
    "work_dir": "./work",
    "language": "zh",
    "asr_model": "0.6b",
    "aligner": "ctc",
    "backend": "auto",
    "port": 8765,
}


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[warn] config.json unreadable, using defaults: {exc}", file=sys.stderr)
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def resolve_path(value: str | Path) -> Path:
    p = Path(value).expanduser()
    return p.resolve() if p.is_absolute() else (ROOT / p).resolve()


def find_binary(value: str) -> str | None:
    if not value:
        return None
    p = Path(value).expanduser()
    if p.is_file():
        return str(p)
    return shutil.which(value)


def status_report(cfg: dict) -> dict:
    ffmpeg = find_binary(cfg.get("ffmpeg", ""))
    cli = find_binary(cfg.get("oneasr_cli", ""))
    inbox = resolve_path(cfg.get("inbox_dir", "./inbox"))
    output = resolve_path(cfg.get("output_dir", "./output"))
    checks = {
        "ffmpeg": bool(ffmpeg),
        "oneasr_cli": bool(cli),
        "inbox": inbox.is_dir(),
        "output": output.is_dir(),
    }
    return {
        "checks": checks,
        "ffmpeg_path": ffmpeg or "",
        "oneasr_cli_path": cli or "",
        "inbox_path": str(inbox),
        "output_path": str(output),
        "ready": all(checks.values()),
        "hint": "" if all(checks.values()) else "请在设置页补全路径，见 README 第 3 节",
    }


def list_inbox(cfg: dict) -> list[dict]:
    inbox = resolve_path(cfg.get("inbox_dir", "./inbox"))
    if not inbox.is_dir():
        return []
    return [
        {"name": f.name, "size": f.stat().st_size}
        for f in sorted(inbox.iterdir(), key=lambda x: x.name.lower())
        if f.is_file() and f.suffix.lower() in MEDIA_SUFFIXES
    ]


def transcribe(cfg: dict, name: str) -> dict:
    inbox = resolve_path(cfg.get("inbox_dir", "./inbox"))
    src = (inbox / name).resolve()
    if inbox not in src.parents:
        raise ValueError("文件不在 inbox 目录内")
    if not src.is_file() or src.suffix.lower() not in MEDIA_SUFFIXES:
        raise ValueError("不支持的文件类型")

    ffmpeg = find_binary(cfg.get("ffmpeg", ""))
    cli = find_binary(cfg.get("oneasr_cli", ""))
    if not ffmpeg:
        raise RuntimeError("找不到 ffmpeg，请检查设置页或 PATH")
    if not cli:
        raise RuntimeError("找不到 OneAsr CLI，请检查设置页")

    work = resolve_path(cfg.get("work_dir", "./work"))
    output = resolve_path(cfg.get("output_dir", "./output"))
    work.mkdir(parents=True, exist_ok=True)
    output.mkdir(parents=True, exist_ok=True)
    wav = work / f"{src.stem}.wav"

    # Convert to 16 kHz mono PCM WAV ourselves. OneAsr copies a compliant WAV
    # directly instead of spawning its own ffmpeg, which avoids "os error 5"
    # on some Windows setups. Transcription/alignment output is unchanged.
    run = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
         "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", str(wav)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if run.returncode != 0:
        raise RuntimeError(f"ffmpeg 转码失败：{run.stderr.strip()[:800]}")

    cmd = [
        cli, "transcribe", "--input", str(wav),
        "--language", cfg.get("language", "zh"),
        "--backend", cfg.get("backend", "auto"),
        "--asr", cfg.get("asr_model", "0.6b"),
        "--aligner", cfg.get("aligner", "ctc"),
        "--txt", "--output-dir", str(output),
    ]
    data_root = str(cfg.get("oneasr_data_root", "")).strip()
    if data_root:
        cmd += ["--data-root", str(resolve_path(data_root))]

    started = time.time()
    run = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    elapsed = round(time.time() - started, 1)
    if run.returncode != 0:
        raise RuntimeError(f"转写失败：{(run.stderr or run.stdout).strip()[-1200:]}")

    srt_path = output / f"{src.stem}.srt"
    txt_path = output / f"{src.stem}.txt"
    return {
        "elapsed": elapsed,
        "srt": srt_path.read_text(encoding="utf-8", errors="replace") if srt_path.exists() else "",
        "txt": txt_path.read_text(encoding="utf-8", errors="replace") if txt_path.exists() else "",
        "srt_path": str(srt_path) if srt_path.exists() else "",
        "txt_path": str(txt_path) if txt_path.exists() else "",
        "log": (run.stdout or "").strip()[-800:],
    }


class Handler(BaseHTTPRequestHandler):
    server_version = "ASRWorkbench/0.1"

    def log_message(self, fmt, *args):
        print(f"[http] {fmt % args}", file=sys.stderr)

    def _json(self, payload, code=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        length = int(self.headers.get("Content-Length", "0"))
        if not length:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def _static(self, path: str):
        rel = path.lstrip("/") or "index.html"
        target = (WEB_DIR / rel).resolve()
        if WEB_DIR not in target.parents or not target.is_file():
            self.send_error(404)
            return
        ctype = mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") or ctype in {"application/javascript", "application/json"}:
            ctype += "; charset=utf-8"
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = urlparse(self.path).path
        try:
            if path == "/api/config":
                return self._json(load_config())
            if path == "/api/status":
                return self._json(status_report(load_config()))
            if path == "/api/files":
                return self._json({"files": list_inbox(load_config())})
            return self._static(path)
        except Exception as exc:
            return self._json({"error": str(exc)}, 500)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            body = self._body()
            if path == "/api/config":
                cfg = load_config()
                cfg.update({k: v for k, v in body.items() if k in DEFAULTS})
                save_config(cfg)
                return self._json({"ok": True, "config": cfg})
            if path == "/api/transcribe":
                return self._json(transcribe(load_config(), str(body.get("name", ""))))
            return self._json({"error": "unknown endpoint"}, 404)
        except Exception as exc:
            return self._json({"error": str(exc)}, 500)


def main():
    cfg = load_config()
    # One-shot mode: no long-running server, no browser needed.
    # Useful on terminals that restrict child processes of background services.
    if len(sys.argv) >= 3 and sys.argv[1] == "--once":
        try:
            result = transcribe(cfg, sys.argv[2])
        except Exception as exc:
            import traceback
            traceback.print_exc()
            print(f"转写失败：{type(exc).__name__}: {exc}", file=sys.stderr)
            sys.exit(1)
        print(f"完成：{result['srt_path']}  /  {result['txt_path']}  ({result['elapsed']} 秒)")
        return
    if not CONFIG_PATH.exists() and EXAMPLE_PATH.exists():
        print("[hint] config.json 尚未创建，请在设置页保存一次。")
    port = int(cfg.get("port", 8765))
    report = status_report(cfg)
    print(f"ASR Workbench  ->  http://127.0.0.1:{port}")
    for key, ok in report["checks"].items():
        print(f"  {key:12s} {'OK' if ok else 'MISSING'}")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
