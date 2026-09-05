#!/bin/bash
# clear_session.sh — このスクリプトを呼び出した Claude Code セッションが動いている
# tmux ペインへ「/clear + Enter」を送り込む。Discord から /clear を実現するための裏方。
#
#   使い方: clear_session.sh [--chat-id <DiscordチャンネルID>] [--dry-run]
#
#   ペイン特定と送信そのものは共通スクリプト scripts/tmux_send_slash.sh（/model、/effort とも共用）が担う。
#   このスクリプトが持つのは、/clear 固有の完了通知マーカーの書き込みだけ。
#   --chat-id を渡すと ~/.claude/discord-bot/pending-clear.json にマーカーを書き、/clear 完了後に
#   SessionStart(clear) フック（hooks/notify-clear-done.py）が Discord へ完了通知を投げる。
set -u

chat_id=""
dry_run=0
while [ $# -gt 0 ]; do
  case "$1" in
    --chat-id) chat_id="${2:-}"; shift 2 ;;
    --dry-run) dry_run=1; shift ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown arg: $1" >&2; exit 2 ;;
  esac
done

# マーカーと通知ログの置き場（フック notify-clear-done.py と共有）
state_dir="${DISCORD_BOT_STATE_DIR:-$HOME/.claude/discord-bot}"

# 共通スクリプトの場所を解決する（プラグインとして動くときは CLAUDE_PLUGIN_ROOT を優先）
if [ -n "${CLAUDE_PLUGIN_ROOT:-}" ]; then
  common_script="$CLAUDE_PLUGIN_ROOT/scripts/tmux_send_slash.sh"
else
  script_dir="$(cd "$(dirname "$0")" && pwd)"
  common_script="$(cd "$script_dir/../../.." && pwd)/scripts/tmux_send_slash.sh"
fi
if [ ! -x "$common_script" ]; then
  echo "NG: 共通スクリプトが見つかりません: $common_script" >&2
  exit 1
fi

# 完了通知用のマーカー（SessionStart(clear) フックが読んで消す）
if [ -n "$chat_id" ]; then
  mkdir -p "$state_dir"
  printf '{"chat_id":"%s","session_id":"%s","cwd":"%s","requested_at":"%s"}\n' \
    "$chat_id" "${CLAUDE_CODE_SESSION_ID:-}" "$PWD" "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    > "$state_dir/pending-clear.json"
fi

if [ "$dry_run" = 1 ]; then
  result=$("$common_script" --dry-run '/clear' 2>&1)
  status=$?
  if [ $status -ne 0 ]; then
    echo "NG: ${result#NG: }" >&2
    exit 1
  fi
  detail=${result#DRY-RUN: }
  echo "DRY-RUN: ${detail% text=*} chat_id=${chat_id:-none} marker=$state_dir/pending-clear.json"
  exit 0
fi

# /clear を送る（スラッシュコマンドの補完ポップアップが出るので、少し待ってから Enter。共通スクリプト内で対応）
result=$("$common_script" '/clear' 2>&1)
status=$?
if [ $status -ne 0 ]; then
  echo "NG: ${result#NG: }" >&2
  exit 1
fi
detail=${result#OK: }
echo "OK: /clear を tmux ペイン ${detail} に送りました。このターンが終わり次第クリアされます"
