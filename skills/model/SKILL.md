---
name: model
description: Discord から「/model sonnet」「モデルを sonnet にして」「今のモデルは？」「Opus に切り替えて」のように依頼されたとき、このセッションが動いている tmux ペインへ /model <alias> を送ってモデルを切り替える。Discord からの依頼で必ず使用する（ターミナルで直接 /model できる場面では不要）
user-invocable: true
argument-hint: "<alias>"
allowed-tools:
  - Bash(${CLAUDE_PLUGIN_ROOT}/scripts/switch_setting.py *)
  - mcp__plugin_discord-bot_discord__reply
---

# Discord からの /model 切り替えスキル

チャンネル経由のメッセージは Claude への入力テキストとして届くだけで、Claude Code の組み込みコマンド
（/model 等）は実行されない（公式未対応: anthropics/claude-code#37342）。そこで、このセッション自身が
動いている tmux ペインへ `tmux send-keys` で「/model <alias> + Enter」を送り込む。/clear と同じ仕組み。

## 手順

1. `$ARGUMENTS` を確認する
   - 引数が無ければ現在値だけを表示する（送信はしない）

     ```bash
     ${CLAUDE_PLUGIN_ROOT}/scripts/switch_setting.py --kind model --show
     ```

     出力をそのまま reply して終わる
   - 引数があれば、その値を alias として次に進む
2. 送信する。`--chat-id` には届いた `<channel>` タグの `chat_id` を渡す（切り替わり検知後の通知先になる）

   ```bash
   ${CLAUDE_PLUGIN_ROOT}/scripts/switch_setting.py --kind model --value <alias> --chat-id <chat_id>
   ```

3. 結果で分岐する
   - `OK:` が出たら、その内容を短く reply し、「切り替えは次のメッセージから。ターミナルで新しく開くセッションの
     デフォルトも変わるよ」を一言添える。切り替わったこと自体は監視プロセスが検知でき次第、別メッセージで通知される
   - `NG:` が出たら、その理由（無効な alias、tmux の外で動いている等）を Discord に伝える。
     無効な alias の場合は下記の一覧を案内する

## 有効な alias

`best` `fable` `opus` `sonnet` `haiku` `sonnet[1m]` `opus[1m]` `opusplan`。
`claude-` で始まる完全なモデル ID も指定できる。

## 仕組みと制約

- 特定方法は `/clear` と同じ（`CLAUDE_PID` → TTY → tmux ペイン）。Discord セッションは tmux の中で動かす前提
- `/model <alias>` の引数指定は「切り替えてデフォルトとして保存」する挙動（ピッカーで Enter したのと同じ）。
  セッション限定にする指定方法は無い
- 切り替わったかどうかは、送信後に切り離して起動する監視プロセスがステータスラインのダンプ
  （`model.id` / `model.display_name`）を最大 90 秒、2 秒おきに確認して判断する。検知できたら Discord へ
  「モデルを Sonnet 5 に切り替えたよ（effort high）」のように投稿する。検知できなくても次のメッセージからは新しいモデルで応対する
