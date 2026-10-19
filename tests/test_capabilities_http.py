# SPDX-License-Identifier: Apache-2.0

"""Local, central and proxy capability parity against a localhost fake AWX."""

import http.server
import json
import os
import subprocess
import sys
import threading

import anyio
import httpx2
import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamable_http_client
from mcp.shared.exceptions import MCPError

from tests.test_integration_passthrough import HOST, REPO, _free_port, _stop, _wait_port


@pytest.fixture(scope="module")
def central_fixture():
    captured = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            captured.append((self.path, self.headers.get("Authorization")))
            status = 403 if self.path == "/api/v2/jobs/403/" else 200
            if status == 403:
                body = json.dumps({"detail": "Fixture permission denied"}).encode()
            else:
                body = json.dumps({"id": 42, "name": "fixture"}).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    fake = http.server.ThreadingHTTPServer((HOST, 0), Handler)
    thread = threading.Thread(target=fake.serve_forever, daemon=True)
    thread.start()
    awx_url = f"http://{HOST}:{fake.server_port}"
    central_port = _free_port()
    env = {
        "PATH": os.environ["PATH"],
        "ANSIBLE_BASE_URL": awx_url,
        "ANSIBLE_TOKEN": "SERVER-MUST-NOT-LEAK",
        "AWX_MCP_READ_ONLY": "true",
    }
    central = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "awx_mcp",
            "--serve",
            "--host",
            HOST,
            "--port",
            str(central_port),
        ],
        cwd=REPO,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_port(central_port)
        yield f"http://{HOST}:{central_port}/mcp", awx_url, captured
    finally:
        _stop(central)
        fake.shutdown()
        fake.server_close()
        thread.join(timeout=5)


def test_central_resources_use_each_requests_token_and_never_static_fallback(
    central_fixture,
):
    central_url, _, captured = central_fixture
    captured.clear()

    async def run():
        async with httpx2.AsyncClient(
            headers={"Authorization": "Bearer CALLER-A"}
        ) as client:
            async with streamable_http_client(central_url, http_client=client) as io:
                async with ClientSession(*io) as session:
                    await session.initialize()
                    first = await session.read_resource("awx://jobs/42")
                    assert json.loads(first.contents[0].text)["id"] == 42
                    client.headers["Authorization"] = "Bearer CALLER-B"
                    second = await session.read_resource("awx://inventories/42")
                    assert json.loads(second.contents[0].text)["name"] == "fixture"
                    del client.headers["Authorization"]
                    with pytest.raises(MCPError, match="token is required"):
                        await session.read_resource("awx://projects/42")
                    # Rendering needs no token and causes no AWX requests.
                    prompt = await session.get_prompt(
                        "failed_job_triage", {"job_id": "42"}
                    )
                    assert "job_id=42" in prompt.messages[0].content.text
                    client.headers["Authorization"] = "Bearer CALLER-C"
                    with pytest.raises(MCPError, match="Fixture permission denied"):
                        await session.read_resource("awx://jobs/403")

    anyio.run(run)
    assert captured == [
        ("/api/v2/jobs/42/", "Bearer CALLER-A"),
        ("/api/v2/inventories/42/", "Bearer CALLER-B"),
        ("/api/v2/jobs/403/", "Bearer CALLER-C"),
    ]


@pytest.mark.parametrize("mode", ["local", "proxy"])
def test_stdio_capability_parity_and_authenticated_resource_read(central_fixture, mode):
    central_url, awx_url, captured = central_fixture
    captured.clear()
    env = {"PATH": os.environ["PATH"], "ANSIBLE_TOKEN": "STDIO-CALLER"}
    args = ["-m", "awx_mcp"]
    if mode == "local":
        env["ANSIBLE_BASE_URL"] = awx_url
        args.extend(["--stdio", "--read-only"])
    else:
        args.extend(["--remote", central_url])
    params = StdioServerParameters(command=sys.executable, args=args, env=env, cwd=REPO)

    async def run():
        async with stdio_client(params) as io:
            async with ClientSession(*io) as session:
                initialized = await session.initialize()
                assert initialized.capabilities.resources is not None
                assert initialized.capabilities.prompts is not None
                assert (await session.list_resources()).resources == []
                assert (
                    len((await session.list_resource_templates()).resource_templates)
                    == 5
                )
                assert len((await session.list_prompts()).prompts) == 3
                result = await session.read_resource("awx://jobs/42")
                assert json.loads(result.contents[0].text)["id"] == 42
                assert result.contents[0].mime_type == "application/json"
                prompt = await session.get_prompt("failed_job_triage", {"job_id": "42"})
                assert "get_job(job_id=42)" in prompt.messages[0].content.text
                with pytest.raises(MCPError, match="integer"):
                    await session.read_resource("awx://jobs/invalid")
                with pytest.raises(MCPError, match="Fixture permission denied"):
                    await session.read_resource("awx://jobs/403")

    anyio.run(run)
    assert captured == [
        ("/api/v2/jobs/42/", "Bearer STDIO-CALLER"),
        ("/api/v2/jobs/403/", "Bearer STDIO-CALLER"),
    ]
