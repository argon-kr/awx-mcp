# SPDX-License-Identifier: Apache-2.0

"""Reusable resource helpers preserve the public tool response contracts."""

import json

import pytest
import responses
from responses import matchers

from awx_mcp.client import AnsibleClient
from awx_mcp.exceptions import AnsibleAuthError
from awx_mcp.tools import _helpers as helpers

BASE = "https://test.example.com"


def test_drop_none_preserves_explicit_false_zero_and_empty_values():
    fields = {
        "omitted": None,
        "enabled": False,
        "count": 0,
        "description": "",
        "hosts": [],
        "variables": {},
    }
    assert helpers.drop_none(**fields) == {
        "enabled": False,
        "count": 0,
        "description": "",
        "hosts": [],
        "variables": {},
    }
    assert "omitted" in fields


@responses.activate
def test_list_resource_preserves_filters_and_non_aligned_page_window():
    extra = {"order_by": "-name", "inventory": 0}
    responses.get(
        f"{BASE}/api/v2/hosts/",
        match=[
            matchers.query_param_matcher(
                {
                    "page_size": "2",
                    "page": "1",
                    "name__icontains": "web",
                    "order_by": "-name",
                    "inventory": "0",
                }
            )
        ],
        json={
            "count": 4,
            "next": f"{BASE}/api/v2/hosts/?page=2&page_size=2",
            "previous": None,
            "results": [{"id": 1}, {"id": 2}],
        },
    )
    responses.get(
        f"{BASE}/api/v2/hosts/",
        match=[matchers.query_param_matcher({"page": "2", "page_size": "2"})],
        json={
            "count": 4,
            "next": None,
            "previous": f"{BASE}/api/v2/hosts/?page=1&page_size=2",
            "results": [{"id": 3}, {"id": 4}],
        },
    )
    with AnsibleClient(BASE, token="test-token") as client:
        out = helpers.list_resource(
            client, "/api/v2/hosts/", limit=2, offset=1, name="  web  ", params=extra
        )

    assert json.loads(out) == {
        "count": 4,
        "returned": 2,
        "offset": 1,
        "results": [{"id": 2}, {"id": 3}],
    }
    assert extra == {"order_by": "-name", "inventory": 0}
    assert len(responses.calls) == 2


@pytest.mark.parametrize("name", [None, "", "   "])
@responses.activate
def test_list_resource_blank_name_omits_filter(name):
    responses.get(
        f"{BASE}/api/v2/groups/",
        match=[matchers.query_param_matcher({"page_size": "20"})],
        json={"count": 0, "next": None, "previous": None, "results": []},
    )
    with AnsibleClient(BASE, token="test-token") as client:
        out = helpers.list_resource(client, "/api/v2/groups/", name=name)
    assert json.loads(out) == {
        "count": 0,
        "returned": 0,
        "offset": 0,
        "results": [],
    }


@responses.activate
def test_list_resource_zero_limit_keeps_offset_without_http():
    with AnsibleClient(BASE, token="test-token") as client:
        out = helpers.list_resource(client, "/api/v2/hosts/", limit=0, offset=9)
    assert json.loads(out) == {
        "count": None,
        "returned": 0,
        "offset": 9,
        "results": [],
    }
    assert len(responses.calls) == 0


@responses.activate
def test_get_resource_returns_compact_unicode_json():
    responses.get(f"{BASE}/api/v2/hosts/7/", json={"id": 7, "name": "호스트"})
    with AnsibleClient(BASE, token="test-token") as client:
        out = helpers.get_resource(client, "/api/v2/hosts/7/")
    assert out == '{"id":7,"name":"호스트"}'


@responses.activate
def test_delete_resource_uses_delete_and_existing_success_message():
    responses.delete(f"{BASE}/api/v2/groups/7/", status=204)
    with AnsibleClient(BASE, token="test-token") as client:
        out = helpers.delete_resource(
            client, "/api/v2/groups/7/", message="Group 7 deleted"
        )
    assert json.loads(out) == {"status": "success", "message": "Group 7 deleted"}
    assert responses.calls[0].request.body is None


@pytest.mark.parametrize(
    "method,helper,kwargs",
    [
        ("GET", "list_resource", {}),
        ("GET", "get_resource", {}),
        ("DELETE", "delete_resource", {"message": "Group 7 deleted"}),
    ],
)
@responses.activate
def test_resource_helpers_propagate_permission_failure(method, helper, kwargs):
    responses.add(
        method, f"{BASE}/api/v2/groups/7/", status=403, json={"detail": "Denied"}
    )
    with AnsibleClient(BASE, token="test-token") as client:
        with pytest.raises(AnsibleAuthError, match="403"):
            getattr(helpers, helper)(client, "/api/v2/groups/7/", **kwargs)
