"""Thin wrapper over the Google Gen AI SDK pointed at Vertex AI.

Everything the agent asks Gemini for is either structured JSON validated by a
Pydantic model, or a short grounded answer. The `LLM` protocol lets tests swap
in a fake without network access.
"""
from __future__ import annotations

from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLM(Protocol):
    def structured(self, prompt: str, schema: type[T], *, image: bytes | None = None, mime_type: str = "image/jpeg") -> T: ...
    def text(self, prompt: str, *, system: str | None = None) -> str: ...


class Gemini:
    def __init__(self, project: str, location: str, model: str):
        from google import genai  # imported lazily so tests don't need credentials

        self._client = genai.Client(vertexai=True, project=project, location=location)
        self.model = model

    def _config(self, **kwargs):
        from google.genai import types

        return types.GenerateContentConfig(
            temperature=0,
            # Classification and extraction don't need long reasoning; keep latency and cost down.
            thinking_config=types.ThinkingConfig(thinking_level="low"),
            **kwargs,
        )

    def structured(self, prompt, schema, *, image=None, mime_type="image/jpeg"):
        from google.genai import types

        contents: list = [prompt]
        if image is not None:
            contents.insert(0, types.Part.from_bytes(data=image, mime_type=mime_type))
        resp = self._client.models.generate_content(
            model=self.model,
            contents=contents,
            config=self._config(response_mime_type="application/json", response_schema=schema),
        )
        if resp.parsed is not None:
            return resp.parsed
        return schema.model_validate_json(resp.text)

    def text(self, prompt, *, system=None):
        resp = self._client.models.generate_content(
            model=self.model,
            contents=[prompt],
            config=self._config(system_instruction=system),
        )
        return (resp.text or "").strip()
