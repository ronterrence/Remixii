from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

import gradio as gr

from .config import ACE_STEP_REPOSITORY, ace_step_revision, ace_step_url
from .errors import GenerationError, RemixiiError
from .generation import AceStepAdapter
from .media import (
    copy_as_basic_arrangement,
    extract_audio,
    normalize_candidate,
    probe_duration,
    trim_audio,
    mix_source_and_backing,
)
from .package import export_project, import_project, media_record
from .schema import new_manifest

STYLE_PRESETS = ["Techno", "House", "Trance", "Drum & Bass", "Afro House", "Custom"]
PRIVATE_ANALYSIS = "Uncleared—private analysis"
SHORT_MODE = "Short clip (10–30 seconds)"
FULL_MODE = "Full length (3 minutes)"
FIVE_MINUTE_MODE = "Full length (5 minutes)"
SEVEN_MINUTE_MODE = "Full length (7 minutes)"
LONG_MODE_DURATIONS = {FULL_MODE: 180, FIVE_MINUTE_MODE: 300, SEVEN_MINUTE_MODE: 420}
FULL_LENGTH_WARNING = (
    "⚠️ Your RX 7600 previously ran out of memory on a two-minute ACE-Step request. "
    "A successful five-minute cover does not guarantee that a seven-minute local generation will succeed."
)


def _effective_style(style: str, custom_style: str = "") -> str:
    if not isinstance(style, str) or not style.strip():
        raise ValueError("Select a remix style.")
    if style != "Custom":
        return style.strip()
    value = custom_style.strip()
    if not value:
        raise ValueError("Enter a custom remix style.")
    return value


def _custom_style_visibility(style: str):
    return gr.update(visible=style == "Custom")


def _new_session() -> dict[str, Any]:
    return {"root": tempfile.mkdtemp(prefix="remixii-create-"), "candidates": []}


def _candidate_details(state: dict[str, Any]) -> list[dict[str, Any]]:
    return state.get("candidates", [])


def _session(value: dict[str, Any] | None) -> dict[str, Any]:
    if value and Path(value.get("root", "")).is_dir():
        return value
    return _new_session()


def _file_path(value: Any) -> str:
    if isinstance(value, str):
        return value
    if hasattr(value, "name"):
        return value.name
    if isinstance(value, dict) and value.get("path"):
        return value["path"]
    raise ValueError("Select a file first.")


def _status(message: str, kind: str = "info") -> str:
    icons = {"info": "ℹ️", "ok": "✅", "error": "❌", "warning": "⚠️"}
    return f"{icons.get(kind, 'ℹ️')} {message}"


def _excerpt_controls(state: dict[str, Any] | None, mode: str):
    state = state or {}
    long_duration = LONG_MODE_DURATIONS.get(mode)
    full = long_duration is not None
    source_duration = float(state.get("duration", 10))
    required = long_duration or 10
    start_maximum = max(0.0, source_duration - required)
    duration_update = (
        gr.update(minimum=10, maximum=required, value=required, interactive=False)
        if full else gr.update(minimum=10, maximum=min(30.0, max(10.0, source_duration)), value=10, interactive=True)
    )
    notice = gr.update(visible=full)
    message = (
        f"Load a source at least {required // 60} minutes long for this mode."
        if full and source_duration < required else
        f"{required // 60}-minute excerpt is ready to select. Generation may exceed RX 7600 memory."
        if full else "Short-clip mode selected."
    )
    return gr.update(maximum=start_maximum, value=0), duration_update, notice, _status(message, "warning" if full else "info")


def load_source(upload: Any, state: dict[str, Any] | None, mode: str = SHORT_MODE):
    state = _session(state)
    try:
        source = Path(_file_path(upload))
        audio = Path(state["root"]) / "source-full.wav"
        extract_audio(source, audio)
        duration = probe_duration(audio)
        if duration < 10:
            raise ValueError("Source media must be at least 10 seconds long.")
        state.update({"source_full": str(audio), "source_name": source.name, "duration": duration})
        state["candidates"] = []
        for key in ("excerpt", "candidate", "backing", "generation", "mix_settings", "prompt_at_generation"):
            state.pop(key, None)
        start_update, duration_update, _, _ = _excerpt_controls(state, mode)
        message = f"Loaded {source.name} ({duration:.1f} seconds)."
        required = LONG_MODE_DURATIONS.get(mode)
        if required and duration < required:
            message += f" This mode needs at least {required} seconds."
        return (
            state,
            str(audio),
            start_update,
            duration_update,
            None,
            [],
            _status(message, "warning" if required and duration < required else "ok"),
        )
    except (RemixiiError, ValueError) as exc:
        return state, None, gr.update(), gr.update(), state.get("candidate"), _candidate_details(state), _status(str(exc), "error")


