#!/bin/bash
# start-discord.sh — Discord セッション一式を tmux セッション "discord" で起動する（discord-bot プラグイン同梱）
#   claude 側   : claude --channels plugin:discord@claude-plugins-official [追加引数]
#   presence 側 : uv run <plugin>/scripts/discord_presence.py（Bot のステータスにコンテキスト使用量を表示）
#
#   使い方: Discord セッションにしたいプロジェクトのディレクトリで実行する
#     start-discord.sh                       新規セッションで起動
#     start-discord.sh --resume <session-id> 会話を引き継いで起動（追加引数はそのまま claude に渡す）
#   環境変数: DISCORD_TMUX_SESSION（既定 discord）
#   すでに動いているものは起動しない（--channels 付き claude が二重に立つと Discord へ二重返信するため）
set -u
SESSION="${DISCORD_TMUX_SESSION:-discord}"
DIR="$PWD"
# ~/.local/bin/discord-start のようなシンボリックリンク経由でも実体の scripts/ を指すようにする
SELF="$0"
while [ -L "$SELF" ]; do
  target=$(readlink "$SELF")
  case "$target" in /*) SELF="$target" ;; *) SELF="$(dirname "$SELF")/$target" ;; esac
done
HERE="$(cd "$(dirname "$SELF")" && pwd)"
CLAUDE_CMD="claude --channels plugin:discord@claude-plugins-official $*"
PRESENCE_CMD="DISCORD_PRESENCE_CWD='$DIR' uv run '$HERE/discord_presence.py'"

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

if pgrep -f 'discord_presence.py' >/dev/null; then
  echo "presence（Bot ステータス更新）は起動済みです"
else
  tmux new-window -d -t "$SESSION" -n presence -c "$DIR" "$PRESENCE_CMD"
  echo "presence を新しいウィンドウで起動しました（対象: $DIR）"
fi

echo "--- windows ---"
tmux list-windows -t "$SESSION" -F '  #{window_index}: #{window_name}  (#{pane_current_command})'
[ -z "${TMUX:-}" ] && echo "接続: tmux attach -t $SESSION"
exit 0
