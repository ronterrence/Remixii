from __future__ import annotations

import os
import sys
from pathlib import Path


def bundled_root() -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))


def ffmpeg_path() -> str:
    bundled = bundled_root() / "vendor" / "ffmpeg" / "ffmpeg.exe"
    configured = os.getenv("REMIXII_FFMPEG")
    if bundled.exists():
        return str(bundled)
    if configured:
        return configured
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, RuntimeError):
        return "ffmpeg"


def ffprobe_path() -> str:
    bundled = bundled_root() / "vendor" / "ffmpeg" / "ffprobe.exe"
    return str(bundled) if bundled.exists() else os.getenv("REMIXII_FFPROBE", "ffprobe")


ACE_STEP_URL = "http://127.0.0.1:8001"
ACE_STEP_REPOSITORY = "https://github.com/ACE-Step/ACE-Step-1.5"


def ace_step_url() -> str:
    """Return the fixed local-only generation endpoint."""
    return ACE_STEP_URL


def ace_step_revision() -> str | None:
    """Return the Git revision recorded by the creator launcher, when available."""
    return os.getenv("REMIXII_ACE_STEP_REVISION") or None
