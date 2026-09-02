"""Send payment-confirmation messages via the WhatsApp Business Cloud API (Meta).

Because this message is sent by the business, not in reply to something the
tenant just wrote, it falls outside WhatsApp's 24-hour "customer service
window" and MUST use a pre-approved message template — a free-form text
message will simply be rejected by the API. Create and get the template
approved once in Meta Business Manager (WhatsApp Manager > Message
Templates) before this will work.

Example template body (category: UTILITY):
    "שלום {{1}}, אישור תקבל תשלום על סך {{2}} ש\"ח עבור {{3}}. תודה!"
with parameters filled in as [tenant_name, amount, months_or_purpose].
"""
from __future__ import annotations

import logging
from dataclasses import dataclass

import requests

log = logging.getLogger(__name__)

GRAPH_API_VERSION = "v21.0"


@dataclass(frozen=True)
class WhatsAppConfig:
    phone_number_id: str
    access_token: str
    template_name: str
    template_language: str = "he"


def normalize_il_phone(raw_phone: str) -> str:
    """Turn a local Israeli number (e.g. '054-5410877' or '0545410877')
    into E.164 without '+' (e.g. '972545410877'), as the API expects."""
    digits = "".join(ch for ch in raw_phone if ch.isdigit())
    if digits.startswith("972"):
        return digits
    if digits.startswith("0"):
        return "972" + digits[1:]
    return digits


def send_payment_confirmation(
    config: WhatsAppConfig,
    to_phone: str,
    template_params: list[str],
) -> dict:
    """Send the configured template message. Returns the parsed API response.

    Raises requests.HTTPError on failure (bad template name/params, phone
    not on WhatsApp, expired token, etc.) — caller should catch and log,
    not let one tenant's failure stop the whole batch.
    """
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{config.phone_number_id}/messages"
    payload = {
        "messaging_product": "whatsapp",
        "to": normalize_il_phone(to_phone),
        "type": "template",
        "template": {
            "name": config.template_name,
            "language": {"code": config.template_language},
            "components": [
                {
                    "type": "body",
                    "parameters": [{"type": "text", "text": p} for p in template_params],
                }
            ],
        },
    }
    headers = {"Authorization": f"Bearer {config.access_token}"}

    response = requests.post(url, json=payload, headers=headers, timeout=15)
    if not response.ok:
        log.error("WhatsApp send failed for %s: %s", to_phone, response.text)
    response.raise_for_status()
    return response.json()
