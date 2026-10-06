from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

import requests

from .errors import GenerationError


class AceStepAdapter:
    MODEL_NAME = "acestep-v15-turbo"
    REPOSITORY_URL = "https://github.com/ACE-Step/ACE-Step-1.5"

    def __init__(self, base_url: str, *, revision: str | None = None, timeout: int = 300):
        self.base_url = base_url.rstrip("/")
        self.revision = revision
        self.timeout = timeout

    def health(self) -> tuple[bool, str]:
        try:
            response = requests.get(f"{self.base_url}/health", timeout=4)
            response.raise_for_status()
            data = response.json().get("data", {})
            return True, f"Connected to {data.get('service', 'ACE-Step')} {data.get('version', '')}".strip()
        except (requests.RequestException, ValueError) as exc:
            return False, f"Generation service unavailable: {exc}"

    def generate(
        self,
        source_audio: str | Path,
        *,
        genre: str,
        bpm: int,
        prompt: str,
        output: str | Path,
        duration: float = 30,
        cover_strength: float = 0.45,
    ) -> dict[str, Any]:
        caption = f"Instrumental {genre.lower()} remix, {bpm} BPM, no singing, no speech, strong groove"
        if prompt.strip():
            caption = f"{caption}. {prompt.strip()}"
        fields = {
            "prompt": caption,
            "lyrics": "[Instrumental]",
            "task_type": "cover",
            "audio_cover_strength": str(cover_strength),
            "bpm": str(bpm),
            "audio_duration": str(round(duration, 2)),
            "audio_format": "wav",
            "batch_size": "1",
            "model": self.MODEL_NAME,
        }
        try:
            with Path(source_audio).open("rb") as stream:
                response = requests.post(
                    f"{self.base_url}/release_task",
                    data=fields,
                    files={"src_audio": (Path(source_audio).name, stream, "audio/wav")},
                    timeout=30,
                )
            response.raise_for_status()
            envelope = response.json()
            if envelope.get("code") != 200:
                raise GenerationError(envelope.get("error") or "ACE-Step rejected the task.")
            task_id = envelope["data"]["task_id"]
            result = self._wait_for_result(task_id)
            self._download(result["file"], output)
            return {
                "provider": "ACE-Step local HTTP API",
                "provider_url": self.REPOSITORY_URL,
                "model_name": result.get("dit_model") or self.MODEL_NAME,
                "model_revision": self.revision or result.get("generation_info") or "unknown",
                "seed": result.get("seed_value") or None,
                "environment": result.get("env") or "local creator computer",
                "parameters": {
                    "task_type": "cover",
                    "audio_cover_strength": cover_strength,
                    "bpm": bpm,
                    "lyrics": "[Instrumental]",
                    "style": genre,
                    "submitted_prompt": caption,
                    "audio_duration": round(duration, 2),
                    "audio_format": "wav",
                    "batch_size": 1,
                },
            }
        except requests.RequestException as exc:
            raise GenerationError(f"ACE-Step request failed: {exc}") from exc
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise GenerationError("ACE-Step returned an unexpected response.") from exc

    def _wait_for_result(self, task_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            response = requests.post(
                f"{self.base_url}/query_result",
                json={"task_id_list": [task_id]},
                timeout=15,
            )
            response.raise_for_status()
            task = response.json()["data"][0]
            if task["status"] == 2:
                raise GenerationError("ACE-Step could not generate this candidate.")
            if task["status"] == 1:
                results = json.loads(task["result"])
                if not results:
                    raise GenerationError("ACE-Step completed without an audio result.")
                return results[0]
            time.sleep(2)
        raise GenerationError("Generation timed out. The service may still be busy; retry later.")

    def _download(self, location: str, output: str | Path) -> None:
        url = urljoin(f"{self.base_url}/", location)
        target = urlparse(url)
        local = urlparse(self.base_url)
        if (target.scheme, target.netloc) != (local.scheme, local.netloc):
            raise GenerationError("ACE-Step returned a non-local audio URL.")
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        destination = Path(output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(response.content)
