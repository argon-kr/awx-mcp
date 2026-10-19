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

In central `--serve` mode (`streamable-http` or `sse`), tool and internal API usage records and HTTP access records are always emitted to stdout in JSON Lines format: https://jsonlines.org/. This includes tool-call arguments after redaction. `AWX_MCP_USAGE_LOG_FILE` and `AWX_MCP_ACCESS_LOG_FILE` optionally add rotated file sinks. Leaving these paths unset does not disable central stdout logging.

In local stdio and `--remote` proxy mode, stdout is reserved for MCP protocol messages. Usage file logging is opt-in through a writable `AWX_MCP_USAGE_LOG_FILE` path. Neither mode runs an inbound HTTP socket, so HTTP access logging does not apply. The server has no built-in remote log exporter, but external collectors such as Filebeat or Fluentd and container/platform logging can collect its configured files or stdout/stderr.

Every log line carries a `type` field so records can be split by kind: `"tool"` (regular MCP tool calls), `"internal_api"` (the `/api/v2/me/` user-resolution call the server makes, recorded with `tool: "me"` and the HTTP verb and path in separate `method`/`endpoint` fields), `"access"` (the HTTP access log), and `"diagnostic"` (the server diagnostic log). The `type` field, together with the shared `@timestamp` timestamp field, is consistent across all four record shapes so a single log index can be filtered by type. Tool-call records also include `params` - the call's arguments with secret-named keys (password, token, key, `inputs`, …) and inline `token=`/`password=`/`Bearer` values redacted.

The `auth_mode` field is `static` (local) or `passthrough` (`--serve`). The `transport` field is one of `stdio`, `streamable-http`, `sse`, or `proxy`. In the central server the `user` field is the AWX account behind each request's token (per-user attribution, resolved once per token and cached; the raw token and its hash are never logged). In the `--remote` proxy's own local log, `transport` is `proxy`, `user` is `AWX_MCP_USAGE_USER` (or `local`), and `awx_host` is the central server's host.

When using file logs, give each replica its own file path. Central usage/access JSONL continues on stdout whether or not file logging is configured. Diagnostic output is separate and uses stderr by default. Apply access and retention policies to configured files and to any container/platform collection of stdout/stderr.

## Sensitive data and log limits

Redaction masks recognized secret-named keys and common inline token/password patterns. It cannot guarantee removal of arbitrary secrets in inventory variables, free text, or job output. Treat logs and MCP results as potentially sensitive, restrict file access and retention, and review client-side logging. Enabling DEBUG can expose more response details.

Four credential/user write tools use Form-mode elicitation for sensitive data and remain opt-in. This is not compliant with the MCP restriction on sensitive Form-mode input. Enable only in a trusted, isolated local environment and never with `--serve`. See the disclosure policy and threat model in [SECURITY.md](../SECURITY.md).
