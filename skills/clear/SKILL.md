---
name: clear
description: Discord から「/clear」「クリアして」「コンテキストをリセットして」「新しいセッションにして」と依頼されたとき、このセッションが動いている tmux ペインへ /clear を送ってコンテキストを空にする。Discord からの依頼で必ず使用する（ターミナルで直接 /clear できる場面では不要）
user-invocable: true
argument-hint: ""
allowed-tools:
  - Bash(${CLAUDE_PLUGIN_ROOT}/skills/ctx/scripts/context_usage.py *)
  - Bash(${CLAUDE_PLUGIN_ROOT}/skills/ctx/scripts/context_usage.py)
  - Bash(${CLAUDE_SKILL_DIR}/scripts/clear_session.sh *)
  - mcp__plugin_discord_discord__reply
---

# Discord からの /clear 実行スキル

チャンネル経由のメッセージは Claude への入力テキストとして届くだけで、Claude Code の組み込みコマンド
（/clear 等）は実行されない（公式未対応: anthropics/claude-code#37342）。そこで、このセッション自身が
動いている tmux ペインへ `tmux send-keys` で「/clear + Enter」を送り込む。/clear はターン実行中でも
キューされ、このターンが終わった直後に実行される。

## 手順

1. 現在の使用量を取る（失敗しても続行してよい）

```bash
${CLAUDE_PLUGIN_ROOT}/skills/ctx/scripts/context_usage.py
```

2. Discord へ宣言を reply する。例: 「コンテキストをクリアするね（今 54%、544K tokens）。終わったらこのチャンネルに通知するよ。」
   - 進行中の作業で未保存の要点（台帳や設計メモ）があれば、この時点で先に保存する（クリア後は引き継がれない）
3. `/clear` を送る。`--chat-id` には届いた `<channel>` タグの `chat_id` を渡す（完了通知の宛先になる）

```bash
${CLAUDE_SKILL_DIR}/scripts/clear_session.sh --chat-id <chat_id>
```

4. 結果で分岐する
   - `OK:` が出たら、それ以上ツールを呼ばず短く終える。ターン終了と同時に /clear が走り、新セッションの
     SessionStart フック（このプラグインの `hooks/notify-clear-done.sh`）が Discord へ「クリアしたよ」を投稿する
   - `NG:` が出たら、その理由（tmux の外で動いている／リモートセッション等）を Discord に伝える。
     その場合はユーザーがターミナルで /clear するしかない

## 仕組みと制約

- 特定方法: `CLAUDE_PID` → そのプロセスの TTY → 同じ TTY を持つ tmux ペイン。Discord セッションは tmux の中で
  `claude --channels plugin:discord@claude-plugins-official` として動かす前提（`scripts/start-discord.sh` が面倒を見る）
- /clear 後もプロセスと MCP 接続（Discord ブリッジ）はそのまま残る。セッション ID だけ新しくなる
- 完了通知はフック経由なので、プラグインを入れ替えたあとは Discord セッションの再起動が必要
- ターミナルで手動 /clear した場合は通知されない（マーカー `~/.claude/discord-bot/pending-clear.json` が無いため）
- /compact は対象外
