# SPDX-License-Identifier: Apache-2.0
"""HTTP contracts for previously unexercised operations and optional fields.

Use the real client and intercept HTTP, including credential/user mutations.
No request reaches an AWX instance. Literal bodies catch omitted, renamed or
incorrectly dropped false/zero/empty fields independently of tool internals.
"""

import asyncio
import json

import pytest
import responses
from responses import matchers

from awx_mcp.tools import (
    ad_hoc,
    credentials,
    execution_environments,
    instances,
    inventories,
    job_templates,
    jobs,
    projects,
    schedules,
    system,
    teams,
    users,
    workflow_jobs,
    workflow_templates,
)
from tests.conftest import FakeContext, _FakeElicitData, _FakeElicitResult

BASE = "https://test.example.com"

UPDATE_CASES = [
    (
        execution_environments.update_execution_environment,
        {"ee_id": 17},
        {
            "name": "runner",
            "image": "example/ee:1",
            "credential_id": 3,
            "description": "",
            "pull": "always",
        },
        "/api/v2/execution_environments/17/",
        {
            "name": "runner",
            "image": "example/ee:1",
            "credential": 3,
            "description": "",
            "pull": "always",
        },
    ),
    (
        inventories.update_inventory,
        {"inventory_id": 17},
        {"name": "hosts", "description": "", "variables": "{}"},
        "/api/v2/inventories/17/",
        {"name": "hosts", "description": "", "variables": "{}"},
    ),
    (
        inventories.update_inventory_source,
        {"source_id": 17},
        {
            "name": "source",
            "source": "scm",
            "source_path": "hosts.yml",
            "source_vars": "{}",
            "credential_id": 3,
            "overwrite": False,
            "overwrite_vars": False,
            "update_on_launch": False,
            "description": "",
        },
        "/api/v2/inventory_sources/17/",
        {
            "name": "source",
            "source": "scm",
            "source_path": "hosts.yml",
            "source_vars": "{}",
            "credential": 3,
            "overwrite": False,
            "overwrite_vars": False,
            "update_on_launch": False,
            "description": "",
        },
    ),
    (
        job_templates.update_job_template,
        {"template_id": 17},
        {
            "name": "deploy",
            "inventory_id": 2,
            "project_id": 3,
            "playbook": "deploy.yml",
            "description": "",
            "extra_vars": "{}",
            "job_type": "check",
            "verbosity": 0,
            "limit": "",
            "forks": 0,
            "become_enabled": False,
            "diff_mode": False,
            "allow_simultaneous": False,
            "timeout": 0,
        },
        "/api/v2/job_templates/17/",
        {
            "name": "deploy",
            "inventory": 2,
            "project": 3,
            "playbook": "deploy.yml",
            "description": "",
            "extra_vars": "{}",
            "job_type": "check",
            "verbosity": 0,
            "limit": "",
            "forks": 0,
            "become_enabled": False,
            "diff_mode": False,
            "allow_simultaneous": False,
            "timeout": 0,
        },
    ),
    (
        projects.update_project,
        {"project_id": 17},
        {
            "name": "project",
            "scm_type": "git",
            "scm_url": "https://git.test/p",
            "scm_branch": "main",
            "description": "",
        },
        "/api/v2/projects/17/",
        {
            "name": "project",
            "scm_type": "git",
            "scm_url": "https://git.test/p",
            "scm_branch": "main",
            "description": "",
        },
    ),
    (
        schedules.update_schedule,
        {"schedule_id": 17},
        {
            "name": "nightly",
            "rrule": "FREQ=DAILY",
            "description": "",
            "extra_data": '{"enabled":false}',
        },
        "/api/v2/schedules/17/",
        {
            "name": "nightly",
            "rrule": "FREQ=DAILY",
            "description": "",
            "extra_data": {"enabled": False},
        },
    ),
    (
        workflow_templates.update_workflow_template,
        {"template_id": 17},
        {
            "name": "workflow",
            "description": "",
            "extra_vars": "{}",
            "survey_enabled": False,
            "allow_simultaneous": False,
            "inventory": 2,
            "limit": "",
            "scm_branch": "main",
        },
        "/api/v2/workflow_job_templates/17/",
        {
            "name": "workflow",
            "description": "",
            "extra_vars": "{}",
            "survey_enabled": False,
            "allow_simultaneous": False,
            "inventory": 2,
            "limit": "",
            "scm_branch": "main",
        },
    ),
    (
        teams.update_team,
        {"team_id": 17},
        {"name": "ops", "description": ""},
        "/api/v2/teams/17/",
        {"name": "ops", "description": ""},
    ),
]


