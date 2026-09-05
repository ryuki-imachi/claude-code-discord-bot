# 仕組み

## /clear の流れ

![/clear の流れ](diagrams/clear-flow.png)

- `/clear` はターン実行中でもキューされ、ターン終了直後に実行されます。プロセスと MCP 接続は残り、セッション ID だけ変わります
- 手動でターミナルから `/clear` した場合はマーカーが無いので通知しません。10 分より古いマーカーも無視します
- 送り先の特定は `CLAUDE_PID` → その TTY → 同じ TTY を持つ tmux ペイン、の順です。tmux の外では NG を返します

## /model と /effort の流れ

`/clear` と同じ「ペイン特定 → tmux send-keys」の仕組みを使い回します。ペイン特定と送信そのものは
`scripts/tmux_send_slash.sh` に共通化してあり、`clear_session.sh` もこれを呼び出しています。

- `scripts/switch_setting.py --kind model|effort --value <v> --chat-id <id>` が、引数（model のエイリアス /
  完全なモデルID、effort の `low` `medium` `high` `xhigh` `max` `auto`）を検証したうえで
  `tmux_send_slash.sh` 経由で `/model <v>` や `/effort <v>` を送ります。無効な値は何も送らず `NG:` で終わります
- 送信直後の応答では「切り替わった」とは言い切れません（スラッシュコマンドはターン終了直後に実行されるため）。
  そこで送信に成功すると、`switch_setting.py` は自分自身を `--watch` サブコマンドで再実行する監視プロセスを
  `subprocess.Popen(start_new_session=True)` で切り離して起動します。Bash ツールがコマンド終了後に子プロセスを
  片付けることがあるため、確実に生き残るようにこの形にしています
- 監視プロセスは最大 90 秒、2 秒おきにステータスラインのダンプ（`model.id` / `model.display_name` /
  `effort.level`）を読み直し、送信前の値から変わった（または指定した値と一致した）ことを検知したら、
  `hooks/notify-clear-done.py` と同じ方法（Discord REST の `POST /channels/{chat_id}/messages`）で
  「モデルを Sonnet 5 に切り替えたよ（effort high）」のように投稿して終了します。タイムアウトしたら
  何も投稿せず `~/.claude/discord-bot/switch-notify.log` に記録するだけです（検知できなくても、次の
  メッセージからは新しい設定で応対します）
- `/model <alias>` の引数指定は「切り替えてデフォルトとして保存」する挙動（ピッカーの Enter 相当）です。
  セッション限定にする指定方法は無いため、ターミナルで新しく開く他のセッションのデフォルトモデルも変わります。
  `effort` の `low`〜`xhigh` はモデルごとに保存されますが、`max` はセッション限り、`auto` は保存済み設定をクリアします

## Bot ステータス

![Bot ステータスのデータの流れ](diagrams/presence.png)

`channel/presence.ts` が、channel サーバーを起動した Claude Code 本体の PID を親プロセスをたどって特定し、
その PID を `_claude_pid` に持つステータスラインのダンプを 20 秒ごとに読んでアクティビティを更新します
（見つからなければ、生きているセッションの最新のダンプを使います）。ctx 80% 以上で取り込み中（赤）、
対象が無ければ退席中（黄）です。
Bot が送れるアクティビティのフィールドは name / type / state / url だけです。`DISCORD_PRESENCE_MODE` で
playing（既定）/ watching / listening / competing / custom を選べます（custom は吹き出し表示で狭い）。

## スラッシュコマンド

![スラッシュコマンドの流れ](diagrams/slash-command.png)

channel サーバーは起動時に、Bot が参加している各サーバーへスラッシュコマンドを登録します（ギルドコマンドなので即時反映）。
定義は `channel/commands.json`（同梱: `/ctx`、`/clear`、`/model`、`/effort`）と、`~/.claude/discord-bot/commands.json`（追加分）を合わせたものです。
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

## サーバー管理 MCP

`mcp/server-admin/` は Python（FastMCP + httpx）の MCP サーバーで、Discord REST API v10 を直接呼びます。
ツールは list_channels / create_channel / create_category / edit_channel / delete_channel /
create_forum_thread / list_threads / close_thread / reopen_thread の 9 つです。
Claude から見たツール名は `mcp__plugin_discord-bot_server-admin__<tool>` になります。
`create_channel` の直後には `hooks/remind-channel-access.py` が「access.json に受信設定を入れる」ことを促す注意書きを注入します。
`requireMention` が `true` のままだとメンション無しの投稿が届かない、という公式プラグインの落とし穴を塞ぐためです。

## 制約と注意

- Discord セッションは tmux の中で動かす前提です。tmux の外やリモート（SDK）セッションでは `/clear` `/model` `/effort` を送れず、Claude がその旨を Discord に伝えます
- `--channels` 付きの claude を 2 つ立てると Discord に二重返信します。ランチャーは検出して止めますが、手で起動するときは注意してください
- Bot のステータスをプログラムから読み取るには Developer Portal で Presence Intent を有効にする必要があります（設定するだけなら不要）。`scripts/discord_presence_check.py` は確認用です
- `/compact` は対象外です。同じ仕組みで送れますが、要約中に Discord 側が無音になるので用意していません

## channel プラグインの承認リスト

Claude Code は `--channels` に渡された channel プラグインを承認リスト（Anthropic 側の設定 `tengu_harbor_ledger`、
`{plugin, marketplace}` の配列）と突き合わせ、載っていなければ「not on the approved channels allowlist」として
通知を捨てます。公式の `discord@claude-plugins-official` は載っていますが、フォークしたこのプラグインは載っていません。

回避策は 2 つあります。

- 管理者設定 `allowedChannelPlugins` に同じ形式で書く（README のセットアップ 4）。管理者設定が承認リストの代わりになります
- `--dangerously-load-development-channels plugin:discord-bot@ryuki-plugins` を付けて起動する。起動時に
  「WARNING: Loading development channels」の確認が出て、承認すると読み込まれます。ただし 2026-09-03 の検証では
  この環境（Claude Max、macOS、tmux）で確認ダイアログが出ずフラグが無視されました。同じ症状が
  anthropics/claude-code#82939 で報告されています。
  `--channels` と両方に同じプラグインを渡すと `--channels` 側で判定されて弾かれるので、付けるなら開発フラグだけにします
