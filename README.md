# discord-bot

リュウキの Discord サーバー管理 Bot「kuroko-chan」の中身です。Claude Code のプラグインとして動きます。
Discord 社および Anthropic 社とは無関係の、非公式なコミュニティ製プラグインです。

Claude Code の Discord チャンネル機能（`claude --channels ...`）は、Discord のメッセージを Claude の会話に流し込みます。
公式の Discord プラグインはメッセージの送受信だけを担当していて、セッションの管理（コンテキストの残量確認やクリア）や
サーバーの管理（チャンネルやスレッドの操作）はできません。このプラグインは、公式プラグインの channel サーバーを
フォークして土台にし、その上にセッション管理・サーバー管理・Bot ステータス表示を足したものです。

## 機能

| 機能 | 使い方 |
| --- | --- |
| Discord との送受信 | 公式プラグインからフォークした channel サーバー（`channel/`）。reply / react / edit_message / fetch_messages / download_attachment |
| アクセス管理 | `/discord-bot:access`（ペアリング承認・allowlist・チャンネルの受信設定）と `/discord-bot:configure`（Bot トークンの保存）。公式と同じ `~/.claude/channels/discord/` を使う |
| コンテキスト使用量の表示 | Discord で `/ctx` と送る。ctx / 5h / 7d の使用率をコードブロックで返す（`/discord-bot:ctx`） |
| Discord からのクリア | Discord で `/clear` と送る。宣言 → tmux ペインに `/clear` を送信 → 新セッション開始時に「クリアしたよ」を自動投稿（`/discord-bot:clear`） |
| Bot ステータスに使用量を常時表示 | channel サーバーが Bot のアクティビティを `ctx 53% · 5h 46% · 7d 17%` に更新。ctx 80% 以上で赤、セッション無しで黄 |
| サーバー管理 MCP | チャンネル・カテゴリ・フォーラムスレッドの作成・編集・削除・一覧（`server-admin`、9 ツール） |
| チャンネル作成ワークフロー | `/discord-bot:setup-channel`。作成 → access.json の受信設定 → 受信テストまで。作成直後にフックが受信設定を促す |
| 起動ランチャー | `scripts/start-discord.sh` が tmux セッション `discord` で `claude --channels plugin:discord-bot@ryuki-plugins` を立てる。二重起動は防ぐ |

`/ctx` と `/clear` は Discord のスラッシュコマンド（補完付き）としても登録されます。文字列で送っても
（「コンテキストどれくらい？」「クリアして」でも）同じように通ります。

## 前提

- tmux、uv、bun が入っていること。Python のスクリプトは `uv run --script`、channel サーバーは bun で動きます
- Discord の Bot が作ってあり、Message Content Intent が有効で、サーバーに招待済みであること
  （作り方は `channel/UPSTREAM-README.md` の Quick Setup 1〜3 と同じ）
- macOS で動作確認しています。`ps` の使い方が BSD 系前提なので、Linux では微調整が要るかもしれません

## セットアップ

### 1. プラグインを入れる

このリポジトリ自体がローカル marketplace（`ryuki-plugins`）になっています。Discord セッションに使う
プロジェクトのディレクトリで、プロジェクトスコープで有効化します。全プロジェクトで有効にしないのは、
プラグインの MCP サーバーが有効なセッション全部で立ち上がり、同じ Bot トークンで何本も接続してしまうためです。

```sh
claude plugin marketplace add ~/Desktop/work/claude-discord-channel/discord-bot
cd <Discord セッションに使うプロジェクト>
claude plugin install discord-bot@ryuki-plugins --scope project
```

GitHub のリポジトリ（https://github.com/ryuki-imachi/claude-code-discord-bot）から入れる場合は、
`claude plugin marketplace add ryuki-imachi/claude-code-discord-bot` で marketplace を登録します。

公式の Discord プラグイン（`discord@claude-plugins-official`）を使っていた場合は無効にしてください
（同じトークンで Gateway 接続が 2 本になり、Discord への返信が二重になります）。設定ファイルは共有しているので、
ペアリングや allowlist はそのまま引き継がれます。

### 2. Bot トークンとギルド

`/discord-bot:configure <トークン>` で `~/.claude/channels/discord/.env` に保存します（公式プラグインで設定済みならそのまま）。
サーバー管理 MCP の `DISCORD_GUILD_ID` は省略可です。Bot が 1 つのサーバーにしか入っていなければ起動時に自動で判定します。
複数のサーバーに入れている場合だけ、同じファイルに `DISCORD_GUILD_ID=<サーバーのID>` を書いてください。

