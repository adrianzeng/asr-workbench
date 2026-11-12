"""Sequential batch transcription queue.

Standard library only. One background thread drains the queue one file at a
time (so GPU/CPU never contend with themselves), while the browser polls for
progress. Closing the browser does NOT stop the job: the server owns it.

The worker is injected (`transcribe(cfg, name)`), so this module never imports
server.py and there is no circular dependency.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable


def _item(name: str) -> dict:
    return {
        "name": name,
        "status": "pending",       # pending | running | done | error | cancelled
        "elapsed": 0,
        "job_dir": "",
        "txt_path": "",
        "srt_path": "",
        "output_mode": "",
        "error": "",
    }


class JobManager:
    def __init__(self, worker: Callable, config_loader: Callable):
        self._worker = worker
        self._config_loader = config_loader
        self._lock = threading.Lock()
        self._cancel = threading.Event()
        self._state = self._blank()

    @staticmethod
    def _blank() -> dict:
        return {
            "running": False,
            "cancelled": False,
            "started_at": 0,
            "finished_at": 0,
            "items": [],
            "total": 0,
            "done": 0,
            "failed": 0,
            "current": "",
        }

    def snapshot(self) -> dict:
        with self._lock:
            out = dict(self._state)
            out["items"] = [dict(item) for item in self._state["items"]]
            return out

    def submit(self, names: list[str]) -> tuple[dict | None, str]:
        with self._lock:
            if self._state["running"]:
                return None, "已经有一批在跑了，等它结束或先点「停止这一批」"
            if not names:
                return None, "还没有选文件"
            self._state = self._blank()
            self._state.update({
                "running": True,
                "started_at": time.time(),
                "items": [_item(n) for n in names],
                "total": len(names),
            })
        self._cancel.clear()
        threading.Thread(target=self._run, daemon=True).start()
        return self.snapshot(), ""

    def cancel(self) -> bool:
        with self._lock:
            if not self._state["running"]:
                return False
        # Let the file currently being transcribed finish; skip the rest.
        self._cancel.set()
        return True

    def result(self, name: str) -> dict | None:
        with self._lock:
            item = next(
                (dict(i) for i in self._state["items"]
                 if i["name"] == name and i["status"] == "done"),
                None,
            )
        if not item:
            return None

        def read(path: str) -> str:
            if not path:
                return ""
            try:
                return Path(path).read_text(encoding="utf-8", errors="replace")
            except OSError:
                return ""

        return {
            "name": name,
            "job_dir": item["job_dir"],
            "txt": read(item["txt_path"]),
            "srt": read(item["srt_path"]),
            "txt_path": item["txt_path"],
            "srt_path": item["srt_path"],
            "output_mode": item["output_mode"],
            "elapsed": item["elapsed"],
            "engine": "local",
        }

    # ——— internals ———
    def _update(self, index: int, **fields) -> None:
        with self._lock:
            self._state["items"][index].update(fields)

    def _run(self) -> None:
        try:
            cfg = self._config_loader()
        except Exception as exc:
            self._fail_all(str(exc))
            return

        total = self.snapshot()["total"]
        for index in range(total):
            if self._cancel.is_set():
                self._update(index, status="cancelled")
                continue
            name = self.snapshot()["items"][index]["name"]
            with self._lock:
                self._state["current"] = name
            self._update(index, status="running")
            started = time.time()
            try:
                result = self._worker(cfg, name)
                self._update(
                    index, status="done",
                    elapsed=result.get("elapsed", 0),
                    job_dir=result.get("job_dir", ""),
                    txt_path=result.get("txt_path", ""),
                    srt_path=result.get("srt_path", ""),
                    output_mode=result.get("output_mode", ""),
                )
                with self._lock:
                    self._state["done"] += 1
            except Exception as exc:
                self._update(index, status="error", error=str(exc),
                             elapsed=round(time.time() - started, 1))
                with self._lock:
                    self._state["failed"] += 1

        with self._lock:
            self._state["running"] = False
            self._state["current"] = ""
            self._state["finished_at"] = time.time()
            self._state["cancelled"] = self._cancel.is_set()

    def _fail_all(self, message: str) -> None:
        with self._lock:
            for item in self._state["items"]:
                if item["status"] == "pending":
                    item["status"] = "error"
                    item["error"] = message
                    self._state["failed"] += 1
            self._state["running"] = False
            self._state["finished_at"] = time.time()
