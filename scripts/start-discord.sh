#!/bin/bash
# start-discord.sh — Discord セッション一式を tmux セッション "discord" で起動する（discord-bot プラグイン同梱）
#   DISCORD_BOT_CHANNEL_MODE=official（既定）なら公式プラグインを channel に、fork ならフォーク版を channel にして起動する
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
# channel（Discord との送受信）をどのプラグインに任せるか。
#   official（既定）: 公式 discord@claude-plugins-official を --channels に渡す。フォーク版 channel サーバーは
#                    プレゼンス表示だけ担当し、スラッシュコマンドは止める（受け付けても Claude に届かないため）
#   fork            : フォーク版を --dangerously-load-development-channels で読み込む。Claude Code が公式以外の
#                    channel を既定で捨てるため、このフラグが必要。ただし環境によっては無視される（調査中）
MODE="${DISCORD_BOT_CHANNEL_MODE:-official}"
if [ "$MODE" = "fork" ]; then
  CLAUDE_CMD="claude --dangerously-load-development-channels plugin:discord-bot@ryuki-plugins $*"
else
  CLAUDE_CMD="DISCORD_SLASH_COMMANDS=off claude --channels plugin:discord@claude-plugins-official $*"
fi

if ! tmux has-session -t "$SESSION" 2>/dev/null; then
  tmux new-session -d -s "$SESSION" -n claude -c "$DIR" "$CLAUDE_CMD"
  echo "tmux セッション $SESSION を作成し、claude を起動しました（cwd: $DIR）"
elif pgrep -f 'claude.*(--channels|--dangerously-load-development-channels).*plugin:discord' >/dev/null; then
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
