#!/usr/bin/env python3
"""Build the V1.1 Windows zip. Standard library only, no git required.

    python build_release.py

Produces dist/ASR_Workbench_v1.1_win64.zip plus SHA256SUMS.txt.
Any failed check aborts before the zip is written.
"""
from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
ZIP_PATH = DIST / "ASR_Workbench_v1.1_win64.zip"
TOP = "ASR_Workbench"
PY_INSTALLER = ROOT / "release_assets" / "python-3.12.10-amd64.exe"
PY_IN_ZIP = "先装 Python（双击）.exe"

CODE_FILES = [
    ".gitattributes", ".gitignore", "LICENSE", "README.md", "requirements.txt",
    "config.example.json", "models_manifest.json", "server.py", "start.py",
    "jobs.py", "cloud_asr.py", "rewrite.py", "downloader.py",
    "models_runtime.py", "first_run.py", "build_release.py",
    "启动工作台.bat", "启动工作台.command", "使用说明.txt",
    "THIRD_PARTY_NOTICES.md",
]
CODE_DIRS = ["web", "THIRD_PARTY_LICENSES"]
RUNTIME_FILES = [
    "runtime/oneasr/oneasr-cli.exe",
    "runtime/oneasr/oneasr.exe",
    "runtime/oneasr/bin/ffmpeg.exe",
    "runtime/oneasr/README.txt",
]
EMPTY_DIRS = [
    "inbox/.keep", "output/.keep", "work/.keep",
    "runtime/oneasr/models/.keep",
    "runtime/oneasr/output/.keep", "runtime/oneasr/runs/.keep",
]

# Sentences that would force a beginner onto the command line.
README_FORBIDDEN = [
    r"oneasr-cli download --model",
    r"从 <https://github\.com/eclipse005/OneAsr/releases> 下载",
    r"把 ffmpeg / OneAsr 的路径填进去",
    r"<your-repo-url>",
    r"E:\\ASR_Test",
]


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def check(ok: bool, label: str, detail: str = "") -> None:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f" — {detail}" if detail else ""))
    if not ok:
        raise SystemExit(f"打包中止：{label}")


def preflight() -> list[tuple[Path, str, int]]:
    """Return [(source, arcname, unix_mode)]."""
    items: list[tuple[Path, str, int]] = []
    missing: list[str] = []

    def add(src: Path, rel: str, mode: int = 0o644) -> None:
        if not src.is_file():
            missing.append(str(src.relative_to(ROOT)) if src.is_relative_to(ROOT) else str(src))
            return
        items.append((src, f"{TOP}/{rel}", mode))

    for name in CODE_FILES:
        p = ROOT / name
        mode = 0o755 if name == "启动工作台.command" else 0o644
        add(p, name, mode)
    for d in CODE_DIRS:
        base = ROOT / d
        if not base.is_dir():
            missing.append(d + "/")
            continue
        for p in sorted(base.rglob("*")):
            if p.is_file() and "__pycache__" not in p.parts:
                add(p, p.relative_to(ROOT).as_posix())
    for name in RUNTIME_FILES:
        add(ROOT / name, name)
    add(PY_INSTALLER, PY_IN_ZIP)

    if missing:
        raise SystemExit("缺少打包必需文件：\n  " + "\n  ".join(missing))
    return items


def validate_sources(items) -> None:
    print("打包前校验")
    cfg = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
    path_keys = ("ffmpeg", "oneasr_cli", "oneasr_data_root",
                 "inbox_dir", "output_dir", "work_dir")
    bad_paths = [k for k in path_keys if re.search(r"[A-Za-z]:[\\/]", str(cfg.get(k, "")))]
    check(not bad_paths, "config.example.json 的路径字段全相对（无盘符）",
          "含盘符: " + ", ".join(bad_paths) if bad_paths else "无")

    bat = (ROOT / "启动工作台.bat").read_bytes()
    check(b"\r\n" in bat and bat.replace(b"\r\n", b"").find(b"\n") == -1,
          "启动工作台.bat 全 CRLF")
    cmd = (ROOT / "启动工作台.command").read_bytes()
    check(b"\r\n" not in cmd, "启动工作台.command 全 LF")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    bad = [p for p in README_FORBIDDEN if re.search(p, readme)]
    check(not bad, "README 不再要求用户敲命令 / 手填路径", "残留: " + ", ".join(bad) if bad else "无")

    manifest = (ROOT / "models_manifest.json").read_text(encoding="utf-8")
    check("sha256" in manifest and "revision" in manifest,
          "模型清单带固定版本与 sha256")
    check((ROOT / "THIRD_PARTY_NOTICES.md").is_file()
          and (ROOT / "THIRD_PARTY_LICENSES" / "GPL-3.0.txt").is_file(),
          "第三方声明与许可证全文齐备")

    # The GPL+nonfree ffmpeg from the upstream bundle must never be shipped.
    import subprocess
    r = subprocess.run([str(ROOT / "runtime/oneasr/bin/ffmpeg.exe"), "-version"],
                       capture_output=True, text=True, errors="replace", timeout=30)
    check("--enable-nonfree" not in (r.stdout or ""),
          "随包 ffmpeg 不含 --enable-nonfree（可合规再分发）",
          (r.stdout or "").splitlines()[0][:70] if r.stdout else "无输出")


