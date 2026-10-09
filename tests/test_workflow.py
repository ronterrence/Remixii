from __future__ import annotations

import json
import shutil
import wave
from pathlib import Path

import pytest

from remixii.app import (
    FULL_LENGTH_WARNING,
    FULL_MODE,
    FIVE_MINUTE_MODE,
    STYLE_PRESETS,
    _credits_markdown,
    _effective_style,
    _excerpt_controls,
    build_app,
    export_current,
    generate_candidate,
    load_source,
    make_basic,
    make_excerpt,
    mix_candidate,
    open_project_file,
)
from remixii.media import probe_duration


@pytest.mark.parametrize("style", STYLE_PRESETS[:-1])
def test_preset_style_selection(style: str) -> None:
    assert _effective_style(style, "ignored") == style


def test_custom_style_selection() -> None:
    assert _effective_style("Custom", "  Melodic industrial electro  ") == "Melodic industrial electro"


def test_custom_style_must_not_be_empty() -> None:
    with pytest.raises(ValueError, match="custom remix style"):
        _effective_style("Custom", "  ")


def test_create_ui_builds_with_cover_and_layer_controls() -> None:
    app = build_app()
    labels = {getattr(component, "label", None) for component in app.blocks.values()}
    assert {"Cover strength", "Seed", "Original source level (dB)", "Generated backing level (dB)"} <= labels
    assert "Excerpt mode" in labels
    assert "two-minute" in FULL_LENGTH_WARNING


@pytest.mark.parametrize("mode, seconds", [(FULL_MODE, 180), (FIVE_MINUTE_MODE, 300)])
def test_full_length_excerpt_preview_and_generation_file(tmp_path: Path, monkeypatch, mode: str, seconds: int) -> None:
    source = tmp_path / "full-source.wav"
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 8000 * (seconds + 5))

    state, _, start_control, duration_control, _, _, _ = load_source(str(source), None, mode)
    assert duration_control["value"] == seconds
    assert duration_control["interactive"] is False
    assert start_control["maximum"] == pytest.approx(5, abs=0.1)
    _, _, full_warning, _ = _excerpt_controls(state, mode)
    assert full_warning["visible"] is True
    _, short_control, warning, _ = _excerpt_controls(state, "Short clip (10–30 seconds)")
    assert short_control["maximum"] == 30
    assert warning["visible"] is False

    state, preview, _, _, message = make_excerpt(state, 2, seconds, mode)
    assert "ready" in message
    assert preview == state["excerpt"]
    assert probe_duration(preview) == pytest.approx(seconds, abs=0.05)
    assert Path(preview).stat().st_size > seconds * 150_000

    _, wrong_preview, _, wrong_status = generate_candidate(
        state, "Techno", 128, "Test", "Authorized", 0.45, 42,
    )
    assert wrong_preview is None
    assert "selected mode" in wrong_status

    submitted = {}

    def fake_generate(self, excerpt, **kwargs):
        submitted.update(kwargs)
        submitted["source_audio"] = excerpt
        shutil.copyfile(excerpt, kwargs["output"])
        return {"provider": "ACE-Step local HTTP API", "task_id": f"full-{seconds}", "seed": 42,
                "parameters": {"submitted_prompt": "Test", "style": "Techno", "bpm": 128}}

    monkeypatch.setattr("remixii.app.AceStepAdapter.generate", fake_generate)
    monkeypatch.setattr("remixii.app.normalize_candidate", lambda source, output, **kwargs: shutil.copyfile(source, output))
    state, candidate, details, result = generate_candidate(
        state, "Techno", 128, "Test", "Authorized", 0.45, 42, "", mode,
    )
    assert "ready" in result
    assert submitted["source_audio"] == preview
    assert submitted["duration"] == pytest.approx(seconds, abs=0.05)
    assert probe_duration(candidate) == pytest.approx(seconds, abs=0.05)
    assert details[-1]["task_id"] == f"full-{seconds}"


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

    state, full, _, _, _, _, loaded = load_source(str(source), None)
    assert "Loaded" in loaded
    assert Path(full).is_file()

    state, excerpt, _, _, trimmed = make_excerpt(state, 1, 10)
    assert "ready" in trimmed
    assert Path(excerpt).is_file()

    state, mix, details, created = make_basic(state)
    assert "fallback" in created
    assert details[-1]["provider"] == "local non-AI fallback"
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

    original, backing, remix, credits, manifest, opened = open_project_file(project)
    assert "validated" in opened
    assert backing is None
    assert Path(original).is_file() and Path(remix).is_file()
    assert "Owned Source" in credits
    assert "local non-AI fallback" in credits
    assert "Generation parameters" in credits
    assert '"schema_version": 1' in manifest


