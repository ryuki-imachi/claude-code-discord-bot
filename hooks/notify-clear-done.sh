#!/bin/bash
# SessionStart(clear): Discord からの /clear 依頼で始まった新セッションなら、完了通知を Discord へ投げる
#   - clear スキル（clear_session.sh --chat-id）が ~/.claude/discord-session/pending-clear.json を置く
#   - ターミナルで手動 /clear した場合はマーカーが無いので何もしない
#   - マーカーが10分より古い場合は無視する（取り残しによる誤爆防止）
#   - マーカーに "dry_run": true があれば投稿せずログだけ残す（動作確認用）
input=$(cat)
state_dir="${DISCORD_SESSION_STATE_DIR:-$HOME/.claude/discord-session}"
marker="$state_dir/pending-clear.json"
log="$state_dir/clear-notify.log"
[ -f "$marker" ] || exit 0
mkdir -p "$state_dir"

source_name=$(printf '%s' "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("source",""))' 2>/dev/null)
read -r chat_id dry_run age < <(python3 - "$marker" <<'PY'
import json, sys, datetime
d = json.load(open(sys.argv[1]))
req = datetime.datetime.fromisoformat(d.get("requested_at", "1970-01-01T00:00:00Z").replace("Z", "+00:00"))
age = int((datetime.datetime.now(datetime.timezone.utc) - req).total_seconds())
print(d.get("chat_id", "") or "-", "1" if d.get("dry_run") else "0", age)
PY
)
rm -f "$marker"

if [ "$chat_id" = "-" ] || [ "$age" -gt 600 ]; then
  echo "$(date '+%F %T') skip: chat_id=$chat_id age=${age}s source=$source_name" >> "$log"
  exit 0
fi

token=$(grep '^DISCORD_BOT_TOKEN=' "$HOME/.claude/channels/discord/.env" | cut -d= -f2-)
msg="コンテキストをクリアしたよ。ここからは新しいセッションで応対するね。"
body=$(python3 -c 'import json,sys; print(json.dumps({"content": sys.argv[1]}, ensure_ascii=False))' "$msg")
if [ "$dry_run" = 1 ]; then
  code="dry-run"
  echo "$(date '+%F %T') DRY-RUN POST /channels/$chat_id/messages $body (source=$source_name)" >> "$log"
else
  code=$(curl -s -o /dev/null -w '%{http_code}' -X POST "https://discord.com/api/v10/channels/$chat_id/messages" \
    -H "Authorization: Bot $token" -H 'Content-Type: application/json' -d "$body")
  echo "$(date '+%F %T') POST chat=$chat_id http=$code age=${age}s source=$source_name" >> "$log"
fi

# ここから下は新セッションの Claude に渡る文脈
echo "このセッションは Discord（chat_id=$chat_id）からの /clear 依頼で始まった新しいセッションです。完了通知はフックが投稿済み（結果: $code）。次のメッセージから通常どおり応対してください。"
