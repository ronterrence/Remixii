from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

import gradio as gr

from .config import ACE_STEP_REPOSITORY, ace_step_revision, ace_step_url
from .errors import RemixiiError
from .generation import AceStepAdapter
from .media import (
    copy_as_basic_arrangement,
    extract_audio,
    normalize_candidate,
    probe_duration,
    trim_audio,
)
from .package import export_project, import_project, media_record
from .schema import new_manifest

STYLE_PRESETS = ["Techno", "House", "Trance", "Drum & Bass", "Afro House", "Custom"]


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
    return {"root": tempfile.mkdtemp(prefix="remixii-create-")}


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


def load_source(upload: Any, state: dict[str, Any] | None):
    state = _session(state)
    try:
        source = Path(_file_path(upload))
        audio = Path(state["root"]) / "source-full.wav"
        extract_audio(source, audio)
        duration = probe_duration(audio)
        if duration < 10:
            raise ValueError("Source media must be at least 10 seconds long.")
        state.update({"source_full": str(audio), "source_name": source.name, "duration": duration})
        maximum_start = max(0.0, duration - 10)
        default_duration = min(30.0, duration)
        return (
            state,
            str(audio),
            gr.update(maximum=maximum_start, value=0),
            gr.update(maximum=min(30.0, duration), value=default_duration),
            _status(f"Loaded {source.name} ({duration:.1f} seconds).", "ok"),
        )
    except (RemixiiError, ValueError) as exc:
        return state, None, gr.update(), gr.update(), _status(str(exc), "error")


def make_excerpt(state: dict[str, Any] | None, start: float, duration: float):
    state = _session(state)
    try:
        if "source_full" not in state:
            raise ValueError("Load source media first.")
        excerpt = Path(state["root"]) / "source-excerpt.wav"
        trim_audio(state["source_full"], excerpt, float(start), float(duration))
        state.update({
            "excerpt": str(excerpt),
            "excerpt_start": float(start),
            "excerpt_end": float(start) + float(duration),
        })
        return state, str(excerpt), _status("Excerpt is ready.", "ok")
    except (RemixiiError, ValueError) as exc:
        return state, None, _status(str(exc), "error")


def make_basic(state: dict[str, Any] | None):
    state = _session(state)
    try:
        if "excerpt" not in state:
            raise ValueError("Create the source excerpt first.")
        candidate = Path(state["root"]) / "selected-mix.wav"
        copy_as_basic_arrangement(state["excerpt"], candidate)
        state["candidate"] = str(candidate)
        state["generation"] = {
            "provider": "local non-AI fallback",
            "model_name": "none",
            "model_revision": "none",
            "seed": None,
            "environment": "local",
            "parameters": {"operation": "normalization and fades"},
        }
        return state, str(candidate), _status("Created a non-AI fallback candidate.", "ok")
    except (RemixiiError, ValueError) as exc:
        return state, None, _status(str(exc), "error")


def import_candidate(upload: Any, state: dict[str, Any] | None):
    state = _session(state)
    try:
        if "excerpt" not in state:
            raise ValueError("Create the source excerpt first.")
        source = _file_path(upload)
        duration = probe_duration(state["excerpt"])
        candidate = Path(state["root"]) / "selected-mix.wav"
        normalize_candidate(source, candidate, max_duration=duration)
        state["candidate"] = str(candidate)
        state["generation"] = {
            "provider": "manual import",
            "model_name": "unknown",
            "model_revision": "unknown",
            "seed": None,
            "environment": "external generation",
            "parameters": {},
        }
        return state, str(candidate), _status("Imported candidate. Model details remain unknown.", "warning")
    except (RemixiiError, ValueError) as exc:
        return state, None, _status(str(exc), "error")


def check_service():
    ok, message = AceStepAdapter(ace_step_url(), revision=ace_step_revision()).health()
    return _status(message, "ok" if ok else "warning")


