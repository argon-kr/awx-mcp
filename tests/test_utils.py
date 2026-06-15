# SPDX-License-Identifier: Apache-2.0

# pyright: reportAny=false, reportUnknownVariableType=false, reportUnknownMemberType=false, reportExplicitAny=false

import json
from collections.abc import Callable
from typing import Any

from awx_mcp import utils as utils_module

validate_json_str: Callable[[str, str], str | None] = utils_module.validate_json_str
parse_json_str: Callable[[str, str], tuple[Any, str | None]] = (
    utils_module.parse_json_str
)


def test_validate_json_str_returns_none_for_valid_object_array_string_number():
    assert validate_json_str('{"k": 1}', "payload") is None
    assert validate_json_str("[1, 2, 3]", "payload") is None
    assert validate_json_str('"hello"', "payload") is None
    assert validate_json_str("42", "payload") is None


def test_validate_json_str_returns_error_string_for_invalid_json_with_param_name():
    error = validate_json_str('{"k":', "extra_vars")

    assert isinstance(error, str)
    assert "extra_vars" in error


def test_validate_json_str_error_payload_shape_and_message_content():
    error = validate_json_str('{"k":', "survey_spec")
    assert error is not None
    payload = json.loads(error)

    assert payload["status"] == "error"
    assert "survey_spec" in payload["message"]


def test_parse_json_str_returns_parsed_data_and_none_error_for_valid_json():
    parsed_obj, error_obj = parse_json_str('{"k": 1}', "payload")
    parsed_arr, error_arr = parse_json_str("[1, 2, 3]", "payload")

    assert parsed_obj == {"k": 1}
    assert error_obj is None
    assert parsed_arr == [1, 2, 3]
    assert error_arr is None


def test_parse_json_str_returns_none_and_error_string_for_invalid_json():
    parsed, error = parse_json_str('{"k":', "inputs")

    assert parsed is None
    assert isinstance(error, str)
    assert "inputs" in error


def test_parse_json_str_returns_expected_python_types_for_dict_and_list():
    parsed_dict, _ = parse_json_str('{"a": 1}', "payload")
    parsed_list, _ = parse_json_str('["a", "b"]', "payload")

    assert isinstance(parsed_dict, dict)
    assert isinstance(parsed_list, list)
