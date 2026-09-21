from __future__ import annotations

import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat, format_number, is_valid_number

from fleet_api.domain.errors import PhoneNormalizationError


def normalize_phone(phone: str, *, default_region: str | None = None) -> str:
    """Return a canonical E.164 phone number without assuming one country."""

    raw_phone = phone.strip()
    if not raw_phone:
        raise PhoneNormalizationError("phone number is required")
    region = None if raw_phone.startswith("+") else default_region
    try:
        parsed = phonenumbers.parse(raw_phone, region)
    except NumberParseException as exc:
        raise PhoneNormalizationError("phone number is invalid") from exc
    if not is_valid_number(parsed):
        raise PhoneNormalizationError("phone number is invalid")
    return format_number(parsed, PhoneNumberFormat.E164)