@pytest.mark.parametrize(
    "tool,ids,fields,path,body",
    UPDATE_CASES,
    ids=[case[0].__name__ for case in UPDATE_CASES],
)
@pytest.mark.parametrize("supply_fields", [False, True], ids=["omitted", "provided"])
@responses.activate
def test_updates_preserve_only_supplied_fields(
    tool, ids, fields, path, body, supply_fields
):
    responses.patch(
        BASE + path,
        json={"id": 17, "updated": True},
        match=[matchers.json_params_matcher(body if supply_fields else {})],
    )
    result = tool(**ids, **(fields if supply_fields else {}))
    assert json.loads(result) == {"id": 17, "updated": True}
    assert len(responses.calls) == 1


@pytest.mark.parametrize(
    "tool,path,kwargs,body",
    [
        (
            job_templates.launch_job,
            "/api/v2/job_templates/17/launch/",
            {
                "extra_vars": "{}",
                "inventory": 2,
                "credential": 3,
                "limit": "",
                "job_tags": "deploy",
                "skip_tags": "cleanup",
                "verbosity": 0,
                "scm_branch": "main",
                "diff_mode": False,
            },
            {
                "extra_vars": "{}",
                "inventory": 2,
                "credentials": [3],
                "limit": "",
                "job_tags": "deploy",
                "skip_tags": "cleanup",
                "verbosity": 0,
                "scm_branch": "main",
                "diff_mode": False,
            },
        ),
        (
            workflow_templates.launch_workflow,
            "/api/v2/workflow_job_templates/17/launch/",
            {"extra_vars": "{}", "inventory": 2, "limit": "", "scm_branch": "main"},
            {"extra_vars": "{}", "inventory": 2, "limit": "", "scm_branch": "main"},
        ),
    ],
)
@responses.activate
def test_launch_overrides_reach_awx(tool, path, kwargs, body):
    responses.post(
        BASE + path,
        json={"id": 18, "status": "pending"},
        match=[matchers.json_params_matcher(body)],
    )
    assert json.loads(tool(template_id=17, **kwargs)) == {"id": 18, "status": "pending"}
    assert len(responses.calls) == 1


@pytest.mark.parametrize("limit", ["", "web*"])
@responses.activate
def test_ad_hoc_command_builds_validated_request(limit):
    expected = {
        "inventory": 2,
        "credential": 3,
        "module_name": "ping",
        "module_args": "",
        "verbosity": 0,
    }
    if limit:
        expected["limit"] = "web*"
    responses.post(
        BASE + "/api/v2/ad_hoc_commands/",
        json={"id": 18},
        match=[matchers.json_params_matcher(expected)],
    )
    assert json.loads(ad_hoc.run_ad_hoc_command(2, 3, "ping", "", limit=limit)) == {
        "id": 18
    }
    assert len(responses.calls) == 1


@pytest.mark.parametrize("verbosity", [-1, 5])
@responses.activate
def test_ad_hoc_invalid_verbosity_never_sends_request(verbosity):
    with pytest.raises(ValueError, match="Verbosity"):
        ad_hoc.run_ad_hoc_command(2, 3, "ping", "", verbosity=verbosity)
    assert len(responses.calls) == 0


@pytest.mark.parametrize(
    "tool,kwargs,path",
    [
        (users.get_user, {"user_id": 17}, "/api/v2/users/17/"),
        (credentials.get_credential, {"credential_id": 17}, "/api/v2/credentials/17/"),
        (system.get_ansible_version, {}, "/api/v2/ping/"),
    ],
)
@responses.activate
def test_detail_tools_return_awx_payload(tool, kwargs, path):
    responses.get(BASE + path, json={"id": 17, "name": "fixture"})
    assert json.loads(tool(**kwargs)) == {"id": 17, "name": "fixture"}
    assert len(responses.calls) == 1


@pytest.mark.parametrize(
    "tool,kwargs,path",
    [
        (users.delete_user, {"user_id": 17}, "/api/v2/users/17/"),
        (
            credentials.delete_credential,
            {"credential_id": 17},
            "/api/v2/credentials/17/",
        ),
    ],
)
@responses.activate
def test_delete_tools_send_delete_and_report_success(tool, kwargs, path):
    responses.delete(BASE + path, status=204)
    assert json.loads(tool(**kwargs))["status"] == "success"
    assert len(responses.calls) == 1


