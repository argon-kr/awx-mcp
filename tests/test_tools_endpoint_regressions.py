# SPDX-License-Identifier: Apache-2.0

"""Previously untested detail/action tools exercised through the real HTTP client.

The Phase 0 job stdout/cancel/relaunch/event tests remain in test_tools_jobs_exec.
These cases cover the other twelve endpoints, their bodies, and API failures.
"""

import json

import pytest
import responses
from responses import matchers

from awx_mcp.exceptions import AnsibleAuthError, AnsibleValidationError
from awx_mcp.tools import ad_hoc, instances, system, workflow_jobs

BASE = "https://test.example.com"

DETAIL_AND_ACTION_CASES = [
    (
        system.get_config,
        {},
        "GET",
        "/api/v2/config/",
        {"version": "24.6.1", "license_info": {"valid_key": True}},
    ),
    (
        system.get_dashboard_stats,
        {},
        "GET",
        "/api/v2/dashboard/",
        {"inventories": {"total": 2}, "jobs": {"total": 5, "failed": 0}},
    ),
    (
        instances.get_instance,
        {"instance_id": 17},
        "GET",
        "/api/v2/instances/17/",
        {"id": 17, "hostname": "awx-task-1", "capacity": 0, "enabled": False},
    ),
    (
        instances.get_instance_group,
        {"group_id": 18},
        "GET",
        "/api/v2/instance_groups/18/",
        {"id": 18, "name": "controlplane", "capacity": 480, "instances": 2},
    ),
    (
        ad_hoc.get_ad_hoc_command,
        {"command_id": 19},
        "GET",
        "/api/v2/ad_hoc_commands/19/",
        {"id": 19, "status": "running", "module_name": "ping", "failed": False},
    ),
    (
        system.get_system_job,
        {"job_id": 20},
        "GET",
        "/api/v2/system_jobs/20/",
        {"id": 20, "status": "successful", "extra_vars": '{"days":90}'},
    ),
    (
        system.get_system_job_template,
        {"template_id": 21},
        "GET",
        "/api/v2/system_job_templates/21/",
        {"id": 21, "name": "Cleanup Job Details", "job_type": "cleanup_jobs"},
    ),
    (
        workflow_jobs.get_workflow_approval_template,
        {"node_id": 22},
        "GET",
        "/api/v2/workflow_job_template_nodes/22/",
        {"id": 22, "identifier": "approval", "unified_job_template": 8},
    ),
    (
        workflow_jobs.cancel_workflow_job,
        {"job_id": 23},
        "POST",
        "/api/v2/workflow_jobs/23/cancel/",
        {"detail": "Cancellation requested."},
    ),
    (
        workflow_jobs.relaunch_workflow_job,
        {"job_id": 24},
        "POST",
        "/api/v2/workflow_jobs/24/relaunch/",
        {"id": 25, "workflow_job": 25, "status": "pending"},
    ),
    (
        ad_hoc.cancel_ad_hoc_command,
        {"command_id": 26},
        "POST",
        "/api/v2/ad_hoc_commands/26/cancel/",
        {"detail": "Cancellation requested."},
    ),
]

CASE_IDS = [case[0].__name__ for case in DETAIL_AND_ACTION_CASES]


@pytest.mark.parametrize(
    "tool,kwargs,method,path,payload", DETAIL_AND_ACTION_CASES, ids=CASE_IDS
)
@responses.activate
def test_detail_and_action_endpoint_preserves_response(
    tool, kwargs, method, path, payload
):
    responses.add(method, BASE + path, json=payload)

    assert json.loads(tool(**kwargs)) == payload
    request = responses.calls[0].request
    assert request.body is None
    assert request.url == BASE + path
    assert len(responses.calls) == 1


@pytest.mark.parametrize(
    "tool,kwargs,method,path,payload", DETAIL_AND_ACTION_CASES, ids=CASE_IDS
)
@responses.activate
def test_detail_and_action_endpoint_surfaces_permission_failure(
    tool, kwargs, method, path, payload
):
    responses.add(
        method, BASE + path, status=403, json={"detail": "Permission denied."}
    )

    with pytest.raises(AnsibleAuthError, match="403.*Permission denied"):
        tool(**kwargs)

    assert len(responses.calls) == 1


@pytest.mark.parametrize(
    "kwargs,body",
    [
        ({}, {}),
        ({"extra_vars": "{}"}, {"extra_vars": "{}"}),
        ({"extra_vars": '{"days":0}'}, {"extra_vars": '{"days":0}'}),
    ],
    ids=["omitted", "empty-object-string", "extra-vars-string"],
)
@responses.activate
def test_launch_system_job_preserves_optional_extra_vars_string(kwargs, body):
    responses.post(
        f"{BASE}/api/v2/system_job_templates/7/launch/",
        match=[matchers.json_params_matcher(body)],
        status=201,
        json={"id": 31, "system_job": 31, "status": "pending"},
    )

    assert json.loads(system.launch_system_job(template_id=7, **kwargs)) == {
        "id": 31,
        "system_job": 31,
        "status": "pending",
    }
    assert len(responses.calls) == 1


@responses.activate
def test_launch_system_job_rejects_invalid_extra_vars_before_http():
    with pytest.raises(ValueError, match="Invalid JSON in extra_vars"):
        system.launch_system_job(template_id=7, extra_vars="{invalid")
    assert len(responses.calls) == 0


@responses.activate
def test_launch_system_job_surfaces_awx_field_validation_failure():
    responses.post(
        f"{BASE}/api/v2/system_job_templates/7/launch/",
        match=[matchers.json_params_matcher({"extra_vars": '{"days":-1}'})],
        status=400,
        json={"extra_vars": ["days must be positive"]},
    )

    with pytest.raises(AnsibleValidationError, match="400.*days must be positive"):
        system.launch_system_job(template_id=7, extra_vars='{"days":-1}')
    assert len(responses.calls) == 1
