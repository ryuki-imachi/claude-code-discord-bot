#!/bin/bash
# clear_session.sh — このスクリプトを呼び出した Claude Code セッションが動いている
# tmux ペインへ「/clear + Enter」を送り込む。Discord から /clear を実現するための裏方。
#
#   使い方: clear_session.sh [--chat-id <DiscordチャンネルID>] [--dry-run]
#
#   仕組み:
#     CLAUDE_PID（Bashツール内で自動設定）→ そのプロセスの TTY → 同じ TTY を持つ tmux ペイン
#     を特定して tmux send-keys する。/clear はターン実行中でもキューされ、ターンが終わった
#     直後に実行される（2026-09-02 に検証済み）。
#   --chat-id を渡すと ~/.claude/discord-bot/pending-clear.json にマーカーを書き、/clear 完了後に
#   SessionStart(clear) フック（hooks/notify-clear-done.sh）が Discord へ完了通知を投げる。
set -u

chat_id=""
dry_run=0
while [ $# -gt 0 ]; do
  case "$1" in
    --chat-id) chat_id="${2:-}"; shift 2 ;;
    --dry-run) dry_run=1; shift ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

# マーカーと通知ログの置き場（フック notify-clear-done.sh と共有）
state_dir="${DISCORD_BOT_STATE_DIR:-$HOME/.claude/discord-bot}"

# 1. 自分を動かしている Claude Code プロセスを特定する
pid="${CLAUDE_PID:-}"
if [ -z "$pid" ]; then
  # 環境変数が無ければ親をたどって claude 本体を探す
  p=$$
  while [ "$p" -gt 1 ]; do
    cmd=$(ps -o command= -p "$p" 2>/dev/null)
    case "$cmd" in *claude*) pid=$p; break ;; esac
    p=$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' ')
    [ -z "$p" ] && break
  done
fi
if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
  echo "NG: Claude Code のプロセスを特定できません（CLAUDE_PID=${CLAUDE_PID:-unset}）" >&2
  exit 1
fi

# 2. その TTY を持つ tmux ペインを探す
tty=$(ps -o tty= -p "$pid" | tr -d ' ')
if [ -z "$tty" ] || [ "$tty" = "??" ]; then
  echo "NG: PID $pid は端末（TTY）に紐づいていません。リモート/SDK セッションでは /clear を送れません" >&2
  exit 1
fi
pane=$(tmux list-panes -a -F '#{pane_id} #{pane_tty} #{session_name}:#{window_index}.#{pane_index}' 2>/dev/null \
  | awk -v t="/dev/$tty" '$2==t{print $1" "$3; exit}')
if [ -z "$pane" ]; then
  echo "NG: /dev/$tty を持つ tmux ペインがありません。このセッションは tmux の外で動いています" >&2
  exit 1
fi
pane_id=${pane%% *}
pane_name=${pane#* }

# 3. 完了通知用のマーカー（SessionStart(clear) フックが読んで消す）
if [ -n "$chat_id" ]; then
  mkdir -p "$state_dir"
  printf '{"chat_id":"%s","session_id":"%s","cwd":"%s","requested_at":"%s"}\n' \
    "$chat_id" "${CLAUDE_CODE_SESSION_ID:-}" "$PWD" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    > "$state_dir/pending-clear.json"
fi

if [ "$dry_run" = 1 ]; then
  echo "DRY-RUN: pid=$pid tty=$tty pane=$pane_id ($pane_name) chat_id=${chat_id:-none} marker=$state_dir/pending-clear.json"
  exit 0
fi

# 4. /clear を送る（スラッシュコマンドの補完ポップアップが出るので、少し待ってから Enter）
tmux send-keys -t "$pane_id" -l '/clear'
sleep 0.3
tmux send-keys -t "$pane_id" Enter
echo "OK: /clear を tmux ペイン $pane_id ($pane_name, $tty, pid $pid) に送りました。このターンが終わり次第クリアされます"
