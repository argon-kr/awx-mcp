# SPDX-License-Identifier: Apache-2.0

"""Endpoint/method/body tests for job execution tools that had no coverage:
stdout, events, host summaries, cancel and relaunch."""

import json
from unittest.mock import patch

import pytest

from awx_mcp.tools import jobs as jobs_mod
from tests.conftest import TOOL_ERRORS, fake_client_factory


def _call(fake_client, fn, *args, **kwargs):
    with patch.object(
        jobs_mod, "get_ansible_client", new=fake_client_factory(fake_client)
    ):
        return fn(*args, **kwargs)


@pytest.mark.parametrize("fmt", ["txt", "ansi", "html", "txt_download"])
def test_get_job_stdout_text_formats(fake_client, fmt):
    fake_client.request_text.return_value = "PLAY RECAP"
    out = _call(fake_client, jobs_mod.get_job_stdout, 7, format=fmt)
    fake_client.request_text.assert_called_once_with(
        "GET", "/api/v2/jobs/7/stdout/", params={"format": fmt}
    )
    assert json.loads(out) == {"status": "success", "stdout": "PLAY RECAP"}


def test_get_job_stdout_json_format(fake_client):
    fake_client.request.return_value = {"content": "x", "range": {}}
    out = _call(fake_client, jobs_mod.get_job_stdout, 7, format="json")
    assert fake_client.request.call_args.args == ("GET", "/api/v2/jobs/7/stdout/")
    assert fake_client.request.call_args.kwargs["params"] == {"format": "json"}
    assert json.loads(out)["content"] == "x"


def test_get_job_stdout_rejects_unknown_format(fake_client):
    with pytest.raises(TOOL_ERRORS, match="Invalid format"):
        _call(fake_client, jobs_mod.get_job_stdout, 7, format="pdf")
    fake_client.request.assert_not_called()
    fake_client.request_text.assert_not_called()


def test_cancel_job_posts_to_cancel_endpoint(fake_client):
    _call(fake_client, jobs_mod.cancel_job, 12)
    assert fake_client.request.call_args.args == ("POST", "/api/v2/jobs/12/cancel/")


def test_relaunch_job_posts_to_relaunch_endpoint(fake_client):
    _call(fake_client, jobs_mod.relaunch_job, 12)
    method, endpoint = fake_client.request.call_args.args[:2]
    assert (method, endpoint) == ("POST", "/api/v2/jobs/12/relaunch/")


def _paginated(rows):
    return {"count": len(rows), "next": None, "previous": None, "results": rows}


def test_get_job_events_paginates_the_events_endpoint(fake_client):
    fake_client.request.return_value = _paginated([{"id": 1, "event": "runner_on_ok"}])
    out = json.loads(_call(fake_client, jobs_mod.get_job_events, 5))
    assert fake_client.request.call_args.args == ("GET", "/api/v2/jobs/5/job_events/")
    assert out["results"][0]["event"] == "runner_on_ok"
    assert out["count"] == 1


def test_get_job_host_summaries_paginates_the_summaries_endpoint(fake_client):
    fake_client.request.return_value = _paginated(
        [{"host_name": "web1", "failed": False}]
    )
    out = json.loads(_call(fake_client, jobs_mod.get_job_host_summaries, 5))
    assert fake_client.request.call_args.args == (
        "GET",
        "/api/v2/jobs/5/job_host_summaries/",
    )
    assert out["results"][0]["host_name"] == "web1"