def test_private_source_preserving_project_round_trip(tmp_path: Path) -> None:
    source = tmp_path / "owned.wav"
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 8000 * 12)
    state, _, _, _, _, _, _ = load_source(str(source), None)
    state, excerpt, _, _, _ = make_excerpt(state, 0, 10)
    state["backing"] = excerpt
    state["generation"] = {
        "provider": "ACE-Step local HTTP API", "task_id": "task-42",
        "seed": 42, "parameters": {"style": "Techno", "bpm": 128,
        "submitted_prompt": "Instrumental techno remix"},
    }
    state["prompt_at_generation"] = "heavy kick"
    state, mix, mixed = mix_candidate(state, -2, -10)
    assert "Both layers" in mixed
    assert Path(mix).is_file()

    project, exported = export_current(
        state, "Private Study", "Student", "Source", "Artist", "owned.wav", "",
        "Uncleared—private analysis", "", "Techno", 128, "heavy kick",
    )
    assert "Private analysis" in exported
    original, backing, remix, credits, manifest_json, opened = open_project_file(project)
    manifest = json.loads(manifest_json)
    assert all(Path(path).is_file() for path in (original, backing, remix))
    assert manifest["source"]["permission_status"] == "uncleared_private_analysis"
    assert manifest["project"]["project_type"] == "private_analysis"
    assert manifest["arrangement"]["mode"] == "source_preserving_mix"
    assert [track["gain_db"] for track in manifest["arrangement"]["tracks"]] == [-2, -10]
    assert "Private analysis" in credits and "task-42" in credits
    assert "Private analysis" in opened


def test_new_generation_switches_preview_and_keeps_task_history(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "owned.wav"
    with wave.open(str(source), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\0\0" * 8000 * 12)
    state, _, _, _, _, _, _ = load_source(str(source), None)
    state, _, _, _, _ = make_excerpt(state, 0, 10)
    calls = []

    def fake_generate(self, excerpt, *, genre, bpm, prompt, output, duration, cover_strength, seed):
        calls.append(prompt)
        Path(output).write_bytes(Path(excerpt).read_bytes())
        return {
            "provider": "ACE-Step local HTTP API", "task_id": f"task-{len(calls)}",
            "seed": seed, "parameters": {"submitted_prompt": prompt, "style": genre,
            "bpm": bpm, "audio_cover_strength": cover_strength, "audio_duration": duration},
        }

    monkeypatch.setattr("remixii.app.AceStepAdapter.generate", fake_generate)
    state, first, details, _ = generate_candidate(state, "Techno", 128, "Techno drums", "Authorized", 0.45, 42)
    state, second, details, _ = generate_candidate(state, "Custom", 128, "Acoustic piano", "Authorized", 0.45, 42, "Acoustic jazz")
    assert Path(first).is_file() and Path(second).is_file()
    assert first != second == state["candidate"]
    assert [item["task_id"] for item in details] == ["task-1", "task-2"]
    assert details[-1]["caption"] == "Acoustic piano"

    state, preview, _, message = generate_candidate(state, "Techno", 128, "Retry", "Unknown / unconfirmed", 0.45, 42)
    assert preview is None and "Choose Authorized" in message
    assert "candidate" not in state
