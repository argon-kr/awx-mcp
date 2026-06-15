# SPDX-License-Identifier: Apache-2.0

"""Tests for Lane 3: token lifecycle management.

Covers:
- threading.Lock around _cached_token mutations
- atexit DELETE token revocation (uses fresh requests.request, NOT self.session)
- 5s timeout, error swallowing, no-op when token_id is falsy
- Concurrent refresh serialization
"""

import os
import threading
from unittest.mock import MagicMock, patch

os.environ.setdefault("ANSIBLE_BASE_URL", "https://test.example.com/")
os.environ.setdefault("ANSIBLE_TOKEN", "test-token")

import awx_mcp.client as client_mod
from awx_mcp.client import _revoke_token_at_shutdown


def test_threading_lock_exists():
    assert isinstance(client_mod._token_cache_lock, type(threading.Lock()))


def test_revoke_noop_when_token_id_zero():
    with patch("awx_mcp.client.requests.request") as mock_req:
        _revoke_token_at_shutdown("https://x", "tk", 0)
        mock_req.assert_not_called()


def test_revoke_noop_when_token_id_none():
    with patch("awx_mcp.client.requests.request") as mock_req:
        _revoke_token_at_shutdown("https://x", "tk", None)  # type: ignore[arg-type]
        mock_req.assert_not_called()


def test_revoke_uses_fresh_request_with_5s_timeout():
    """R2: must use requests.request, not Session, with 5s timeout."""
    with patch("awx_mcp.client.requests.request") as mock_req:
        mock_req.return_value = MagicMock(status_code=204)
        _revoke_token_at_shutdown("https://x.example.com/", "tk", 42)
        mock_req.assert_called_once()
        args = mock_req.call_args.args
        kwargs = mock_req.call_args.kwargs
        assert args == ("DELETE", "https://x.example.com/api/v2/tokens/42/")
        assert kwargs["timeout"] == 5
        assert kwargs["headers"]["Authorization"] == "Bearer tk"


def test_revoke_swallows_errors():
    """Best-effort cleanup must not raise even on failure."""
    with patch("awx_mcp.client.requests.request", side_effect=Exception("boom")):
        # should not raise
        _revoke_token_at_shutdown("https://x", "tk", 7)


def test_atexit_drain_iterates_registered_targets():
    saved = list(client_mod._atexit_revoke_targets)
    try:
        client_mod._atexit_revoke_targets.clear()
        client_mod._atexit_revoke_targets.append(("https://a", "tA", 1))
        client_mod._atexit_revoke_targets.append(("https://b", "tB", 2))
        with patch("awx_mcp.client.requests.request") as mock_req:
            mock_req.return_value = MagicMock(status_code=204)
            client_mod._atexit_drain()
            assert mock_req.call_count == 2
    finally:
        client_mod._atexit_revoke_targets[:] = saved


def test_atexit_drain_callable():
    assert callable(client_mod._atexit_drain)


def test_concurrent_lock_acquire_release_no_deadlock():
    """5 threads call _token_cache_lock.acquire/release; assert no deadlock."""
    counter = {"ok": 0}
    barrier = threading.Barrier(5)

    def worker():
        barrier.wait()
        with client_mod._token_cache_lock:
            counter["ok"] += 1

    threads = [threading.Thread(target=worker) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
    assert counter["ok"] == 5
