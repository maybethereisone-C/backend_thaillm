from dataclasses import dataclass

from app.middleware import _key_prefix


@dataclass
class _Client:
    host: str


@dataclass
class _Request:
    headers: dict
    client: _Client | None = None


def req(headers: dict | None = None, host: str | None = "127.0.0.1") -> _Request:
    return _Request(
        headers=headers or {},
        client=_Client(host=host) if host else None,
    )


# ── x-api-key header ──────────────────────────────────────────────────────────

def test_returns_none_when_no_headers():
    assert _key_prefix(req()) is None


def test_returns_prefix_from_x_api_key():
    assert _key_prefix(req({"x-api-key": "abc12345xyz"})) == "abc12345..."


def test_truncates_key_to_8_chars():
    result = _key_prefix(req({"x-api-key": "verylongapikey"}))
    assert result == "verylong..."


def test_result_length_is_8_plus_ellipsis():
    result = _key_prefix(req({"x-api-key": "12345678abcdef"}))
    assert len(result) == 11  # 8 chars + "..."


def test_short_key_shows_all_chars_plus_ellipsis():
    assert _key_prefix(req({"x-api-key": "short"})) == "short..."


def test_single_char_key():
    assert _key_prefix(req({"x-api-key": "x"})) == "x..."


def test_exactly_8_char_key():
    assert _key_prefix(req({"x-api-key": "12345678"})) == "12345678..."


# ── Authorization: Bearer header ──────────────────────────────────────────────

def test_returns_prefix_from_bearer_authorization():
    assert _key_prefix(req({"authorization": "Bearer mytoken123"})) == "mytoken1..."


def test_bearer_check_is_case_insensitive_lowercase():
    assert _key_prefix(req({"authorization": "bearer mytoken123"})) == "mytoken1..."


def test_bearer_check_is_case_insensitive_mixed():
    assert _key_prefix(req({"authorization": "BEARER mytoken123"})) == "mytoken1..."


def test_basic_auth_returns_none():
    assert _key_prefix(req({"authorization": "Basic dXNlcjpwYXNz"})) is None


def test_bearer_without_space_returns_none():
    assert _key_prefix(req({"authorization": "Bearer"})) is None


def test_bearer_with_empty_token_returns_none():
    assert _key_prefix(req({"authorization": "Bearer "})) is None


def test_empty_authorization_header_returns_none():
    assert _key_prefix(req({"authorization": ""})) is None


def test_digest_auth_returns_none():
    assert _key_prefix(req({"authorization": "Digest realm=test"})) is None


# ── Priority: x-api-key wins over Authorization ───────────────────────────────

def test_x_api_key_preferred_over_authorization():
    result = _key_prefix(req({"x-api-key": "xkey1234", "authorization": "Bearer authtoken"}))
    assert result == "xkey1234..."


def test_empty_x_api_key_falls_through_to_bearer():
    result = _key_prefix(req({"x-api-key": "", "authorization": "Bearer mytoken1"}))
    assert result == "mytoken1..."


def test_empty_x_api_key_and_no_auth_returns_none():
    assert _key_prefix(req({"x-api-key": ""})) is None


# ── client presence does not affect key_prefix ────────────────────────────────

def test_no_client_does_not_affect_key_prefix():
    result = _key_prefix(req({"x-api-key": "abc12345"}, host=None))
    assert result == "abc12345..."


def test_key_prefix_none_regardless_of_client():
    assert _key_prefix(req({}, host=None)) is None