def make_excerpt(state: dict[str, Any] | None, start: float, duration: float, mode: str = SHORT_MODE):
    state = _session(state)
    try:
        if "source_full" not in state:
            raise ValueError("Load source media first.")
        required = LONG_MODE_DURATIONS.get(mode)
        if required and abs(float(duration) - required) >= 0.01:
            raise ValueError(f"This full-length mode requires a {required}-second excerpt.")
        if mode == SHORT_MODE and not 10 <= float(duration) <= 30:
            raise ValueError("Short-clip mode requires 10–30 seconds.")
        excerpt = Path(state["root"]) / "source-excerpt.wav"
        trim_audio(state["source_full"], excerpt, float(start), float(duration))
        state.update({
            "excerpt": str(excerpt),
            "excerpt_mode": mode,
            "excerpt_start": float(start),
            "excerpt_end": float(start) + float(duration),
            "candidates": [],
        })
        for key in ("candidate", "backing", "generation", "mix_settings"):
            state.pop(key, None)
        return state, str(excerpt), None, [], _status(f"Excerpt is ready ({probe_duration(excerpt):.0f} seconds).", "ok")
    except (RemixiiError, ValueError) as exc:
        return state, None, state.get("candidate"), _candidate_details(state), _status(str(exc), "error")


def make_basic(state: dict[str, Any] | None):
    state = _session(state)
    try:
        if "excerpt" not in state:
            raise ValueError("Create the source excerpt first.")
        candidate = Path(state["root"]) / f"fallback-{uuid4().hex}.wav"
        copy_as_basic_arrangement(state["excerpt"], candidate)
        state["candidate"] = str(candidate)
        state.pop("backing", None)
        state.pop("mix_settings", None)
        state.pop("prompt_at_generation", None)
        state["generation"] = {
            "provider": "local non-AI fallback",
            "model_name": "none",
            "model_revision": "none",
            "seed": None,
            "environment": "local",
            "parameters": {"operation": "normalization and fades"},
        }
        state.setdefault("candidates", []).append({
            "provider": "local non-AI fallback", "task_id": None,
            "file": str(candidate), "settings": state["generation"]["parameters"],
        })
        return state, str(candidate), _candidate_details(state), _status("Created a non-AI fallback candidate.", "ok")
    except (RemixiiError, ValueError) as exc:
        return state, None, _candidate_details(state), _status(str(exc), "error")


def import_candidate(upload: Any, state: dict[str, Any] | None):
    state = _session(state)
    try:
        if "excerpt" not in state:
            raise ValueError("Create the source excerpt first.")
        source = _file_path(upload)
        duration = probe_duration(state["excerpt"])
        candidate = Path(state["root"]) / f"imported-{uuid4().hex}.wav"
        normalize_candidate(source, candidate, max_duration=duration)
        state["candidate"] = str(candidate)
        state.pop("backing", None)
        state.pop("mix_settings", None)
        state.pop("prompt_at_generation", None)
        state["generation"] = {
            "provider": "manual import",
            "model_name": "unknown",
            "model_revision": "unknown",
            "seed": None,
            "environment": "external generation",
            "parameters": {},
        }
        state.setdefault("candidates", []).append({
            "provider": "manual import", "task_id": None,
            "file": str(candidate), "settings": {},
        })
        return state, str(candidate), _candidate_details(state), _status("Imported candidate. Model details remain unknown.", "warning")
    except (RemixiiError, ValueError) as exc:
        return state, None, _candidate_details(state), _status(str(exc), "error")


def check_service():
    ok, message = AceStepAdapter(ace_step_url(), revision=ace_step_revision()).health()
    return _status(message, "ok" if ok else "warning")


