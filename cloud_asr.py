"""Optional OpenAI-compatible cloud speech-to-text engine.

The endpoint contract is POST {base_url}/audio/transcriptions with multipart
form data. Audio is streamed in chunks rather than loaded into memory. The
module uses only the Python standard library and never runs unless the user
selects the cloud engine and starts a transcription.
"""

from __future__ import annotations

import http.client
import json
import ssl
import uuid
import wave
from pathlib import Path
from urllib.parse import urlsplit

MAX_RESPONSE_BYTES = 20 * 1024 * 1024
CHUNK_SIZE = 1024 * 1024


def _part(boundary: str, name: str, value: str) -> bytes:
    return (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n"
        f"{value}\r\n"
    ).encode("utf-8")


def _file_header(boundary: str, filename: str) -> bytes:
    safe_name = filename.replace('"', "_").replace("\r", "_").replace("\n", "_")
    return (
        f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
        f"filename=\"{safe_name}\"\r\nContent-Type: audio/wav\r\n\r\n"
    ).encode("utf-8")


def _format_time(seconds: float) -> str:
    millis = max(0, round(float(seconds) * 1000))
    hours, millis = divmod(millis, 3_600_000)
    minutes, millis = divmod(millis, 60_000)
    secs, millis = divmod(millis, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def make_srt(segments: list[dict], duration: float) -> tuple[str, str]:
    """Return SRT and its precision: provider segments or whole-file fallback."""
    cues = []
    for seg in segments:
        try:
            start = float(seg.get("start", 0))
            end = float(seg.get("end", start))
            text = str(seg.get("text", "")).strip()
        except (TypeError, ValueError):
            continue
        if text:
            cues.append((start, max(start, end), text))
    precision = "segment"
    if not cues:
        cues = [(0.0, max(0.001, duration), "")]
        precision = "whole_file"
    lines = []
    for index, (start, end, text) in enumerate(cues, 1):
        lines.extend([str(index), f"{_format_time(start)} --> {_format_time(end)}", text, ""])
    return "\n".join(lines), precision


def transcribe(wav_path: str | Path, cfg: dict) -> dict:
    """Stream one WAV to the configured API and normalize its response."""
    base_url = str(cfg.get("cloud_asr_base_url", "")).strip()
    model = str(cfg.get("cloud_asr_model", "")).strip()
    api_key = str(cfg.get("cloud_asr_api_key", "")).strip()
    if not base_url or not model:
        raise ValueError("云端听写尚未配置 Base URL 和模型名")
    parsed = urlsplit(base_url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValueError("云端 Base URL 必须是有效的 http(s) 地址")
    if parsed.query or parsed.fragment:
        raise ValueError("云端 Base URL 不要带查询参数或 # 片段")

    wav = Path(wav_path)
    with wave.open(str(wav), "rb") as audio:
        duration = audio.getnframes() / float(audio.getframerate())

    boundary = "----ASRWorkbench" + uuid.uuid4().hex
    fields = [
        ("model", model),
        ("response_format", "verbose_json"),
        ("timestamp_granularities[]", "segment"),
    ]
    language = str(cfg.get("language", "")).strip()
    if language and language != "auto":
        fields.append(("language", language))
    prefix = b"".join(_part(boundary, key, value) for key, value in fields)
    header = _file_header(boundary, wav.name)
    suffix = f"\r\n--{boundary}--\r\n".encode("ascii")
    content_length = len(prefix) + len(header) + wav.stat().st_size + len(suffix)
    path = parsed.path.rstrip("/") + "/audio/transcriptions"

    if parsed.scheme == "https":
        conn = http.client.HTTPSConnection(
            parsed.hostname, parsed.port or 443, timeout=900,
            context=ssl.create_default_context(),
        )
    else:
        conn = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=900)
    try:
        conn.putrequest("POST", path)
        conn.putheader("Host", parsed.netloc)
        conn.putheader("Content-Type", f"multipart/form-data; boundary={boundary}")
        conn.putheader("Content-Length", str(content_length))
        conn.putheader("Accept", "application/json")
        if api_key:
            conn.putheader("Authorization", f"Bearer {api_key}")
        conn.endheaders()
        conn.send(prefix)
        conn.send(header)
        with wav.open("rb") as src:
            while chunk := src.read(CHUNK_SIZE):
                conn.send(chunk)
        conn.send(suffix)
        response = conn.getresponse()
        body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise RuntimeError("云端响应过大，已停止读取")
    except (OSError, http.client.HTTPException) as exc:
        raise RuntimeError(f"连接云端听写服务失败：{exc}") from exc
    finally:
        conn.close()

    try:
        payload = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"云端返回的不是有效 JSON（HTTP {response.status}）") from exc
    if response.status < 200 or response.status >= 300:
        detail = payload.get("error", payload) if isinstance(payload, dict) else payload
        raise RuntimeError(f"云端听写失败（HTTP {response.status}）：{str(detail)[:800]}")
    if not isinstance(payload, dict) or not str(payload.get("text", "")).strip():
        raise RuntimeError("云端响应缺少非空 text 字段")

    text = str(payload["text"]).strip() + "\n"
    segments = payload.get("segments") or []
    srt, precision = make_srt(segments, duration)
    if precision == "whole_file":
        # A text-only provider cannot supply sentence timestamps. Keep an
        # honest full-length cue rather than inventing timestamps.
        lines = srt.splitlines()
        lines[2] = text.strip()
        srt = "\n".join(lines)
    timeline = {
        "engine": "openai_compatible_cloud",
        "model": model,
        "duration": duration,
        "timestamp_precision": precision,
        "segments": segments,
    }
    return {
        "txt": text,
        "srt": srt,
        "timeline": timeline,
        "timestamp_precision": precision,
        "provider": parsed.netloc,
    }