@responses.activate
def test_copy_credential_sends_new_name():
    responses.post(
        BASE + "/api/v2/credentials/17/copy/",
        json={"id": 18},
        match=[matchers.json_params_matcher({"name": "copy"})],
    )
    assert json.loads(credentials.copy_credential(17, "copy")) == {"id": 18}


@pytest.mark.parametrize("update_password", [False, True])
@responses.activate
def test_update_user_sends_supplied_fields_and_elicited_password(update_password):
    body = {
        "username": "alice",
        "first_name": "",
        "last_name": "Lee",
        "email": "alice@example.test",
        "is_superuser": False,
        "is_system_auditor": False,
    }
    if update_password:
        body["password"] = "synthetic-password"
    responses.patch(
        BASE + "/api/v2/users/17/",
        json={"id": 17},
        match=[matchers.json_params_matcher(body)],
    )
    ctx = FakeContext(
        _FakeElicitResult("accept", _FakeElicitData(password="synthetic-password"))
    )
    result = asyncio.run(
        users.update_user(
            17,
            ctx,
            username="alice",
            first_name="",
            last_name="Lee",
            email="alice@example.test",
            is_superuser=False,
            is_system_auditor=False,
            update_password=update_password,
        )
    )
    assert json.loads(result) == {"id": 17}
    assert len(responses.calls) == 1


@pytest.mark.parametrize("update_inputs", [False, True])
@responses.activate
def test_update_credential_preserves_metadata_and_optional_elicited_inputs(
    update_inputs,
):
    body = {"name": "renamed", "description": ""}
    if update_inputs:
        body["inputs"] = {"password": "synthetic-password"}
    responses.patch(
        BASE + "/api/v2/credentials/17/",
        json={"id": 17},
        match=[matchers.json_params_matcher(body)],
    )
    ctx = FakeContext(
        _FakeElicitResult(
            "accept", _FakeElicitData(inputs='{"password":"synthetic-password"}')
        )
    )
    result = asyncio.run(
        credentials.update_credential(
            17, ctx, name="renamed", description="", update_inputs=update_inputs
        )
    )
    assert json.loads(result) == {"id": 17}
    assert len(responses.calls) == 1


@pytest.mark.parametrize("action", ["decline", "cancel"])
@responses.activate
def test_update_credential_declined_inputs_do_not_send_http(action):
    ctx = FakeContext(_FakeElicitResult(action))
    result = asyncio.run(credentials.update_credential(17, ctx, update_inputs=True))
    assert json.loads(result)["status"] == "cancelled"
    assert len(responses.calls) == 0


@responses.activate
def test_instance_topology_failure_keeps_empty_primary_results():
    responses.get(
        BASE + "/api/v2/instances/", json={"count": 0, "next": None, "results": []}
    )
    responses.get(BASE + "/api/v2/ping/", status=403, json={"detail": "denied"})
    assert json.loads(instances.list_instances()) == {
        "count": 0,
        "returned": 0,
        "offset": 0,
        "results": [],
    }
    assert len(responses.calls) == 2


@responses.activate
def test_list_jobs_applies_status_filter():
    responses.get(
        BASE + "/api/v2/jobs/",
        json={"count": 0, "next": None, "results": []},
        match=[
            matchers.query_param_matcher(
                {"status": "failed", "page_size": "20", "order_by": "-created"}
            )
        ],
    )
    assert json.loads(jobs.list_jobs(status="failed"))["results"] == []
    assert len(responses.calls) == 1


@responses.activate
def test_approval_templates_are_scoped_to_the_requested_workflow():
    responses.get(
        BASE + "/api/v2/workflow_job_templates/9/workflow_nodes/",
        json={
            "count": 1,
            "next": None,
            "results": [
                {
                    "id": 17,
                    "summary_fields": {
                        "unified_job_template": {
                            "type": "workflow_approval_template",
                            "id": 18,
                        }
                    },
                }
            ],
        },
    )
    result = json.loads(
        workflow_jobs.list_workflow_approval_templates(workflow_template_id=9, limit=1)
    )
    assert result["returned"] == 1
    assert len(responses.calls) == 1
