#!/bin/bash
# start-discord.sh — Discord セッション一式を tmux セッション "discord" で起動する（discord-bot プラグイン同梱）
#   claude --channels plugin:discord-bot@ryuki-plugins [追加引数] を tmux の中で起動する
#   （Bot のステータス表示は channel サーバーが担当するので常駐スクリプトは無い）
#
#   使い方: Discord セッションにしたいプロジェクトのディレクトリで実行する
#     start-discord.sh                       新規セッションで起動
#     start-discord.sh --resume <session-id> 会話を引き継いで起動（追加引数はそのまま claude に渡す）
#   環境変数: DISCORD_TMUX_SESSION（既定 discord）
#   すでに動いているものは起動しない（--channels 付き claude が二重に立つと Discord へ二重返信するため）
set -u
SESSION="${DISCORD_TMUX_SESSION:-discord}"
DIR="$PWD"
CLAUDE_CMD="claude --channels plugin:discord-bot@ryuki-plugins $*"

if ! tmux has-session -t "$SESSION" 2>/dev/null; then
  tmux new-session -d -s "$SESSION" -n claude -c "$DIR" "$CLAUDE_CMD"
  echo "tmux セッション $SESSION を作成し、claude を起動しました（cwd: $DIR）"
elif pgrep -f 'claude.*--channels.*plugin:discord' >/dev/null; then
  echo "claude（--channels）は起動済みです"
elif tmux list-panes -s -t "$SESSION" -F '#{pane_pid}' | xargs -I{} pgrep -P {} -x claude 2>/dev/null | grep -q . \
  || tmux list-panes -s -t "$SESSION" -F '#{pane_current_command}' | grep -Eq '^(claude|[0-9]+\.[0-9]+\.[0-9]+)$'; then
  echo "注意: tmux セッション $SESSION 内で claude は動いていますが --channels が付いていません。二重起動を避けるため何もしません"
  echo "      Discord に繋ぐには、その claude を終了してからもう一度このスクリプトを実行してください"
else
  tmux new-window -d -t "$SESSION" -n claude -c "$DIR" "$CLAUDE_CMD"
  echo "claude を新しいウィンドウで起動しました（cwd: $DIR）"
fi

echo "--- windows ---"
tmux list-windows -t "$SESSION" -F '  #{window_index}: #{window_name}  (#{pane_current_command})'
[ -z "${TMUX:-}" ] && echo "接続: tmux attach -t $SESSION"
exit 0