def generate_candidate(
    state: dict[str, Any] | None,
    genre: str,
    bpm: int,
    prompt: str,
    permission_status: str,
    cover_strength: float = 0.45,
    seed: int = 42,
    custom_style: str = "",
    excerpt_mode: str = SHORT_MODE,
):
    state = _session(state)
    try:
        if "excerpt" not in state:
            raise ValueError("Create the source excerpt first.")
        if state.get("excerpt_mode", SHORT_MODE) != excerpt_mode:
            raise ValueError("Create an excerpt in the selected mode before generating.")
        if permission_status not in {"Authorized", "Public domain", PRIVATE_ANALYSIS}:
            raise ValueError("Choose Authorized, Public domain, or Uncleared—private analysis for local generation.")
        effective_style = _effective_style(genre, custom_style)
        duration = probe_duration(state["excerpt"])
        run_id = uuid4().hex
        raw = Path(state["root"]) / f"ace-step-result-{run_id}.wav"
        model = AceStepAdapter(
            ace_step_url(), revision=ace_step_revision(),
            timeout=2400 if duration >= 420 else 1800 if duration >= 300 else 1200 if duration >= 180 else 300,
        ).generate(
            state["excerpt"], genre=effective_style, bpm=int(bpm), prompt=prompt,
            output=raw, duration=duration, cover_strength=float(cover_strength), seed=int(seed),
        )
        returned_duration = probe_duration(raw)
        if duration >= 180 and returned_duration < duration - 2:
            raise GenerationError(
                f"ACE-Step task {model['task_id']} returned {returned_duration:.1f} seconds "
                f"for a {duration:.1f}-second cover request. The shortened file was not selected."
            )
        candidate = Path(state["root"]) / f"ace-step-candidate-{run_id}.wav"
        normalize_candidate(raw, candidate, max_duration=duration)
        state["candidate"] = str(candidate)
        state["backing"] = str(candidate)
        state.pop("mix_settings", None)
        state["generation"] = model
        state["prompt_at_generation"] = prompt
        state.setdefault("candidates", []).append({
            "provider": model["provider"],
            "task_id": model["task_id"],
            "caption": model["parameters"]["submitted_prompt"],
            "settings": model["parameters"],
            "file": str(candidate),
        })
        return state, str(candidate), _candidate_details(state), _status("ACE-Step cover candidate is ready. Listen before exporting.", "ok")
    except (RemixiiError, ValueError) as exc:
        for key in ("candidate", "backing", "generation", "mix_settings"):
            state.pop(key, None)
        return state, None, _candidate_details(state), _status(str(exc), "error")


def mix_candidate(state: dict[str, Any] | None, source_gain_db: float, backing_gain_db: float):
    state = _session(state)
    try:
        if state.get("generation", {}).get("provider") != "ACE-Step local HTTP API" or not state.get("backing"):
            raise ValueError("Generate an ACE-Step cover candidate before mixing its backing with the source.")
        output = Path(state["root"]) / f"source-preserving-{uuid4().hex}.wav"
        mix_source_and_backing(
            state["excerpt"], state["backing"], output,
            source_gain_db=float(source_gain_db), backing_gain_db=float(backing_gain_db),
        )
        state["candidate"] = str(output)
        state["mix_settings"] = {
            "source_gain_db": float(source_gain_db),
            "backing_gain_db": float(backing_gain_db),
        }
        return state, str(output), _status("Source and backing mixed. Both layers will be saved in the project.", "ok")
    except (RemixiiError, ValueError) as exc:
        return state, state.get("candidate"), _status(str(exc), "error")