def generate_candidate(
    state: dict[str, Any] | None,
    genre: str,
    bpm: int,
    prompt: str,
    permission_status: str,
    custom_style: str = "",
):
    state = _session(state)
    try:
        if "excerpt" not in state:
            raise ValueError("Create the source excerpt first.")
        if permission_status not in {"Authorized", "Public domain"}:
            raise ValueError("Confirm that the excerpt is authorized before local AI generation.")
        effective_style = _effective_style(genre, custom_style)
        duration = probe_duration(state["excerpt"])
        raw = Path(state["root"]) / "ace-step-result.wav"
        model = AceStepAdapter(ace_step_url(), revision=ace_step_revision()).generate(
            state["excerpt"], genre=effective_style, bpm=int(bpm), prompt=prompt,
            output=raw, duration=duration,
        )
        candidate = Path(state["root"]) / "selected-mix.wav"
        normalize_candidate(raw, candidate, max_duration=duration)
        state["candidate"] = str(candidate)
        state["generation"] = model
        return state, str(candidate), _status("ACE-Step candidate is ready. Listen before exporting.", "ok")
    except (RemixiiError, ValueError) as exc:
        return state, None, _status(str(exc), "error")


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
        }
        excerpt_duration = probe_duration(state["excerpt"])
        mix_duration = probe_duration(state["candidate"])
        effective_style = _effective_style(genre, custom_style)
        source_name = "media/source-excerpt.wav"
        mix_name = "media/selected-mix.wav"
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
            genre=effective_style,
            bpm=int(bpm),
            vocal_treatment="instrumental",
            prompt=prompt,
            model=state.get("generation", {"provider": "unknown", "model_name": "unknown"}),
            source_media=media_record(state["excerpt"], source_name, excerpt_duration),
            mix_media=media_record(state["candidate"], mix_name, mix_duration),
        )
        safe_title = "".join(c if c.isalnum() or c in "-_" else "_" for c in project_title).strip("_")
        target = Path(state["root"]) / f"{safe_title or 'project'}.remix"
        export_project(target, manifest, {source_name: state["excerpt"], mix_name: state["candidate"]})
        return str(target), _status("Project exported. Keep this file for offline playback.", "ok")
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

    return f"""### {project['title']}

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
**Seed:** {unknown(generation.get('seed'))}  
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
        return str(source), str(mix), _credits_markdown(manifest), json.dumps(manifest, indent=2), _status("Project validated and opened offline.", "ok")
    except (RemixiiError, ValueError) as exc:
        return None, None, "", "", _status(str(exc), "error")


def clear_session(state: dict[str, Any] | None):
    if state and state.get("root"):
        shutil.rmtree(state["root"], ignore_errors=True)
    return _new_session(), None, None, None, _status("Temporary project files cleared.", "ok")


def build_app() -> gr.Blocks:
    with gr.Blocks(title="AI Remix Studio", theme=gr.themes.Soft()) as demo:
        state = gr.State(None)
        gr.Markdown("# AI Remix Studio\nCreate a short authorized remix project, or open one entirely offline.")
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
                        with gr.Row():
                            start = gr.Slider(0, 1, value=0, step=0.1, label="Excerpt start (seconds)")
                            duration = gr.Slider(10, 30, value=30, step=0.1, label="Excerpt duration")
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
                            ["Authorized", "Public domain", "Unknown / unconfirmed", "Not authorized"],
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
                    service_button = gr.Button("Check generation service")
                    generate_button = gr.Button("Generate with ACE-Step", variant="primary")
                    basic_button = gr.Button("Create non-AI fallback")

                with gr.Accordion("Import an already-generated candidate", open=False):
                    candidate_upload = gr.File(label="Generated audio", type="filepath", file_types=["audio"])
                    import_button = gr.Button("Use imported candidate")
                candidate_preview = gr.Audio(label="Selected remix candidate", show_download_button=False, show_share_button=False, editable=False)

                with gr.Row():
                    export_button = gr.Button("Export .remix project", variant="primary")
                    clear_button = gr.Button("Clear temporary files")
                exported_file = gr.File(label="Portable project")

            with gr.Tab("Open project"):
                project_upload = gr.File(label="Drop a .remix project", type="filepath", file_types=[".remix"])
                open_button = gr.Button("Validate and open", variant="primary")
                with gr.Row():
                    opened_source = gr.Audio(label="Original excerpt", show_download_button=False, show_share_button=False, editable=False)
                    opened_mix = gr.Audio(label="Remix", show_download_button=False, show_share_button=False, editable=False)
                credits = gr.Markdown()
                with gr.Accordion("Manifest details", open=False):
                    manifest_json = gr.Code(language="json", label="manifest.json")

        load_button.click(load_source, [media_upload, state], [state, full_preview, start, duration, status])
        genre.change(_custom_style_visibility, genre, custom_style)
        trim_button.click(make_excerpt, [state, start, duration], [state, source_preview, status])
        service_button.click(check_service, outputs=status)
        basic_button.click(make_basic, [state], [state, candidate_preview, status])
        import_button.click(import_candidate, [candidate_upload, state], [state, candidate_preview, status])
        generate_button.click(
            generate_candidate,
            [state, genre, bpm, prompt, permission_status, custom_style],
            [state, candidate_preview, status],
        )
        export_button.click(
            export_current,
            [state, project_title, creator, source_title, source_artist, source_recording, influence,
             permission_status, permission_evidence, genre, bpm, prompt, custom_style],
            [exported_file, status],
        )
        clear_button.click(clear_session, [state], [state, full_preview, source_preview, candidate_preview, status])
        open_button.click(
            open_project_file,
            [project_upload],
            [opened_source, opened_mix, credits, manifest_json, status],
        )
    return demo


def main() -> None:
    open_browser = os.getenv("REMIXII_INBROWSER", "1").lower() not in {"0", "false", "no"}
    build_app().launch(server_name="127.0.0.1", inbrowser=open_browser, show_error=True)


if __name__ == "__main__":
    main()
