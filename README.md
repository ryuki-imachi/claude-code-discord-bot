# discord-session

Claude Code の Discord チャンネルセッション（`claude --channels plugin:discord@claude-plugins-official`）を
Discord 側から管理するためのプラグインです。公式 Discord プラグインの上に乗せて使います。

チャンネル経由のメッセージは Claude への入力テキストとして届くだけで、`/clear` などの組み込みコマンドは
実行されません（[anthropics/claude-code#37342](https://github.com/anthropics/claude-code/issues/37342)）。
このプラグインは、その穴を tmux とステータスラインの情報で埋めます。

## できること

| Discord で送る | 動き |
| --- | --- |
| `/ctx` | コンテキスト使用率・5h/7d の利用上限をコードブロックで返す |
| `/clear` | 宣言の返信 → tmux ペインに `/clear` を送信 → 新セッション開始時にフックが「クリアしたよ」を投稿 |
| （常時） | Bot のステータスに `ctx 53% · 5h 46% · 7d 17%` を表示。ctx 80% 以上で赤、セッション無しで黄 |

## 構成

```
.claude-plugin/plugin.json          マニフェスト
.claude-plugin/marketplace.json     このディレクトリ自体をローカル marketplace として登録するための定義
skills/ctx/                         /discord-session:ctx  使用量の表示
skills/clear/                       /discord-session:clear  tmux 経由の /clear
hooks/hooks.json                    SessionStart(clear) で完了通知
hooks/notify-clear-done.sh
scripts/discord_presence.py         Bot ステータスに使用量を常時表示する常駐（uv run）
scripts/discord_presence_check.py   自 Bot のプレゼンスを読む確認用（Presence Intent が必要）
scripts/start-discord.sh            tmux セッション discord に claude と presence を起動するランチャー
scripts/statusline_dump.py          ステータスライン JSON を保存するラッパー（statusline を改造したくない人向け）
```

状態ファイルは `~/.claude/discord-session/`（`pending-clear.json`、`clear-notify.log`）、
ステータスラインのダンプは `~/.claude/tmp/statusline/<session_id>.json` に置きます。

## 前提

- 公式 Discord プラグイン（`discord@claude-plugins-official`）が設定済みで、Bot トークンが
  `~/.claude/channels/discord/.env` にあること
- tmux と uv が入っていること
- ステータスラインのダンプ（後述）

## セットアップ

1. ローカル marketplace として登録し、Discord セッションに使うプロジェクトで有効化する

```sh
claude plugin marketplace add ~/Desktop/work/claude-discord-channel/discord-session
cd <Discord セッションに使うプロジェクト>
claude plugin install discord-session@ryuki-plugins --scope project
```

2. ステータスラインの JSON を保存するようにする。どちらか一方でよい
   - 自分の statusline スクリプトに、受け取った JSON を `~/.claude/tmp/statusline/<session_id>.json` へ保存する処理を足す
     （`_dumped_at` と `_claude_pid` も入れる。`scripts/statusline_dump.py` の `find_claude_pid` を参考に）
   - または `settings.json` の `statusLine.command` を `python3 <plugin>/scripts/statusline_dump.py -- <元のコマンド>` にする

3. Discord セッションを tmux で起動する（プロジェクトのディレクトリで実行）

```sh
<plugin>/scripts/start-discord.sh                       # 新規
<plugin>/scripts/start-discord.sh --resume <session-id> # 会話を引き継ぐ
```

`<plugin>` はこのリポジトリのパス（例: `~/Desktop/work/claude-discord-channel/discord-session`）。

## 更新のしかた

インストール時にプラグインは `~/.claude/plugins/cache/ryuki-plugins/discord-session/<version>/` へコピーされます。
このリポジトリを編集してコミットしたら、次で反映してください。

```sh
claude plugin update discord-session@ryuki-plugins
```

そのあと、動いている Discord セッションで `/reload-plugins` を打つか、セッションを再起動します。

## 仕組みのメモ

- `/clear` の送り先は `CLAUDE_PID` → その TTY → 同じ TTY の tmux ペイン、で特定します。tmux の外や
  リモートセッションでは NG を返し、Claude がその旨を Discord に伝えます
- `/clear` はターン実行中でもキューされ、ターン終了直後に実行されます。プロセスと MCP 接続は残り、セッション ID だけ変わります
- Bot が送れるアクティビティのフィールドは name / type / state / url のみです。`DISCORD_PRESENCE_MODE`
  で playing / watching / listening / competing / custom を選べます
- プラグインの hooks は起動時に固定されるので、プラグインを更新したら Discord セッションを再起動してください
- ステータスの更新タイミングは「Claude が応答してステータスラインが再描画されたとき」です。常駐は最大 20 秒ごとに読みます
