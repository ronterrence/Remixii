# Build from the repository root with: pyinstaller packaging/remixii.spec
from pathlib import Path
import re
from PyInstaller.utils.hooks import collect_data_files

root = Path(SPECPATH).parent
vendor = root / "vendor" / "ffmpeg"
binaries = []
for filename in ("ffmpeg.exe", "ffprobe.exe"):
    binary = vendor / filename
    if binary.exists():
        binaries.append((str(binary), "vendor/ffmpeg"))

# Gradio ships a Jinja template with relative asset URLs and an optional
# iframe-resizer CDN script. Keep a local copy whose assets resolve from the
# app root, including when Windows opens a URL with a path component.
gradio_data = collect_data_files("gradio", include_py_files=True)
offline_templates = []
offline_dir = root / "build" / "offline-gradio"
offline_dir.mkdir(parents=True, exist_ok=True)
for template_name in ("index.html", "share.html"):
    matches = [
        source for source, destination in gradio_data
        if Path(source).name == template_name
        and destination.replace("\\", "/") == "gradio/templates/frontend"
    ]
    if len(matches) != 1:
        raise ValueError(f"Expected one Gradio frontend {template_name}, found {len(matches)}")
    content = Path(matches[0]).read_text(encoding="utf-8")
    content, removed = re.subn(
        r'<script\s+src="https://cdnjs\.cloudflare\.com/ajax/libs/iframe-resizer/[^\"]+"\s+async\s*></script>',
        "",
        content,
    )
    if removed != 1:
        raise ValueError(f"Could not remove iframe-resizer CDN script from {template_name}")
    content = re.sub(
        r'<link\s+rel="preconnect"\s+href="https://fonts\.googleapis\.com"\s*/>',
        "",
        content,
    )
    content = re.sub(
        r'<link\s+rel="preconnect"\s+href="https://fonts\.gstatic\.com"\s+crossorigin="anonymous"\s*/>',
        "",
        content,
    )
    content = content.replace('"./assets/', '"/assets/')
    if '"./assets/' in content or "iframe-resizer/4.3.1" in content:
        raise ValueError(f"Offline template rewrite failed for {template_name}")
    output = offline_dir / template_name
    output.write_text(content, encoding="utf-8")
    offline_templates.append((str(output), "gradio/templates/frontend"))

gradio_data = [
    entry for entry in gradio_data
    if not (
        Path(entry[0]).name in {"index.html", "share.html"}
        and entry[1].replace("\\", "/") == "gradio/templates/frontend"
    )
]

a = Analysis(
    [str(root / "remixii_launcher.py")],
    pathex=[str(root)],
    binaries=binaries,
    datas=(
        collect_data_files("imageio_ffmpeg")
        + gradio_data
        + offline_templates
        + collect_data_files("gradio_client")
        + collect_data_files("safehttpx", includes=["version.txt"])
        + collect_data_files("groovy", includes=["version.txt"])
    ),
    hiddenimports=["gradio", "imageio_ffmpeg"],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="AI Remix Studio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    name="AI Remix Studio",
)