### 3. ステータスラインの JSON を保存する

`/ctx` と Bot ステータス表示は、Claude Code がステータスライン用に渡してくる JSON
（`context_window` や `rate_limits` を含む）を `~/.claude/tmp/statusline/<session_id>.json` から読みます。
どちらかの方法で保存されるようにしてください。

- `settings.json` の `statusLine.command` をラッパー経由にする（`uv` が PATH に無い環境ではフルパスで書く）

```json
{
  "statusLine": {
    "type": "command",
    "command": "uv run ~/Desktop/work/claude-discord-channel/discord-bot/scripts/statusline_dump.py -- <元のコマンド>"
  }
}
```

- または自分の statusline スクリプトに保存処理を足す。`_dumped_at`（ISO 形式の時刻）と `_claude_pid`
  （Claude Code 本体の PID。親プロセスをたどって探す）も一緒に入れます。実装例は `scripts/statusline_dump.py` にあります。
  古いダンプは同スクリプトの `prune_stale_dumps()` が書き込みのたびに消すので、これも写して呼んでください

保存が無くても `/ctx` は会話ログから概算を出しますが、5h/7d は出ず、Bot ステータスも「セッションなし」のままになります。

### 4. 起動する

Discord セッションに使うプロジェクトのディレクトリで実行します。`~/.local/bin/discord-start` のような
シンボリックリンクを作っておくと短く呼べます。

```sh
scripts/start-discord.sh                       # 新規セッション
scripts/start-discord.sh --resume <session-id> # 会話を引き継ぐ（追加引数はそのまま claude に渡る）
```

tmux セッション `discord` の中で `claude --channels plugin:discord-bot@ryuki-plugins` が動きます。
初回は DM でペアリングコードが返るので `/discord-bot:access pair <コード>` で承認し、チャンネルごとの受信設定は
`/discord-bot:access group add <チャンネルID> --no-mention` か `/discord-bot:setup-channel` で行います。

## 使い方

Discord のチャンネルで `/ctx` と送ると、次のような返事が来ます。

```
コンテキスト使用量
ctx ■■■■■□□□□□ 54%  544.8K / 1000.0K tokens
5h  ■■■■■□□□□□ 48%  リセット 09/03 00:00
7d  ■□□□□□□□□□ 13%  リセット 09/06 19:00
セッション 1c5a207c  Fable 5.1  計測 09/02 23:00:54  source statusline
```

`/clear` と送ると「クリアするね（今 54%）」と返事があり、数秒後に「コンテキストをクリアしたよ」が届きます。
その次のメッセージから新しいセッションになります。作業途中の要点は、クリア前に台帳などへ書いておいてください。

Bot のステータスは Claude が応答するたびに更新されます（ステータスラインが再描画された時点の値を、
channel サーバーが最大 20 秒ごとに拾います）。何もしていない間は変わりません。カード 2 行目の
「更新 HH:MM」が最後に再描画された時刻です。

チャンネルを増やしたいときは Discord で「〇〇というチャンネル作って」と頼めば `/discord-bot:setup-channel` が
作成から受信設定、受信テストまで案内します。

## 仕組み

### /clear の流れ

```
Discord「/clear」
  → Claude が /discord-bot:clear を実行
     1. context_usage.py で使用量を取得
     2. reply「クリアするね（今 54%）」
     3. clear_session.sh --chat-id <chat_id>
          CLAUDE_PID → その TTY → 同じ TTY を持つ tmux ペイン を特定
          ~/.claude/discord-bot/pending-clear.json にマーカーを書く
          tmux send-keys '/clear' Enter（ターン中なのでキューされる）
     4. ツールを呼ばずにターンを終える
  → キューされた /clear が実行され、新しいセッションが始まる
  → SessionStart(clear) フック notify-clear-done.py
       マーカーを読んで Discord REST API で「クリアしたよ」を投稿し、マーカーを消す
```

- `/clear` はターン実行中でもキューされ、ターン終了直後に実行されます。プロセスと MCP 接続は残り、セッション ID だけ変わります
- 手動でターミナルから `/clear` した場合はマーカーが無いので通知しません。10 分より古いマーカーも無視します

### Bot ステータス

