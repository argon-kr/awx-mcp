# SPDX-License-Identifier: Apache-2.0

import json


def validate_json_str(value: str, param_name: str) -> str | None:
    """Validate a JSON string parameter.

    Returns MCP error response if invalid, None if valid.
    """
    try:
        json.loads(value)
        return None
    except json.JSONDecodeError:
        return json.dumps(
            {"status": "error", "message": f"Invalid JSON in {param_name}"}
        )


def parse_json_str(value: str, param_name: str) -> tuple:
    """Parse a JSON string.

    Returns (parsed_data, None) on success, (None, error_response) on failure.
    """
    try:
        return json.loads(value), None
    except json.JSONDecodeError:
        return None, json.dumps(
            {"status": "error", "message": f"Invalid JSON in {param_name}"}
        )
