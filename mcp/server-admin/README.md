# server-admin MCP サーバー

Discord のサーバー（チャンネル・カテゴリ・フォーラムスレッド）を Claude Code から操作するための自作 MCP サーバー。
公式 Discord プラグインはメッセージの送受信のみを担当するため、その穴を埋める。

## 技術構成

- 言語: Python 3.10+
- MCP SDK: mcp（FastMCP）
- Discord API クライアント: httpx（Discord REST API v10 を直接呼び出す。discord.py は使わない。
  Bot のイベントループ（Gateway 接続）前提の設計で、MCP サーバー独自の async イベントループと競合しやすいため）
- パッケージ管理: uv + pyproject.toml
- トランスポート: stdio

## ディレクトリ構成

```
mcp/server-admin/
├── pyproject.toml
├── uv.lock
├── docs/design.md          設計書（original-tools 時代のもの）
└── src/discord_mcp/
    ├── server.py           MCP サーバー本体（エントリポイント）
    ├── client.py           Discord REST API クライアント
    └── tools/channels.py   チャンネル・スレッド管理ツール（9 ツール）
```

## 設定

トークンとギルド ID は、公式 Discord プラグインと共有する
`${DISCORD_STATE_DIR:-~/.claude/channels/discord}/.env` から読む
（環境変数 `DISCORD_BOT_TOKEN` / `DISCORD_GUILD_ID` が既にあればそちらを優先）。
このディレクトリに `.env` は置かない。

## 移植元

`~/path/to/claude-code-discord-bot/` と並ぶディレクトリの `original-tools/` にあった同名プロジェクトを、
discord-bot プラグイン（issue #1）に取り込んだもの。元の `.venv` は作り直し、コミット履歴は引き継いでいない。