def export_current(
    state: dict[str, Any] | None,
    project_title: str,
    creator: str,
    source_title: str,
    source_artist: str,
    source_recording: str,
    influence: str,
    permission_status: str,
    permission_evidence: str,
    genre: str,
    bpm: int,
    prompt: str,
    custom_style: str = "",
):
    state = _session(state)
    try:
        required = {
            "Project title": project_title,
            "Creator": creator,
            "Source title": source_title,
            "Source artist/performer": source_artist,
            "Actual source recording": source_recording,
        }
        missing = [name for name, value in required.items() if not value or not value.strip()]
        if missing:
            raise ValueError("Complete these fields: " + ", ".join(missing))
        if "excerpt" not in state or "candidate" not in state:
            raise ValueError("Create an excerpt and select a candidate before exporting.")
        permission_map = {
            "Authorized": "authorized",
            "Public domain": "public_domain",
            "Unknown / unconfirmed": "unknown",
            "Not authorized": "not_authorized",
            PRIVATE_ANALYSIS: "uncleared_private_analysis",
        }
        excerpt_duration = probe_duration(state["excerpt"])
        mix_duration = probe_duration(state["candidate"])
        generation_params = state.get("generation", {}).get("parameters", {})
        effective_style = generation_params.get("style") or _effective_style(genre, custom_style)
        source_name = "media/source-excerpt.wav"
        mix_name = "media/selected-mix.wav"
        backing_name = "media/backing-track.wav"
        mix_settings = state.get("mix_settings")
        media_files = {source_name: state["excerpt"], mix_name: state["candidate"]}
        backing_media = None
        if mix_settings:
            backing_media = media_record(state["backing"], backing_name, probe_duration(state["backing"]))
            media_files[backing_name] = state["backing"]
        manifest = new_manifest(
            title=project_title,
            creator=creator,
            source_title=source_title,
            source_artist=source_artist,
            source_recording=source_recording,
            influence=influence,
            permission_status=permission_map[permission_status],
            permission_evidence=permission_evidence,
            excerpt_start=state["excerpt_start"],
            excerpt_end=state["excerpt_end"],
            genre=generation_params.get("style", effective_style),
            bpm=int(generation_params.get("bpm", bpm)),
            vocal_treatment="keep_original_vocals" if mix_settings else "instrumental",
            prompt=state.get("prompt_at_generation", prompt),
            model=state.get("generation", {"provider": "unknown", "model_name": "unknown"}),
            source_media=media_record(state["excerpt"], source_name, excerpt_duration),
            mix_media=media_record(state["candidate"], mix_name, mix_duration),
            backing_media=backing_media,
            source_gain_db=mix_settings["source_gain_db"] if mix_settings else 0.0,
            backing_gain_db=mix_settings["backing_gain_db"] if mix_settings else -9.0,
        )
        safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in project_title).strip("_")
        target = Path(state["root"]) / f"{safe_title or 'project'}.remix"
        export_project(target, manifest, media_files)
        label = "Private analysis project exported; permission remains uncleared." if permission_status == PRIVATE_ANALYSIS else "Project exported. Keep this file for offline playback."
        return str(target), _status(label, "ok")
    except (RemixiiError, ValueError, KeyError) as exc:
        return None, _status(str(exc), "error")


def _credits_markdown(manifest: dict[str, Any]) -> str:
    project, source = manifest["project"], manifest["source"]
    transform, generation = manifest["transformation"], manifest["generation"]
    def unknown(value: Any) -> str:
        if value in (None, ""):
            return "unknown"
        if isinstance(value, (dict, list)):
            return f"`{json.dumps(value, ensure_ascii=False, sort_keys=True)}`"
        return str(value)

    provider_url = generation.get("provider_url")
    model_source = f"[{provider_url}]({provider_url})" if provider_url else "not applicable"
    project_label = (
        "Private analysis — uncleared; not a cleared release"
        if source["permission_status"] == "uncleared_private_analysis" else "Remix project"
    )
    arrangement = manifest.get("arrangement", {})
    layers = unknown(arrangement.get("tracks")) if arrangement.get("mode") == "source_preserving_mix" else "Selected candidate"

    return f"""### {project['title']}

**Project label:** {project_label}<br>
**Creator:** {project['creator']}  
**Created:** {project['created_at']}  
**Source work:** {source['work_title']} — {source['performers']}  
**Actual recording:** {source['actual_recording']}  
**Declared influence:** {unknown(source.get('declared_influence'))}  
**Permission:** {source['permission_status']}  
**Evidence reference:** {unknown(source.get('permission_evidence'))}  
**Transformation:** {transform['genre']}, {transform['bpm']} BPM, {transform['vocal_treatment']}  
**Prompt:** {unknown(transform.get('prompt'))}  
**Provider:** {unknown(generation.get('provider'))}  
**Model:** {unknown(generation.get('model_name'))} / {unknown(generation.get('model_revision'))}  
**Task ID:** {unknown(generation.get('task_id'))}<br>
**Seed:** {unknown(generation.get('seed'))}  
**Layers:** {layers}<br>
**Environment:** {unknown(generation.get('environment'))}  
**Generation parameters:** {unknown(generation.get('parameters'))}  
**Model source:** {model_source}

This record contains user declarations and processing details. It is not proof of ownership or a licence.
"""


