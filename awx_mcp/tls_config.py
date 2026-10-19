# SPDX-License-Identifier: Apache-2.0

"""Shared, dependency-free configuration helpers.

This module holds configuration that both the full server (``server.py``) and
the lightweight client proxy (``proxy.py``) need, without either importing the
other. It imports only the standard library, so proxy mode can resolve outbound
TLS settings without importing ``server`` (which requires ``ANSIBLE_BASE_URL``
and would crash a proxy user who legitimately has none).
"""

from __future__ import annotations

import logging
import os

from .utils import truthy


def resolve_ssl_verify(logger: logging.Logger, target_url: str | None) -> bool | str:
    """Resolve the requests/httpx ``verify=`` value from the environment.

    Reads ``ANSIBLE_SSL_VERIFY`` (default on) and ``ANSIBLE_CA_BUNDLE``:

    * ``False``  -> verification disabled (insecure; a warning is logged, naming
      ``target_url`` so the message is meaningful in both server mode — where
      the target is AWX — and proxy mode — where it is the central awx-mcp).
    * ``<path>`` -> custom CA bundle (must exist, else ``ValueError``).
    * ``True``   -> system trust store (default).
    """
    enabled = truthy(os.environ.get("ANSIBLE_SSL_VERIFY", "true"))
    ca_bundle = os.environ.get("ANSIBLE_CA_BUNDLE") or None

    if not enabled:
        logger.warning(
            "TLS certificate verification is DISABLED (ANSIBLE_SSL_VERIFY=false). "
            "Connections to %s are vulnerable to man-in-the-middle attacks. Enable "
            "verification (and set ANSIBLE_CA_BUNDLE for a private CA) in production.",
            target_url or "the target",
        )
        return False
    if ca_bundle:
        if not os.path.isfile(ca_bundle):
            raise ValueError(
                f"ANSIBLE_CA_BUNDLE points to a file that does not exist: {ca_bundle}"
            )
        return ca_bundle
    return True
