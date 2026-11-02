from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import date


def _env(name: str, default: str | None = None) -> str:
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"Missing required environment variable {name}")
    return value


@dataclass(frozen=True)
class Settings:
    project: str
    dataset: str = "smartspend"
    # Gemini 2.5 models were retired on Vertex AI on 2026-10-20. The 3.x Flash models are
    # served from the global endpoint, so the model location is separate from the Cloud Run region.
    gemini_model: str = "gemini-3.8-flash"
    gemini_location: str = "global"
    receipts_bucket: str = ""
    user_id: str = "demo-user"
    today_override: date | None = field(default=None)

    @property
    def today(self) -> date:
        return self.today_override or date.today()

    @classmethod
    def from_env(cls) -> "Settings":
        project = _env("GCP_PROJECT", os.environ.get("GOOGLE_CLOUD_PROJECT"))
        today = os.environ.get("SMARTSPEND_TODAY")
        return cls(
            project=project,
            dataset=_env("BQ_DATASET", "smartspend"),
            gemini_model=_env("GEMINI_MODEL", cls.gemini_model),
            gemini_location=_env("GEMINI_LOCATION", cls.gemini_location),
            receipts_bucket=_env("RECEIPTS_BUCKET", f"{project}-smartspend-receipts"),
            user_id=_env("SMARTSPEND_USER", "demo-user"),
            today_override=date.fromisoformat(today) if today else None,
        )
