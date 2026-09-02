"""Load configuration from environment variables (see .env.example).

Never hardcode credentials in source — this project reads everything
(OXS login, WhatsApp API token, building IDs) from the environment so the
same code can run for any building without editing files, and so secrets
never end up committed to git.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Settings:
    oxs_username: str
    oxs_password: str
    whatsapp_phone_number_id: str
    whatsapp_access_token: str
    whatsapp_template_name: str


def load_settings() -> Settings:
    return Settings(
        oxs_username=_require("OXS_USERNAME"),
        oxs_password=_require("OXS_PASSWORD"),
        whatsapp_phone_number_id=_require("WHATSAPP_PHONE_NUMBER_ID"),
        whatsapp_access_token=_require("WHATSAPP_ACCESS_TOKEN"),
        whatsapp_template_name=os.environ.get("WHATSAPP_TEMPLATE_NAME", "payment_confirmation"),
    )


@dataclass(frozen=True)
class BuildingConfig:
    """One building to process: its OXS building id and the bank statement
    to read for it. Buildings are configured in buildings.json (see
    buildings.example.json) rather than hardcoded, since the user manages
    several buildings."""

    name: str
    oxs_building_id: str
    bank_statement_path: str
