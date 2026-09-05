---
name: restart
description: Discord から「/restart」「再起動して」「Claude Code を新しいバージョンにして」「アップデートして立ち上げ直して」と依頼されたとき、常駐セッションの再起動をスーパーバイザーに予約する。Discord からの依頼で必ず使用する（ターミナルで直接 /exit して起動し直せる場面では不要）
user-invocable: true
argument-hint: "[resume]"
allowed-tools:
  - Bash(${CLAUDE_SKILL_DIR}/scripts/request_restart.py *)
  - Bash(${CLAUDE_SKILL_DIR}/scripts/request_restart.py)
  - mcp__plugin_discord-bot_discord__reply
---

# Discord からの再起動スキル

自動更新でバイナリは新しくなっても、動いているセッションは古いバージョンのまま。切り替えには再起動が要るが、
セッション自身が `tmux new-window` や自分を落とすコマンドを打とうとすると auto mode の分類器に拒否される。
そこで、危ない操作は外側のスーパーバイザー（`scripts/start-discord.sh --supervise`。tmux ペインの中で claude を
見守っている親プロセス）に任せ、このスキルは再起動要求のマーカーを書くだけにする。

スーパーバイザーはマーカーを見つけると、自分のペインへ `/exit` を送り、claude が終わったら `claude update` を
挟んで同じ cwd・同じ引数で起動し直す。完了通知は新セッションの SessionStart フック
（このプラグインの `hooks/notify-restart-done.py`）が投稿する。

## 手順

1. 進行中の作業で未保存の要点（台帳や設計メモ）があれば、この時点で先に保存する
   （`resume` を付けない限り会話は引き継がれない）
2. Discord へ宣言を reply する。例: 「再起動するね（会話は引き継がない）。終わったらこのチャンネルに通知するよ。」
   - `resume` を付けて呼ばれたときは「会話は引き継ぐ」と言う
3. 再起動を予約する。`--chat-id` には届いた `<channel>` タグの `chat_id` を渡す（完了通知の宛先になる）。
   引数に `resume` / `yes` / `引き継ぐ` があれば `--resume` を付ける

```bash
${CLAUDE_SKILL_DIR}/scripts/request_restart.py --chat-id <chat_id>
${CLAUDE_SKILL_DIR}/scripts/request_restart.py --chat-id <chat_id> --resume
```

4. 結果で分岐する
   - `OK:` が出たら、それ以上ツールを呼ばず短く終える。**ターンが終わらないと `/exit` が効かない**ので、
     ここで追加の調査や作業を始めない。数秒後にスーパーバイザーがセッションを落として起動し直し、
     新セッションのフックが Discord へ「再起動したよ（2.1.261 → 2.1.262）」を投稿する
   - `NG:` が出たら、その理由（スーパーバイザー配下で動いていない等）を Discord に伝える。
     その場合はユーザーがターミナルで `/exit` して `discord-start` を打ち直すしかない

## 仕組みと制約

- 判定: `~/.claude/discord-bot/supervisor.json` があり、その `pid` が生きていて、自分（`CLAUDE_PID`）の
  祖先にその pid が居ること。3 つ揃わなければ NG（マーカーを書いても拾う人が居ないため）
- 再起動後は既定でまっさら。`resume` を付けたときだけ今のセッション ID を `--resume` に渡して起動し直す
- `claude update` はスーパーバイザーが実行する（180 秒でタイムアウト、失敗しても起動はし直す）。
  出力は `~/.claude/discord-bot/restart.log` に残る
- ターミナルで `/exit` した場合はマーカーが無いので起動し直さず、tmux のウィンドウが閉じる（今までどおり）
- MCP 接続もプロセスも作り直しになるので、`/clear` より数十秒長くかかる
