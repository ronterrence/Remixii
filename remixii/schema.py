from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

SCHEMA_VERSION = 1
PERMISSION_STATUSES = {
    "authorized", "public_domain", "unknown", "not_authorized",
    "uncleared_private_analysis",
}
VOCAL_TREATMENTS = {"instrumental", "keep_original_vocals"}


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def new_manifest(
    *,
    title: str,
    creator: str,
    source_title: str,
    source_artist: str,
    source_recording: str,
    influence: str,
    permission_status: str,
    permission_evidence: str,
    excerpt_start: float,
    excerpt_end: float,
    genre: str,
    bpm: int,
    vocal_treatment: str,
    prompt: str,
    model: dict[str, Any],
    source_media: dict[str, Any],
    mix_media: dict[str, Any],
    backing_media: dict[str, Any] | None = None,
    source_gain_db: float = 0.0,
    backing_gain_db: float = -9.0,
) -> dict[str, Any]:
    media = {"source_excerpt": source_media, "selected_mix": mix_media}
    tracks = [{"media_id": "selected_mix", "start_seconds": 0.0, "gain_db": 0.0}]
    if backing_media is not None:
        media["backing_track"] = backing_media
        tracks = [
            {"media_id": "source_excerpt", "start_seconds": 0.0, "gain_db": float(source_gain_db)},
            {"media_id": "backing_track", "start_seconds": 0.0, "gain_db": float(backing_gain_db)},
        ]
    return {
        "schema_version": SCHEMA_VERSION,
        "project": {
            "id": str(uuid4()),
            "title": title.strip(),
            "creator": creator.strip(),
            "created_at": utc_now(),
            "project_type": (
                "private_analysis" if permission_status == "uncleared_private_analysis"
                else "remix_project"
            ),
        },
        "source": {
            "work_title": source_title.strip(),
            "performers": source_artist.strip(),
            "actual_recording": source_recording.strip(),
            "declared_influence": influence.strip(),
            "permission_status": permission_status,
            "permission_evidence": permission_evidence.strip(),
            "excerpt": {"start_seconds": excerpt_start, "end_seconds": excerpt_end},
        },
        "transformation": {
            "genre": genre,
            "bpm": bpm,
            "vocal_treatment": vocal_treatment,
            "prompt": prompt.strip(),
        },
        "generation": model,
        "media": media,
        "arrangement": {
            "selected_candidate": "selected_mix",
            "mode": "source_preserving_mix" if backing_media is not None else "candidate_only",
            "tracks": tracks,
            "effects": [],
        },
    }


def validate_manifest(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["manifest must be a JSON object"]
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"unsupported schema_version; expected {SCHEMA_VERSION}")

    for section in ("project", "source", "transformation", "generation", "media", "arrangement"):
        if not isinstance(data.get(section), dict):
            errors.append(f"{section} must be an object")
    if errors:
        return errors

    for field in ("id", "title", "creator", "created_at"):
        if not isinstance(data["project"].get(field), str) or not data["project"][field].strip():
            errors.append(f"project.{field} is required")

    source = data["source"]
    for field in ("work_title", "performers", "actual_recording"):
        if not isinstance(source.get(field), str) or not source[field].strip():
            errors.append(f"source.{field} is required")
    if source.get("permission_status") not in PERMISSION_STATUSES:
        errors.append("source.permission_status is invalid")
    if source.get("permission_status") == "uncleared_private_analysis" and data["project"].get("project_type") != "private_analysis":
        errors.append("uncleared projects must be labeled private_analysis")
    if data["project"].get("project_type") == "private_analysis" and source.get("permission_status") != "uncleared_private_analysis":
        errors.append("private_analysis projects must keep the uncleared permission status")
    excerpt = source.get("excerpt")
    if not isinstance(excerpt, dict):
        errors.append("source.excerpt must be an object")
    else:
        start, end = excerpt.get("start_seconds"), excerpt.get("end_seconds")
        if not isinstance(start, (int, float)) or not isinstance(end, (int, float)):
            errors.append("source excerpt times must be numeric")
        elif start < 0 or end <= start or not (10 <= end - start <= 30 or any(abs(end - start - target) < 0.01 for target in (180, 300))):
            errors.append("source excerpt must be 10–30, 180, or 300 seconds")

    transform = data["transformation"]
    genre = transform.get("genre")
    if not isinstance(genre, str) or not genre.strip():
        errors.append("transformation.genre must be a non-empty style name")
    if transform.get("vocal_treatment") not in VOCAL_TREATMENTS:
        errors.append("transformation.vocal_treatment is invalid")
    bpm = transform.get("bpm")
    if not isinstance(bpm, int) or not 60 <= bpm <= 200:
        errors.append("transformation.bpm must be an integer from 60 to 200")

    media = data["media"]
    for media_id in ("source_excerpt", "selected_mix", "backing_track"):
        if media_id == "backing_track" and media_id not in media:
            continue
        item = media.get(media_id)
        if not isinstance(item, dict):
            errors.append(f"media.{media_id} must be an object")
            continue
        for field in ("filename", "sha256"):
            if not isinstance(item.get(field), str) or not item[field]:
                errors.append(f"media.{media_id}.{field} is required")
        if not isinstance(item.get("duration_seconds"), (int, float)):
            errors.append(f"media.{media_id}.duration_seconds must be numeric")
    arrangement = data["arrangement"]
    tracks = arrangement.get("tracks")
    if not isinstance(tracks, list) or not tracks:
        errors.append("arrangement.tracks must be a non-empty list")
    else:
        for track in tracks:
            if not isinstance(track, dict) or track.get("media_id") not in media:
                errors.append("arrangement track references missing media")
                continue
            if not isinstance(track.get("gain_db"), (int, float)):
                errors.append("arrangement track gain_db must be numeric")
    if arrangement.get("mode") == "source_preserving_mix":
        track_ids = {track.get("media_id") for track in tracks if isinstance(track, dict)} if isinstance(tracks, list) else set()
        if "backing_track" not in media or track_ids != {"source_excerpt", "backing_track"}:
            errors.append("source-preserving mix requires source and backing layers")
    return errors
