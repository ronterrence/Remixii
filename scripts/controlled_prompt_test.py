"""Run two ACE-Step cover prompts against one 10-second excerpt."""

from __future__ import annotations

import argparse
import json
import math
import struct
import wave
from pathlib import Path

from remixii.config import ace_step_revision, ace_step_url
from remixii.generation import AceStepAdapter
from remixii.media import extract_audio, trim_audio


def original_test_excerpt(path: Path) -> None:
    sample_rate = 44100
    notes = (261.63, 329.63, 392.0, 440.0)
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(sample_rate)
        frames = bytearray()
        for index in range(sample_rate * 10):
            position = index / sample_rate
            note = notes[int(position * 2) % len(notes)]
            envelope = min(1.0, (position % 0.5) * 30) * math.exp(-2 * (position % 0.5))
            melody = 0.15 * envelope * math.sin(2 * math.pi * note * position)
            bass = 0.08 * math.sin(2 * math.pi * 130.81 * position)
            value = int(max(-1, min(1, melody + bass)) * 32767)
            frames.extend(struct.pack("<hh", value, value))
        audio.writeframes(frames)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, help="Local audio or video to excerpt")
    parser.add_argument("--start", type=float, default=0.0)
    parser.add_argument("--output", type=Path, default=Path("build/controlled-prompt-test"))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    excerpt = args.output / "source-excerpt.wav"
    if args.source:
        full = args.output / "source-full.wav"
        extract_audio(args.source, full)
        trim_audio(full, excerpt, args.start, 10)
    else:
        original_test_excerpt(excerpt)

    adapter = AceStepAdapter(ace_step_url(), revision=ace_step_revision(), timeout=300)
    conditions = (
        ("techno", "Techno", "Four-on-the-floor kick, pulsing synth bass, crisp electronic hi-hats, energetic club groove"),
        ("acoustic-jazz", "Acoustic jazz", "Brush drums, upright bass, mellow piano chords, intimate acoustic trio, no synthesizers"),
    )
    results = []
    for name, style, prompt in conditions:
        destination = args.output / f"{name}.wav"
        print(f"Generating {name} with seed=42, BPM=128, cover strength=0.45", flush=True)
        details = adapter.generate(
            excerpt, genre=style, bpm=128, prompt=prompt, output=destination,
            duration=10, cover_strength=0.45, seed=42,
        )
        results.append({"name": name, "audio": str(destination), "generation": details})
        print(f"Finished {name}: task {details['task_id']}", flush=True)
    report = args.output / "requests.json"
    report.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Saved {report}", flush=True)


if __name__ == "__main__":
    main()
