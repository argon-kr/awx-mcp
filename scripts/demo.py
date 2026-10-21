# SPDX-License-Identifier: Apache-2.0
"""Reproduce the README demo with real MCP reads against a local fake AWX.

Run: uv run python scripts/demo.py
GIF: uv run --with pillow==11.3.0 python scripts/demo.py --render

No real credentials are read. The child receives only explicit fixture settings.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
TOKEN = "demo-fixture-token-not-a-secret"
JOB = {"id": 42, "name": "Demo deploy", "status": "failed"}
STDOUT = (
    "PLAY [Demo deployment] ************************************************\n"
    "TASK [Check service] **************************************************\n"
    'fatal: [demo-host]: FAILED! => {"msg": "Synthetic health check failed"}\n'
    "PLAY RECAP ************************************************************\n"
    "demo-host : ok=1 changed=0 unreachable=0 failed=1\n"
)


class FakeAWX(BaseHTTPRequestHandler):
    """Serve only the two read endpoints used by the demonstration."""

    requests_seen: list[str] = []

    def log_message(self, format: str, *args: object) -> None:
        pass

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if self.headers.get("Authorization") != f"Bearer {TOKEN}":
            self.send_error(401)
            return
        self.requests_seen.append(parsed.path)
        if parsed.path == "/api/v2/jobs/":
            query = parse_qs(parsed.query)
            if query.get("status") != ["failed"] or query.get("page_size") != ["5"]:
                self.send_error(400, "Expected failed-job filter and limit")
                return
            payload = json.dumps(
                {"count": 1, "next": None, "previous": None, "results": [JOB]}
            ).encode()
            content_type = "application/json"
        elif parsed.path == "/api/v2/jobs/42/stdout/":
            if parse_qs(parsed.query).get("format") != ["txt"]:
                self.send_error(400, "Expected text stdout")
                return
            payload = STDOUT.encode()
            content_type = "text/plain"
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


async def run_demo(port: int) -> str:
    lines = [
        "$ uv run python scripts/demo.py",
        "LOCAL FIXTURE DEMO - synthetic AWX data, no LLM session",
        "Connection: MCP stdio -> awx-mcp -> fake AWX on 127.0.0.1",
        "Credentials: hard-coded fake demo token only. Read-only mode enabled.",
        "",
    ]
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "awx_mcp", "--stdio"],
        cwd=str(ROOT),
        env={
            "ANSIBLE_BASE_URL": f"http://127.0.0.1:{port}/",
            "ANSIBLE_TOKEN": TOKEN,
            "ANSIBLE_SSL_VERIFY": "true",
            "ANSIBLE_LOG_LEVEL": "ERROR",
            "AWX_MCP_READ_ONLY": "true",
        },
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            for name, arguments in [
                ("list_jobs", {"status": "failed", "limit": 5}),
                ("get_job_stdout", {"job_id": 42}),
            ]:
                lines.append(f"> MCP call_tool {name} {json.dumps(arguments)}")
                result = await session.call_tool(name, arguments)
                if result.is_error:
                    raise RuntimeError(f"Fixture tool call failed: {result.content}")
                data = json.loads(result.content[0].text)
                if name == "list_jobs":
                    assert data["results"] == [JOB] and data["returned"] == 1
                    lines.append(json.dumps(data, separators=(",", ":")))
                else:
                    assert data == {"status": "success", "stdout": STDOUT}
                    lines.append("Result: status=success, stdout:")
                    lines.extend(data["stdout"].splitlines())
                lines.append("")
    assert FakeAWX.requests_seen == ["/api/v2/jobs/", "/api/v2/jobs/42/stdout/"]
    lines.append("PASS: 2 actual MCP read calls, 2 fixture GETs, no write calls.")
    return "\n".join(lines) + "\n"


def render_gif(transcript: str) -> None:
    """Render the captured transcript deterministically without terminal tools."""
    from PIL import Image, ImageDraw, ImageFont

    font = None
    for candidate in [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "/System/Library/Fonts/Menlo.ttc",
    ]:
        if Path(candidate).is_file():
            font = ImageFont.truetype(candidate, 16)
            break
    if font is None:
        font = ImageFont.load_default(size=16)
    lines = transcript.splitlines()
    width = max(960, int(max(font.getlength(line) for line in lines)) + 48)
    height = 64 + len(lines) * 27
    frames = []
    for count in [5, 8, len(lines)]:
        frame = Image.new("RGB", (width, height), "#10151d")
        draw = ImageDraw.Draw(frame)
        draw.rectangle((0, 0, width, 38), fill="#243044")
        draw.text((20, 9), "awx-mcp | LOCAL FAKE AWX FIXTURE | read-only", font=font)
        for index, line in enumerate(lines[:count]):
            color = "#a1e8b4" if line.startswith((">", "PASS", "$")) else "#e1e8f2"
            draw.text((24, 52 + index * 27), line, fill=color, font=font)
        frames.append(frame)
    frames[0].save(
        ROOT / "docs/demo.gif",
        save_all=True,
        append_images=frames[1:],
        duration=[1800, 2500, 6500],
        loop=0,
        optimize=False,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--render", action="store_true", help="also render docs/demo.gif"
    )
    args = parser.parse_args()
    FakeAWX.requests_seen = []
    fixture = ThreadingHTTPServer(("127.0.0.1", 0), FakeAWX)
    worker = threading.Thread(target=fixture.serve_forever, daemon=True)
    worker.start()
    try:
        transcript = asyncio.run(run_demo(fixture.server_address[1]))
    finally:
        fixture.shutdown()
        fixture.server_close()
        worker.join(timeout=5)
    print(transcript, end="")
    (ROOT / "docs/demo.txt").write_text(transcript, encoding="utf-8")
    if args.render:
        with contextlib.suppress(ImportError):
            render_gif(transcript)
            return
        parser.error("GIF rendering requires: uv run --with pillow==11.3.0")


if __name__ == "__main__":
    main()
