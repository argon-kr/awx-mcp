# 배포 안내

[README](../README.ko.md) | [English](deployment.md) | [한국어](deployment.ko.md) | [日本語](deployment.ja.md)

로컬 클라이언트에는 stdio를, 새 원격 배포에는 Streamable HTTP를 권장합니다. SSE는 기존 클라이언트의 호환성을 위한 legacy transport로 유지합니다(`--serve --sse`, `/sse`).

## 배포 모드

로컬 stdio는 개인 API 토큰 또는 사용자명/비밀번호를 지원합니다. 중앙 서버는 호출자마다 개인 토큰을 받으며, 프록시도 개인 토큰만 전달합니다.

### 1. 로컬 (기본값)

각 사용자가 자신의 토큰으로 AWX와 통신하는 로컬 stdio 서버를 실행합니다.

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

`AWX_MCP_USAGE_LOG_FILE`을 설정하면 자신의 도구 호출도 로컬에 기록할 수 있습니다.

### 2. 중앙 서버 - 관리자 (`--serve`)

관리자가 **하나**의 공유 서버를 실행합니다. 이 서버는 AWX 자격 증명을 갖지 않으며, 각 요청은 **호출자 본인의 토큰**으로 인증되고, 모든 도구 호출은 사용 로그에서 해당 호출자에게 귀속됩니다. 호출자 토큰이 요청 헤더로 전달되므로 TLS를 강력히 권장합니다.

```bash
export ANSIBLE_BASE_URL=https://awx.example.com/
export AWX_MCP_USAGE_LOG_FILE=/var/log/awx-mcp/usage.jsonl   # 사용자별 귀속
export AWX_MCP_TLS_ENABLE=true
export AWX_MCP_TLS_CERT=/etc/awx-mcp/cert.pem
export AWX_MCP_TLS_KEY=/etc/awx-mcp/key.pem
uvx --from git+https://github.com/lycorp-jp/awx-mcp awx-mcp --serve --host 127.0.0.1 --port 8443        # sse 트랜스포트를 쓰려면 --sse 추가
```

위 명령은 같은 호스트에서만 접속할 수 있도록 `127.0.0.1`에 bind합니다. 원격 사용자가 접속하려면 같은 호스트에 TLS reverse proxy를 두고 각 호출자의 `Authorization` 헤더를 그대로 전달하세요.

`ANSIBLE_TOKEN` / `ANSIBLE_USERNAME` / `ANSIBLE_PASSWORD`는 `--serve` 모드에서 무시됩니다(설정되어 있으면 경고가 로깅됩니다) - 서버 자체는 아무런 정체성을 갖지 않습니다.

### 3. 중앙 서버 - 사용자 (`--remote`)

각 사용자는 중앙 서버로 요청을 중계하는 stdio **프록시**를 실행하며, 자신의 토큰을 `Authorization: Bearer` 헤더로 주입합니다. 로컬 서버는 시작되지 않으며, 중앙 서버가 반드시 실행 중이어야 합니다.

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

`ANSIBLE_BASE_URL`은 필요하지 않습니다(중앙 서버가 AWX에 접근합니다). 프록시 모드는 **개인 액세스 토큰 전용**입니다 - `ANSIBLE_USERNAME`/`PASSWORD`는 Bearer 헤더로 전달할 수 없습니다. 여기서 `ANSIBLE_SSL_VERIFY`/`ANSIBLE_CA_BUNDLE`은 AWX가 아니라 **중앙 서버**와의 연결을 검증합니다. `AWX_MCP_USAGE_LOG_FILE`(과 선택적으로 `AWX_MCP_USAGE_USER`)을 설정하면 로컬 사용 로그도 남길 수 있습니다.

> `headers` 블록에서 `${VAR}` 확장을 지원하는 MCP 클라이언트는 프록시 없이 중앙 서버에 직접 연결할 수 있습니다: `{ "type": "streamable-http", "url": "https://awx-mcp.example.com:8443/mcp", "headers": { "Authorization": "Bearer ${AWX_TOKEN}" } }`.

### 중앙 서버 접속

관리자가 중앙 `awx-mcp --serve` 인스턴스를 실행하면, 사용자는 두 가지 방법 중 하나로 접속합니다. 둘 다 사용자 본인의 AWX 토큰을 전송하며, 권장되는 프록시 방식은 토큰을 환경변수에 보관한 채 어떤 MCP 클라이언트에서도 동작합니다.

**프록시 (권장)** - 로컬 stdio 프로세스이며 토큰은 `ANSIBLE_TOKEN`에 유지됩니다:

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

**직접 HTTP 연결** - `headers` 블록에서 `${VAR}` 확장을 지원하는 MCP 클라이언트용(로컬 프로세스 없음):

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

sse 트랜스포트(`awx-mcp --serve --sse`)의 경우 `"type": "sse"`와 `/sse` 엔드포인트를 사용하세요.

> **보안 (중요):** `--serve` 모드에서는 각 요청이 호출자 본인의 AWX 토큰으로 인증되며, AWX RBAC이 사용자별로 적용됩니다. 그 토큰이 요청 헤더로 전달되므로 전송 구간을 보호해야 합니다: 프로세스 내 TLS(`AWX_MCP_TLS_ENABLE`)를 활성화하거나 인증 기능을 갖춘 TLS 리버스 프록시로 서버 앞단을 감싸고, 방화벽으로 포트 접근을 제한하세요. 서버는 기본적으로 `127.0.0.1`에 바인드되며, TLS 없이 비로컬 주소에 바인드하면 경고를 로깅합니다.

## 읽기 전용 경계와 replica 구성

중앙 서버에 `AWX_MCP_READ_ONLY=true`를 설정하면 쓰기/파괴적 도구를 전역적으로 제거합니다. 프록시의 설정은 `X-AWX-Read-Only`를 전달하여 해당 호출자만 제한합니다. 클라이언트를 제어하는 호출자가 헤더를 생략할 수 있으므로 프록시 설정은 자발적인 제한입니다. 접근 권한은 AWX RBAC와 서버 측 정책으로 강제하세요.

여러 Streamable HTTP replica를 round-robin load balancer 뒤에서 운영하려면 `AWX_MCP_STATELESS_HTTP=true`를 설정하세요. stateful MCP session을 사용하면 해당 session의 요청을 같은 replica로 전달해야 합니다. 로그 파일 경로는 process나 pod마다 분리하세요. `TimedRotatingFileHandler`는 여러 process의 동시 회전을 안전하게 처리하지 못합니다.

[TLS와 로그](security.ko.md)
