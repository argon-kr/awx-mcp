# SPDX-License-Identifier: Apache-2.0

"""HTTP-boundary regression proof for the incremental resource-helper migration."""

import json

import pytest
import responses
from responses import matchers

from awx_mcp.tools import groups, hosts

BASE = "https://test.example.com"


@pytest.mark.parametrize(
    "tool,kwargs,path,payload",
    [
        (
            hosts.update_host,
            {"host_id": 7, "name": "", "description": "", "enabled": False},
            "/api/v2/hosts/7/",
            {"name": "", "description": "", "enabled": False},
        ),
        (
            groups.update_group,
            {"group_id": 7, "name": "", "description": "", "variables": "{}"},
            "/api/v2/groups/7/",
            {"name": "", "description": "", "variables": "{}"},
        ),
    ],
)
@responses.activate
def test_partial_update_preserves_explicit_clears(tool, kwargs, path, payload):
    responses.patch(
        BASE + path,
        match=[matchers.json_params_matcher(payload)],
        json={"id": 7, **payload},
    )
    assert json.loads(tool(**kwargs)) == {"id": 7, **payload}
    assert len(responses.calls) == 1


@pytest.mark.parametrize(
    "tool,kwargs,path",
    [
        (
            hosts.list_hosts,
            {"inventory_id": 0, "hostname": "  web  "},
            "/api/v2/inventories/0/hosts/",
        ),
        (
            groups.list_groups,
            {"inventory_id": 0, "group_name": "  web  "},
            "/api/v2/inventories/0/groups/",
        ),
    ],
)
@responses.activate
def test_scoped_list_keeps_zero_id_and_trimmed_name_filter(tool, kwargs, path):
    responses.get(
        BASE + path,
        match=[
            matchers.query_param_matcher(
                {"page_size": "2", "page": "2", "name__icontains": "web"}
            )
        ],
        json={"count": 3, "next": None, "previous": None, "results": [{"id": 9}]},
    )
    assert json.loads(tool(**kwargs, limit=2, offset=2)) == {
        "count": 3,
        "returned": 1,
        "offset": 2,
        "results": [{"id": 9}],
    }
