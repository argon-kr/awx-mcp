# TLS, logging, and data handling

[README](../README.md) | [English](security.md) | [한국어](security.ko.md) | [日本語](security.ja.md)

## TLS / certificate verification

TLS certificate verification is **on by default** (`ANSIBLE_SSL_VERIFY=true`). If your AWX instance uses a certificate issued by a private/internal CA (or a self-signed certificate), set `ANSIBLE_CA_BUNDLE` to the path of the CA bundle (PEM) - this lets the server trust it while keeping verification enabled, which is the recommended approach over disabling verification.

Setting `ANSIBLE_SSL_VERIFY=false` disables verification entirely; the server logs a warning whenever this is used, and it should only be done in development environments. A bare `ANSIBLE_BASE_URL` host with no scheme is automatically upgraded to `https://`; an explicit `http://` URL is honored but the server logs a warning since the API token would be sent unencrypted.

## Serving over HTTPS (inbound TLS)

This is **inbound** TLS - encrypting the connection from MCP clients to this server - which is a different direction from the outbound AWX certificate verification controlled by `ANSIBLE_SSL_VERIFY`. Don't confuse the two.

It only applies to the `--serve` central server (streamable-http or sse). Local stdio mode has no network socket - it's a local pipe between the MCP client and this process - so TLS doesn't apply there; security instead comes from process/host isolation.

To enable, set `AWX_MCP_TLS_ENABLE=true` along with `AWX_MCP_TLS_CERT` and `AWX_MCP_TLS_KEY` (and `AWX_MCP_TLS_KEY_PASSWORD` if the key is encrypted):

```bash
export AWX_MCP_TLS_ENABLE=true
export AWX_MCP_TLS_CERT=/path/to/server.crt
export AWX_MCP_TLS_KEY=/path/to/server.key
uvx --from git+https://github.com/lycorp-jp/awx-mcp awx-mcp --serve --host 127.0.0.1 --port 8443
```

**Important:** In `--serve` mode each request *is* authenticated - by the caller's own AWX token in the `Authorization` header - and TLS protects that token in transit, so enabling TLS (or fronting the server with an authenticating TLS reverse proxy) is important, not optional, for any network-exposed deployment. A non-local bind without TLS logs a warning at startup. In Kubernetes, terminating TLS at the ingress is the usual approach; in-process TLS here is only needed when you require end-to-end encryption all the way to the pod.

## Verbose usage logging

Usage logging is opt-in: set `AWX_MCP_USAGE_LOG_FILE` to a writable path to start recording one JSON document per tool call in JSON Lines: https://jsonlines.org/ format, designed to be picked up by external log collectors (Filebeat, Fluentd, etc.) for later collection and statistics. Logs are never written to stdout - the MCP stdio transport uses stdout for protocol messages, so writing logs there would corrupt the protocol stream. No log data is sent over the network by the server itself; it only writes to the local file(s) you configure.

Every log line carries a `type` field so records can be split by kind: `"tool"` (regular MCP tool calls), `"internal_api"` (the `/api/v2/me/` user-resolution call the server makes, recorded with `tool: "me"` and the HTTP verb and path in separate `method`/`endpoint` fields), `"access"` (the HTTP access log), and `"diagnostic"` (the server diagnostic log). The `type` field, together with the shared `@timestamp` timestamp field, is consistent across all four record shapes so a single log index can be filtered by type. Tool-call records also include `params` - the call's arguments with secret-named keys (password, token, key, `inputs`, …) and inline `token=`/`password=`/`Bearer` values redacted.

The `auth_mode` field is `static` (local) or `passthrough` (`--serve`). The `transport` field is one of `stdio`, `streamable-http`, `sse`, or `proxy`. In the central server the `user` field is the AWX account behind each request's token (per-user attribution, resolved once per token and cached; the raw token and its hash are never logged). In the `--remote` proxy's own local log, `transport` is `proxy`, `user` is `AWX_MCP_USAGE_USER` (or `local`), and `awx_host` is the central server's host.

Give each replica its own file path. If usage/access file logging is disabled, those records are not emitted elsewhere. Only diagnostic output continues on stderr, which your platform can collect.

## Sensitive data and log limits

Redaction masks recognized secret-named keys and common inline token/password patterns. It cannot guarantee removal of arbitrary secrets in inventory variables, free text, or job output. Treat logs and MCP results as potentially sensitive, restrict file access and retention, and review client-side logging. Enabling DEBUG can expose more response details.

Four credential/user write tools use Form-mode elicitation for sensitive data and remain opt-in. This is not compliant with the MCP restriction on sensitive Form-mode input. Enable only in a trusted, isolated local environment and never with `--serve`. See the disclosure policy and threat model in [SECURITY.md](../SECURITY.md).
