"""One-click launcher for ASR Workbench.

Double-click 启动工作台.bat (Windows) or 启动工作台.command (macOS), or run
`python start.py` from a terminal. It checks whether the service is already
up, opens the browser for you, and starts the server in the foreground so
closing the window stops everything. No packages, no PATH edits, no installs.
"""
from __future__ import annotations

import os
import socket
import sys
import threading
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
    import server  # noqa: E402  (module import has no side effects)
except Exception as exc:
    print(f"  启动文件没能读全：{exc}")
    print("  请确认 start.py、server.py 和 web 文件夹都在同一个目录里。")
    sys.exit(1)


def port_open(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def open_browser(url: str) -> None:
    if os.environ.get("ASR_NO_BROWSER") == "1":
        return
    try:
        webbrowser.open(url)
    except Exception as exc:
        print(f"（浏览器没能自动打开：{exc}）")
        print(f"  请自己复制这个网址到浏览器：{url}")


def main() -> int:
    cfg = server.load_config()
    port = int(cfg.get("port", 8765))
    url = f"http://127.0.0.1:{port}"

    print("=" * 52)
    print("   ASR Workbench · 把视频里说的话变成文字稿")
    print("=" * 52)

    if port_open(port):
        print(f"  服务已经在运行了，帮你打开页面：")
        print(f"  {url}")
        open_browser(url)
        print("  这个窗口可以关掉，服务会继续在后台跑着。")
        print("=" * 52)
        return 0

    print("  正在启动，稍等一下…")
    report = server.status_report(cfg)
    if not report.get("ready"):
        print("  提示：环境还没配齐，页面里会告诉你缺什么，")
        print("        展开最下面的「高级设置」照着填就行。")

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
