#!/bin/bash
# start-discord.sh — Discord セッション一式を tmux セッション "discord" で起動する（discord-bot プラグイン同梱）
#   DISCORD_BOT_CHANNEL_MODE=fork（既定）ならフォーク版を、official なら公式プラグインを channel にして起動する
#   （Bot のステータス表示は channel サーバーが担当するので常駐スクリプトは無い）
#
#   使い方: Discord セッションにしたいプロジェクトのディレクトリで実行する
#     start-discord.sh                       新規セッションで起動
#     start-discord.sh --resume <session-id> 会話を引き継いで起動（追加引数はそのまま claude に渡す）
#     start-discord.sh --supervise [引数...] スーパーバイザー本体。tmux のペインの中でこのスクリプト自身が
#                                            呼び出す内部モードなので、手で打つ必要は無い
#
#   tmux のペインの中で動かすのは claude ではなくこのスクリプト（--supervise）で、claude はその子プロセスになる。
#   スーパーバイザーは claude の終了を待ち、Discord からの /restart（restart スキルが
#   ${DISCORD_BOT_STATE_DIR:-~/.claude/discord-bot}/pending-restart.json に置くマーカー）があれば
#   claude update を挟んで同じペインで起動し直す。マーカーが無ければそのまま終了する（ターミナルで /exit したとき）。
#
#   環境変数: DISCORD_TMUX_SESSION（既定 discord）、DISCORD_BOT_CHANNEL_MODE（fork / official）、
#             DISCORD_BOT_STATE_DIR（既定 ~/.claude/discord-bot）、DISCORD_BOT_CLAUDE_BIN（既定 claude、検証用の差し替え）
#   すでに動いているものは起動しない（--channels 付き claude が二重に立つと Discord へ二重返信するため）
set -u
# tmux のペインの中は PATH が短いことがあるので、claude を見つけられるようにしておく
PATH="$HOME/.local/bin:/opt/homebrew/bin:$PATH"
export PATH

SESSION="${DISCORD_TMUX_SESSION:-discord}"
DIR="$PWD"
# channel（Discord との送受信）をどのプラグインに任せるか。
#   official        : 公式 discord@claude-plugins-official を --channels に渡す。フォーク版 channel サーバーは
#                    プレゼンス表示だけ担当し、スラッシュコマンドは止める（受け付けても Claude に届かないため）
#   fork（既定）    : フォーク版を --channels に渡す。Claude Code は公式以外の channel を既定で捨てるので、
#                    管理者設定 allowedChannelPlugins で承認しておく（README セットアップ 4）
MODE="${DISCORD_BOT_CHANNEL_MODE:-fork}"
# マーカーの置き場（restart スキル・完了通知フックと共有）と、起動する claude（検証時だけ差し替える）
STATE_DIR="${DISCORD_BOT_STATE_DIR:-$HOME/.claude/discord-bot}"
CLAUDE_BIN="${DISCORD_BOT_CLAUDE_BIN:-claude}"
# ~/.local/bin へコピーして使う運用（discord-start）でも 1 ファイルで完結させるため、自分自身を再実行する
SELF="$(cd "$(dirname "$0")" && pwd)/$(basename "$0")"

now_utc() { date -u +%Y-%m-%dT%H:%M:%SZ; }

# JSON から値を 1 つ取り出す。bash だけで読むと壊れやすいので python3 に任せる（真偽値は true/false の文字列で返す）
json_get() {
  python3 -c 'import json,sys
try:
    v = json.load(open(sys.argv[1])).get(sys.argv[2], "")
except Exception:
    v = ""
if isinstance(v, bool):
    v = "true" if v else "false"
elif v is None:
    v = ""
print(v)' "$1" "$2" 2>/dev/null
}