def write_zip(items) -> None:
    DIST.mkdir(exist_ok=True)
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    t0 = time.time()
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for src, arc, mode in items:
            zi = zipfile.ZipInfo(arc, date_time=time.localtime(src.stat().st_mtime)[:6])
            zi.create_system = 3
            zi.external_attr = (0o100000 | mode) << 16
            zi.compress_type = zipfile.ZIP_DEFLATED
            with zf.open(zi, "w") as out, src.open("rb") as inp:
                shutil.copyfileobj(inp, out, 1 << 20)
        for rel in EMPTY_DIRS:
            zi = zipfile.ZipInfo(f"{TOP}/{rel}")
            zi.create_system = 3
            zi.external_attr = 0o100644 << 16
            zi.compress_type = zipfile.ZIP_DEFLATED
            with zf.open(zi, "w") as out:
                out.write(b"")
    print(f"  写出 {ZIP_PATH.name}  ({time.time()-t0:.1f}s)")


def validate_zip(items) -> None:
    print("压缩包校验")
    with zipfile.ZipFile(ZIP_PATH) as zf:
        names = zf.namelist()
        check(all(n.startswith(TOP + "/") for n in names),
              "顶层只有 ASR_Workbench/ 一个目录", f"{len(names)} 个条目")
        check(not any(n.endswith("/config.json") for n in names),
              "不含本机 config.json")
        check(not any(n.endswith((".safetensors", ".part", ".zip", ".7z")) for n in names),
              "不含模型权重 / 断点文件 / 嵌套压缩包")
        model_entries = [n for n in names if "/runtime/oneasr/models/" in n and not n.endswith(".keep")]
        check(not model_entries, "runtime/oneasr/models/ 里只有 .keep",
              f"{len(model_entries)} 个多余条目")
        required = [
            f"{TOP}/使用说明.txt", f"{TOP}/THIRD_PARTY_NOTICES.md",
            f"{TOP}/启动工作台.bat", f"{TOP}/启动工作台.command",
            f"{TOP}/{PY_IN_ZIP}", f"{TOP}/runtime/oneasr/oneasr-cli.exe",
            f"{TOP}/runtime/oneasr/bin/ffmpeg.exe", f"{TOP}/models_manifest.json",
            f"{TOP}/THIRD_PARTY_LICENSES/GPL-3.0.txt",
            f"{TOP}/web/index.html", f"{TOP}/web/author-qr.png",
        ]
        absent = [n for n in required if n not in names]
        check(not absent, "必需文件齐全", "缺: " + ", ".join(absent) if absent else "无")

        # byte-for-byte identity for the three binaries + installer
        src_by_arc = {arc: src for src, arc, _ in items}
        for arc in (f"{TOP}/runtime/oneasr/oneasr-cli.exe",
                    f"{TOP}/runtime/oneasr/oneasr.exe",
                    f"{TOP}/runtime/oneasr/bin/ffmpeg.exe",
                    f"{TOP}/{PY_IN_ZIP}"):
            with zf.open(arc) as f:
                h = hashlib.sha256()
                for chunk in iter(lambda: f.read(1 << 20), b""):
                    h.update(chunk)
            check(h.hexdigest() == sha256_file(src_by_arc[arc]),
                  f"二进制与源文件一致  {arc.split('/')[-1]}")

        bat = zf.read(f"{TOP}/启动工作台.bat")
        cmd = zf.read(f"{TOP}/启动工作台.command")
        check(b"\r\n" in bat and b"\n" not in bat.replace(b"\r\n", b""),
              "zip 内 .bat 仍是 CRLF")
        check(b"\r\n" not in cmd, "zip 内 .command 仍是 LF")
        readme = zf.read(f"{TOP}/README.md").decode("utf-8")
        check(not any(re.search(p, readme) for p in README_FORBIDDEN),
              "zip 内 README 无命令行安装步骤")
        raw = sum(i.file_size for i in zf.infolist())

    sums = hashlib.sha256(ZIP_PATH.read_bytes()).hexdigest()
    (DIST / "SHA256SUMS.txt").write_text(f"{sums}  {ZIP_PATH.name}\n", encoding="utf-8")
    size = ZIP_PATH.stat().st_size
    print("\n产物")
    print(f"  {ZIP_PATH}")
    print(f"  压缩后 {size/1048576:.1f} MB  |  解压后 {raw/1048576:.1f} MB  |  {len(names)} 个条目")
    print(f"  SHA256 {sums}")


def main() -> int:
    print("=" * 60)
    print("  ASR Workbench V1.1 · 发布包构建")
    print("=" * 60)
    items = preflight()
    validate_sources(items)
    write_zip(items)
    validate_zip(items)
    print("  全部校验通过，可以拿去另一台电脑测试了。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
