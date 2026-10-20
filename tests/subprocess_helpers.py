# SPDX-License-Identifier: Apache-2.0
"""Keep isolated test environments while propagating coverage instrumentation."""

import os


def coverage_env(env: dict[str, str]) -> dict[str, str]:
    """Forward only coverage settings, never ambient application credentials."""
    instrumentation = {
        name: os.environ[name]
        for name in (
            "COVERAGE_PROCESS_CONFIG",
            "COVERAGE_PROCESS_START",
            "COVERAGE_FILE",
        )
        if name in os.environ
    }
    return {**instrumentation, **env}
