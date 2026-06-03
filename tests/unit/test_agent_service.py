"""Unit tests for app/services/agent_service.py.

Tests cover:
- _sanitize_question: encoding-obfuscation stripping
- run_agent: early validation (empty src_path, empty question)
- _make_chat: HTTP retry logic using a real loopback server
"""
import asyncio
import http.server
import json
import threading
import urllib.error
from unittest.mock import patch

import pytest

from app.services.agent_service import (
    AgentConfig,
    _make_chat,
    _sanitize_question,
    run_agent,
)


# ── _sanitize_question ────────────────────────────────────────────────────────

def test_sanitize_strips_null_bytes():
    assert _sanitize_question("hello\x00world") == "helloworld"


def test_sanitize_strips_zero_width_space():
    assert _sanitize_question("hello​world") == "helloworld"


def test_sanitize_strips_zero_width_non_joiner():
    assert _sanitize_question("hello‌world") == "helloworld"


def test_sanitize_strips_zero_width_joiner():
    assert _sanitize_question("hello‍world") == "helloworld"


def test_sanitize_strips_bom():
    assert _sanitize_question("﻿hello") == "hello"


def test_sanitize_strips_surrounding_whitespace():
    assert _sanitize_question("  hello  ") == "hello"


def test_sanitize_preserves_normal_thai():
    text = "ราคา MSRP ของ NT-LT-001 คือเท่าไหร่"
    assert _sanitize_question(text) == text


def test_sanitize_empty_string_stays_empty():
    assert _sanitize_question("") == ""


def test_sanitize_only_zero_width_becomes_empty():
    assert _sanitize_question("\x00​‌") == ""


# ── run_agent validation ──────────────────────────────────────────────────────

def test_run_agent_raises_on_empty_src_path():
    config = AgentConfig(
        model_id="m",
        base_url="http://fake/v1",
        agent_src_path="",
        agent_db_path="/data/db",
    )
    with pytest.raises(ValueError, match="LLM_AGENT_SRC_PATH"):
        asyncio.run(run_agent("test question", config))


def test_run_agent_raises_on_empty_question_after_sanitize():
    config = AgentConfig(
        model_id="m",
        base_url="http://fake/v1",
        agent_src_path="/some/path",
        agent_db_path="/data/db",
    )
    with pytest.raises(ValueError, match="empty after sanitization"):
        asyncio.run(run_agent("\x00​", config))


# ── _make_chat HTTP retry logic ───────────────────────────────────────────────

def _json_ok_body(content: str = "42", completion_tokens: int = 5) -> bytes:
    return json.dumps({
        "choices": [{"message": {"content": content}}],
        "usage": {"completion_tokens": completion_tokens},
    }).encode()


class _FixedStatusHandler(http.server.BaseHTTPRequestHandler):
    """Always returns the status configured on `server.respond_status`."""

    def do_POST(self):
        self.server.hits += 1
        content_len = int(self.headers.get("Content-Length", 0))
        self.rfile.read(content_len)
        status = getattr(self.server, "respond_status", 200)
        if status == 200:
            body = _json_ok_body()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(status)
            self.send_header("Content-Length", "0")
            self.end_headers()

    def log_message(self, *_):
        pass


def _spin_server(respond_status: int = 200):
    server = http.server.HTTPServer(("127.0.0.1", 0), _FixedStatusHandler)
    server.hits = 0
    server.respond_status = respond_status
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    return server


def test_make_chat_success_on_first_attempt():
    server = _spin_server(200)
    port = server.server_address[1]
    try:
        config = AgentConfig(model_id="m", base_url=f"http://127.0.0.1:{port}/v1", timeout=5)
        token_counter = [0]
        result = _make_chat(config, token_counter)([{"role": "user", "content": "hello"}])
        assert result == "42"
        assert token_counter[0] == 5
        assert server.hits == 1
    finally:
        server.shutdown()


def test_make_chat_retries_on_502_then_succeeds():
    """First two requests return 502; third returns 200."""
    flip_count = 0

    class _FlipHandler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            nonlocal flip_count
            flip_count += 1
            content_len = int(self.headers.get("Content-Length", 0))
            self.rfile.read(content_len)
            if flip_count < 3:
                self.send_response(502)
                self.send_header("Content-Length", "0")
                self.end_headers()
            else:
                body = _json_ok_body("retried", 3)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        def log_message(self, *_):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), _FlipHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    port = server.server_address[1]
    try:
        config = AgentConfig(model_id="m", base_url=f"http://127.0.0.1:{port}/v1", timeout=5)
        token_counter = [0]
        with patch("app.services.agent_service.time.sleep"):
            result = _make_chat(config, token_counter)([{"role": "user", "content": "hi"}])
        assert result == "retried"
        assert token_counter[0] == 3
        assert flip_count == 3
    finally:
        server.shutdown()


def test_make_chat_raises_after_exhausting_retries():
    """All four attempts return 503; HTTPError raised after retries exhausted."""
    server = _spin_server(503)
    port = server.server_address[1]
    try:
        config = AgentConfig(model_id="m", base_url=f"http://127.0.0.1:{port}/v1", timeout=5)
        token_counter = [0]
        with patch("app.services.agent_service.time.sleep"):
            with pytest.raises(urllib.error.HTTPError) as exc_info:
                _make_chat(config, token_counter)([{"role": "user", "content": "hi"}])
        assert exc_info.value.code == 503
        assert server.hits == 4  # 1 initial + 3 retries
    finally:
        server.shutdown()
