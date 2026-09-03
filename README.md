# discord-bot

リュウキの Discord サーバー管理 Bot「kuroko-chan」の中身です。Claude Code のプラグインとして動きます。
Discord 社および Anthropic 社とは無関係の、非公式なコミュニティ製プラグインです。

Claude Code の公式 Discord プラグインに足りない機能を補う、自作の Claude Code プラグインです。
公式プラグイン（`discord@claude-plugins-official`）の上に乗せて使います。公式側はメッセージの
送受信だけを担当し、こちらは「セッションの管理」と「サーバーの管理」を担当する、という分担です。

Discord のチャンネル機能は 1 つのセッションを開きっぱなしにするので、コンテキストが溜まり続けます。
ところが、チャンネル経由のメッセージは Claude への入力テキストとして届くだけで、`/clear` などの
組み込みコマンドは実行されません（[anthropics/claude-code#37342](https://github.com/anthropics/claude-code/issues/37342)）。
このプラグインは、その穴を tmux とステータスラインの情報で埋めるところから始まりました。

## 機能

| 機能 | 状態 | 使い方 |
| --- | --- | --- |
| コンテキスト使用量の表示 | 済 | Discord で `/ctx` と送る。ctx / 5h / 7d の使用率をコードブロックで返す |
| Discord からのクリア | 済 | Discord で `/clear` と送る。宣言 → tmux ペインに `/clear` を送信 → 新セッション開始時に「クリアしたよ」を自動投稿 |
| Bot ステータスに使用量を常時表示 | 済 | 常駐スクリプトが Bot のアクティビティを `ctx 53% · 5h 46% · 7d 17%` に更新。ctx 80% 以上で赤、セッション無しで黄 |
| 起動ランチャー | 済 | `start-discord.sh` が tmux セッション `discord` に claude と常駐スクリプトを立てる。二重起動は防ぐ |
| サーバー管理 MCP | 済 | チャンネル・カテゴリ・フォーラムスレッドの作成・編集・削除・一覧（9 ツール）。`.mcp.json` で `server-admin` として自動起動 |
| チャンネル作成ワークフロー | 移植予定 | チャンネルを作ったあと、公式プラグインの `access.json` に受信設定を入れて受信テストまで行うスキルと、忘れ防止フック |

Claude Code から見たスキル名は `/discord-bot:ctx` と `/discord-bot:clear` です。
Discord 側で送る文字列は `/ctx` と `/clear` のままで構いません（「コンテキストどれくらい？」「クリアして」でも通ります）。

## 前提

- 公式 Discord プラグインが設定済みで、Bot トークンが `~/.claude/channels/discord/.env` にあること。
  サーバー管理 MCP を使うには、同じファイルに `DISCORD_GUILD_ID=<サーバーのID>` も書く
- tmux と uv が入っていること。Python のスクリプトはすべて `uv run --script` で動きます（shebang に書いてあるので直接実行できます）。
  常駐スクリプト以外は標準ライブラリだけ、常駐スクリプトは discord.py だけを使います
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

公式 Discord プラグインも同じ理由でプロジェクトスコープに絞ることを勧めます
（`~/.claude/settings.json` の `enabledPlugins` から外し、プロジェクトの `.claude/settings.json` で有効にする）。

### 2. ステータスラインの JSON を保存する

`/ctx` と常駐スクリプトは、Claude Code がステータスライン用に渡してくる JSON
（`context_window` や `rate_limits` を含む）を `~/.claude/tmp/statusline/<session_id>.json` から読みます。
どちらかの方法で保存されるようにしてください。

- 自分の statusline スクリプトに保存処理を足す。`_dumped_at`（ISO 形式の時刻）と `_claude_pid`
  （Claude Code 本体の PID。親プロセスをたどって探す）も一緒に入れます。実装例は `scripts/statusline_dump.py` にあります
- または `settings.json` の `statusLine.command` をラッパー経由にする（`uv` が PATH に無い環境では `/opt/homebrew/bin/uv` のようにフルパスで書く）

```json
{
  "statusLine": {
    "type": "command",
    "command": "uv run ~/Desktop/work/claude-discord-channel/discord-bot/scripts/statusline_dump.py -- <元のコマンド>"
  }
}
```

保存が無くても `/ctx` は会話ログから概算を出しますが、5h/7d は出ず、常駐スクリプトも対象を見つけられません。

古いダンプ（Claude Code 本体が終了済みで 24 時間以上更新の無いファイル）は `statusline_dump.py` が
書き込みのたびに自動で消します。走査はディレクトリ1回だけで、例外は握りつぶすので statusline の表示は
邪魔しません。自分の statusline スクリプトに保存処理を足す方式を選んだ場合は、`statusline_dump.py` の
`prune_stale_dumps(dump_dir, keep_path=...)` 関数をそのまま自分のスクリプトへ写し、書き込み直後に
`keep_path` に今回書いたファイルのパスを渡して呼んでください（`_claude_pid` が無いファイルは更新時刻だけで判定します）。

### 3. 起動する

Discord セッションに使うプロジェクトのディレクトリで実行します。`~/.local/bin/discord-start` のような
シンボリックリンクを作っておくと短く呼べます。

```sh
scripts/start-discord.sh                       # 新規セッション
scripts/start-discord.sh --resume <session-id> # 会話を引き継ぐ（追加引数はそのまま claude に渡る）
```

tmux セッション `discord` に、claude のウィンドウと presence（常駐スクリプト）のウィンドウができます。
`tmux attach -t discord` で覗けます。止めるときは presence ウィンドウを閉じるだけです。

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
常駐スクリプトが最大 20 秒ごとに拾います）。何もしていない間は変わりません。カード 2 行目の
「更新 HH:MM」が最後に再描画された時刻です。

## 仕組み

`/clear` の流れです。

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

- `/clear` はターン実行中でもキューされ、ターン終了直後に実行されます。プロセスと MCP 接続（Discord ブリッジ）は残り、セッション ID だけ変わります
- 手動でターミナルから `/clear` した場合はマーカーが無いので通知しません。10 分より古いマーカーも無視します
- 常駐スクリプトは「cwd が対象プロジェクトで、`_claude_pid` のプロセスが生きているセッション」のうち、
  `--channels` 付きで起動されたものを優先し、その中で最新のダンプを使います
- Bot が送れるアクティビティのフィールドは name / type / state / url だけです。`DISCORD_PRESENCE_MODE` で
  playing / watching / listening / competing / custom を選べます（既定 playing。custom は吹き出し表示で狭い）

GitHub のリポジトリ（https://github.com/ryuki-imachi/claude-code-discord-bot）から入れる場合は、
`claude plugin marketplace add ryuki-imachi/claude-code-discord-bot` で marketplace を登録します。

## 更新のしかた

インストール時にプラグインは `~/.claude/plugins/cache/ryuki-plugins/discord-bot/<version>/` へコピーされます。
このリポジトリを編集してコミットしたら、`plugin.json` と `marketplace.json` の `version` を上げてから反映します。

```sh
cd <Discord セッションに使うプロジェクト>
claude plugin update discord-bot@ryuki-plugins --scope project
```

そのあと、動いている Discord セッションで `/reload-plugins` を打つか、セッションを再起動します。
ローカルディレクトリ由来のプラグインはスキル本文を元ディレクトリから直接読んでいるようなので
（`${CLAUDE_SKILL_DIR}` が元のパスを指す）、`/reload-plugins` だけで反映されることも多いです。

## サーバー管理 MCP

`mcp/server-admin/` にある自作 MCP サーバー（Python + FastMCP + httpx、stdio）が、Discord REST API v10 を
直接呼び出してチャンネル・カテゴリ・フォーラムスレッドを操作します。公式プラグインと同じ
`~/.claude/channels/discord/.env` の `DISCORD_BOT_TOKEN` / `DISCORD_GUILD_ID` を読みます
（環境変数 `DISCORD_BOT_TOKEN` / `DISCORD_GUILD_ID` が既にあればそちらを優先）。

| ツール | 内容 |
| --- | --- |
| `list_channels` | サーバーのチャンネル一覧を取得する |
| `create_channel` | 新しいチャンネルを作成する（テキスト / アナウンス / フォーラム）。作成したチャンネルは公式プラグインの `access.json` に自動で追加される |
| `create_category` | チャンネルカテゴリを作成する |
| `edit_channel` | チャンネルの名前やトピックを変更する |
| `delete_channel` | チャンネルを削除する。`access.json` からも自動で削除される |
| `create_forum_thread` | フォーラムチャンネルにスレッドを作成する |
| `list_threads` | 指定チャンネル（フォーラム等）のアクティブなスレッド一覧を取得する |
| `close_thread` | スレッドをクローズ（アーカイブ）する。`lock` でロックも可能 |
| `reopen_thread` | クローズ済みのスレッドを再開する |

Claude Code から見えるツール名は `mcp__plugin_discord-bot_server-admin__<tool>` の形になります
（`/mcp` かツール一覧で実際の名前を確認してください）。

## 制約と注意

- Discord セッションは tmux の中で動かす前提です。tmux の外やリモート（SDK）セッションでは `/clear` を送れず、Claude がその旨を Discord に伝えます
- `--channels` 付きの claude を 2 つ立てると Discord に二重返信します。ランチャーは検出して止めますが、手で起動するときは注意してください
- Bot のステータスをプログラムから読み取るには Developer Portal で Presence Intent を有効にする必要があります（設定するだけなら不要）。`scripts/discord_presence_check.py` は確認用です
- `/compact` は対象外です。同じ仕組みで送れますが、要約中に Discord 側が無音になるので用意していません

## ディレクトリ構成

```
.claude-plugin/plugin.json          マニフェスト
.claude-plugin/marketplace.json     このディレクトリをローカル marketplace として登録するための定義
.mcp.json                           サーバー管理 MCP（server-admin）の起動定義
mcp/server-admin/                   サーバー管理 MCP サーバー本体（Python + FastMCP + httpx）
skills/ctx/                         /discord-bot:ctx
skills/clear/                       /discord-bot:clear
hooks/hooks.json                    SessionStart(clear) で完了通知
hooks/notify-clear-done.py           完了通知の本体（Discord REST API へ投稿）
scripts/discord_presence.py         Bot ステータスに使用量を常時表示する常駐（uv run）
scripts/discord_presence_check.py   自 Bot のプレゼンスを読む確認用
scripts/start-discord.sh            tmux セッション discord に claude と presence を起動するランチャー
scripts/statusline_dump.py          ステータスライン JSON を保存するラッパー
```

状態ファイルは `~/.claude/discord-bot/`（`pending-clear.json`、`clear-notify.log`）に置きます。

## ライセンス

MIT License です。公式 Discord プラグイン（`anthropics/claude-plugins-official`）のコードは含んでいません。
公式は Apache-2.0 なので、将来フォークしたファイルを同梱する場合は、そのファイルだけ Apache-2.0 の表示を残します。
