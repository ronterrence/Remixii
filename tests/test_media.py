from __future__ import annotations

import wave
from pathlib import Path

from remixii.media import copy_as_basic_arrangement, probe_duration, trim_audio


def write_silence(path: Path, seconds: int = 12) -> None:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 8000 * seconds)


def test_trim_and_basic_arrangement(tmp_path: Path) -> None:
    source = tmp_path / "source.wav"
    excerpt = tmp_path / "excerpt.wav"
    mix = tmp_path / "mix.wav"
    write_silence(source)

    assert 11.9 <= probe_duration(source) <= 12.1
    trim_audio(source, excerpt, start=1, duration=10)
    copy_as_basic_arrangement(excerpt, mix)

    assert 9.9 <= probe_duration(excerpt) <= 10.1
    assert 9.9 <= probe_duration(mix) <= 10.1

