# デプロイガイド

[README](../README.ja.md) | [English](deployment.md) | [한국어](deployment.ko.md) | [日本語](deployment.ja.md)

ローカルクライアントには stdio、新しいリモートデプロイには Streamable HTTP を推奨します。SSE は既存クライアント向けの legacy 互換 transport として維持します（`--serve --sse`、`/sse`）。

## デプロイモード

ローカル stdio は個人 API トークン、またはユーザー名/パスワードをサポートします。中央サーバーは呼び出し元ごとに個人トークンを受け取り、プロキシも個人トークンのみ転送します。

### 1. ローカル（デフォルト）

各ユーザーが、自分のトークンで AWX と通信するローカル stdio サーバーを実行します。

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

自分のツール呼び出しをローカルにも記録したい場合は `AWX_MCP_USAGE_LOG_FILE` を設定してください。

### 2. 中央サーバー - 管理者向け（`--serve`）

管理者が**1 つ**の共有サーバーを実行します。サーバー自体は AWX の資格情報を保持せず、各リクエストは**呼び出し元自身のトークン**で認証され、すべてのツール呼び出しは利用ログでその呼び出し元に帰属します。呼び出し元のトークンがリクエストヘッダーで送信されるため、TLS の利用を強く推奨します。

```bash
export ANSIBLE_BASE_URL=https://awx.example.com/
export AWX_MCP_USAGE_LOG_FILE=/var/log/awx-mcp/usage.jsonl   # ユーザーごとの帰属
export AWX_MCP_TLS_ENABLE=true
export AWX_MCP_TLS_CERT=/etc/awx-mcp/cert.pem
export AWX_MCP_TLS_KEY=/etc/awx-mcp/key.pem
uvx --from git+https://github.com/lycorp-jp/awx-mcp awx-mcp --serve --host 127.0.0.1 --port 8443        # sse トランスポートを使う場合は --sse を追加
```

上記のコマンドは `127.0.0.1` に bind し、同じホストからの接続のみを受け付けます。リモートユーザーが接続する場合は、同じホストに TLS reverse proxy を配置し、各呼び出し元の `Authorization` ヘッダーを変更せずに転送してください。

`--serve` モードでは `ANSIBLE_TOKEN` / `ANSIBLE_USERNAME` / `ANSIBLE_PASSWORD` は無視されます（設定されていると警告がログに出力されます）— サーバー自身は独自のアイデンティティを持ちません。

### 3. 中央サーバー - 利用者向け（`--remote`）

各ユーザーは、中央サーバーへリレーする stdio **プロキシ**を実行し、自分のトークンを `Authorization: Bearer` ヘッダーとして注入します。ローカルサーバーは起動されず、中央サーバーが稼働している必要があります。

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

`ANSIBLE_BASE_URL` は不要です（中央サーバーが AWX にアクセスします）。プロキシモードは**個人アクセストークン専用**です - `ANSIBLE_USERNAME`/`PASSWORD` は Bearer ヘッダーとして転送できません。ここでの `ANSIBLE_SSL_VERIFY`/`ANSIBLE_CA_BUNDLE` は AWX ではなく**中央サーバー**への接続を検証します。ローカルにも利用ログを残したい場合は `AWX_MCP_USAGE_LOG_FILE`（任意で `AWX_MCP_USAGE_USER`）を設定してください。

> `headers` ブロックで `${VAR}` 展開をサポートする MCP クライアントであれば、プロキシを介さず中央サーバーへ直接接続できます: `{ "type": "streamable-http", "url": "https://awx-mcp.example.com:8443/mcp", "headers": { "Authorization": "Bearer ${AWX_TOKEN}" } }`。

### 中央サーバーへの接続

管理者が中央の `awx-mcp --serve` インスタンスを運用している場合、ユーザーは 2 通りの方法で接続できます。どちらもユーザー自身の AWX トークンを送信しますが、推奨されるプロキシ方式ではトークンを環境変数に保持でき、あらゆる MCP クライアントで動作します。

**プロキシ（推奨）** - ローカル stdio プロセス。トークンは `ANSIBLE_TOKEN` に保持されます:

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

**Direct HTTP** - `headers` ブロックで `${VAR}` 展開をサポートする MCP クライアント向け（ローカルプロセスなし）:

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

sse トランスポート（`awx-mcp --serve --sse`）の場合は `"type": "sse"` と `/sse` エンドポイントを使用してください。

> **セキュリティ（重要）:** `--serve` モードでは各リクエストが呼び出し元自身の AWX トークンで認証され、AWX の RBAC がユーザーごとに適用されます。そのトークンはリクエストヘッダーで送信されるため、トランスポートを保護してください: プロセス内 TLS（`AWX_MCP_TLS_ENABLE`）を有効にするか、認証機能を持つ TLS リバースプロキシの背後に配置し、ファイアウォールでポートアクセスを制限してください。サーバーはデフォルトで `127.0.0.1` にバインドされ、TLS なしでループバック以外にバインドすると警告をログに出力します。

## 読み取り専用の境界と replica

中央サーバーで `AWX_MCP_READ_ONLY=true` を設定すると、書き込み/破壊的ツールをグローバルに除外します。プロキシ側の設定は `X-AWX-Read-Only` を送信し、その呼び出し元だけを制限します。クライアントを制御する呼び出し元はヘッダーを省略できるため、プロキシ設定は自主的な制限です。認可は AWX RBAC とサーバー側の方針で強制してください。

複数の Streamable HTTP replica を round-robin load balancer の背後で実行する場合は `AWX_MCP_STATELESS_HTTP=true` を設定します。stateful MCP session を使う場合は同じ replica にリクエストを送り続ける必要があります。ログパスは process または Pod ごとに分けてください。`TimedRotatingFileHandler` は複数 process による同時ローテーションに対応しません。

[TLS とログ](security.ja.md)
