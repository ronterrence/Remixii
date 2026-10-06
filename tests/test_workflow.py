from __future__ import annotations

import wave
from pathlib import Path

import pytest

from remixii.app import (
    STYLE_PRESETS,
    _credits_markdown,
    _effective_style,
    export_current,
    load_source,
    make_basic,
    make_excerpt,
    open_project_file,
)


@pytest.mark.parametrize("style", STYLE_PRESETS[:-1])
def test_preset_style_selection(style: str) -> None:
    assert _effective_style(style, "ignored") == style


def test_custom_style_selection() -> None:
    assert _effective_style("Custom", "  Melodic industrial electro  ") == "Melodic industrial electro"


def test_custom_style_must_not_be_empty() -> None:
    with pytest.raises(ValueError, match="custom remix style"):
        _effective_style("Custom", "  ")


def test_professor_credits_show_provenance() -> None:
    manifest = {
        "project": {"title": "Remix", "creator": "Student", "created_at": "2026-10-06"},
        "source": {
            "work_title": "Source Work", "performers": "Original Performer",
            "actual_recording": "Recording A", "declared_influence": "Artist B",
            "permission_status": "authorized", "permission_evidence": "Written permission",
        },
        "transformation": {
            "genre": "Industrial Techno", "bpm": 132,
            "vocal_treatment": "instrumental", "prompt": "dark drums",
        },
        "generation": {
            "provider": "ACE-Step local HTTP API",
            "provider_url": "https://github.com/ACE-Step/ACE-Step-1.5",
            "model_name": "acestep-v15-turbo", "model_revision": "abc123",
            "seed": 42, "environment": "local AMD GPU",
            "parameters": {"audio_cover_strength": 0.45},
        },
    }
    credits = _credits_markdown(manifest)
    for expected in (
        "Student", "2026-10-06", "Source Work", "Original Performer",
        "Recording A", "Artist B", "Written permission", "Industrial Techno",
        "132 BPM", "instrumental", "dark drums", "ACE-Step local HTTP API",
        "acestep-v15-turbo", "abc123", "42", "local AMD GPU",
        "audio_cover_strength", "not proof of ownership or a licence",
    ):
        assert expected in credits


def test_create_export_and_open_offline(tmp_path: Path) -> None:
    source = tmp_path / "owned.wav"
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 8000 * 12)

    state, full, _, _, loaded = load_source(str(source), None)
    assert "Loaded" in loaded
    assert Path(full).is_file()

    state, excerpt, trimmed = make_excerpt(state, 1, 10)
    assert "ready" in trimmed
    assert Path(excerpt).is_file()

    state, mix, created = make_basic(state)
    assert "fallback" in created
    assert Path(mix).is_file()

    project, exported = export_current(
        state,
        "Class Demo",
        "Student",
        "Owned Source",
        "Student",
        "owned.wav",
        "",
        "Authorized",
        "recorded by student",
        "Techno",
        128,
        "",
    )
    assert "exported" in exported
    assert Path(project).is_file()

    original, remix, credits, manifest, opened = open_project_file(project)
    assert "validated" in opened
    assert Path(original).is_file() and Path(remix).is_file()
    assert "Owned Source" in credits
    assert "local non-AI fallback" in credits
    assert "Generation parameters" in credits
    assert '"schema_version": 1' in manifest
