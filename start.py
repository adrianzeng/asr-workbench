"""One-click launcher for ASR Workbench.

Double-click 启动工作台.bat (Windows) or 启动工作台.command (macOS), or run
`python start.py` from a terminal. It checks whether the service is already
up, opens the browser for you, and starts the server in the foreground so
closing the window stops everything. No packages, no PATH edits, no installs.
"""
from __future__ import annotations

import json
import os
import socket
import sys
import threading
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

# Chinese messages must survive Windows' console code page. The .bat sets
# chcp 65001 + PYTHONIOENCODING before calling us.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

if sys.version_info < (3, 10):
    print("  你的 Python 版本太老了，需要 3.12 或更新版本。")
    print("  到 https://www.python.org/downloads/ 装好之后，重新双击本文件。")
    sys.exit(1)

try:
    import first_run  # noqa: E402
    import server  # noqa: E402  (module import has no side effects)
except Exception as exc:
    print(f"  启动文件没能读全：{exc}")
    print("  请确认 start.py、server.py 和 web 文件夹都在同一个目录里。")
    sys.exit(1)


def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def probe_owner(port: int) -> dict | None:
    """Ask who is listening; only reuse the port if it is our own instance."""
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/status", timeout=1
        ) as res:
            return json.loads(res.read().decode("utf-8"))
    except Exception:
        return None


def open_browser(url: str) -> None:
    if os.environ.get("ASR_NO_BROWSER") == "1":
        return
    try:
        webbrowser.open(url)
    except Exception as exc:
        print(f"（浏览器没能自动打开：{exc}）")
        print(f"  请自己复制这个网址到浏览器：{url}")


def main() -> int:
    # Creates config.json with relative paths on a brand-new machine.
    first_run.bootstrap()
    cfg = server.load_config()
    port = int(cfg.get("port", 8765))
    url = f"http://127.0.0.1:{port}"

    print("=" * 52)
    print("   ASR Workbench · 把音视频里说的话变成文字稿")
    print("=" * 52)

    if port_open(port):
        owner = probe_owner(port)
        if owner and owner.get("app_id") == "asr-workbench":
            print(f"  服务已经在运行了，帮你打开页面：")
            print(f"  {url}")
            open_browser(url)
            print("  这个窗口可以关掉，服务会继续跑着。")
            print("=" * 52)
            return 0
        # Some other program owns the port: move to a free one without
        # writing anything back into config.json.
        for candidate in range(port + 1, port + 21):
            if not port_open(candidate):
                port = candidate
                break
        else:
            print("  8765 附近的端口都被占用了，请先关掉占用端口的程序。")
            return 1
        os.environ["ASR_PORT_OVERRIDE"] = str(port)
        url = f"http://127.0.0.1:{port}"

    print("  正在启动，稍等一下…")
    report = server.status_report(cfg)
    if not report.get("models_ready"):
        print("  第一次使用要下载约 2.8 GB 模型（国内源，只此一次）。")
        print("  下载期间别关这个黑窗口；关了下次打开会接着下。")

    threading.Timer(1.2, open_browser, args=(url,)).start()
    print(f"  启动好了：{url}")
    print("  浏览器会自动弹出来；没弹的话，把上面网址复制到浏览器。")
    print("  用完直接关掉这个窗口，服务就停了。")
    print("-" * 52)
    sys.stdout.flush()

    try:
        server.main()
    except KeyboardInterrupt:
        print("\n  已停止。想再用，重新双击启动文件就行。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