# ---------------------------------------------------------------- スーパーバイザー本体
if [ "${1:-}" = "--supervise" ]; then
  shift
  mkdir -p "$STATE_DIR"
  PENDING="$STATE_DIR/pending-restart.json"     # restart スキルが置く再起動要求
  DONE_FILE="$STATE_DIR/restart-done.json"      # 新セッションの SessionStart フックが読む完了マーカー
  SUPERVISOR="$STATE_DIR/supervisor.json"       # restart スキルの「配下かどうか」判定用
  LOG="$STATE_DIR/restart.log"

  slog() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$LOG"; }

  # 1. 前回の異常終了で取り残されたマーカーを消す（起動直後に再起動し続けるのを防ぐ）
  rm -f "$PENDING"

  # 2. 自分の情報を書く。restart スキルはこの pid が自分の祖先にいるかで「配下かどうか」を判定する
  printf '{"pid":%s,"pane":"%s","cwd":"%s","mode":"%s","started_at":"%s"}\n' \
    "$$" "${TMUX_PANE:-}" "$PWD" "$MODE" "$(now_utc)" > "$SUPERVISOR"
  trap 'rm -f "$SUPERVISOR"' EXIT

  if [ "$MODE" = "fork" ]; then
    CHANNEL_ARG="plugin:discord-bot@ryuki-plugins"
  else
    CHANNEL_ARG="plugin:discord@claude-plugins-official"
    export DISCORD_SLASH_COMMANDS=off
  fi

  # 追加引数から --resume <id> を分けておく。再起動のたびに付け替える（引き継がないときは外す）ため
  RESUME_ID=""
  BASE_ARGS=()
  while [ $# -gt 0 ]; do
    case "$1" in
      --resume) RESUME_ID="${2:-}"; shift 2 ;;
      --resume=*) RESUME_ID="${1#--resume=}"; shift ;;
      *) BASE_ARGS+=("$1"); shift ;;
    esac
  done

  # 自分のペインへ /exit を送る。スラッシュコマンドの補完ポップアップが出るので Enter は少し遅らせる
  send_exit() {
    tmux send-keys -t "$1" -l '/exit' 2>/dev/null || return 1
    sleep 0.3
    tmux send-keys -t "$1" Enter 2>/dev/null || return 1
  }

  # 再起動要求を見張る。claude が終了したら親（スーパーバイザー）がこのループを kill するので、
  # /exit のあと 90 秒生き残っていれば「まだ claude が終わっていない」とみなして C-c を挟んで送り直す
  watch_pending() {
    trap - EXIT
    pane="$1"
    waited=0
    while :; do
      sleep 3
      [ -f "$PENDING" ] || continue
      slog "watcher: 再起動要求を検知。ペイン $pane へ /exit を送る"
      send_exit "$pane"
      waited=0
      while [ "$waited" -lt 90 ]; do
        sleep 3
        waited=$((waited + 3))
      done
      slog "watcher: 90 秒たっても終了しないので C-c → /exit を送り直す"
      tmux send-keys -t "$pane" C-c 2>/dev/null || true
      sleep 1
      send_exit "$pane"
      return 0
    done
  }

  # 2.1.261 のような先頭のバージョン番号だけ取り出す（"2.1.261 (Claude Code)" のような行が来る）
  claude_version() {
    "$CLAUDE_BIN" --version 2>/dev/null | head -n 1 | sed -e 's/[\\"]//g' -e 's/^\([0-9][0-9.]*\).*$/\1/'
  }

  while :; do
    set -- ${BASE_ARGS[@]+"${BASE_ARGS[@]}"}
    [ -n "$RESUME_ID" ] && set -- "$@" --resume "$RESUME_ID"

    WATCHER_PID=""
    if [ -n "${TMUX_PANE:-}" ]; then
      watch_pending "$TMUX_PANE" &
      WATCHER_PID=$!
    else
      slog "TMUX_PANE が無いので /exit の自動送信はしない（tmux の外で起動された）"
    fi

    slog "claude 起動: $CLAUDE_BIN --channels $CHANNEL_ARG $*"
    "$CLAUDE_BIN" --channels "$CHANNEL_ARG" "$@"
    STATUS=$?
    slog "claude 終了 (exit $STATUS)"

    if [ -n "$WATCHER_PID" ]; then
      kill "$WATCHER_PID" 2>/dev/null
      wait "$WATCHER_PID" 2>/dev/null
    fi

    # 要求が無ければ通常終了（ターミナルで /exit した場合）。tmux のウィンドウはここで閉じる
    [ -f "$PENDING" ] || break

    CHAT_ID=$(json_get "$PENDING" chat_id)
    REQ_SESSION=$(json_get "$PENDING" session_id)
    REQ_RESUME=$(json_get "$PENDING" resume)
    REQUESTED_AT=$(json_get "$PENDING" requested_at)
    REQ_DRY=$(json_get "$PENDING" dry_run)
    rm -f "$PENDING"

    OLD_VERSION=$(claude_version)
    slog "再起動要求: chat=${CHAT_ID:-none} resume=${REQ_RESUME:-false} 現在 ${OLD_VERSION:-unknown}。claude update を実行する"
    # 終了コードの仕様が公開されていないので、失敗しても・タイムアウトしても起動はし直す
    if command -v timeout >/dev/null 2>&1; then
      timeout 180 "$CLAUDE_BIN" update >> "$LOG" 2>&1 || slog "claude update が失敗またはタイムアウトしたが続行する"
    elif command -v gtimeout >/dev/null 2>&1; then
      gtimeout 180 "$CLAUDE_BIN" update >> "$LOG" 2>&1 || slog "claude update が失敗またはタイムアウトしたが続行する"
    else
      "$CLAUDE_BIN" update >> "$LOG" 2>&1 || slog "claude update が失敗したが続行する"
    fi
    NEW_VERSION=$(claude_version)

    if [ "$REQ_RESUME" = "true" ] && [ -n "$REQ_SESSION" ]; then
      RESUME_ID="$REQ_SESSION"
      RESUMED="true"
    else
      RESUME_ID=""
      RESUMED="false"
    fi
    if [ "$REQ_DRY" = "true" ]; then DRY="true"; else DRY="false"; fi

    printf '{"chat_id":"%s","old_version":"%s","new_version":"%s","resumed":%s,"dry_run":%s,"requested_at":"%s","restarted_at":"%s"}\n' \
      "$CHAT_ID" "$OLD_VERSION" "$NEW_VERSION" "$RESUMED" "$DRY" "$REQUESTED_AT" "$(now_utc)" > "$DONE_FILE"
    slog "起動し直す: ${OLD_VERSION:-?} -> ${NEW_VERSION:-?} resumed=$RESUMED"
  done

  rm -f "$SUPERVISOR"
  exit 0