def open_project_file(upload: Any):
    try:
        manifest, extracted = import_project(_file_path(upload))
        source = extracted / Path(manifest["media"]["source_excerpt"]["filename"])
        mix = extracted / Path(manifest["media"]["selected_mix"]["filename"])
        backing_record = manifest["media"].get("backing_track")
        backing = str(extracted / Path(backing_record["filename"])) if backing_record else None
        label = "Private analysis" if manifest["source"]["permission_status"] == "uncleared_private_analysis" else "Project"
        return str(source), backing, str(mix), _credits_markdown(manifest), json.dumps(manifest, indent=2), _status(f"{label} validated and opened offline.", "ok")
    except (RemixiiError, ValueError) as exc:
        return None, None, None, "", "", _status(str(exc), "error")


def clear_session(state: dict[str, Any] | None):
    if state and state.get("root"):
        shutil.rmtree(state["root"], ignore_errors=True)
    return _new_session(), None, None, None, [], _status("Temporary project files cleared.", "ok")


def build_app() -> gr.Blocks:
    with gr.Blocks(title="AI Remix Studio", theme=gr.themes.Soft()) as demo:
        state = gr.State(None)
        gr.Markdown("# AI Remix Studio\nCreate a short clip or a full-length cover project, or open one entirely offline.")
        gr.Markdown(
            f"**Local generation model:** [ACE-Step 1.5]({ACE_STEP_REPOSITORY}) · "
            "The model is optional for playback and is never included in a `.remix` file."
        )
        status = gr.Markdown(_status("Ready."))

        with gr.Tabs():
            with gr.Tab("Create"):
                with gr.Row():
                    with gr.Column(scale=2):
                        media_upload = gr.File(label="Audio or video source", type="filepath")
                        load_button = gr.Button("Load media", variant="primary")
                        full_preview = gr.Audio(label="Imported audio", show_download_button=False, show_share_button=False, editable=False)
                        excerpt_mode = gr.Radio(
                            [SHORT_MODE, FULL_MODE, FIVE_MINUTE_MODE, SEVEN_MINUTE_MODE], value=SHORT_MODE, label="Excerpt mode",
                        )
                        full_length_warning = gr.Markdown(FULL_LENGTH_WARNING, visible=False)
                        with gr.Row():
                            start = gr.Slider(0, 1, value=0, step=0.1, label="Excerpt start (seconds)")
                            duration = gr.Slider(10, 30, value=10, step=0.1, label="Excerpt duration (seconds)")
                        trim_button = gr.Button("Create excerpt")
                        source_preview = gr.Audio(label="Original excerpt", show_download_button=False, show_share_button=False, editable=False)

                    with gr.Column(scale=2):
                        project_title = gr.Textbox(label="Project title")
                        creator = gr.Textbox(label="Creator")
                        source_title = gr.Textbox(label="Source work title")
                        source_artist = gr.Textbox(label="Source artist / performers")
                        source_recording = gr.Textbox(label="Actual source recording", placeholder="Filename, recording name, or catalog reference")
                        influence = gr.Textbox(label="Declared influence (optional)")
                        permission_status = gr.Dropdown(
                            ["Authorized", "Public domain", PRIVATE_ANALYSIS, "Unknown / unconfirmed", "Not authorized"],
                            value="Unknown / unconfirmed",
                            label="Permission status",
                        )
                        permission_evidence = gr.Textbox(label="Permission evidence reference (optional)")

                gr.Markdown("### Transformation")
                with gr.Row():
                    genre = gr.Dropdown(STYLE_PRESETS, value="Techno", label="Style")
                    custom_style = gr.Textbox(
                        label="Custom style",
                        placeholder="For example: melodic industrial electro",
                        visible=False,
                    )
                    bpm = gr.Slider(60, 200, value=128, step=1, label="Target BPM")
                    gr.Radio(["Instrumental"], value="Instrumental", label="Vocal treatment")
                prompt = gr.Textbox(label="Model prompt", lines=2, placeholder="Instrumental driving techno remix, no singing or speech...")
                with gr.Row():
                    cover_strength = gr.Slider(0, 1, value=0.45, step=0.05, label="Cover strength")
                    seed = gr.Number(value=42, minimum=0, maximum=2147483647, precision=0, label="Seed")
                with gr.Row():
                    service_button = gr.Button("Check generation service")
                    generate_button = gr.Button("Generate with ACE-Step", variant="primary")
                    basic_button = gr.Button("Create non-AI fallback")

                with gr.Accordion("Import an already-generated candidate", open=False):
                    candidate_upload = gr.File(label="Generated audio", type="filepath", file_types=["audio"])
                    import_button = gr.Button("Use imported candidate")
                candidate_preview = gr.Audio(label="Selected remix candidate", show_download_button=False, show_share_button=False, editable=False)
                candidate_details = gr.JSON(label="Candidate requests and task IDs", value=[])
                gr.Markdown("### Source-preserving mix\nKeep the original excerpt audible above the ACE-Step generated backing.")
                with gr.Row():
                    source_gain = gr.Slider(-30, 6, value=0, step=1, label="Original source level (dB)")
                    backing_gain = gr.Slider(-30, 6, value=-9, step=1, label="Generated backing level (dB)")
                    mix_button = gr.Button("Mix original + backing")

                with gr.Row():
                    export_button = gr.Button("Export .remix project", variant="primary")
                    clear_button = gr.Button("Clear temporary files")
                exported_file = gr.File(label="Portable project")

            with gr.Tab("Open project"):
                project_upload = gr.File(label="Drop a .remix project", type="filepath", file_types=[".remix"])
                open_button = gr.Button("Validate and open", variant="primary")
                with gr.Row():
                    opened_source = gr.Audio(label="Original excerpt", show_download_button=False, show_share_button=False, editable=False)
                    opened_backing = gr.Audio(label="Generated backing layer", show_download_button=False, show_share_button=False, editable=False)
                    opened_mix = gr.Audio(label="Remix", show_download_button=False, show_share_button=False, editable=False)
                credits = gr.Markdown()
                with gr.Accordion("Manifest details", open=False):
                    manifest_json = gr.Code(language="json", label="manifest.json")

        excerpt_mode.change(_excerpt_controls, [state, excerpt_mode], [start, duration, full_length_warning, status])
        load_button.click(load_source, [media_upload, state, excerpt_mode], [state, full_preview, start, duration, candidate_preview, candidate_details, status])
        genre.change(_custom_style_visibility, genre, custom_style)
        trim_button.click(make_excerpt, [state, start, duration, excerpt_mode], [state, source_preview, candidate_preview, candidate_details, status])
        service_button.click(check_service, outputs=status)
        basic_button.click(make_basic, [state], [state, candidate_preview, candidate_details, status])
        import_button.click(import_candidate, [candidate_upload, state], [state, candidate_preview, candidate_details, status])
        generate_button.click(
            generate_candidate,
            [state, genre, bpm, prompt, permission_status, cover_strength, seed, custom_style, excerpt_mode],
            [state, candidate_preview, candidate_details, status],
        )
        mix_button.click(mix_candidate, [state, source_gain, backing_gain], [state, candidate_preview, status])
        export_button.click(
            export_current,
            [state, project_title, creator, source_title, source_artist, source_recording, influence,
             permission_status, permission_evidence, genre, bpm, prompt, custom_style],
            [exported_file, status],
        )
        clear_button.click(clear_session, [state], [state, full_preview, source_preview, candidate_preview, candidate_details, status])
        open_button.click(
            open_project_file,
            [project_upload],
            [opened_source, opened_backing, opened_mix, credits, manifest_json, status],
        )
    return demo


def main() -> None:
    open_browser = os.getenv("REMIXII_INBROWSER", "1").lower() not in {"0", "false", "no"}
    build_app().launch(server_name="127.0.0.1", inbrowser=open_browser, show_error=True)


if __name__ == "__main__":
    main()
