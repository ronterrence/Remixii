# AI Remix Studio

AI Remix Studio is a local school-project MVP for turning an authorized 10–30 second excerpt into a short genre remix, recording its provenance, and exporting a portable `.remix` file. Presets include Techno, House, Trance, Drum & Bass, and Afro House, with a custom-style option. A listener can validate and play the project offline without a model or GPU.

## What works

- Audio or video import through FFmpeg, waveform preview, and 10–30 second trimming.
- Separate source, influence, permission, model, and generation records.
- ACE-Step 1.5 generation through its asynchronous HTTP API.
- Manual candidate import and a non-AI fallback when generation is unavailable.
- Safe `.remix` export/import with schema, path, size, and SHA-256 validation.
- Offline original/remix playback and readable “How this was made” credits.

Instrumental output is the MVP requirement. The app does not claim that a generated candidate is instrumental; the creator must listen before export. Retained-original-vocal processing is intentionally deferred.

## Development setup

Install Python 3.11. The project dependency supplies an FFmpeg executable for development; `REMIXII_FFMPEG` can point to a different compatible build. Then run:

```powershell
py -3.11 -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev]"
.venv\Scripts\python.exe -m pytest
.venv\Scripts\python.exe -m remixii.app
```

The interface opens at `http://127.0.0.1:7860`.

If an old `.venv` points to a Python installation that has been removed, it may report that `pip` or `gradio` is missing. The development launcher checks for a working environment and can use the prepared `.test-venv` without changing the old folder:

```powershell
.\scripts\run-dev.ps1
```

## Local ACE-Step creator setup

Generation uses only the official [ACE-Step 1.5 repository](https://github.com/ACE-Step/ACE-Step-1.5). The model is optional: project opening and playback never start ACE-Step or access the network.

On the creator computer, install Git, `uv`, and AMD driver 26.1.1 or later, then prepare the tested official revision in a sibling `ACE-Step-1.5` directory. The script obtains Python 3.12 and installs the ROCm 7.2 SDK and PyTorch wheels specified by the official repository:

```powershell
.\scripts\setup-ace-step.ps1
```

The setup uses the official repository's Windows ROCm dependencies for this creator computer's Radeon RX 7600. It creates ACE-Step's separate Python 3.12 `venv_rocm`; Remixii continues to use Python 3.11. The first server launch can download approximately 10 GB of model files.

Start the local API and Remixii together:

```powershell
.\scripts\run-creator.ps1
```

The launcher runs the official `acestep.api_server` module with the RX 7600 setting `HSA_OVERRIDE_GFX_VERSION=11.0.2`. The upstream ROCm batch file currently hardcodes `11.0.0` for a different GPU, so the creator launcher sets the documented RX 7600 value without editing ACE-Step. It connects only to `http://127.0.0.1:8001`, records the checked-out ACE-Step Git revision, and stops the API process it started when Remixii closes. There is no remote endpoint or API-key workflow. Manual candidate import and the non-AI fallback remain available without ACE-Step.

## Windows bundle

The default bundle collects the FFmpeg executable supplied by `imageio-ffmpeg`. You may instead place compatible `ffmpeg.exe` and `ffprobe.exe` in `vendor/ffmpeg/`. Complete the distribution obligations in `THIRD_PARTY_NOTICES.md`, record the exact build used, then run:

```powershell
.\scripts\build-windows.ps1
```

Distribute the entire `dist\AI Remix Studio` folder, including `THIRD_PARTY_NOTICES.md`, together with the submitted `.remix` file. Do not include the ACE-Step checkout, its Python environment, or its model weights. Test the folder on a fresh offline Windows laptop before the presentation.

For an offline check, disconnect Wi-Fi on the second laptop, copy the complete folder, and run `powershell -ExecutionPolicy Bypass -File .\verify-offline.ps1` from inside it. The script checks that the interface and its JS/CSS load locally, then opens the app. In `Open project`, import the included `Offline playback test.remix` and play both the original and remix. This fixture contains original programmatically generated audio and is explicitly non-AI; it checks packaging and playback without needing source rights or a GPU.

## Project format

See [docs/remix-format.md](docs/remix-format.md). A project contains the authorized excerpt and selected mix, so sharing it is a distribution decision even though the player has no audio download button.