fi

# ---------------------------------------------------------------- ランチャー
# 引数を tmux へ渡すコマンド文字列に安全に埋め込む（シングルクォート囲み）
shq() {
  for a in "$@"; do
    printf "'%s' " "$(printf '%s' "$a" | sed "s/'/'\\\\''/g")"
  done
}

# tmux サーバーの環境には引き継がれないことがあるので、コマンド文字列に明示的に前置する
CMD_ENV="DISCORD_BOT_CHANNEL_MODE=$(shq "$MODE")"
[ -n "${DISCORD_BOT_STATE_DIR:-}" ] && CMD_ENV="$CMD_ENV DISCORD_BOT_STATE_DIR=$(shq "$DISCORD_BOT_STATE_DIR")"
[ -n "${DISCORD_BOT_CLAUDE_BIN:-}" ] && CMD_ENV="$CMD_ENV DISCORD_BOT_CLAUDE_BIN=$(shq "$DISCORD_BOT_CLAUDE_BIN")"
# ペインの中ではスーパーバイザー（自分自身）を動かす。claude 自身のコマンドラインは今までどおりなので
# 下の二重起動チェック（pgrep）はそのまま効く
CLAUDE_CMD="$CMD_ENV $(shq "$SELF") --supervise $(shq "$@")"

if ! tmux has-session -t "${SESSION}" 2>/dev/null; then
  tmux new-session -d -s "${SESSION}" -n claude -c "${DIR}" "${CLAUDE_CMD}"
  echo "tmux セッション ${SESSION} を作成し、claude を起動しました（cwd: ${DIR}）"
elif pgrep -f 'claude.*(--channels|--dangerously-load-development-channels).*plugin:discord' >/dev/null; then
  echo "claude（--channels）は起動済みです"
elif tmux list-panes -s -t "${SESSION}" -F '#{pane_pid}' | xargs -I{} pgrep -P {} -x claude 2>/dev/null | grep -q . \
  || tmux list-panes -s -t "${SESSION}" -F '#{pane_current_command}' | grep -Eq '^(claude|[0-9]+\.[0-9]+\.[0-9]+)$'; then
  echo "注意: tmux セッション ${SESSION} 内で claude は動いていますが --channels が付いていません。二重起動を避けるため何もしません"
  echo "      Discord に繋ぐには、その claude を終了してからもう一度このスクリプトを実行してください"
else
  tmux new-window -d -t "${SESSION}" -n claude -c "${DIR}" "${CLAUDE_CMD}"
  echo "claude を新しいウィンドウで起動しました（cwd: ${DIR}）"
fi

echo "--- windows ---"
tmux list-windows -t "${SESSION}" -F '  #{window_index}: #{window_name}  (#{pane_current_command})'
[ -z "${TMUX:-}" ] && echo "接続: tmux attach -t ${SESSION}"
exit 0
