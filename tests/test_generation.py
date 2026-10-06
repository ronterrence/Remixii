from __future__ import annotations

import json
from pathlib import Path

import pytest

from remixii.errors import GenerationError
from remixii.generation import AceStepAdapter


class FakeResponse:
    def __init__(self, payload: dict | None = None, content: bytes = b""):
        self.payload = payload or {}
        self.content = content

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


def test_cover_request_records_local_model_provenance(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "source.wav"
    output = tmp_path / "result.wav"
    source.write_bytes(b"source")
    posts: list[tuple[str, dict]] = []

    def fake_post(url: str, **kwargs):
        posts.append((url, kwargs))
        if url.endswith("/release_task"):
            return FakeResponse({"code": 200, "data": {"task_id": "task-1"}})
        result = [{
            "file": "/v1/audio?path=result.wav",
            "dit_model": "acestep-v15-turbo",
            "seed_value": 42,
            "env": "local test",
        }]
        return FakeResponse({"data": [{"status": 1, "result": json.dumps(result)}]})

    monkeypatch.setattr("remixii.generation.requests.post", fake_post)
    monkeypatch.setattr(
        "remixii.generation.requests.get",
        lambda *args, **kwargs: FakeResponse(content=b"generated audio"),
    )

    details = AceStepAdapter(
        "http://127.0.0.1:8001", revision="official-git-revision"
    ).generate(
        source,
        genre="Drum & Bass",
        bpm=174,
        prompt="dark rolling bassline",
        output=output,
        duration=12.5,
    )

    submitted = posts[0][1]["data"]
    assert submitted["task_type"] == "cover"
    assert submitted["model"] == "acestep-v15-turbo"
    assert submitted["bpm"] == "174"
    assert submitted["audio_cover_strength"] == "0.45"
    assert submitted["audio_duration"] == "12.5"
    assert submitted["lyrics"] == "[Instrumental]"
    assert "drum & bass" in submitted["prompt"].lower()
    assert "dark rolling bassline" in submitted["prompt"]
    assert posts[0][1]["files"]["src_audio"][0] == "source.wav"
    assert output.read_bytes() == b"generated audio"
    assert details["model_revision"] == "official-git-revision"
    assert details["provider_url"] == "https://github.com/ACE-Step/ACE-Step-1.5"
    assert details["parameters"]["style"] == "Drum & Bass"
    assert details["parameters"]["audio_duration"] == 12.5


def test_rejects_remote_result_url(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        "remixii.generation.requests.get",
        lambda *args, **kwargs: pytest.fail("A remote URL must not be fetched"),
    )
    with pytest.raises(GenerationError, match="non-local audio URL"):
        AceStepAdapter("http://127.0.0.1:8001")._download(
            "https://example.com/generated.wav", tmp_path / "result.wav"
        )
