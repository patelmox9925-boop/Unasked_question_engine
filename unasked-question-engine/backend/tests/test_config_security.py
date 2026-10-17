import logging

import pytest
from pydantic import ValidationError

from app.config import Settings
from app.logging_setup import RedactingFilter
from app.security import REDACTED, redact
from tests.conftest import make_settings


def test_defaults_have_no_roles_configured():
    status = make_settings().public_status()
    assert status["live_analysis_available"] is False
    assert status["all_roles_ready"] is False
    assert all(not r["primary_ready"] for r in status["roles"].values())


def test_role_config_and_readiness():
    s = make_settings(
        llm_a_provider="Groq", llm_a_model="m-a", groq_api_key="sk-ant-secret-value-123456",
        llm_b_provider="deepseek", llm_b_model="m-b",  # no key -> not ready
        llm_b_fallback_provider="gemini", llm_b_fallback_model="m-g", gemini_api_key="AIzaSyFAKEFAKEFAKEFAKE1234",
    )
    assert s.role_config("A").provider == "groq"  # normalised
    status = s.public_status()
    assert status["roles"]["A"]["primary_ready"] is True
    assert status["roles"]["B"]["primary_ready"] is False
    assert status["roles"]["B"]["fallback_ready"] is True
    assert status["live_analysis_available"] is True
    assert status["all_roles_ready"] is False  # C missing


def test_unsupported_provider_rejected():
    with pytest.raises(ValidationError):
        make_settings(llm_a_provider="skynet")


def test_unknown_role_rejected():
    with pytest.raises(ValueError):
        make_settings().role_config("Z")


def test_public_status_never_contains_key_material():
    key = "sk-ant-super-secret-value-0123456789"
    s = make_settings(groq_api_key=key, deepseek_api_key="sk-deepseek-secret-9876543210abcdef")
    dumped = repr(s.public_status())
    assert key not in dumped and "sk-deepseek-secret" not in dumped
    assert s.public_status()["providers"]["groq"]["api_key_configured"] is True
    assert key not in repr(s)  # SecretStr hides it in repr too


def test_blank_key_counts_as_unconfigured():
    s = make_settings(deepseek_api_key="   ")
    assert s.api_key_for("deepseek") is None


def test_redact_known_secret_and_patterns():
    secret = "my-custom-token-abcdef123456"
    text = f"failed with {secret} and sk-abcdefghijklmnopqrstuv and Bearer abcdefghijklmnopqrstuvwxyz"
    cleaned = redact(text, [secret])
    assert secret not in cleaned and "sk-abcdefghijkl" not in cleaned and "abcdefghijklmnopqrstuvwxyz" not in cleaned
    assert REDACTED in cleaned
    assert "x-api-key: " + REDACTED == redact("x-api-key: abc123", [])


def test_logging_filter_redacts(caplog):
    secret = "topsecretvalue12345"
    logger = logging.getLogger("redaction-test")
    handler = logging.StreamHandler()
    record_holder = []
    handler.emit = lambda record: record_holder.append(record.getMessage())  # type: ignore[assignment]
    handler.addFilter(RedactingFilter(lambda: [secret]))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    logger.info("calling with %s", secret)
    assert record_holder and secret not in record_holder[0]
