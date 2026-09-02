---
name: ctx
description: 今のセッションのコンテキスト使用量（ctx / 5h / 7d の使用率）を調べて Discord に返す。Discord から「/ctx」「/context」「コンテキストどれくらい？」「残り容量は」などが届いたときに必ず使用する。ターミナルから呼ばれた場合はその場に表示する
user-invocable: true
argument-hint: ""
allowed-tools:
  - Bash(${CLAUDE_SKILL_DIR}/scripts/context_usage.py *)
  - Bash(${CLAUDE_SKILL_DIR}/scripts/context_usage.py)
  - mcp__plugin_discord_discord__reply
---

# コンテキスト使用量の確認スキル

Discord セッションは 1 セッションを開きっぱなしにするので、コンテキストの残量を Discord 側から
確認できるようにする。ターミナル下部のステータスラインと同じ数値を返す。

## 手順

1. Bash で次を実行する（引数不要。セッション ID は環境変数 `CLAUDE_CODE_SESSION_ID` から自動取得）

```bash
${CLAUDE_SKILL_DIR}/scripts/context_usage.py
```

2. 出力をそのままコードブロックに入れて reply する（Discord は行頭の記号をリスト表示に変えて崩すため）。前置きは不要
3. `ctx` が 80% 以上なら「区切りのいいところで /clear しようか」と一言添える
4. Discord 経由でない（ターミナルから呼ばれた）場合は reply せず、出力をそのまま答える

## 数値の意味

- `ctx`: コンテキストウィンドウの使用率。直前の API 応答時点の入力トークン（キャッシュ含む）÷ ウィンドウ幅
- `5h` / `7d`: 利用上限の使用率とリセット時刻（JST）
- `source statusline`: ステータスラインが保存した JSON 由来。ターミナル表示と同じ値
- `source transcript`: statusline のダンプが無いときのフォールバック。会話ログの usage から概算し、
  ウィンドウ幅は settings.json の model（`[1m]` なら 1M）から推定。5h/7d は出ない

## 失敗したとき

- 「使用量データが見つかりません」: まだ API 応答が 1 回も無い新セッションか、ステータスラインの
  ダンプが設定されていない環境。1 ターン進めてから再実行するか、README の「ステータスラインの設定」を確認する
