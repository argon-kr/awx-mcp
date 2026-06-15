# Security Policy

## Reporting Vulnerabilities

Please report security vulnerabilities via GitHub Security Advisories:
<https://github.com/lycorp-jp/awx-mcp/security/advisories/new>

Do not open a public issue for security vulnerabilities.

## Threat Model

This server runs on the operator's host with a static AWX token supplied via
environment variable. The trust boundary sits between three components:

```
MCP client (LLM) <-> MCP server (this process) <-> AWX REST API
```

The server itself is trusted; the LLM is untrusted input. AWX enforces its
own RBAC on every API call using the configured token.

All 4 credential/user write tools (`create_credential`, `update_credential`,
`create_user`, `update_user`) are gated behind
`AWX_MCP_ENABLE_CREDENTIAL_MANAGEMENT=true` (default: off). The default
deployment registers 142 of 146 tools and exposes no tool that handles
sensitive data.

## Sensitive Data

When `AWX_MCP_ENABLE_CREDENTIAL_MANAGEMENT=true` is set, the 4 gated tools
collect sensitive inputs (passwords, credential fields) via **Form-mode
elicitation**.

Form-mode elicitation is not spec-compliant for sensitive data per the MCP
specification. Only URL-mode elicitation guarantees that sensitive data does
not transit through the LLM context, MCP client, or other intermediate
systems. Form mode does not provide this guarantee — sensitive responses may
still be exposed through client-side logging, transcript persistence, or
other intermediate systems.

This is the residual risk operators accept when enabling the flag. Use only
in trusted, isolated environments and document the acceptance in your
runbooks.

## Security Hardening History

Notable security-relevant changes, newest first. See the
[CHANGELOG](CHANGELOG.md) and
[release notes](https://github.com/lycorp-jp/awx-mcp/releases) for full detail.

- Corrected Form-mode elicitation security claims — clarified that Form mode is
  not spec-compliant for sensitive data.
- Gated the 4 credential/user write tools behind an opt-in env flag
  (`AWX_MCP_ENABLE_CREDENTIAL_MANAGEMENT=true`); they are not registered by default.
- Documented the residual risk of Form-mode elicitation for sensitive inputs and
  updated the threat model accordingly.
