# SPDX-License-Identifier: Apache-2.0

"""Wire-format contract for tool results.

Every tool returns a JSON string. Left to the SDK defaults, a ``-> str`` tool is
given an auto-generated ``{"result": string}`` outputSchema and the same JSON is
sent twice: once as the text content block and once, escaped, as
``structuredContent.result``. The registration decorators pass
``structured_output=False`` so each result is sent once, and ``to_json`` drops
pretty-printing whitespace that would otherwise be pure token cost.
"""

import json
from unittest.mock import patch

import anyio

from awx_mcp import server
from awx_mcp.tools import inventories as inventories_mod
from awx_mcp.utils import to_json
from tests.conftest import fake_client_factory


def test_no_tool_advertises_an_output_schema():
    tools = anyio.run(server.mcp.list_tools)
    assert tools
    with_schema = [t.name for t in tools if t.output_schema]
    assert with_schema == []


def test_call_result_has_text_only_no_structured_duplicate(fake_client):
    fake_client.request.return_value = {
        "count": 1,
        "next": None,
        "previous": None,
        "results": [{"id": 1, "name": "웹서버"}],
    }
    with patch.object(
        inventories_mod, "get_ansible_client", new=fake_client_factory(fake_client)
    ):
        result = anyio.run(server.mcp.call_tool, "list_inventories", {})

    assert result.structured_content is None
    assert len(result.content) == 1
    text = result.content[0].text
    assert json.loads(text)["results"][0]["name"] == "웹서버"
    # compact: no pretty-print newlines/indentation, non-ASCII kept readable
    assert "\n" not in text
    assert "웹서버" in text


def test_to_json_is_compact_and_unicode_preserving():
    assert to_json({"a": [1, 2], "b": "ü"}) == '{"a":[1,2],"b":"ü"}'
