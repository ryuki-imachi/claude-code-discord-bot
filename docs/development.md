# 開発と更新

## 更新のしかた

インストール時にプラグインは `~/.claude/plugins/cache/ryuki-plugins/discord-bot/<version>/` へコピーされます。
このリポジトリを編集してコミットしたら、`plugin.json` と `marketplace.json` の `version` を上げてから反映します。

```sh
cd <Discord セッションに使うプロジェクト>
claude plugin update discord-bot@ryuki-plugins --scope project
```

そのあと、動いている Discord セッションで `/reload-plugins` を打つとスキルとフックが入れ替わります。
ただし MCP サーバー（channel サーバーと server-admin）は、`.mcp.json` の設定が変わらない限り `/reload-plugins` では
再起動されません。`channel/` や `mcp/` のコードを変えたときや、`~/.claude/discord-bot/commands.json` に
コマンドを足したときは、セッションを再起動してください（`scripts/start-discord.sh --resume <session-id>` で会話は引き継げます）。
ローカルディレクトリ由来のプラグインはスキル本文を元ディレクトリから直接読んでいるようなので
（`${CLAUDE_SKILL_DIR}` が元のパスを指す）、`/reload-plugins` だけで反映されることも多いです。

channel サーバーの元になった公式プラグインは `discord@claude-plugins-official` の 0.0.4 です。
上流に変更があったら `channel/server.ts` に取り込みます（差分の要点はファイル先頭のコメントに書いてあります）。

## ディレクトリ構成

```
.claude-plugin/plugin.json          マニフェスト
.claude-plugin/marketplace.json     このディレクトリをローカル marketplace として登録するための定義
.mcp.json                           MCP サーバーの登録（discord = channel サーバー、server-admin = サーバー管理）
channel/                            Discord channel サーバー（公式プラグインのフォーク、Apache-2.0）
  server.ts                         送受信・アクセス制御・権限中継（上流 0.0.4 + 改変）
  presence.ts                       Bot ステータスへの使用量表示
  commands.ts / commands.json       スラッシュコマンドの登録と、スキル呼び出しへの変換
  ACCESS.md / UPSTREAM-README.md    上流のドキュメント
mcp/server-admin/                   サーバー管理 MCP（Python、uv）
skills/access/ skills/configure/    アクセス管理とトークン設定（上流のスキルを名前空間だけ変えたもの）
skills/ctx/                         /discord-bot:ctx
skills/clear/                       /discord-bot:clear
skills/setup-channel/               /discord-bot:setup-channel
hooks/hooks.json                    SessionStart(clear) の完了通知、PostToolUse(create_channel) の受信設定リマインド
hooks/notify-clear-done.py
hooks/remind-channel-access.py
scripts/start-discord.sh            tmux セッション discord に claude を起動するランチャー
scripts/statusline_dump.py          ステータスライン JSON を保存するラッパー（古いダンプの掃除つき）
scripts/discord_presence_check.py   自 Bot のプレゼンスを読む確認用（Presence Intent が必要）
docs/migration-plan.md              移植の手順書と公開前チェックリスト
```

状態ファイルは `~/.claude/discord-bot/`（`pending-clear.json`、`clear-notify.log`）に、
Discord の設定は公式プラグインと同じ `~/.claude/channels/discord/`（`.env`、`access.json`）に置きます。

## 移植の経緯

手順書と公開前チェックリストは [migration-plan.md](migration-plan.md) にあります。
