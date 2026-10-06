from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

from .config import ffmpeg_path
from .errors import MediaError


def _run(args: list[str], *, label: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            check=True,
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except FileNotFoundError as exc:
        raise MediaError(
            f"{label} is unavailable. Install FFmpeg or include it in vendor/ffmpeg."
        ) from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "unknown media error").strip().splitlines()
        raise MediaError(f"{label} failed: {detail[-1] if detail else 'unknown error'}") from exc


def probe_duration(path: str | Path) -> float:
    source = Path(path)
    if not source.is_file():
        raise MediaError("The selected media file no longer exists.")
    try:
        result = subprocess.run(
            [ffmpeg_path(), "-hide_banner", "-i", str(source)],
            check=False,
            capture_output=True,
            text=True,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except FileNotFoundError as exc:
        raise MediaError("Media inspection is unavailable. Install the project dependencies.") from exc
    try:
        match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr)
        if not match:
            raise ValueError("duration not reported")
        hours, minutes, seconds = match.groups()
        duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    except (TypeError, ValueError) as exc:
        raise MediaError("The file contains no supported audio stream.") from exc
    if duration <= 0:
        raise MediaError("The media duration is invalid.")
    return duration


def extract_audio(source: str | Path, output: str | Path) -> Path:
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            ffmpeg_path(), "-y", "-i", str(source), "-vn", "-ac", "2", "-ar", "44100",
            "-c:a", "pcm_s16le", str(destination),
        ],
        label="Audio extraction",
    )
    return destination


def trim_audio(source: str | Path, output: str | Path, start: float, duration: float) -> Path:
    if start < 0 or not 10 <= duration <= 30:
        raise MediaError("Choose an excerpt between 10 and 30 seconds.")
    available = probe_duration(source)
    if start + duration > available + 0.05:
        raise MediaError("The selected excerpt extends beyond the end of the media.")
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            ffmpeg_path(), "-y", "-ss", f"{start:.3f}", "-i", str(source),
            "-t", f"{duration:.3f}", "-ac", "2", "-ar", "44100",
            "-c:a", "pcm_s16le", str(destination),
        ],
        label="Excerpt creation",
    )
    return destination


def normalize_candidate(source: str | Path, output: str | Path, max_duration: float = 30) -> Path:
    duration = probe_duration(source)
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            ffmpeg_path(), "-y", "-i", str(source), "-t", f"{min(duration, max_duration):.3f}",
            "-vn", "-ac", "2", "-ar", "44100", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
            "-c:a", "pcm_s16le", str(destination),
        ],
        label="Candidate preparation",
    )
    return destination


def copy_as_basic_arrangement(source: str | Path, output: str | Path) -> Path:
    """Create a dependable non-AI preview with normalization and short fades."""
    duration = probe_duration(source)
    destination = Path(output)
    fade_out = max(0.0, duration - 0.25)
    _run(
        [
            ffmpeg_path(), "-y", "-i", str(source),
            "-af", f"afade=t=in:st=0:d=0.05,afade=t=out:st={fade_out:.3f}:d=0.25,loudnorm=I=-16:TP=-1.5:LRA=11",
            "-ac", "2", "-ar", "44100", "-c:a", "pcm_s16le", str(destination),
        ],
        label="Basic arrangement",
    )
    return destination


def available() -> bool:
    return bool(shutil.which(ffmpeg_path()) or Path(ffmpeg_path()).is_file())
