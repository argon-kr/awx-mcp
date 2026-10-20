# SPDX-License-Identifier: Apache-2.0
"""Logging failures and concurrent initialization must not affect tool results."""

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from awx_mcp import access_log, client, usage
from tests.conftest import set_test_settings


class BarrierLock:
    """Schedule both callers before either creates a cached value."""

    def __init__(self):
        self.barrier = threading.Barrier(2)
        self.lock = threading.Lock()

    def __enter__(self):
        self.barrier.wait(timeout=5)
        return self.lock.__enter__()

    def __exit__(self, *args):
        return self.lock.__exit__(*args)


@pytest.mark.parametrize(
    "module,attr,lock_name",
    [
        (usage, "_get_usage_logger", "_usage_logger_lock"),
        (access_log, "_get_access_logger", "_access_logger_lock"),
    ],
)
def test_concurrent_log_initialization_creates_one_sink(
    monkeypatch, tmp_path, module, attr, lock_name
):
    path = tmp_path / "concurrent.jsonl"
    set_test_settings(monkeypatch, usage_log_file=str(path), access_log_file=str(path))
    monkeypatch.setattr(module, lock_name, BarrierLock())
    with ThreadPoolExecutor(max_workers=2) as pool:
        sinks = list(pool.map(lambda _: getattr(module, attr)(), range(2)))
    # Restore a regular lock before the fixture's normal sink cleanup.
    monkeypatch.setattr(module, lock_name, threading.Lock())
    assert sinks[0] is sinks[1]
    assert len(sinks[0].handlers) == 1
    sinks[0].info("single-record")
    assert path.read_text().splitlines() == ["single-record"]


@pytest.mark.parametrize("auth_mode", ["static", "passthrough"])
def test_concurrent_identity_resolution_reuses_winning_cache(monkeypatch, auth_mode):
    set_test_settings(monkeypatch, auth_mode=auth_mode)
    monkeypatch.setattr(client, "get_request_token", lambda: "synthetic-caller-token")
    barrier = threading.Barrier(2)

    def lookup(**kwargs):
        barrier.wait(timeout=5)
        return "alice"

    monkeypatch.setattr(usage, "_lookup_me_username", lookup)
    with ThreadPoolExecutor(max_workers=2) as pool:
        values = list(pool.map(lambda _: usage.resolve_user_identifier(), range(2)))
    assert values == ["alice", "alice"]

    def unexpected_network(**kwargs):
        pytest.fail("Resolved identity should be cached")

    monkeypatch.setattr(usage, "_lookup_me_username", unexpected_network)
    assert usage.resolve_user_identifier() == "alice"


def test_log_file_chmod_failure_keeps_a_working_sink(monkeypatch, tmp_path):
    path = tmp_path / "usage.jsonl"

    def unavailable(*args):
        raise OSError("chmod unavailable")

    monkeypatch.setattr(usage.os, "chmod", unavailable)
    handler = usage.make_timed_rotating_handler(str(path))
    try:
        handler.emit(
            logging.LogRecord("fixture", logging.INFO, "", 0, "record", (), None)
        )
        assert path.read_text().strip() == "record"
    finally:
        handler.close()


def test_usage_log_compatibility_alias_tracks_reconfiguration(monkeypatch, tmp_path):
    path = str(tmp_path / "usage.jsonl")
    set_test_settings(monkeypatch, usage_log_file=path)
    assert usage.USAGE_LOG_FILE == path


@pytest.mark.parametrize("base_url", [None, "https://[invalid"])
def test_usage_payload_handles_unavailable_or_malformed_host(monkeypatch, base_url):
    # The normal Settings validator rejects malformed URLs. A defensive logger
    # must still survive an embedding that provides an invalid settings object.
    from types import SimpleNamespace

    monkeypatch.setattr(
        usage, "get_settings", lambda: SimpleNamespace(base_url=base_url)
    )
    assert usage._awx_host() == "unknown"


def test_redaction_bounds_depth_and_preserves_safe_list_values():
    cycle = {}
    cycle["again"] = cycle
    safe = usage._safe_params(
        {
            "values": [False, 0, {"api_key": "synthetic-secret", "name": "web"}],
            "cycle": cycle,
            "malformed": "{not-json token=synthetic-secret",
            "long": "x" * 600,
        }
    )
    assert safe["values"] == [False, 0, {"api_key": "***", "name": "web"}]
    assert "<max-depth>" in json.dumps(safe["cycle"])
    assert safe["malformed"] == "{not-json token=***"
    assert safe["long"] == "x" * 512 + "...(truncated)"
    assert "synthetic-secret" not in json.dumps(safe)


def test_unserializable_argument_is_safe_for_usage_logging():
    class BrokenString:
        def __str__(self):
            raise RuntimeError("cannot stringify")

    assert usage._safe_params({"value": BrokenString()}) == {
        "value": "<unserializable>"
    }


@pytest.mark.parametrize("record_kind", ["tool", "proxy", "internal", "access"])
def test_sink_failures_never_escape_to_callers(monkeypatch, caplog, record_kind):
    class BrokenSink:
        def info(self, message):
            raise OSError("token=synthetic-secret")

    monkeypatch.setattr(usage, "_get_usage_logger", lambda: BrokenSink())
    monkeypatch.setattr(access_log, "_get_access_logger", lambda: BrokenSink())
    caplog.set_level(logging.DEBUG)
    if record_kind == "tool":
        # Invoke the real decorator so any logging failure would break a tool.
        monkeypatch.setattr(usage, "_is_enabled", lambda: True)
        monkeypatch.setattr(usage, "resolve_user_identifier", lambda: "alice")

        @usage.instrument_tool
        def tool():
            return "successful-result"

        assert tool() == "successful-result"
    elif record_kind == "proxy":
        usage.record_proxy_tool_call(
            "get_job",
            time.monotonic(),
            True,
            None,
            user="alice",
            awx_host="central.test",
        )
    elif record_kind == "internal":
        usage._record_internal_api("me", "alice", True, 1, None)
    else:
        access_log._record({"type": "http"}, 200, time.monotonic())
    assert "recording failed: OSError" in caplog.text
    assert "synthetic-secret" not in caplog.text


def test_disabled_recorders_do_not_resolve_identity(monkeypatch):
    def unexpected_lookup():
        pytest.fail("Disabled logging must not query AWX")

    monkeypatch.setattr(usage, "resolve_user_identifier", unexpected_lookup)
    usage._record("get_job", time.monotonic(), True, None)
    usage._record_internal_api("me", "unknown", True, 1, None)
