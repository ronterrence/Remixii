from __future__ import annotations

import json
import random
import wave
import zipfile
from pathlib import Path

import pytest

from remixii.errors import PackageError
from remixii.package import export_project, import_project, media_record
from remixii.schema import new_manifest


def write_silence(path: Path, seconds: int = 10) -> None:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 8000 * seconds)


def manifest_for(source: Path, mix: Path, genre: str = "Techno", seconds: int = 10) -> dict:
    return new_manifest(
        title="Test Remix",
        creator="Test Creator",
        source_title="Owned Source",
        source_artist="Test Artist",
        source_recording="test-source.wav",
        influence="",
        permission_status="authorized",
        permission_evidence="class recording consent",
        excerpt_start=0,
        excerpt_end=seconds,
        genre=genre,
        bpm=128,
        vocal_treatment="instrumental",
        prompt="instrumental techno",
        model={"provider": "test", "model_name": "fixture", "model_revision": "1"},
        source_media=media_record(source, "media/source-excerpt.wav", seconds),
        mix_media=media_record(mix, "media/selected-mix.wav", seconds),
    )


def test_project_round_trip(tmp_path: Path) -> None:
    source, mix = tmp_path / "source.wav", tmp_path / "mix.wav"
    write_silence(source)
    write_silence(mix)
    manifest = manifest_for(source, mix)
    project = export_project(
        tmp_path / "test.remix",
        manifest,
        {"media/source-excerpt.wav": source, "media/selected-mix.wav": mix},
    )

    opened, extracted = import_project(project, tmp_path / "opened")

    assert opened == manifest
    assert (extracted / "media" / "source-excerpt.wav").is_file()
    assert (extracted / "media" / "selected-mix.wav").is_file()


def test_custom_style_project_round_trip(tmp_path: Path) -> None:
    source, mix = tmp_path / "source.wav", tmp_path / "mix.wav"
    write_silence(source)
    write_silence(mix)
    manifest = manifest_for(source, mix, genre="Melodic industrial electro")
    project = export_project(
        tmp_path / "custom.remix",
        manifest,
        {"media/source-excerpt.wav": source, "media/selected-mix.wav": mix},
    )

    opened, _ = import_project(project, tmp_path / "custom-opened")
    assert opened["transformation"]["genre"] == "Melodic industrial electro"


@pytest.mark.parametrize("seconds", [180, 300])
def test_full_length_project_round_trip(tmp_path: Path, seconds: int) -> None:
    source, mix = tmp_path / "source.wav", tmp_path / "mix.wav"
    frames = random.Random(42).randbytes(8000 * 2 * seconds)
    for path in (source, mix):
        with wave.open(str(path), "wb") as audio:
            audio.setnchannels(1)
            audio.setsampwidth(2)
            audio.setframerate(8000)
            audio.writeframes(frames)
    manifest = manifest_for(source, mix, seconds=seconds)
    project = export_project(
        tmp_path / "full.remix", manifest,
        {"media/source-excerpt.wav": source, "media/selected-mix.wav": mix},
    )
    opened, extracted = import_project(project, tmp_path / "full-opened")
    assert opened["source"]["excerpt"]["end_seconds"] == seconds
    assert (extracted / "media" / "source-excerpt.wav").stat().st_size == source.stat().st_size


def test_rejects_hash_mismatch(tmp_path: Path) -> None:
    source, mix = tmp_path / "source.wav", tmp_path / "mix.wav"
    write_silence(source)
    write_silence(mix)
    manifest = manifest_for(source, mix)
    manifest["media"]["selected_mix"]["sha256"] = "0" * 64
    project = tmp_path / "bad.remix"
    with zipfile.ZipFile(project, "w") as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        archive.write(source, "media/source-excerpt.wav")
        archive.write(mix, "media/selected-mix.wav")

    with pytest.raises(PackageError, match="hash mismatch"):
        import_project(project, tmp_path / "opened")


def test_rejects_archive_traversal(tmp_path: Path) -> None:
    project = tmp_path / "unsafe.remix"
    with zipfile.ZipFile(project, "w") as archive:
        archive.writestr("manifest.json", "{}")
        archive.writestr("../outside.txt", "unsafe")

    with pytest.raises(PackageError, match="Unsafe archive path"):
        import_project(project, tmp_path / "opened")
    assert not (tmp_path / "outside.txt").exists()


def test_rejects_invalid_schema(tmp_path: Path) -> None:
    project = tmp_path / "invalid.remix"
    with zipfile.ZipFile(project, "w") as archive:
        archive.writestr("manifest.json", json.dumps({"schema_version": 99}))

    with pytest.raises(PackageError, match="Invalid project manifest"):
        import_project(project, tmp_path / "opened")


def test_failed_import_preserves_existing_destination(tmp_path: Path) -> None:
    project = tmp_path / "invalid.remix"
    project.write_bytes(b"invalid")
    destination = tmp_path / "existing"
    destination.mkdir()
    marker = destination / "keep.txt"
    marker.write_text("keep", encoding="utf-8")

    with pytest.raises(PackageError, match="already exists"):
        import_project(project, destination)
    assert marker.read_text(encoding="utf-8") == "keep"
