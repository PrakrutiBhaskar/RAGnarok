"""Unit tests for SecretScrubber."""

import pytest
from backend.security.secret_scrubber import scrub, scrub_dict, scrub_error_message


class TestScrub:
    def test_scrubs_openai_key(self):
        text = "My key is sk-abc123XYZ789abcdef123456789012"
        result = scrub(text)
        assert "sk-" not in result
        assert "[REDACTED]" in result

    def test_scrubs_bearer_token(self):
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc"
        result = scrub(text)
        assert "eyJhbGci" not in result

    def test_scrubs_generic_api_key(self):
        text = "api_key=supersecretvalue123"
        result = scrub(text)
        assert "supersecretvalue123" not in result

    def test_clean_text_unchanged(self):
        text = "The quick brown fox jumps over the lazy dog."
        assert scrub(text) == text

    def test_scrub_dict_sensitive_keys(self):
        data = {"openai_api_key": "sk-secret", "name": "pipeline"}
        result = scrub_dict(data)
        assert result["openai_api_key"] == "[REDACTED]"
        assert result["name"] == "pipeline"

    def test_scrub_dict_nested(self):
        data = {"llm": {"api_key": "sk-secret123", "model": "gpt-4"}}
        result = scrub_dict(data)
        assert result["llm"]["api_key"] == "[REDACTED]"
        assert result["llm"]["model"] == "gpt-4"

    def test_scrub_dict_list_values(self):
        # Key must be at least 20 chars after sk- to match the pattern
        data = {"tokens": ["sk-abcdefghijklmnopqrstuvwxyz123456", "normal-value"]}
        result = scrub_dict(data)
        assert "sk-" not in result["tokens"][0]
        assert result["tokens"][1] == "normal-value"

    def test_scrub_error_message(self):
        try:
            raise ValueError("Invalid API key: sk-abc123secretkey9999999")
        except ValueError as e:
            result = scrub_error_message(e)
        assert "sk-" not in result
        assert "[REDACTED]" in result


class TestPickleDetector:
    def test_rejects_pickle_protocol2(self):
        from backend.security.pickle_detector import PickleDetectedError, check_bytes
        with pytest.raises(PickleDetectedError):
            check_bytes(b"\x80\x02" + b"some pickle data")

    def test_rejects_pickle_extension(self):
        from backend.security.pickle_detector import PickleDetectedError, check_file_path
        with pytest.raises(PickleDetectedError):
            check_file_path("/tmp/model.pkl")

    def test_accepts_json_bytes(self):
        from backend.security.pickle_detector import check_bytes
        check_bytes(b'{"key": "value"}')  # should not raise

    def test_accepts_yaml_extension(self):
        from backend.security.pickle_detector import check_file_path
        check_file_path("/tmp/config.yaml")  # should not raise


class TestPIIRedactor:
    def test_redacts_email(self):
        from backend.security.pii_redactor import redact
        result = redact("Contact us at user@example.com for help.")
        assert "user@example.com" not in result
        assert "[EMAIL]" in result

    def test_redacts_phone(self):
        from backend.security.pii_redactor import redact
        result = redact("Call me at 555-867-5309.")
        assert "555-867-5309" not in result
        assert "[PHONE]" in result

    def test_redacts_ssn(self):
        from backend.security.pii_redactor import redact
        result = redact("SSN: 123-45-6789")
        assert "123-45-6789" not in result
        assert "[SSN]" in result

    def test_clean_text_unchanged(self):
        from backend.security.pii_redactor import redact
        text = "The weather in Bengaluru is pleasant today."
        assert redact(text) == text

    def test_redact_chunks(self):
        from backend.security.pii_redactor import redact_chunks
        chunks = [{"chunk_id": "c1", "text": "Email: admin@corp.com"}]
        result = redact_chunks(chunks)
        assert "admin@corp.com" not in result[0]["text"]
        assert result[0]["chunk_id"] == "c1"  # unchanged
