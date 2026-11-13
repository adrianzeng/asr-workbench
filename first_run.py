"""First-run bootstrap: one folder, relative paths, no manual setup.

Idempotent: safe to call from both start.py and server.main(). It never
touches inbox_dir / output_dir / work_dir chosen by the user, and never writes
an absolute path into config.json.
"""
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"
EXAMPLE_PATH = ROOT / "config.example.json"
RUNTIME_DIR = ROOT / "runtime" / "oneasr"

# These three must always live inside the project. Absolute paths from a
# developer's old debug setup (e.g. E:\ASR_Test) are rewritten on bootstrap.
INTERNAL_KEYS = {
    "ffmpeg": "./runtime/oneasr/bin/ffmpeg.exe",
    "oneasr_cli": "./runtime/oneasr/oneasr-cli.exe",
    "oneasr_data_root": "./runtime/oneasr",
}


def is_first_run(root: Path = ROOT) -> bool:
    return not (root / "config.json").exists()


def normalize_config(cfg: dict, root: Path = ROOT) -> tuple[dict, bool]:
    """Fold internal absolute paths back into project-relative ones."""
    changed = False
    for key, default in INTERNAL_KEYS.items():
        value = str(cfg.get(key) or "").strip()
        if not value:
            cfg[key] = default
            changed = True
            continue
        path = Path(value)
        if not path.is_absolute():
            continue
        try:
            relative = path.relative_to(root)
        except ValueError:
            cfg[key] = default
        else:
            cfg[key] = "./" + relative.as_posix()
        changed = True
    return cfg, changed


def _read_json(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def bootstrap(root: Path = ROOT) -> dict:
    """Ensure config.json and runtime/oneasr/{models,output,runs} exist.

    On a source checkout (no portable OneAsr inside runtime/) we deliberately
    leave an existing config.json alone — a developer may legitimately point it
    at a separate model directory. The one-folder rewrite only kicks in for a
    real release zip, where the portable binaries are present.
    """
    example = _read_json(root / "config.example.json")
    target = root / "config.json"
    runtime = root / "runtime" / "oneasr"
    portable_ready = (runtime / "oneasr-cli.exe").is_file()

    if target.exists() and not portable_ready:
        merged = dict(example)
        merged.update(_read_json(target))
    elif target.exists():
        existing = _read_json(target)
        # Keep every value the user chose; add any key introduced by a new version.
        merged = dict(example)
        merged.update(existing)
        merged, changed = normalize_config(merged, root)
        if changed or set(example) - set(existing):
            target.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
                              encoding="utf-8")
    else:
        merged, _ = normalize_config(dict(example), root)
        target.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")

    for sub in ("models", "output", "runs"):
        (runtime / sub).mkdir(parents=True, exist_ok=True)
    return merged
