from remixii.schema import new_manifest, validate_manifest


def valid_manifest(style: str) -> dict:
    media = {"filename": "media/test.wav", "duration_seconds": 10, "sha256": "0" * 64}
    return new_manifest(
        title="Test",
        creator="Creator",
        source_title="Source",
        source_artist="Artist",
        source_recording="source.wav",
        influence="",
        permission_status="authorized",
        permission_evidence="owned",
        excerpt_start=0,
        excerpt_end=10,
        genre=style,
        bpm=128,
        vocal_treatment="instrumental",
        prompt="",
        model={"provider": "test"},
        source_media=media,
        mix_media=media,
    )


def test_manifest_requires_supported_version() -> None:
    assert "unsupported schema_version" in validate_manifest({"schema_version": 2})[0]


def test_manifest_must_be_object() -> None:
    assert validate_manifest([]) == ["manifest must be a JSON object"]


def test_schema_accepts_a_custom_style() -> None:
    assert validate_manifest(valid_manifest("Melodic industrial electro")) == []


def test_schema_rejects_an_empty_style() -> None:
    assert "transformation.genre must be a non-empty style name" in validate_manifest(valid_manifest("  "))
