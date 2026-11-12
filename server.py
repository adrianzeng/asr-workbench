#!/usr/bin/env python3
"""ASR Workbench - a tiny, dependency-free local backend.

Serves the web UI and runs ffmpeg + OneAsr CLI on files placed in the inbox.
All external paths come from config.json; nothing here is tied to a
particular machine, note-taking app, or knowledge base.

The draft-rewrite engine is a reserved extension point (see rewrite.py).
Local ASR is the default. The optional cloud ASR engine sends audio only when
explicitly configured and selected by the user (see cloud_asr.py).
"""

from __future__ import annotations

import base64
import json
import mimetypes
import shutil
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import cloud_asr
import jobs
import rewrite

ROOT = Path(__file__).resolve().parent
WEB_DIR = ROOT / "web"
CONFIG_PATH = ROOT / "config.json"
EXAMPLE_PATH = ROOT / "config.example.json"

# Sent to the browser instead of the stored value; posting it back keeps the
# existing key unchanged.
KEY_MASK = "********"

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
    "asr_engine": "local",
    "asr_model": "0.6b",
    "aligner": "ctc",
    "backend": "auto",
    # Which files stay in the per-media output folder:
    #   txt      -> <stem>.txt
    #   txt_srt  -> <stem>.txt + <stem>.srt                      (default)
    #   all      -> <stem>.txt + <stem>.srt + <stem>.timeline.json
    # Whatever is not kept is moved to work/kept/<stem>/ rather than deleted, so
    # subtitles can be re-rendered later without transcribing again.
    "output_mode": "txt_srt",
    # Optional OpenAI-compatible cloud transcription (POST {base_url}/audio/transcriptions).
    # Off by default; audio is only uploaded when this engine is selected.
    "cloud_asr_base_url": "",
    "cloud_asr_api_key": "",
    "cloud_asr_model": "",
    # Reserved: an OpenAI-compatible rewrite engine, off and unimplemented.
    "rewrite_engine": "off",
    "rewrite_base_url": "",
    "rewrite_api_key": "",
    "rewrite_model": "",
    "port": 8765,
}

