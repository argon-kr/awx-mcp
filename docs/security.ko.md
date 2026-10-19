# TLS, 로그, 민감 데이터 처리

[README](../README.ko.md) | [English](security.md) | [한국어](security.ko.md) | [日本語](security.ja.md)

## TLS / 인증서 검증

TLS 인증서 검증은 **기본적으로 켜져 있습니다** (`ANSIBLE_SSL_VERIFY=true`). AWX 인스턴스가 사설/내부 CA가 발급한 인증서(또는 자체 서명 인증서)를 사용한다면, `ANSIBLE_CA_BUNDLE`에 CA 번들(PEM) 경로를 설정하세요 - 검증을 비활성화하지 않고도 해당 CA를 신뢰하게 되며, 이는 검증 비활성화보다 권장되는 방법입니다.

`ANSIBLE_SSL_VERIFY=false`로 설정하면 검증이 완전히 비활성화됩니다. 이 값을 사용할 때마다 서버가 경고를 로깅하며, 개발 환경에서만 사용해야 합니다. 스킴이 없는 `ANSIBLE_BASE_URL` 호스트는 자동으로 `https://`로 승격됩니다. 명시적인 `http://` URL은 그대로 사용되지만, API 토큰이 암호화되지 않은 채 전송되므로 서버가 경고를 로깅합니다.

## HTTPS로 서빙 (인바운드 TLS)

이는 **인바운드** TLS입니다 - MCP 클라이언트에서 이 서버로의 연결을 암호화하는 것으로, `ANSIBLE_SSL_VERIFY`가 제어하는 아웃바운드 AWX 인증서 검증과는 방향이 다릅니다. 두 가지를 혼동하지 마세요.

`--serve` 중앙 서버(streamable-http 또는 sse)에만 적용됩니다. 로컬 stdio 모드는 네트워크 소켓이 없는 로컬 파이프이므로 TLS가 적용되지 않으며, 보안은 프로세스/호스트 격리에서 나옵니다.

활성화하려면 `AWX_MCP_TLS_ENABLE=true`와 함께 `AWX_MCP_TLS_CERT`, `AWX_MCP_TLS_KEY`를 설정하세요 (키가 암호화된 경우 `AWX_MCP_TLS_KEY_PASSWORD`도 설정):

```bash
export AWX_MCP_TLS_ENABLE=true
export AWX_MCP_TLS_CERT=/path/to/server.crt
export AWX_MCP_TLS_KEY=/path/to/server.key
uvx --from git+https://github.com/lycorp-jp/awx-mcp awx-mcp --serve --host 127.0.0.1 --port 8443
```

**중요:** `--serve` 모드에서는 각 요청이 `Authorization` 헤더에 담긴 호출자 본인의 AWX 토큰으로 *실제로* 인증됩니다. TLS는 전송 중인 그 토큰을 보호하므로, 네트워크에 노출되는 배포라면 TLS 활성화(또는 인증 기능을 갖춘 TLS 리버스 프록시로 앞단을 감싸는 것)는 선택이 아니라 필수입니다. TLS 없이 비로컬 주소에 바인드하면 시작 시 경고가 로깅됩니다. 쿠버네티스에서는 보통 ingress에서 TLS를 종료하는 방식을 사용하며, 파드까지 종단 간 암호화가 필요한 경우에만 프로세스 내 TLS가 필요합니다.

## 상세 사용 로그

사용 로그는 opt-in 방식입니다. `AWX_MCP_USAGE_LOG_FILE`에 쓰기 가능한 경로를 설정하면, 도구 호출마다 하나의 JSON 문서를 JSON Lines: https://jsonlines.org/ 형식으로 기록하기 시작합니다. 이 형식은 Filebeat, Fluentd 등 외부 로그 수집기가 나중에 수집·통계 처리하기 쉽도록 설계되었습니다. 로그는 stdout으로 절대 출력되지 않습니다 - MCP stdio 트랜스포트는 stdout을 프로토콜 메시지 전송에 사용하므로, 여기에 로그를 쓰면 프로토콜 스트림이 손상됩니다. 서버 자체는 로그 데이터를 네트워크로 전송하지 않으며, 설정한 로컬 파일에만 기록합니다.

모든 로그 라인에는 `type` 필드가 있어 종류별로 분리할 수 있습니다: `"tool"`(일반 MCP 도구 호출), `"internal_api"`(서버가 호출하는 `/api/v2/me/` 사용자 확인 요청 - `tool: "me"`로 기록하며 HTTP 메서드와 경로는 별도 `method`/`endpoint` 필드에 기록), `"access"`(HTTP 액세스 로그), `"diagnostic"`(서버 진단 로그). `type` 필드와 공통 `@timestamp` 타임스탬프 필드는 네 종류 레코드에서 일관되게 사용되므로 단일 로그 인덱스에서 type으로 필터링할 수 있습니다. 도구 호출 레코드에는 `params`(호출 인자)도 포함되며, 비밀 성격의 키(password, token, key, `inputs` 등)와 문자열 내 `token=`/`password=`/`Bearer` 값은 마스킹됩니다.

`auth_mode` 필드는 `static`(로컬) 또는 `passthrough`(`--serve`)입니다. `transport` 필드는 `stdio`, `streamable-http`, `sse`, `proxy` 중 하나입니다. 중앙 서버에서 `user` 필드는 각 요청의 토큰이 속한 AWX 계정입니다(사용자별 귀속이며, 토큰당 한 번 조회하여 캐시하고, 원본 토큰과 그 해시는 절대 로깅하지 않습니다). `--remote` 프록시 자체의 로컬 로그에서는 `transport`가 `proxy`이고, `user`는 `AWX_MCP_USAGE_USER`(또는 `local`)이며, `awx_host`는 중앙 서버의 호스트입니다.

각 replica에 고유한 파일 경로를 지정하세요. 사용/접속 파일 로그를 설정하지 않으면 해당 기록이 다른 출력으로 전달되지는 않습니다. 진단 로그만 stderr에 계속 출력되며 플랫폼의 로그 수집기로 수집할 수 있습니다.

## 민감 데이터와 로그의 한계

마스킹은 비밀 성격의 키와 일반적인 token/password 문자열 패턴을 대상으로 합니다. 인벤토리 변수, 자유 형식 텍스트, 작업 출력에 포함된 임의의 비밀까지 제거한다고 보장할 수는 없습니다. 로그와 MCP 결과를 민감할 수 있는 데이터로 취급하고, 파일 접근과 보관 기간을 제한하며 클라이언트의 로깅 방식도 확인하세요. DEBUG를 활성화하면 더 많은 응답 내용이 노출될 수 있습니다.

자격 증명/사용자 쓰기 도구 4개는 Form mode elicitation으로 민감 데이터를 수집하므로 opt-in으로 유지합니다. 이 방식은 민감 데이터의 Form mode 입력을 금지하는 MCP 규칙을 준수하지 않습니다. 신뢰할 수 있는 격리된 로컬 환경에서만 활성화하고 `--serve`와 함께 사용하지 마세요. 취약점 공개 정책과 위협 모델은 [SECURITY.md](../SECURITY.md)를 참고하세요.
