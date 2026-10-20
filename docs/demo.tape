# README demo reproduction recipe
# This is a documented fallback recipe, not a vhs recording.
# vhs was unavailable when the GIF was created.
#
# From the repository root, capture real MCP read calls:
#   uv run python scripts/demo.py
#
# Capture again and generate the deterministic terminal-style GIF:
#   uv run --with pillow==11.3.0 python scripts/demo.py --render
#
# Outputs: docs/demo.txt and docs/demo.gif
# Python environment/dependencies: uv sync --frozen
# Renderer dependency: Pillow 11.3.0 (in a temporary uv environment)
# Font: DejaVu Sans Mono on Linux, Menlo on macOS, Pillow default fallback.
# No unpinned executable download and no screen recording are required.
# Font differences across platforms may change glyph pixels, not the transcript.
#
# Scenario: list failed jobs, then retrieve job 42 stdout.
# The script launches the real awx-mcp server over MCP stdio and a local
# ThreadingHTTPServer fixture bound to 127.0.0.1 on an ephemeral port.
# The fixture accepts only the fake token and the two expected GET endpoints.
# It validates query parameters and the runner checks the returned tool data.
# The child receives only explicit fixture connection settings and a fake token.
# It never reads .env, ~/.projectenv, or real AWX credentials.
# There is no LLM call, real AWX access, job launch, or write tool call.
# The fixed synthetic data makes the transcript stable across runs.