`channel/presence.ts` が、channel サーバーを起動した Claude Code 本体の PID を親プロセスをたどって特定し、
その PID を `_claude_pid` に持つステータスラインのダンプを 20 秒ごとに読んでアクティビティを更新します
（見つからなければ、生きているセッションの最新のダンプを使います）。
Bot が送れるアクティビティのフィールドは name / type / state / url だけです。`DISCORD_PRESENCE_MODE` で
playing（既定）/ watching / listening / competing / custom を選べます（custom は吹き出し表示で狭い）。

### スラッシュコマンド

channel サーバーは起動時に、Bot が参加している各サーバーへスラッシュコマンドを登録します（ギルドコマンドなので即時反映）。
定義は `channel/commands.json`（同梱: `/ctx`、`/clear`）と、`~/.claude/discord-bot/commands.json`（追加分）を合わせたものです。
ワークスペース固有のコマンドは追加分のファイルに書きます。同名なら追加分が勝ちます。

```js
[
  {
    "name": "task",
    "description": "タスク台帳を操作する",
    "skill": "/task-memo",
    "options": [
      { "name": "text", "description": "操作と内容（例: 追加 明日〇〇する）", "required": true }
    ]
  }
]
```

コマンドを受けると、送信者が allowlist に居ることと送信先が受信設定済みのチャンネル（または DM）であることを確認し、
3 秒以内に「受け付けたよ」を本人にだけ見える形で返してから、`<skill> <引数...>` の 1 行を Claude に渡します
（例: `/discord-bot:ctx`、`/task-memo 追加 明日〇〇する`）。Claude はそれをスキル呼び出しとして実行し、結果を
通常のメッセージとしてチャンネルに投稿します。登録には Bot の招待時に `applications.commands` スコープが必要で、
無い場合は起動ログに再認可用の URL が出ます。`DISCORD_SLASH_COMMANDS=off` で登録を止められます。

### サーバー管理 MCP

`mcp/server-admin/` は Python（FastMCP + httpx）の MCP サーバーで、Discord REST API v10 を直接呼びます。
ツールは list_channels / create_channel / create_category / edit_channel / delete_channel /
create_forum_thread / list_threads / close_thread / reopen_thread の 9 つです。
Claude から見たツール名は `mcp__plugin_discord-bot_server-admin__<tool>` になります。
`create_channel` の直後には `hooks/remind-channel-access.py` が「access.json に受信設定を入れる」ことを促す注意書きを注入します。
`requireMention` が `true` のままだとメンション無しの投稿が届かない、という公式プラグインの落とし穴を塞ぐためです。

## 更新のしかた

インストール時にプラグインは `~/.claude/plugins/cache/ryuki-plugins/discord-bot/<version>/` へコピーされます。
このリポジトリを編集してコミットしたら、`plugin.json` と `marketplace.json` の `version` を上げてから反映します。

```sh
cd <Discord セッションに使うプロジェクト>
claude plugin update discord-bot@ryuki-plugins --scope project
```

そのあと、動いている Discord セッションで `/reload-plugins` を打ちます。channel サーバーもこのとき再起動されます。
ローカルディレクトリ由来のプラグインはスキル本文を元ディレクトリから直接読んでいるようなので
（`${CLAUDE_SKILL_DIR}` が元のパスを指す）、`/reload-plugins` だけで反映されることも多いです。

channel サーバーの元になった公式プラグインは `discord@claude-plugins-official` の 0.0.4 です。
上流に変更があったら `channel/server.ts` に取り込みます（差分の要点はファイル先頭のコメントに書いてあります）。

## 制約と注意

- Discord セッションは tmux の中で動かす前提です。tmux の外やリモート（SDK）セッションでは `/clear` を送れず、Claude がその旨を Discord に伝えます
- `--channels` 付きの claude を 2 つ立てると Discord に二重返信します。ランチャーは検出して止めますが、手で起動するときは注意してください
- Bot のステータスをプログラムから読み取るには Developer Portal で Presence Intent を有効にする必要があります（設定するだけなら不要）。`scripts/discord_presence_check.py` は確認用です
- `/compact` は対象外です。同じ仕組みで送れますが、要約中に Discord 側が無音になるので用意していません

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

## ライセンス

このリポジトリは MIT License です。ただし `channel/` は公式 Discord プラグイン
（`anthropics/claude-plugins-official`、Apache-2.0）のフォークなので、そのディレクトリのファイルは
Apache-2.0 のままです（`channel/LICENSE`）。改変した内容は `channel/server.ts` の先頭に書いてあります。
