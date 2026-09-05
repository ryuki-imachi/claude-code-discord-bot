---
name: effort
description: Discord から「/effort low」「effort を high にして」「思考の深さを xhigh に」「今の effort は？」のように依頼されたとき、このセッションが動いている tmux ペインへ /effort <level> を送って思考の深さを切り替える。Discord からの依頼で必ず使用する（ターミナルで直接 /effort できる場面では不要）
user-invocable: true
argument-hint: "<level>"
allowed-tools:
  - Bash(${CLAUDE_PLUGIN_ROOT}/scripts/switch_setting.py *)
  - mcp__plugin_discord-bot_discord__reply
---

# Discord からの /effort 切り替えスキル

チャンネル経由のメッセージは Claude への入力テキストとして届くだけで、Claude Code の組み込みコマンド
（/effort 等）は実行されない（公式未対応: anthropics/claude-code#37342）。そこで、このセッション自身が
動いている tmux ペインへ `tmux send-keys` で「/effort <level> + Enter」を送り込む。/clear と同じ仕組み。

## 手順

1. `$ARGUMENTS` を確認する
   - 引数が無ければ現在値だけを表示する（送信はしない）

     ```bash
     ${CLAUDE_PLUGIN_ROOT}/scripts/switch_setting.py --kind effort --show
     ```

     出力をそのまま reply して終わる
   - 引数があれば、その値を level として次に進む
2. 送信する。`--chat-id` には届いた `<channel>` タグの `chat_id` を渡す（切り替わり検知後の通知先になる）

   ```bash
   ${CLAUDE_PLUGIN_ROOT}/scripts/switch_setting.py --kind effort --value <level> --chat-id <chat_id>
   ```

3. 結果で分岐する
   - `OK:` が出たら、その内容を短く reply する。「切り替えは次のメッセージから」を一言添える
   - `NG:` が出たら、その理由（無効な level、tmux の外で動いている等）を Discord に伝える。
     無効な level の場合は下記の一覧を案内する

## 有効な level

`low` `medium` `high` `xhigh` `max` `auto`。

- `low`〜`xhigh` はモデルごとに設定として保存される（次にそのモデルへ切り替えたときも引き継がれる）
- `max` はセッション限りで、保存はされない
- `auto` は保存済みの effort 設定をクリアする

## 仕組みと制約

- 特定方法は `/clear` と同じ（`CLAUDE_PID` → TTY → tmux ペイン）。Discord セッションは tmux の中で動かす前提
- 切り替わったかどうかは、送信後に切り離して起動する監視プロセスがステータスラインのダンプ（`effort.level`）を
  最大 90 秒、2 秒おきに確認して判断する。検知できたら Discord へ「effort を low に切り替えたよ（Fable 5.1）」の
  ように投稿する。検知できなくても次のメッセージからは新しい effort で応対する
