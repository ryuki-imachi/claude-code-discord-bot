# Claude Code 用 Discord Bot プラグイン（discord-bot）

開発者が運用している Discord サーバー管理 Bot「kuroko-chan」の中身です。Claude Code のプラグインとして動きます。
Discord 社および Anthropic 社とは無関係の、非公式なコミュニティ製プラグインです。

Claude Code の Discord チャンネル機能（`claude --channels ...`）は、Discord のメッセージを Claude の会話に流し込みます。
公式の Discord プラグインはメッセージの送受信だけを担当していて、セッションの管理（コンテキストの残量確認やクリア）や
サーバーの管理（チャンネルやスレッドの操作）はできません。このプラグインは、公式プラグインの channel サーバーを
フォークして土台にし、その上にセッション管理・サーバー管理・Bot ステータス表示を足したものです。
作った経緯と考え方は [docs/background.md](docs/background.md) にあります。

## 機能

| 機能 | 使い方 |
| --- | --- |
| Discord との送受信 | 公式プラグインからフォークした channel サーバー（`channel/`）。reply / react / edit_message / fetch_messages / download_attachment |
| アクセス管理 | `/discord-bot:access`（ペアリング承認・allowlist・チャンネルの受信設定）と `/discord-bot:configure`（Bot トークンの保存）。公式と同じ `~/.claude/channels/discord/` を使う |
| コンテキスト使用量の表示 | Discord で `/ctx`。ctx / 5h / 7d の使用率をコードブロックで返す |
| Discord からのクリア | Discord で `/clear`。宣言 → tmux ペインに `/clear` を送信 → 新セッション開始時に「クリアしたよ」を自動投稿 |
| Bot ステータスに使用量を常時表示 | Bot のアクティビティを `ctx 53% · 5h 46% · 7d 17%` に更新。ctx 80% 以上で赤、セッション無しで黄 |
| サーバー管理 MCP | チャンネル・カテゴリ・フォーラムスレッドの作成・編集・削除・一覧（`server-admin`、9 ツール） |
| チャンネル作成ワークフロー | `/discord-bot:setup-channel`。作成 → access.json の受信設定 → 受信テストまで。作成直後にフックが受信設定を促す |
| スラッシュコマンド | `/ctx` `/clear` を同梱。`~/.claude/discord-bot/commands.json` に書けば任意のスキルを引数付きで呼べる |
| 起動ランチャー | `scripts/start-discord.sh` が tmux セッション `discord` で claude を立てる。二重起動は防ぐ |

## セットアップ

前提は tmux、uv、bun と、Message Content Intent を有効にしてサーバーに招待済みの Discord Bot です
（Bot の作り方は `channel/UPSTREAM-README.md` の Quick Setup 1〜3 と同じ）。macOS で動作確認しています。

1. Discord セッションに使うプロジェクトのディレクトリで、プロジェクトスコープで有効化します。
   公式の Discord プラグインを使っていた場合は無効にしてください（同じトークンで接続が 2 本になり、返信が二重になります）。

```sh
claude plugin marketplace add ryuki-imachi/claude-code-discord-bot
cd <Discord セッションに使うプロジェクト>
claude plugin install discord-bot@ryuki-plugins --scope project
```

2. Bot トークンを保存します（公式プラグインで設定済みならそのまま）。ギルド ID は Bot が 1 つのサーバーにしか入っていなければ省略できます。

```
/discord-bot:configure <トークン>
```

3. ステータスラインの JSON を保存するようにします。`/ctx` と Bot ステータス表示がこれを読みます。
   `settings.json` の `statusLine.command` を次のようにラッパー経由にするのが簡単です。

```json
{
  "statusLine": {
    "type": "command",
    "command": "uv run ~/path/to/claude-code-discord-bot/scripts/statusline_dump.py -- <元のコマンド>"
  }
}
```

4. プロジェクトのディレクトリで起動します。tmux セッション `discord` の中で
   `claude --channels plugin:discord-bot@ryuki-plugins` が動きます。初回は DM のペアリングコードを
   `/discord-bot:access pair <コード>` で承認してください。

```sh
~/path/to/claude-code-discord-bot/scripts/start-discord.sh                       # 新規
~/path/to/claude-code-discord-bot/scripts/start-discord.sh --resume <session-id> # 会話を引き継ぐ
```

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

## ドキュメント

- [docs/background.md](docs/background.md) 背景と考え方、関連記事
- [docs/how-it-works.md](docs/how-it-works.md) /clear の流れ、Bot ステータス、スラッシュコマンド、サーバー管理 MCP、制約
- [docs/development.md](docs/development.md) 更新のしかた、ディレクトリ構成、移植の経緯

## ライセンス

このリポジトリは MIT License です。ただし `channel/` は公式 Discord プラグイン
（`anthropics/claude-plugins-official`、Apache-2.0）のフォークなので、そのディレクトリのファイルは
Apache-2.0 のままです（`channel/LICENSE`）。改変した内容は `channel/server.ts` の先頭に書いてあります。
