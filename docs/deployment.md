# Deployment guide

[README](../README.md) | [English](deployment.md) | [한국어](deployment.ko.md) | [日本語](deployment.ja.md)

Use stdio for local clients and Streamable HTTP for new remote deployments. SSE is retained as a legacy compatibility transport (`--serve --sse`, `/sse`).

## Deployment modes

Local stdio supports either a personal API token or username/password. The central server accepts each caller’s personal token. The proxy forwards a personal token only.

### 1. Local (default)

Each user runs a local stdio server that talks to AWX with their own token.

```json
{
  "mcpServers": {
    "awx": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/lycorp-jp/awx-mcp", "awx-mcp"],
      "env": {
        "ANSIBLE_BASE_URL": "https://awx.example.com/",
        "ANSIBLE_TOKEN": "your_api_token"
      }
    }
  }
}
```

Set `AWX_MCP_USAGE_LOG_FILE` to also record your own tool calls locally.

### 2. Central server - admin (`--serve`)

An admin runs **one** shared server. It holds no AWX credential; each request is authenticated with the **caller's own token**, and every tool call is attributed to that caller in the usage log. TLS is strongly recommended because caller tokens travel in a request header.

```bash
export ANSIBLE_BASE_URL=https://awx.example.com/
export AWX_MCP_USAGE_LOG_FILE=/var/log/awx-mcp/usage.jsonl   # per-user attribution
export AWX_MCP_TLS_ENABLE=true
export AWX_MCP_TLS_CERT=/etc/awx-mcp/cert.pem
export AWX_MCP_TLS_KEY=/etc/awx-mcp/key.pem
uvx --from git+https://github.com/lycorp-jp/awx-mcp awx-mcp --serve --host 127.0.0.1 --port 8443        # add --sse for the sse transport
```

The command above binds to `127.0.0.1` and accepts connections only from the same host. For remote users, place a TLS reverse proxy on that host and forward each caller's `Authorization` header unchanged.

`ANSIBLE_TOKEN` / `ANSIBLE_USERNAME` / `ANSIBLE_PASSWORD` are ignored in `--serve` mode (a warning is logged if set) - the server has no identity of its own.

### 3. Central server - user (`--remote`)

Each user runs a stdio **proxy** that relays to the central server, injecting their own token as an `Authorization: Bearer` header. No local server is started; the central server must be running.

```json
{
  "mcpServers": {
    "awx": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/lycorp-jp/awx-mcp",
               "awx-mcp", "--remote", "https://awx-mcp.example.com:8443/mcp"],
      "env": { "ANSIBLE_TOKEN": "your_api_token" }
    }
  }
}
```

`ANSIBLE_BASE_URL` is not needed (the central server reaches AWX). Proxy mode is **personal-access-token only** - `ANSIBLE_USERNAME`/`PASSWORD` cannot be forwarded as a Bearer header. `ANSIBLE_SSL_VERIFY`/`ANSIBLE_CA_BUNDLE` here verify the connection to the **central server**, not to AWX. Set `AWX_MCP_USAGE_LOG_FILE` (and optionally `AWX_MCP_USAGE_USER`) to also keep a local usage log.

> MCP clients that support `${VAR}` expansion in a `headers` block may connect to the central server directly, without the proxy: `{ "type": "streamable-http", "url": "https://awx-mcp.example.com:8443/mcp", "headers": { "Authorization": "Bearer ${AWX_TOKEN}" } }`.

### Connecting to a central server

When an admin runs a central `awx-mcp --serve` instance, users connect in one of two ways. Both send the user's own AWX token; the recommended proxy path keeps the token in an env var and works with any MCP client.

**Proxy (recommended)** - a local stdio process; token stays in `ANSIBLE_TOKEN`:

```json
{
  "mcpServers": {
    "awx": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/lycorp-jp/awx-mcp",
               "awx-mcp", "--remote", "https://awx-mcp.example.com:8443/mcp"],
      "env": { "ANSIBLE_TOKEN": "your_api_token" }
    }
  }
}
```

**Direct HTTP** - for MCP clients that expand `${VAR}` in a `headers` block (no local process):

```json
{
  "mcpServers": {
    "awx": {
      "type": "streamable-http",
      "url": "https://awx-mcp.example.com:8443/mcp",
      "headers": { "Authorization": "Bearer ${AWX_TOKEN}" }
    }
  }
}
```

For the sse transport (`awx-mcp --serve --sse`), use `"type": "sse"` and the `/sse` endpoint.

> **Security (IMPORTANT):** In `--serve` mode each request is authenticated by the caller's own AWX token, and AWX RBAC applies per user. Because that token travels in a request header, protect the transport: enable in-process TLS (`AWX_MCP_TLS_ENABLE`) or front the server with an authenticating TLS reverse proxy, and restrict port access with a firewall. The server binds to `127.0.0.1` by default and logs a warning on a non-local bind without TLS.

## Read-only boundaries and replicas

Set `AWX_MCP_READ_ONLY=true` on the central server to remove write/destructive tools globally. A proxy-side setting sends `X-AWX-Read-Only` for that caller only. It is an advisory self-limit because a caller who controls their client can omit the header. Enforce authorization with AWX RBAC and server-side policy.

For multiple Streamable HTTP replicas behind round-robin load balancing, set `AWX_MCP_STATELESS_HTTP=true`. Otherwise, keep requests for a stateful MCP session on its original replica. Use a separate log path per process or pod. `TimedRotatingFileHandler` is not safe for concurrent rotation by multiple processes.

[TLS / logs](security.md)
