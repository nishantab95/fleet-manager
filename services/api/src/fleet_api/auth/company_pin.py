from __future__ import annotations

from hashlib import pbkdf2_hmac, sha256
from hmac import compare_digest
from secrets import randbelow, token_bytes, token_urlsafe

ACTIVATION_PURPOSE = "COMPANY_ACTIVATION"
PIN_PBKDF2_ITERATIONS = 600_000
ACTIVATION_PBKDF2_ITERATIONS = 120_000


def generate_activation_code() -> str:
    return f"{randbelow(1_000_000):06d}"


def generate_device_credential() -> str:
    return token_urlsafe(48)


def generate_salt() -> str:
    return token_bytes(16).hex()


def _pbkdf2(value: str, salt_hex: str, iterations: int) -> str:
    return pbkdf2_hmac(
        "sha256",
        value.encode("utf-8"),
        bytes.fromhex(salt_hex),
        iterations,
    ).hex()


def hash_activation_code(code: str, salt_hex: str) -> str:
    return _pbkdf2(code, salt_hex, ACTIVATION_PBKDF2_ITERATIONS)


def activation_code_matches(code: str, salt_hex: str, expected_hash: str) -> bool:
    return compare_digest(hash_activation_code(code, salt_hex), expected_hash)


def hash_pin(pin: str, salt_hex: str) -> str:
    return _pbkdf2(pin, salt_hex, PIN_PBKDF2_ITERATIONS)


def pin_matches(pin: str, salt_hex: str, expected_hash: str) -> bool:
    return compare_digest(hash_pin(pin, salt_hex), expected_hash)


def hash_device_credential(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()


def hash_installation_identifier(value: str) -> str:
    return sha256(value.encode("utf-8")).hexdigest()
