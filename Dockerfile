# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS builder

# uv binary from the official distroless image, pinned to a stable release + the
# multi-arch index digest (covers both linux/amd64 and linux/arm64 manifests).
# To update: pick a new release from https://github.com/astral-sh/uv/releases,
# then resolve its index digest with:
#   docker buildx imagetools inspect ghcr.io/astral-sh/uv:<new-version>
# and paste the reported "Digest:" value below.
COPY --from=ghcr.io/astral-sh/uv:0.11.29@sha256:eb2843a1e56fd9e30c7276ce1a52cba86e64c7b385f5e3279a0e08e02dd058fc /uv /usr/local/bin/

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

# Cache locked dependencies separately from application source changes.
COPY pyproject.toml uv.lock /app/
RUN uv sync --frozen --no-dev --no-install-project
COPY awx_mcp /app/awx_mcp
COPY README.md LICENSE /app/
RUN uv sync --frozen --no-dev --no-editable --compile-bytecode

FROM python:3.12-slim AS runtime

ARG VERSION=24.6.1
LABEL org.opencontainers.image.source="https://github.com/lycorp-jp/awx-mcp" \
    org.opencontainers.image.licenses="Apache-2.0" \
    org.opencontainers.image.version="${VERSION}" \
    org.opencontainers.image.description="MCP server for AWX and Ansible Tower" \
    io.modelcontextprotocol.server.name="io.github.lycorp-jp/awx-mcp"

ENV PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    HOME=/app
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv

# Fixed uid/gid keeps file ownership reproducible. Runtime contains no uv or source tree.
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid 10001 --home-dir /app --no-create-home --shell /usr/sbin/nologin app \
    && chown -R app:app /app
USER 10001

EXPOSE 8000

# Liveness probe for the --serve HTTP endpoint: any HTTP response (including
# 400/406 from a GET with no session) counts as healthy — it proves the
# process is up and accepting connections; only a connection failure is
# unhealthy. curl isn't in this image, so probe with python3's urllib instead.
# NOTE: this HEALTHCHECK targets --serve on 127.0.0.1:8000/mcp. If you run this
# image with --stdio, use --no-healthcheck since stdio opens no HTTP listener.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python3", "-c", "import sys, urllib.request, urllib.error\ntry:\n    urllib.request.urlopen('http://127.0.0.1:8000/mcp', timeout=3)\nexcept urllib.error.HTTPError:\n    pass\nexcept Exception:\n    sys.exit(1)\n"]

# Central multi-user server (streamable-http, passthrough auth). Endpoint: /mcp
# The server holds no AWX credential — each request authenticates with the
# caller's own Bearer token. Override the CMD for --sse or a different host/port.
ENTRYPOINT ["awx-mcp"]
CMD ["--serve", "--host", "0.0.0.0", "--port", "8000"]
