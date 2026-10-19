# AWX MCP Server

MCP 클라이언트에서 AWX의 실패한 작업과 실행 로그를 조회하고, 호출자의 AWX 권한으로 자동화를 관리할 수 있습니다. 개인용 stdio 프로세스로 실행하거나, 사용자별 토큰을 전달하는 중앙 서버로 공유할 수 있습니다.

![CI](https://github.com/lycorp-jp/awx-mcp/actions/workflows/ci.yml/badge.svg)
![Release](https://img.shields.io/github/v/release/lycorp-jp/awx-mcp)
![Python](https://img.shields.io/badge/Python-≥3.10-3776AB?logo=python&logoColor=white)
![License](https://img.shields.io/badge/License-Apache_2.0-blue)
![MCP Tools](https://img.shields.io/badge/MCP_Tools-145-blue)
![AWX](https://img.shields.io/badge/AWX-tested_24.6.1-EE0000?logo=redhat&logoColor=white)

[English](README.md) | [日本語](README.ja.md)

현재 Git 저장소에서 설치할 수 있으며 **PyPI에는 게시하지 않습니다**. 첫 release와 GHCR 이미지, MCP Registry 게시는 아직 진행하지 않았으므로 Release badge에는 release가 없다고 표시될 수 있습니다.

## 빠른 시작

먼저 uv를 설치하세요: https://docs.astral.sh/uv/

본인의 AWX URL과 토큰을 설정합니다. 아래 예시는 토큰을 명령어에 직접 넣지 않고 환경변수로 전달하며, 읽기 전용 모드로 시작합니다.

```bash
export ANSIBLE_BASE_URL="https://awx.example.com/"
export ANSIBLE_TOKEN="REPLACE_WITH_YOUR_AWX_TOKEN"
export AWX_MCP_READ_ONLY=true
claude mcp add --scope project awx \
  -e 'ANSIBLE_BASE_URL=${ANSIBLE_BASE_URL}' \
  -e 'ANSIBLE_TOKEN=${ANSIBLE_TOKEN}' \
  -e 'AWX_MCP_READ_ONLY=${AWX_MCP_READ_ONLY}' \
  -- uvx --from git+https://github.com/lycorp-jp/awx-mcp awx-mcp
```

`AWX_MCP_READ_ONLY=true`는 선택적인 시작 설정입니다. 쓰기 도구가 필요하고 AWX 역할에 권한이 있을 때 해제하세요. 서버 프로세스는 MCP 클라이언트가 실행하도록 설정합니다. Claude Desktop 등 다른 클라이언트의 설정은 [MCP 클라이언트 연동](#mcp-클라이언트-연동)을 참고하세요.

작은따옴표는 `.mcp.json`에 `${VAR}` 참조를 그대로 보관합니다. 해당 환경변수를 설정한 셸에서 Claude Code를 실행하세요. 환경변수 확장 안내: https://code.claude.com/docs/en/mcp#environment-variable-expansion-in-mcpjson

## 읽기 전용 fixture 데모

![Read-only MCP fixture demo](docs/demo.gif)

GIF는 로컬 fake AWX fixture에 실제 MCP `list_jobs(status="failed")`와 `get_job_stdout(job_id=42)`를 호출한 결과입니다. 데이터와 토큰은 모두 가짜입니다. 실제 AWX 운영 환경이나 LLM 대화를 촬영한 영상이 아니라 MCP 프로토콜 동작을 재현한 데모입니다.

[실행 기록](docs/demo.txt) · [재현 방법](docs/demo.tape)

## 목차

- [빠른 시작](#빠른-시작)
- [읽기 전용 fixture 데모](#읽기-전용-fixture-데모)
- [사전 요구사항](#사전-요구사항)
- [아키텍처](#아키텍처)
- [호환성](#호환성)
- [주요 기능](#주요-기능)
- [설치](#설치)
- [배포 모드](#배포-모드)
- [설정](#설정)
- [Credential Management (opt-in)](#credential-management-opt-in)
- [MCP 클라이언트 연동](#mcp-클라이언트-연동)
- [사용 예시](#사용-예시)
- [도구 목록](#도구-목록)
- [트러블슈팅](#트러블슈팅)
- [기여하기](#기여하기)
- [행동 강령](#행동-강령)
- [변경 이력](#변경-이력)
- [보안 정책](#보안-정책)
- [라이선스](#라이선스)

---

## 사전 요구사항

- 접근 가능한 AWX 인스턴스 및 해당 기본 URL (REST API v2), 그리고 적절한 권한이 있는 API 토큰 (또는 사용자명 + 비밀번호)
- uv: https://docs.astral.sh/uv/ (`uvx`를 제공하며, 클론 없이 git 저장소에서 바로 서버를 실행합니다)

---

## 아키텍처

```mermaid
flowchart LR
    User([사용자])
    LLM[LLM<br/>Claude / GPT 등]
    MCP[MCP Client<br/>Claude Desktop<br/>Claude Code<br/>Cline 등]
    AWX_MCP["AWX MCP Server<br/>(awx-mcp)<br/>145개 도구 (기본 141 + opt-in 4)"]
    AWX[AWX<br/>REST API v2]

    User -- 자연어 요청 --> LLM
    LLM -- 도구 선택 & 호출 --> MCP
    MCP -- "STDIO / SSE / HTTP" --> AWX_MCP
    AWX_MCP -- HTTPS --> AWX

    style AWX_MCP fill:#1a73e8,color:#fff
    style AWX fill:#ee0000,color:#fff
```

> LLM이 사용자 요청을 분석하여 적절한 MCP 도구를 선택하고, AWX MCP 서버가 AWX REST API를 호출하여 결과를 반환합니다.

> 로컬 클라이언트에는 stdio를, 새 원격 배포에는 Streamable HTTP를 권장합니다. SSE는 기존 클라이언트의 호환성을 위한 legacy transport로 유지합니다(`--serve --sse`, `/sse`).

---

## 호환성

| 컴포넌트 | 지원 버전 |
|---------|---------|
| AWX | 24.6.1 (REST API v2) |
| Python | ≥ 3.10 |
| MCP transport | STDIO, SSE, Streamable HTTP |
| 버전 정책 | 서버 버전은 검증한 AWX 버전을 따릅니다. 예를 들어 `24.6.1`을 사용하며, 동일한 AWX 버전에서 서버만 변경하면 `24.6.1.1`처럼 네 번째 숫자를 추가합니다. 이 값은 정책을 설명하는 예시이며 release tag의 존재를 뜻하지 않습니다. |
| 다른 AWX / Ansible Tower 버전 | 이 호환성 표에서 검증했다고 주장하지 않습니다. 도입 전에 사용하는 인스턴스에서 확인하세요. |

---

## 주요 기능

| 기능 | 활용 효과 |
|------|-----------|
| AWX의 20개 영역을 지원하는 145개 도구 | 인벤토리, 작업, 워크플로우, 프로젝트, RBAC, 시스템 상태를 MCP 클라이언트 한 곳에서 조회할 수 있습니다. |
| 로컬 stdio와 중앙 `--serve` | 개인 프로세스로 실행하거나, 호출자별 AWX 토큰을 사용하는 공유 서버로 운영할 수 있습니다. |
| `AWX_MCP_READ_ONLY=true` | 서버 시작 시 읽기 도구만 노출합니다. AWX RBAC도 그대로 적용됩니다. |
| 이름 필터와 페이지네이션 | 이름으로 리소스를 찾고 클라이언트에 반환할 레코드 수를 제한할 수 있습니다. |
| 토큰 캐시 | 로컬에서 사용자명과 비밀번호로 인증하면 서버가 생성한 OAuth2 토큰을 재사용합니다. |
| TLS와 opt-in 로컬 로그 | 네트워크로 전달하는 자격 증명을 보호하고, 중앙 서버에서는 호출자별 도구 실행 기록을 남길 수 있습니다. |

기본으로 141개 도구가 활성화됩니다. 자격 증명/사용자 쓰기 도구 4개는 명시적인 opt-in이 필요합니다. 다른 도구도 민감한 인벤토리 변수, 작업 출력, 계정 정보를 반환할 수 있습니다. 쓰기 기능을 켜기 전에 [Credential Management](#credential-management-opt-in)와 [보안 안내](docs/security.ko.md)를 확인하세요.

---

## 설치

패키지 배포의 기준은 GitHub입니다. 지금은 main branch를 사용하거나 `@<commit-sha-or-existing-ref>`를 붙여 실제로 존재하는 revision을 선택하세요. 첫 release 전에는 사용할 수 있는 release tag가 있다고 가정하지 않습니다.

```bash
uvx --from git+https://github.com/lycorp-jp/awx-mcp awx-mcp
```

`uvx`는 저장소를 가져와 빌드한 뒤 캐시합니다. 캐시된 main branch를 갱신하려면 한 번 `--refresh`를 추가하세요. 개발 환경에서는 `uv run --directory /path/to/awx-mcp awx-mcp --stdio`를 사용합니다. 해당 환경에서 `awx-mcp --version`으로 설치된 버전을 확인할 수 있습니다.

### Docker / Podman

지금은 로컬 checkout에서 컨테이너를 빌드할 수 있습니다. 이미지의 기본 명령은 중앙 HTTP 서버이므로 아래 stdio 실행에서는 `--stdio`를 명시해야 합니다.

```bash
docker build -t awx-mcp:local .
docker run -i --rm -e ANSIBLE_BASE_URL -e ANSIBLE_TOKEN -e AWX_MCP_READ_ONLY awx-mcp:local --stdio
```

값은 환경변수로 전달하고, MCP stdio에는 `-t`를 사용하지 마세요. GHCR 이미지와 tag 설치 명령은 첫 release를 게시한 뒤 안내합니다. 다중 사용자 HTTP, 프록시, TLS, replica 구성은 [배포 안내](docs/deployment.ko.md)를 참고하세요.

---

## 배포 모드

| 명령 | 모드 | 인증 방식 |
|------|------|-----------|
| `awx-mcp` / `awx-mcp --stdio` | 로컬 stdio | 본인의 AWX 토큰 또는 사용자명/비밀번호 |
| `awx-mcp --remote <URL>` | 중앙 서버에 연결하는 로컬 프록시 | 본인의 AWX 토큰만 사용 |
| `awx-mcp --serve` | 중앙 Streamable HTTP 서버 | 요청마다 호출자의 토큰을 사용 |

중앙 서버는 정적으로 설정된 AWX 자격 증명을 무시합니다. 호출자 토큰을 TLS로 보호하고 네트워크 접근을 제한하세요. `--host`와 `--port`는 환경변수보다 우선합니다. [배포 예제, 직접 HTTP 연결, replica 구성](docs/deployment.ko.md)과 [TLS 및 로그](docs/security.ko.md)를 참고하세요.

---

## 설정

환경변수로 AWX 접속 정보를 설정합니다. MCP 클라이언트 설정의 `env` 블록에 직접 넣으면 됩니다.

### 필수 환경 변수

| 변수 | 설명 | 예시 |
|------|------|------|
| `ANSIBLE_BASE_URL` | AWX 인스턴스 URL (끝 `/` 선택) | `https://awx.example.com` |

### 인증 (둘 중 하나 선택)

**방법 1: API 토큰 (권장)**

AWX UI에서 미리 생성한 토큰을 사용합니다. 토큰은 AWX 정책에 따라 만료되거나 폐기될 수 있습니다. 필요한 최소 권한과 scope를 선택하고, 필요할 때 교체하세요.

| 변수 | 설명 |
|------|------|
| `ANSIBLE_TOKEN` | 사전 생성된 API 토큰 |

> AWX UI에서 토큰 생성: 사용자 프로필 > 토큰 > 추가. 읽기 전용이면 Read scope를 선택하고, 쓰기가 필요할 때만 Write를 선택하세요. AWX RBAC도 접근 권한을 제한합니다.

**방법 2: 사용자명 + 비밀번호**

서버가 자동으로 OAuth2 토큰을 생성하고 캐시합니다.

| 변수 | 설명 |
|------|------|
| `ANSIBLE_USERNAME` | AWX 사용자명 |
| `ANSIBLE_PASSWORD` | AWX 비밀번호 |

### 선택 환경 변수

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `ANSIBLE_SSL_VERIFY` | `true` | TLS 인증서 검증 (`true`/`false`). 검증은 **기본적으로 켜져 있습니다**. `false`로 설정하면 검증이 비활성화됩니다 (**보안 취약** - 경고가 로깅됩니다. CA 번들이 없는 개발/자체 서명 환경에서만 사용하세요). |
| `ANSIBLE_CA_BUNDLE` | 미설정 | 검증이 활성화된 상태에서 신뢰할 커스텀 CA 번들/자체 서명 인증서(PEM) 경로. 검증을 끄지 않고도 사설 CA를 사용하는 AWX 인스턴스에 연결할 수 있습니다. 경로가 존재하지 않으면 서버가 시작 시 즉시 실패합니다. |
| `ANSIBLE_LOG_LEVEL` | `INFO` | 로그 레벨 (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `AWX_HTTP_TIMEOUT_READ` | `90` | AWX API 요청 하나의 읽기 timeout(초). 느린 AWX 에서 큰 `get_job_stdout` / `get_job_events` 호출이 timeout 나면 늘린다. |
| `AWX_MCP_ENABLE_CREDENTIAL_MANAGEMENT` | `false` | Form mode elicitation으로 민감 데이터를 수집하는 자격 증명/사용자 쓰기 도구 4개의 활성화 여부. [Credential Management (opt-in)](#credential-management-opt-in) 섹션 참조. |
| `AWX_MCP_READ_ONLY` | `false` | 읽기 전용 모드. `--serve` 중앙 서버에서 `true`로 설정하면 모든 쓰기/파괴적 도구가 전역적으로 등록 해제됩니다(사용자가 다시 켤 수 없음). `--remote` 프록시 모드에서 `true`는 해당 사용자의 세션에만 적용됩니다(프록시가 `X-AWX-Read-Only`를 전송하고, 서버는 그 호출자의 쓰기 호출만 거부합니다). 어드바이저리 성격의 자기 제한이며 - [배포 모드](docs/deployment.ko.md) 참조. |
| `AWX_MCP_REMOTE_URL` | 미설정 | 프록시 모드용 중앙 서버 URL(`--remote <URL>`과 동등하며, 플래그가 우선합니다). |
| `AWX_MCP_HOST` | `127.0.0.1` | `--serve` 서버의 바인드 호스트. `--host`로 오버라이드됩니다. |
| `AWX_MCP_PORT` | `8000` | `--serve` 서버의 바인드 포트. `--port`로 오버라이드됩니다. |
| `AWX_MCP_TLS_ENABLE` | `false` | `true`로 설정하면 `--serve` 서버가 프로세스 내에서 HTTPS로 서빙합니다 (uvicorn). 호출자 토큰이 요청 헤더로 전달되므로 강력히 권장됩니다. |
| `AWX_MCP_TLS_CERT` | 미설정 | 서버 TLS 인증서(PEM) 경로. `AWX_MCP_TLS_ENABLE=true`일 때 필수이며, 경로가 없거나 찾을 수 없으면 서버가 시작 시 즉시 실패합니다. |
| `AWX_MCP_TLS_KEY` | 미설정 | 서버 TLS 개인 키(PEM) 경로. TLS가 활성화되면 필수입니다. |
| `AWX_MCP_TLS_KEY_PASSWORD` | 미설정 | 개인 키가 암호화된 경우의 비밀번호. 선택 사항. |
| `AWX_MCP_STATELESS_HTTP` | `false` | 상태 비저장(stateless) streamable-http 모드. 각 요청이 그 자체로 완결되어 프로세스에 세션별 상태를 유지하지 않습니다. 단순 라운드로빈 로드밸런서 뒤에 여러 `--serve` replica를 운영할 때 필요합니다(그렇지 않으면 한 replica에서 만든 세션이 다른 replica로 라우팅될 때 404가 발생합니다). 기본값(off)은 단일 인스턴스/sse 구성의 상태 유지(stateful) 세션 동작을 그대로 유지합니다. |
| `AWX_MCP_USAGE_LOG_FILE` | 미설정 | JSON Lines 형식의 사용 로그 파일 경로. MCP 도구 호출마다 하나의 JSON 문서(`@timestamp`, `type`, `user`, `tool`, `params`(마스킹된 호출 인자), `trace_id`, `server_version`, `success`, `latency_ms`, `auth_mode`, `transport`, `awx_host`, 실패 시 `error{type,message}`)가 기록됩니다. `--remote` 프록시를 포함해 모든 모드에서 동작합니다. 미설정 시 계측이 비활성화됩니다. [상세 사용 로그](docs/security.ko.md#상세-사용-로그) 섹션 참조. |
| `AWX_MCP_USAGE_USER` | 미설정 | 프록시의 로컬 사용 로그에서 `user` 필드로 사용할 레이블(선택 사항). 프록시 모드는 사용자명을 조회할 AWX 접근 권한이 없으므로 기본값은 `local`입니다. |
| `AWX_MCP_ACCESS_LOG_FILE` | 미설정 | `--serve` 서버용 JSON Lines 접속(access) 로그 파일 경로. 들어오는 모든 HTTP 요청이 기록됩니다(클라이언트 IP, 메서드, 경로, 상태 코드, 지연시간). 사용 로그와 마찬가지로 매일 자정(UTC)에 회전합니다. `--serve` 모드에서만 동작합니다 - stdio와 `--remote` 프록시에는 HTTP 소켓이 없습니다. |
| `AWX_MCP_SERVER_LOG_FILE` | 미설정 | 서버 진단 로그 파일 경로. 기존 stderr 진단/에러 출력을 그대로 파일에도 기록합니다. 미설정 시 stderr에만 출력되고 파일은 생성되지 않습니다. |
| `AWX_MCP_SERVER_LOG_FORMAT` | `plain` | 서버 진단 로그 형식: `plain` 또는 `json`. |
| `AWX_MCP_LOG_BACKUP_COUNT` | `7` | 로테이션된 로그 파일 보관 개수. 두 로그 파일 모두 매일 자정(UTC)에 날짜 접미사를 붙여 로테이션됩니다. |

### TLS / 인증서 검증

TLS 인증서 검증은 기본적으로 활성화됩니다. 사설 CA는 `ANSIBLE_CA_BUNDLE`로 신뢰하도록 설정하세요. `--remote`에서는 이 검증 설정이 AWX가 아닌 중앙 서버에 적용됩니다. 네트워크에 노출하는 중앙 서버에는 TLS와 접근 제한이 필요합니다. 사용/접속 로그는 opt-in이며 진단 로그는 기본적으로 stderr에 출력됩니다. stdout은 MCP 메시지 전용입니다. [TLS, 로그 필드, 마스킹 한계, replica 주의사항](docs/security.ko.md)을 참고하세요.

---

## Credential Management (opt-in)

`create_credential`, `update_credential`, `create_user`, `update_user`는 **Form mode elicitation**으로 비밀번호나 자격 증명 입력을 수집하므로 기본적으로 등록하지 않습니다. 나머지 도구도 작업 stdout이나 인벤토리 변수처럼 민감한 리소스 데이터를 반환할 수 있습니다.

활성화하려면 다음을 설정하세요:

```bash
AWX_MCP_ENABLE_CREDENTIAL_MANAGEMENT=true
```

Form mode elicitation은 MCP 스펙 관점에서 민감 데이터에 대해 비준수 상태입니다 - 응답이 클라이언트 측 로깅이나 기타 중간 시스템을 통해 노출될 수 있습니다. 신뢰할 수 있는 격리된 환경에서만 활성화하고, `--serve`와 **함께 사용하지 마세요**(공유 네트워크 배포는 로컬 stdio 프로세스보다 상황을 더 악화시킵니다). 전체 위협 모델 및 공개 정책은 [SECURITY.md](./SECURITY.md)를 참고하세요.

---

## MCP 클라이언트 연동

### Claude Desktop

`claude_desktop_config.json`에 다음을 추가합니다:

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

### Claude Code (CLI)

```bash
claude mcp add awx \
  -e ANSIBLE_BASE_URL=https://awx.example.com/ \
  -e ANSIBLE_TOKEN=your_api_token \
  -- uvx --from git+https://github.com/lycorp-jp/awx-mcp awx-mcp
```

### Cursor

아래 설치 링크는 **읽기 전용 설정 틀**을 추가합니다. 연결 설정이 완료되는 것은 아닙니다. 실행 전에 Cursor MCP 설정에서 `REPLACE_WITH_YOUR_AWX_HTTPS_URL`과 `REPLACE_WITH_YOUR_AWX_TOKEN`을 **모두 교체하세요**. 이 설정을 version control에 포함하지 마세요.

cursor://anysphere.cursor-deeplink/mcp/install?name=awx&config=eyJjb21tYW5kIjoidXZ4IiwiYXJncyI6WyItLWZyb20iLCJnaXQraHR0cHM6Ly9naXRodWIuY29tL2x5Y29ycC1qcC9hd3gtbWNwIiwiYXd4LW1jcCJdLCJlbnYiOnsiQU5TSUJMRV9CQVNFX1VSTCI6IlJFUExBQ0VfV0lUSF9ZT1VSX0FXWF9IVFRQU19VUkwiLCJBTlNJQkxFX1RPS0VOIjoiUkVQTEFDRV9XSVRIX1lPVVJfQVdYX1RPS0VOIiwiQVdYX01DUF9SRUFEX09OTFkiOiJ0cnVlIn19

공식 형식: https://cursor.com/docs/mcp/install-links

### VS Code (native MCP)

`.vscode/mcp.json`이나 사용자 MCP 설정에 아래 내용을 추가합니다. VS Code가 URL과 토큰을 입력받으며 토큰 입력은 가려집니다. `env`의 참조는 아래 `inputs`에 연결됩니다.

```json
{
  "inputs": [
    {
      "id": "awx-url",
      "type": "promptString",
      "description": "AWX HTTPS 기본 URL"
    },
    {
      "id": "awx-token",
      "type": "promptString",
      "description": "AWX API 토큰",
      "password": true
    }
  ],
  "servers": {
    "awx": {
      "type": "stdio",
      "command": "uvx",
      "args": [
        "--from",
        "git+https://github.com/lycorp-jp/awx-mcp",
        "awx-mcp"
      ],
      "env": {
        "ANSIBLE_BASE_URL": "${input:awx-url}",
        "ANSIBLE_TOKEN": "${input:awx-token}",
        "AWX_MCP_READ_ONLY": "true"
      }
    }
  }
}
```

설정 안내: https://code.visualstudio.com/docs/agents/reference/mcp-configuration

### Cline (VS Code)

MCP 서버 설정에 다음을 추가합니다:

```json
{
  "awx": {
    "command": "uvx",
    "args": ["--from", "git+https://github.com/lycorp-jp/awx-mcp", "awx-mcp"],
    "env": {
      "ANSIBLE_BASE_URL": "https://awx.example.com/",
      "ANSIBLE_TOKEN": "your_api_token"
    }
  }
}
```

### 중앙 서버 접속

본인의 AWX 토큰으로 stdio 프록시 또는 직접 Streamable HTTP 연결을 사용합니다. 프록시에는 `ANSIBLE_TOKEN`이 필요하며 `ANSIBLE_BASE_URL`은 필요하지 않습니다. 사용자명/비밀번호 인증은 로컬 모드에서만 지원합니다. [전체 프록시/직접 HTTP 설정과 TLS 요구사항](docs/deployment.ko.md)을 참고하세요.

---

## 사용 예시

MCP 클라이언트(Claude 등)에 자연어로 요청하면 서버가 적절한 도구를 호출합니다.

### 인벤토리 관리

```
"Production 인벤토리의 호스트 목록을 보여줘"
→ list_hosts(inventory_id=1) 호출

"web-server-01 호스트를 Production 인벤토리에 추가해줘"
→ create_host(name="web-server-01", inventory_id=1) 호출

"DB 서버들을 database 그룹으로 묶어줘"
→ create_group(...) + add_host_to_group(...) 호출
```

### 작업 실행 및 모니터링

```
"Deploy App 작업 템플릿을 실행해줘"
→ launch_job(template_id=5) 호출

"방금 실행한 작업의 진행 상황을 확인해줘"
→ get_job(job_id=123) 호출

"작업 실행 로그를 보여줘"
→ get_job_stdout(job_id=123) 호출

"실패한 작업을 재실행해줘"
→ relaunch_job(job_id=123) 호출
```

### 프로젝트 & SCM

```
"모든 프로젝트를 최신 상태로 동기화해줘"
→ list_projects() + sync_project(project_id=...) 반복 호출

"my-project에 있는 플레이북 목록을 보여줘"
→ list_project_playbooks(project_id=3) 호출
```

### 워크플로우

```
"배포 워크플로우를 실행하고 승인이 필요하면 승인해줘"
→ launch_workflow(template_id=10) 호출
→ list_workflow_approvals() → approve_workflow(approval_id=...) 호출

"워크플로우 실행 결과에서 실패한 노드를 확인해줘"
→ list_workflow_job_nodes(workflow_job_id=50) 호출
```

### RBAC & 사용자 관리

```
"developer 팀에 Production 인벤토리 읽기 권한을 부여해줘"
→ list_object_roles(...) + grant_role_to_team(role_id=..., team_id=...) 호출

"새 사용자 john을 생성하고 DevOps 팀에 추가해줘"
→ create_user(...) + grant_role_to_user(...) 호출
```

### 시스템 관리

```
"AWX 버전과 클러스터 상태를 확인해줘"
→ get_ansible_version() + list_instances() 호출

"90일 이전의 오래된 작업 기록을 정리해줘"
→ list_system_job_templates() → launch_system_job(template_id=..., extra_vars='{"days": 90}') 호출
```

---

## 도구 목록

총 **145개** 도구를 20개 모듈로 제공합니다. 기본값으로 141개가 등록되며, 아래에서 **opt-in**으로 표시된 4개는 `AWX_MCP_ENABLE_CREDENTIAL_MANAGEMENT=true` 설정 시에만 노출됩니다([Credential Management (opt-in)](#credential-management-opt-in) 섹션 참조).

### 이름으로 검색하기

이름을 가진 컬렉션을 다루는 모든 `list_*` 도구는 이름 인자를 선택적으로 받습니다.
AWX가 이를 **서버 사이드**에서 대소문자 구분 없는 부분 일치로 적용하므로, 컬렉션을
페이지 단위로 훑지 않고 한 번의 호출로 이름을 ID로 해석할 수 있습니다.

```
list_job_templates(template_name="deploy")      -> "deploy"와 일치하는 템플릿만
list_projects(project_name="platform")          -> "platform"과 일치하는 프로젝트만
```

인자 이름은 리소스에 따라 정해집니다(`project_name`, `inventory_name`,
`credential_name` 등). `list_hosts`와 `list_instances`는 `hostname`,
`list_users`는 `username`을 사용합니다. 인자를 생략하면 기존과 동일하게 전체를
조회합니다.

이름 필터가 없는 두 부류가 있습니다. `list_roles`는 AWX가 역할 이름을 저장하지 않고
role 필드에서 파생시키기 때문에 필터링할 수 없습니다. 실행 기록 조회
(`list_jobs`, `list_project_updates` 등)는 이름 대신 상태와 상위 템플릿으로
조회합니다.

<details>
<summary><strong>전체 145개 도구 보기</strong></summary>

### 인벤토리 & 인벤토리 소스 관리 (14개) - `inventories.py`

| 도구 | 설명 |
|------|------|
| `list_inventories` | 모든 인벤토리 목록 조회 |
| `get_inventory` | 특정 인벤토리 상세 조회 |
| `create_inventory` | 새 인벤토리 생성 |
| `update_inventory` | 인벤토리 수정 |
| `delete_inventory` | 인벤토리 삭제 |
| `list_inventory_sources` | 인벤토리 소스 목록 |
| `get_inventory_source` | 특정 인벤토리 소스 상세 조회 |
| `create_inventory_source` | 새 인벤토리 소스 생성 |
| `update_inventory_source` | 인벤토리 소스 수정 |
| `sync_inventory_source` | 인벤토리 소스 동기화 |
| `delete_inventory_source` | 인벤토리 소스 삭제 |
| `list_inventory_updates` | 인벤토리 업데이트(동기화) 기록 조회 |
| `get_inventory_update` | 특정 인벤토리 업데이트 상세 조회 |
| `cancel_inventory_update` | 실행 중인 인벤토리 업데이트 취소 |

### 호스트 관리 (5개) - `hosts.py`

| 도구 | 설명 |
|------|------|
| `list_hosts` | 호스트 목록 (인벤토리 필터 가능) |
| `get_host` | 특정 호스트 상세 조회 |
| `create_host` | 새 호스트 생성 (변수 포함) |
| `update_host` | 호스트 수정 |
| `delete_host` | 호스트 삭제 |

### 그룹 관리 (7개) - `groups.py`

| 도구 | 설명 |
|------|------|
| `list_groups` | 인벤토리 내 그룹 목록 |
| `get_group` | 특정 그룹 상세 조회 |
| `create_group` | 새 그룹 생성 (변수 포함) |
| `update_group` | 그룹 수정 |
| `delete_group` | 그룹 삭제 |
| `add_host_to_group` | 호스트를 그룹에 추가 |
| `remove_host_from_group` | 그룹에서 호스트 제거 |

### 작업 템플릿 관리 (13개) - `job_templates.py`

| 도구 | 설명 |
|------|------|
| `list_job_templates` | 모든 작업 템플릿 목록 |
| `get_job_template` | 특정 작업 템플릿 상세 조회 |
| `create_job_template` | 새 작업 템플릿 생성 |
| `update_job_template` | 작업 템플릿 수정 |
| `delete_job_template` | 작업 템플릿 삭제 |
| `launch_job` | 작업 템플릿에서 작업 실행 |
| `copy_job_template` | 작업 템플릿 복사 |
| `get_job_template_survey` | 작업 템플릿 설문 조회 |
| `set_job_template_survey` | 작업 템플릿 설문 설정 |
| `delete_job_template_survey` | 작업 템플릿 설문 삭제 |
| `list_template_credentials` | 템플릿에 연결된 자격 증명 목록 |
| `associate_credential_with_template` | 템플릿에 자격 증명 연결 |
| `disassociate_credential_from_template` | 템플릿에서 자격 증명 해제 |

### 작업 관리 (7개) - `jobs.py`

| 도구 | 설명 |
|------|------|
| `list_jobs` | 작업 목록 (상태 필터 가능) |
| `get_job` | 특정 작업 상세 조회 |
| `cancel_job` | 실행 중인 작업 취소 |
| `relaunch_job` | 완료/실패된 작업 재실행 |
| `get_job_events` | 작업 이벤트 목록 |
| `get_job_stdout` | 작업 표준 출력 (txt/html/json/ansi) |
| `get_job_host_summaries` | 호스트별 작업 결과 요약 |

### 프로젝트 관리 (11개) - `projects.py`

| 도구 | 설명 |
|------|------|
| `list_projects` | 모든 프로젝트 목록 |
| `get_project` | 특정 프로젝트 상세 조회 |
| `create_project` | 새 프로젝트 생성 (Git/SVN/Hg/수동) |
| `update_project` | 프로젝트 수정 |
| `delete_project` | 프로젝트 삭제 |
| `sync_project` | SCM 소스와 프로젝트 동기화 |
| `list_project_playbooks` | 프로젝트 내 플레이북 목록 |
| `list_project_updates` | 프로젝트 업데이트(동기화) 기록 조회 |
| `get_project_update` | 특정 프로젝트 업데이트 상세 조회 |
| `cancel_project_update` | 실행 중인 프로젝트 업데이트 취소 |
| `get_project_update_stdout` | 프로젝트 업데이트 표준 출력 |

### 자격 증명 관리 (7개: 기본 5 + opt-in 2) - `credentials.py`

| 도구 | 설명 |
|------|------|
| `list_credentials` | 모든 자격 증명 목록 |
| `get_credential` | 특정 자격 증명 상세 조회 |
| `list_credential_types` | 자격 증명 유형 목록 |
| `create_credential` | **opt-in.** 새 자격 증명 생성 (elicitation으로 민감 입력 수집) |
| `update_credential` | **opt-in.** 자격 증명 수정 (elicitation으로 민감 입력 수집 가능) |
| `delete_credential` | 자격 증명 삭제 |
| `copy_credential` | 자격 증명 복사 |

### 조직 관리 (5개) - `organizations.py`

| 도구 | 설명 |
|------|------|
| `list_organizations` | 모든 조직 목록 |
| `get_organization` | 특정 조직 상세 조회 |
| `create_organization` | 새 조직 생성 |
| `update_organization` | 조직 수정 |
| `delete_organization` | 조직 삭제 |

### 팀 관리 (5개) - `teams.py`

| 도구 | 설명 |
|------|------|
| `list_teams` | 팀 목록 (조직 필터 가능) |
| `get_team` | 특정 팀 상세 조회 |
| `create_team` | 새 팀 생성 |
| `update_team` | 팀 수정 |
| `delete_team` | 팀 삭제 |

### 사용자 관리 (5개: 기본 3 + opt-in 2) - `users.py`

| 도구 | 설명 |
|------|------|
| `list_users` | 모든 사용자 목록 |
| `get_user` | 특정 사용자 상세 조회 |
| `create_user` | **opt-in.** 새 사용자 생성 (elicitation으로 비밀번호 수집) |
| `update_user` | **opt-in.** 사용자 수정 (elicitation으로 비밀번호 수집 가능) |
| `delete_user` | 사용자 삭제 |

### Ad Hoc 명령 (3개) - `ad_hoc.py`

| 도구 | 설명 |
|------|------|
| `run_ad_hoc_command` | Ad hoc Ansible 명령 실행 |
| `get_ad_hoc_command` | Ad hoc 명령 상세 조회 |
| `cancel_ad_hoc_command` | 실행 중인 Ad hoc 명령 취소 |

### 워크플로우 템플릿 & 노드 관리 (17개) - `workflow_templates.py`

| 도구 | 설명 |
|------|------|
| `list_workflow_templates` | 모든 워크플로우 템플릿 목록 |
| `get_workflow_template` | 특정 워크플로우 템플릿 상세 조회 |
| `create_workflow_template` | 새 워크플로우 템플릿 생성 |
| `update_workflow_template` | 워크플로우 템플릿 수정 |
| `delete_workflow_template` | 워크플로우 템플릿 삭제 |
| `launch_workflow` | 워크플로우 실행 |
| `copy_workflow_template` | 워크플로우 템플릿 복사 |
| `get_workflow_template_survey` | 워크플로우 설문 조회 |
| `set_workflow_template_survey` | 워크플로우 설문 설정 |
| `delete_workflow_template_survey` | 워크플로우 설문 삭제 |
| `list_workflow_template_nodes` | 워크플로우 노드 목록 |
| `get_workflow_template_node` | 특정 노드 상세 조회 |
| `create_workflow_template_node` | 새 노드 생성 |
| `delete_workflow_template_node` | 노드 삭제 |
| `add_workflow_node_success_link` | 성공 시 실행할 노드 연결 |
| `add_workflow_node_failure_link` | 실패 시 실행할 노드 연결 |
| `add_workflow_node_always_link` | 항상 실행할 노드 연결 |

### 워크플로우 작업 & 승인 (11개) - `workflow_jobs.py`

| 도구 | 설명 |
|------|------|
| `list_workflow_jobs` | 워크플로우 작업 목록 (상태 필터 가능) |
| `get_workflow_job` | 특정 워크플로우 작업 상세 조회 |
| `cancel_workflow_job` | 실행 중인 워크플로우 작업 취소 |
| `relaunch_workflow_job` | 완료/실패된 워크플로우 작업 재실행 |
| `list_workflow_job_nodes` | 실행된 워크플로우의 노드 목록 (디버깅용) |
| `list_workflow_approvals` | 워크플로우 승인 요청 목록 |
| `get_workflow_approval` | 특정 승인 요청 상세 조회 |
| `approve_workflow` | 워크플로우 승인 |
| `deny_workflow` | 워크플로우 거부 |
| `list_workflow_approval_templates` | 워크플로우 승인 템플릿 목록 |
| `get_workflow_approval_template` | 특정 승인 템플릿 상세 조회 |

### 스케줄 관리 (5개) - `schedules.py`

| 도구 | 설명 |
|------|------|
| `list_schedules` | 스케줄 목록 (템플릿 필터 가능) |
| `get_schedule` | 특정 스케줄 상세 조회 |
| `create_schedule` | 새 스케줄 생성 (iCal rrule) |
| `update_schedule` | 스케줄 수정 |
| `delete_schedule` | 스케줄 삭제 |

### 실행 환경 (5개) - `execution_environments.py`

| 도구 | 설명 |
|------|------|
| `list_execution_environments` | 실행 환경 목록 |
| `get_execution_environment` | 특정 실행 환경 상세 조회 |
| `create_execution_environment` | 새 실행 환경 생성 |
| `update_execution_environment` | 실행 환경 수정 |
| `delete_execution_environment` | 실행 환경 삭제 |

### 알림 템플릿 (3개) - `notifications.py`

| 도구 | 설명 |
|------|------|
| `list_notification_templates` | 알림 템플릿 목록 |
| `get_notification_template` | 특정 알림 템플릿 상세 조회 |
| `test_notification_template` | 테스트 알림 발송 |

### 라벨 관리 (2개) - `labels.py`

| 도구 | 설명 |
|------|------|
| `list_labels` | 라벨 목록 |
| `create_label` | 새 라벨 생성 |

### RBAC 역할 관리 (7개) - `rbac.py`

| 도구 | 설명 |
|------|------|
| `list_roles` | RBAC 역할 목록 |
| `get_role` | 특정 역할 상세 조회 |
| `grant_role_to_user` | 사용자에게 역할 부여 |
| `revoke_role_from_user` | 사용자에서 역할 해제 |
| `grant_role_to_team` | 팀에 역할 부여 |
| `revoke_role_from_team` | 팀에서 역할 해제 |
| `list_object_roles` | 특정 리소스의 RBAC 역할 목록 조회 |

### 인스턴스 관리 (4개) - `instances.py`

| 도구 | 설명 |
|------|------|
| `list_instances` | 클러스터 인스턴스 목록 |
| `get_instance` | 특정 인스턴스 상세 조회 |
| `list_instance_groups` | 인스턴스 그룹 목록 |
| `get_instance_group` | 특정 인스턴스 그룹 상세 조회 |

### 시스템 관리 (9개) - `system.py`

| 도구 | 설명 |
|------|------|
| `list_activity_stream` | 감사 기록 조회 (객체 유형/ID 필터링) |
| `get_config` | AWX 설정 정보 조회 |
| `get_ansible_version` | AWX 버전 정보 조회 |
| `get_dashboard_stats` | 대시보드 통계 조회 |
| `list_system_job_templates` | 시스템 작업 템플릿 목록 (정리, 분석 등) |
| `get_system_job_template` | 특정 시스템 작업 템플릿 상세 조회 |
| `launch_system_job` | 시스템 유지보수 작업 실행 |
| `list_system_jobs` | 시스템 작업 실행 기록 목록 |
| `get_system_job` | 특정 시스템 작업 상세 조회 |

</details>

---

## 트러블슈팅

### 서버가 시작되지 않아요

**`ValueError: ANSIBLE_BASE_URL environment variable is required`**

환경변수가 설정되지 않았습니다. MCP 클라이언트 설정의 `env` 블록에 `ANSIBLE_BASE_URL`을 추가하세요.

**`ValueError: Authentication is required`**

`ANSIBLE_TOKEN` 또는 `ANSIBLE_USERNAME` + `ANSIBLE_PASSWORD` 중 하나를 설정해야 합니다.

### 연결이 안 돼요

**SSL 인증서 오류**

TLS 검증은 기본적으로 켜져 있습니다. AWX 인스턴스가 사설/내부 CA가 발급한 인증서 또는 자체 서명 인증서를 사용한다면, `ANSIBLE_CA_BUNDLE`에 해당 CA/인증서의 PEM 파일 경로를 설정하세요. 검증을 켠 채로 그 인증서를 신뢰할 수 있습니다. CA 인증서를 구할 수 없는 등 최후의 수단으로만 `ANSIBLE_SSL_VERIFY`를 `"false"`(반드시 문자열)로 설정하세요. 이 경우 검증이 완전히 비활성화되며 서버가 경고를 로깅합니다. 자세한 내용은 [TLS 인증서 검증](docs/security.ko.md#tls--인증서-검증)을 참고하세요.

**Connection refused / timeout**

- `ANSIBLE_BASE_URL`이 정확한지 확인하세요
- AWX 인스턴스가 실행 중인지 확인하세요
- 방화벽/네트워크 설정을 확인하세요

### MCP 스키마 오류

**`Does not adhere to MCP server configuration schema`**

`env` 블록의 모든 값은 **문자열**이어야 합니다. `false` (boolean) 대신 `"false"` (문자열)을 사용하세요.

### 권한 오류

**403 Forbidden**

API 토큰 또는 사용자 계정에 해당 리소스에 대한 권한이 없습니다. AWX 관리자에게 적절한 역할을 요청하세요.

### 디버깅

로그 레벨을 `DEBUG`로 설정하면 상세한 API 요청/응답 로그를 확인할 수 있습니다:

```json
"ANSIBLE_LOG_LEVEL": "DEBUG"
```

---

## 기여하기

기여를 환영합니다. 이슈 제출, 변경 제안, PR 오픈 방법은 [CONTRIBUTING.md](CONTRIBUTING.md)를 참고하세요.

## 행동 강령

이 프로젝트는 [행동 강령](CODE_OF_CONDUCT.md)을 따릅니다. 참여 시 해당 조항을 준수해야 합니다.

## 변경 이력

주요 변경 사항의 이력은 [CHANGELOG.md](CHANGELOG.md)를 참조하세요.

## 보안 정책

취약점 공개, 위협 모델, 보안 이력은 [SECURITY.md](SECURITY.md)를 참조하세요.

---

## 라이선스

Apache License 2.0 - 자세한 내용은 [LICENSE](LICENSE) 파일을 참조하세요.