# Whitelisted titles for the native folder picker. No user-supplied text is
# ever interpolated into a PowerShell / AppleScript command.
FOLDER_PICK_TITLES = {
    "inbox": "选择素材目录",
    "output": "选择输出目录",
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


def public_config(cfg: dict) -> dict:
    """Never return a stored API key to the browser in clear text."""
    out = dict(cfg)
    if out.get("rewrite_api_key"):
        out["rewrite_api_key"] = KEY_MASK
    if out.get("cloud_asr_api_key"):
        out["cloud_asr_api_key"] = KEY_MASK
    return out


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


# — Windows folder picker ————————————————————————————————————————————————
# The modern IFileDialog (the one Explorer uses) is the only stock dialog whose
# left rail carries 桌面 / 下载 / 文档. The legacy FolderBrowserDialog rooted at
# "MyComputer" silently drops 桌面 from the tree, which is where most people
# keep their material. So we prefer IFileDialog and fall back to the legacy
# dialog rooted at the desktop when the COM interop cannot be compiled.
#
# PowerShell cannot cast a ComImport class to its interface reliably, so every
# cast happens inside the C# helper and PowerShell only calls a static method.
WIN_PICKER_CS = r"""
using System;
using System.Runtime.InteropServices;

[ComImport, Guid("DC1C5A9C-E88A-4DDE-A5A1-60F82A20AEF7")]
public class FileOpenDialogRCW { }

[ComImport, Guid("42F85136-DB7E-439C-85F1-E4075D135FC8"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IFileDialog {
    [PreserveSig] int Show(IntPtr parent);
    void SetFileTypes(uint cFileTypes, IntPtr rgFilterSpec);
    void SetFileTypeIndex(uint iFileType);
    void GetFileTypeIndex(out uint piFileType);
    void Advise(IntPtr pfde, out uint pdwCookie);
    void Unadvise(uint dwCookie);
    void SetOptions(uint fos);
    void GetOptions(out uint pfos);
    void SetDefaultFolder(IShellItem psi);
    void SetFolder(IShellItem psi);
    void GetFolder(out IShellItem ppsi);
    void GetCurrentSelection(out IShellItem ppsi);
    void SetFileName([MarshalAs(UnmanagedType.LPWStr)] string pszName);
    void GetFileName([MarshalAs(UnmanagedType.LPWStr)] out string pszName);
    void SetTitle([MarshalAs(UnmanagedType.LPWStr)] string pszTitle);
    void SetOkButtonLabel([MarshalAs(UnmanagedType.LPWStr)] string pszText);
    void SetFileNameLabel([MarshalAs(UnmanagedType.LPWStr)] string pszLabel);
    void GetResult(out IShellItem ppsi);
    void AddPlace(IShellItem psi, int fdap);
    void SetDefaultExtension([MarshalAs(UnmanagedType.LPWStr)] string pszDefaultExtension);
    void Close(int hr);
    void SetClientGuid(ref Guid guid);
    void ClearClientData();
    void SetFilter(IntPtr pFilter);
}

[ComImport, Guid("43826D1E-E718-42EE-BC55-A1E261C37BFE"), InterfaceType(ComInterfaceType.InterfaceIsIUnknown)]
public interface IShellItem {
    void BindToHandler(IntPtr pbc, ref Guid bhid, ref Guid riid, out IntPtr ppv);
    void GetParent(out IShellItem ppsi);
    void GetDisplayName(uint sigdnName, [MarshalAs(UnmanagedType.LPWStr)] out string ppszName);
    void GetAttributes(uint sfgaoMask, out uint psfgaoAttribs);
    void Compare(IShellItem psi, uint hint, out int piOrder);
}

public static class FolderPicker {
    private const uint FOS_PICKFOLDERS     = 0x00000020;
    private const uint FOS_FORCEFILESYSTEM = 0x00000040;
    private const uint FOS_PATHMUSTEXIST   = 0x00000800;
    private const uint SIGDN_FILESYSPATH   = 0x80058000;

    // Returns the chosen folder, or "" when the user cancels.
    public static string Pick(string title) {
        IFileDialog dlg = (IFileDialog)new FileOpenDialogRCW();
        try {
            uint opts;
            dlg.GetOptions(out opts);
            dlg.SetOptions(opts | FOS_PICKFOLDERS | FOS_FORCEFILESYSTEM | FOS_PATHMUSTEXIST);
            dlg.SetTitle(title);
            if (dlg.Show(IntPtr.Zero) != 0) return "";
            IShellItem item;
            dlg.GetResult(out item);
            try {
                string path;
                item.GetDisplayName(SIGDN_FILESYSPATH, out path);
                return path ?? "";
            } finally {
                Marshal.ReleaseComObject(item);
            }
        } finally {
            Marshal.ReleaseComObject(dlg);
        }
    }
}
"""

WIN_PICKER_PS = """
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
try {
    Add-Type -TypeDefinition @'
__CS__
'@ -Language CSharp
} catch {
    [Console]::Error.WriteLine('PICKER_ERROR compile: ' + $_.Exception.Message)
    exit 3
}
try {
    $p = [FolderPicker]::Pick('__TITLE__')
    if ($p) { Write-Output $p }
} catch {
    [Console]::Error.WriteLine('PICKER_ERROR runtime: ' + $_.Exception.Message)
    exit 4
}
"""

# Legacy dialog, used only if the modern one cannot be created. Rooting it at
# the desktop at least keeps 桌面 (and 此电脑 under it) reachable.
WIN_FALLBACK_PS = """
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$ProgressPreference = 'SilentlyContinue'
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Application]::EnableVisualStyles()
$d = New-Object System.Windows.Forms.FolderBrowserDialog
$d.Description = '__TITLE__'
$d.ShowNewFolderButton = $true
$d.RootFolder = [System.Environment+SpecialFolder]::Desktop
if ($d.ShowDialog() -eq [System.Windows.Forms.DialogResult]::OK) { Write-Output $d.SelectedPath }
$d.Dispose()
"""


def _run_powershell(template: str, title: str) -> tuple[str, int, str]:
    """Run a PowerShell snippet as UTF-16LE base64 and return (out, rc, err).

    -EncodedCommand avoids every quoting and console-code-page problem with
    Chinese titles, folder names and non-ASCII user paths. Synthetic return
    codes: 124 = the dialog was left open too long, 127 = no PowerShell at all.
    """
    script = template.replace("__CS__", WIN_PICKER_CS)
    script = script.replace("__TITLE__", title.replace("'", "''"))
    encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    try:
        run = subprocess.run(
            ["powershell", "-NoProfile", "-STA", "-EncodedCommand", encoded],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        return "", 124, "选择超时"
    except FileNotFoundError as exc:
        return "", 127, f"找不到系统目录选择器：{exc}"
    except Exception as exc:
        return "", 1, f"打开目录选择器失败：{exc}"
    return run.stdout or "", run.returncode, run.stderr or ""


def pick_folder(kind: str = "") -> dict:
    """Open the OS-native folder picker and return the chosen absolute path.

    Uses only OS-bundled commands: Windows PowerShell, macOS osascript, or
    zenity on Linux. This keeps the project free of third-party Python
    packages and GUI toolkits.
    """
    title = FOLDER_PICK_TITLES.get(str(kind), "选择文件夹")
    if sys.platform == "win32":
        raw, rc, err = _run_powershell(WIN_PICKER_PS, title)
        if rc == 124:
            return {"cancelled": True, "note": "选择超时，已取消"}
        if rc == 127:
            return {"cancelled": False, "error": err}
        if rc != 0 or "PICKER_ERROR" in raw or "PICKER_ERROR" in err:
            # Modern dialog unavailable (locked-down PowerShell, exotic build).
            # The legacy one is a Windows Forms control and always loads.
            raw, rc, err = _run_powershell(WIN_FALLBACK_PS, title)
            if rc != 0:
                detail = (err or raw).strip().splitlines()
                return {"cancelled": False,
                        "error": "打不开系统目录选择窗口：" + (detail[-1] if detail else f"退出码 {rc}")}
        lines = [x.strip() for x in raw.splitlines() if x.strip()]
        chosen = lines[-1] if lines else ""
        if not chosen:
            return {"cancelled": True}
        return {"path": str(Path(chosen.rstrip("/\\") or chosen)), "cancelled": False}
    if sys.platform == "darwin":
        safe_title = title.replace("\\", "\\\\").replace('"', '\\"')
        cmd = ["osascript", "-e", f'POSIX path of (choose folder with prompt "{safe_title}")']
    else:
        zenity = shutil.which("zenity")
        if not zenity:
            return {"cancelled": False,
                    "error": "当前系统没有可用的图形目录选择器（Linux 需安装 zenity），请手动填写路径。"}
        cmd = [zenity, "--file-selection", "--directory", f"--title={title}"]

    try:
        run = subprocess.run(
            cmd, capture_output=True, text=True,
            encoding="utf-8", errors="replace", timeout=180,
        )
    except subprocess.TimeoutExpired:
        return {"cancelled": True, "note": "选择超时，已取消"}
    except FileNotFoundError as exc:
        return {"cancelled": False, "error": f"找不到系统目录选择器：{exc}"}
    except Exception as exc:
        return {"cancelled": False, "error": f"打开目录选择器失败：{exc}"}

    lines = [
        line.strip() for line in (run.stdout or "").splitlines()
        if line.strip() and not line.lstrip().startswith(("#<", "<Objs", "<Obj "))
    ]
    chosen = lines[-1] if lines else ""
    if not chosen:
        # Cancelling yields no stdout on every platform (osascript also exits
        # non-zero with "User canceled" on stderr).
        return {"cancelled": True}
    trimmed = chosen.rstrip("/\\")
    return {"path": str(Path(trimmed or chosen)), "cancelled": False}


def safe_folder_name(stem: str) -> str:
    """Turn a media filename stem into one safe directory name."""
    cleaned = "".join(c for c in stem if c not in '<>:"|?*' and ord(c) >= 32)
    cleaned = cleaned.strip().rstrip(". ")
    return cleaned or "untitled"


OUTPUT_MODES = ("txt", "txt_srt", "all")


def normalize_output_mode(value) -> str:
    mode = str(value or "").strip().lower()
    return mode if mode in OUTPUT_MODES else "txt_srt"


def park_unwanted(job_dir: Path, work: Path, stem: str, wanted: dict) -> str:
    """Move files the user chose not to publish into work/kept/<stem>/.

    Nothing is deleted: the timeline still lets `oneasr-cli render` rebuild
    subtitles later without running the whole transcription again. Returns the
    folder used, or "" when nothing had to move.
    """
    parked_dir = work / "kept" / safe_folder_name(stem)
    moved = False
    for path, keep in wanted.items():
        if keep or not path.exists():
            continue
        parked_dir.mkdir(parents=True, exist_ok=True)
        shutil.move(str(path), str(parked_dir / path.name))
        moved = True
    return str(parked_dir) if moved else ""


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
    if not ffmpeg:
        raise RuntimeError("找不到 ffmpeg，请检查设置页或 PATH")
    engine = str(cfg.get("asr_engine", "local")).strip().lower()

    work = resolve_path(cfg.get("work_dir", "./work"))
    output = resolve_path(cfg.get("output_dir", "./output"))
    work.mkdir(parents=True, exist_ok=True)
    # Every media file gets its own folder: output/<stem>/<stem>.srt|txt|timeline.json
    job_dir = output / safe_folder_name(src.stem)
    job_dir.mkdir(parents=True, exist_ok=True)
    wav = work / f"{src.stem}.wav"

    # Convert to 16 kHz mono PCM WAV ourselves. The local CLI copies a
    # compliant WAV directly instead of spawning its own ffmpeg, which avoids
    # "os error 5" on some Windows setups; the cloud engine uploads this WAV
    # as a plain, predictable payload. Transcription output is unchanged.
    run = subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
         "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", str(wav)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if run.returncode != 0:
        raise RuntimeError(f"ffmpeg 转码失败：{run.stderr.strip()[:800]}")

    srt_path = job_dir / f"{src.stem}.srt"
    txt_path = job_dir / f"{src.stem}.txt"
    timeline_path = job_dir / f"{src.stem}.timeline.json"
    mode = normalize_output_mode(cfg.get("output_mode"))
    keep_srt = mode in ("txt_srt", "all")
    keep_timeline = mode == "all"
    started = time.time()

    if engine == "cloud":
        result = cloud_asr.transcribe(wav, cfg)
        txt_path.write_text(result["txt"], encoding="utf-8")
        srt_path.write_text(result["srt"], encoding="utf-8")
        timeline_path.write_text(
            json.dumps(result["timeline"], ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        parked = park_unwanted(
            job_dir, work, src.stem, {srt_path: keep_srt, timeline_path: keep_timeline}
        )
        return {
            "elapsed": round(time.time() - started, 1),
            "job_dir": str(job_dir),
            "srt": result["srt"],
            "txt": result["txt"],
            "srt_path": str(srt_path) if keep_srt else "",
            "txt_path": str(txt_path),
            "engine": "cloud",
            "cloud_provider": result.get("provider", ""),
            "timestamp_precision": result.get("timestamp_precision", ""),
            "output_mode": mode,
            "parked": parked,
            "rewrite": rewrite.rewrite_status(cfg),
            "log": f"云端听写：{result.get('provider', '')} / {cfg.get('cloud_asr_model', '')}",
        }

    cli = find_binary(cfg.get("oneasr_cli", ""))
    if not cli:
        raise RuntimeError("找不到 OneAsr CLI，请检查设置页")

    cmd = [
        cli, "transcribe", "--input", str(wav),
        "--language", cfg.get("language", "zh"),
        "--backend", cfg.get("backend", "auto"),
        "--asr", cfg.get("asr_model", "0.6b"),
        "--aligner", cfg.get("aligner", "ctc"),
        "--txt", "--output-dir", str(job_dir),
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

    # Read the previews before parking: the draft pane always shows the full
    # timed text, even when the user asked for a bare .txt on disk.
    srt_text = srt_path.read_text(encoding="utf-8", errors="replace") if srt_path.exists() else ""
    txt_text = txt_path.read_text(encoding="utf-8", errors="replace") if txt_path.exists() else ""
    srt_ready = keep_srt and srt_path.exists()
    txt_ready = txt_path.exists()
    parked = park_unwanted(
        job_dir, work, src.stem, {srt_path: keep_srt, timeline_path: keep_timeline}
    )

    return {
        "elapsed": elapsed,
        "job_dir": str(job_dir),
        "srt": srt_text,
        "txt": txt_text,
        "srt_path": str(srt_path) if srt_ready else "",
        "txt_path": str(txt_path) if txt_ready else "",
        "engine": "local",
        "output_mode": mode,
        "parked": parked,
        "rewrite": rewrite.rewrite_status(cfg),
        "log": (run.stdout or "").strip()[-800:],
    }


# One queue per server process. Config is snapshotted when a batch is submitted,
# so changing settings mid-run cannot desynchronise files in the same batch.
JOB_MANAGER = jobs.JobManager(transcribe, load_config)


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
                return self._json(public_config(load_config()))
            if path == "/api/status":
                return self._json(status_report(load_config()))
            if path == "/api/files":
                return self._json({"files": list_inbox(load_config())})
            if path == "/api/rewrite":
                return self._json(rewrite.rewrite_status(load_config()))
            if path == "/api/jobs":
                return self._json(JOB_MANAGER.snapshot())
            if path == "/api/jobs/result":
                name = parse_qs(urlparse(self.path).query).get("name", [""])[0]
                result = JOB_MANAGER.result(name)
                if result is None:
                    return self._json({"error": "这份稿子还没做好，或者不在这批里"}, 404)
                return self._json(result)
            return self._static(path)
        except Exception as exc:
            return self._json({"error": str(exc)}, 500)

    def do_POST(self):
        path = urlparse(self.path).path
        try:
            body = self._body()
            if path == "/api/config":
                cfg = load_config()
                updates = {k: v for k, v in body.items() if k in DEFAULTS}
                # Masked keys coming back from the UI mean "keep the stored one".
                for key_field in ("rewrite_api_key", "cloud_asr_api_key"):
                    if updates.get(key_field) == KEY_MASK:
                        updates.pop(key_field)
                cfg.update(updates)
                save_config(cfg)
                return self._json({"ok": True, "config": public_config(cfg)})
            if path == "/api/pick-folder":
                return self._json(pick_folder(str(body.get("for", ""))))
            if path == "/api/transcribe":
                return self._json(transcribe(load_config(), str(body.get("name", ""))))
            if path == "/api/jobs":
                raw = body.get("names")
                if not isinstance(raw, list) or not raw:
                    return self._json({"error": "请先选至少一个素材"}, 400)
                # Whitelist against the real inbox listing: no path traversal.
                allowed = {item["name"] for item in list_inbox(load_config())}
                names = []
                for value in raw:
                    name = str(value)
                    if name in allowed and name not in names:
                        names.append(name)
                if not names:
                    return self._json({"error": "选中的文件不在素材目录里，点「刷新列表」再试"}, 400)
                snapshot, err = JOB_MANAGER.submit(names)
                if err:
                    return self._json({"error": err}, 409)
                return self._json(snapshot)
            if path == "/api/jobs/cancel":
                return self._json({"ok": JOB_MANAGER.cancel(),
                                   "note": "正在跑的这一个会做完，剩下的跳过"})
            if path == "/api/rewrite":
                return self._json(rewrite.rewrite_draft(str(body.get("text", "")), load_config()))
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
    state = rewrite.rewrite_status(cfg)
    print(f"ASR Workbench  ->  http://127.0.0.1:{port}")
    for key, ok in report["checks"].items():
        print(f"  {key:12s} {'OK' if ok else 'MISSING'}")
    print(f"  rewrite      {state['status']} (reserved, no outbound requests)")
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
