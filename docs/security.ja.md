# TLS、ログ、機密データの扱い

[README](../README.ja.md) | [English](security.md) | [한국어](security.ko.md) | [日本語](security.ja.md)

## TLS / 証明書検証

TLS 証明書検証は**デフォルトで有効**です（`ANSIBLE_SSL_VERIFY=true`）。AWX インスタンスがプライベート/内部 CA が発行した証明書（または自己署名証明書）を使用している場合は、`ANSIBLE_CA_BUNDLE` に CA バンドル（PEM）のパスを設定してください - 検証を有効にしたままそのCAを信頼できるようになり、検証を無効化するより推奨される方法です。

`ANSIBLE_SSL_VERIFY=false` を設定すると検証が完全に無効になります。この値が使用されるたびにサーバーが警告をログに出力するため、開発環境でのみ使用してください。スキームのない `ANSIBLE_BASE_URL` ホストは自動的に `https://` へ引き上げられます。明示的な `http://` URL はそのまま使用されますが、API トークンが暗号化されずに送信されるため、サーバーが警告をログに出力します。

## HTTPS で配信（インバウンド TLS）

これは**インバウンド** TLS です - MCP クライアントからこのサーバーへの接続を暗号化するもので、`ANSIBLE_SSL_VERIFY` が制御するアウトバウンドの AWX 証明書検証とは方向が異なります。両者を混同しないでください。

`--serve` の中央サーバー（streamable-http または sse）にのみ適用されます。ローカル stdio モードはネットワークソケットを持たないローカルパイプであるため TLS は適用されず、セキュリティはプロセス/ホストの分離によって確保されます。

有効化するには、`AWX_MCP_TLS_ENABLE=true` とともに `AWX_MCP_TLS_CERT`、`AWX_MCP_TLS_KEY` を設定してください（鍵が暗号化されている場合は `AWX_MCP_TLS_KEY_PASSWORD` も設定）:

```bash
export AWX_MCP_TLS_ENABLE=true
export AWX_MCP_TLS_CERT=/path/to/server.crt
export AWX_MCP_TLS_KEY=/path/to/server.key
uvx --from git+https://github.com/lycorp-jp/awx-mcp awx-mcp --serve --host 127.0.0.1 --port 8443
```

**重要:** `--serve` モードでは各リクエストが `Authorization` ヘッダー内の呼び出し元自身の AWX トークンによって*実際に認証*されており、TLS はそのトークンを転送時に保護します。そのため、ネットワークに公開するデプロイでは TLS を有効化する（または認証機能を持つ TLS リバースプロキシの背後に配置する）ことは任意ではなく重要です。ループバック以外にバインドしつつ TLS が無効な場合、起動時に警告がログに出力されます。Kubernetes では ingress で TLS を終端するのが一般的な方法であり、プロセス内 TLS は Pod までのエンドツーエンド暗号化が必要な場合にのみ必要です。

## 詳細利用ログ

利用ログは opt-in 方式です。`AWX_MCP_USAGE_LOG_FILE` に書き込み可能なパスを設定すると、ツール呼び出しごとに 1 件の JSON ドキュメントを JSON Lines: https://jsonlines.org/ 形式で記録し始めます。この形式は Filebeat や Fluentd などの外部ログ収集基盤が後で収集・集計しやすいように設計されています。ログが stdout に出力されることはありません - MCP stdio トランスポートはプロトコルメッセージの送受信に stdout を使用するため、ここにログを書き込むとプロトコルストリームが破損します。サーバー自体がログデータをネットワーク経由で送信することもなく、設定したローカルファイルにのみ書き込みます。

すべてのログ行には `type` フィールドがあり、種類ごとに分離できます: `"tool"`（通常の MCP ツール呼び出し）、`"internal_api"`（サーバーが呼び出す `/api/v2/me/` ユーザー解決リクエスト。`tool: "me"` として記録し、HTTP メソッドとパスは別の `method`/`endpoint` フィールドに記録）、`"access"`（HTTP アクセスログ）、`"diagnostic"`（サーバー診断ログ）。`type` フィールドと共通の `@timestamp` タイムスタンプフィールドは 4 種類のレコードで一貫しているため、単一のログインデックスを type でフィルタできます。ツール呼び出しレコードには `params`（呼び出し引数）も含まれ、秘密を示すキー（password、token、key、`inputs` など）や文字列内の `token=`/`password=`/`Bearer` の値はマスキングされます。

`auth_mode` フィールドは `static`（ローカル）または `passthrough`（`--serve`）です。`transport` フィールドは `stdio`、`streamable-http`、`sse`、`proxy` のいずれかです。中央サーバーでは、`user` フィールドは各リクエストのトークンに紐づく AWX アカウントです（ユーザーごとの帰属。トークンごとに一度だけ解決してキャッシュされ、生のトークンやそのハッシュがログに残ることはありません）。`--remote` プロキシ自身のローカルログでは、`transport` は `proxy`、`user` は `AWX_MCP_USAGE_USER`（未設定なら `local`）、`awx_host` は中央サーバーのホストになります。

各 replica に固有のファイルパスを割り当ててください。利用/アクセスのファイルログを無効にしても、その記録が別の出力に送られるわけではありません。診断ログだけは stderr に引き続き出力され、プラットフォーム側で収集できます。

## 機密データとログの限界

マスキングは認識可能な秘密のキー名と一般的な token/password パターンを対象とします。インベントリ変数、自由記述、ジョブ出力に含まれる任意の秘密をすべて除去する保証はありません。ログと MCP 結果は機密データを含むものとして扱い、ファイルアクセスと保持期間を制限し、クライアント側のログも確認してください。DEBUG はさらに多くの応答内容を露出させる場合があります。

認証情報/ユーザー書き込みツール 4 個は Form mode elicitation で機密情報を収集するため opt-in です。この方法は機密データの Form mode 入力を禁じる MCP 規則に準拠しません。信頼できる隔離されたローカル環境のみで有効にし、`--serve` と併用しないでください。開示方針と脅威モデルは [SECURITY.md](../SECURITY.md) を参照してください。
