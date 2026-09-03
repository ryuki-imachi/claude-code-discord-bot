#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///
"""
notify-clear-done.py — SessionStart(clear) フック

Discord からの /clear 依頼（clear スキル）で始まった新セッションなら、依頼元のチャンネルへ完了通知を投稿する。
  - clear スキル（clear_session.sh --chat-id）が ~/.claude/discord-session/pending-clear.json にマーカーを置く
  - ターミナルで手動 /clear した場合はマーカーが無いので何もしない
  - マーカーが 10 分より古い場合は無視する（取り残しによる誤爆防止）
  - マーカーに "dry_run": true があれば投稿せずログだけ残す（動作確認用）
標準出力は新セッションの Claude に文脈として渡る。
"""

import json
import os
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

STATE_DIR = os.environ.get("DISCORD_SESSION_STATE_DIR") or os.path.expanduser("~/.claude/discord-session")
DISCORD_STATE_DIR = os.environ.get("DISCORD_STATE_DIR") or os.path.expanduser("~/.claude/channels/discord")
MARKER = os.path.join(STATE_DIR, "pending-clear.json")
LOG = os.path.join(STATE_DIR, "clear-notify.log")
MESSAGE = "コンテキストをクリアしたよ。ここからは新しいセッションで応対するね。"
MAX_AGE_SEC = 600


def log(msg: str) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")


def load_token() -> str | None:
    if os.environ.get("DISCORD_BOT_TOKEN"):
        return os.environ["DISCORD_BOT_TOKEN"]
    try:
        with open(os.path.join(DISCORD_STATE_DIR, ".env")) as f:
            for line in f:
                m = re.match(r"^DISCORD_BOT_TOKEN=(.*)$", line.strip())
                if m:
                    return m.group(1)
    except OSError:
        pass
    return None


def post_message(chat_id: str, token: str) -> str:
    req = urllib.request.Request(
        f"https://discord.com/api/v10/channels/{chat_id}/messages",
        data=json.dumps({"content": MESSAGE}).encode(),
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "discord-session (Claude Code plugin)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return f"http {r.status}"
    except urllib.error.HTTPError as e:
        return f"http {e.code}"
    except Exception as e:  # noqa: BLE001
        return f"error {e!r}"


def main() -> int:
    try:
        hook_input = json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        hook_input = {}
    source = hook_input.get("source", "")
    if not os.path.exists(MARKER):
        return 0
    try:
        with open(MARKER) as f:
            marker = json.load(f)
    except Exception:  # noqa: BLE001
        marker = {}
    os.remove(MARKER)

    chat_id = str(marker.get("chat_id") or "")
    try:
        requested = datetime.fromisoformat(str(marker.get("requested_at")).replace("Z", "+00:00"))
        age = int((datetime.now(timezone.utc) - requested).total_seconds())
    except Exception:  # noqa: BLE001
        age = 10**9
    if not chat_id or age > MAX_AGE_SEC:
        log(f"skip: chat_id={chat_id or '-'} age={age}s source={source}")
        return 0

    if marker.get("dry_run"):
        result = "dry-run"
        log(f"DRY-RUN POST /channels/{chat_id}/messages {json.dumps({'content': MESSAGE}, ensure_ascii=False)} (source={source})")
    else:
        token = load_token()
        result = post_message(chat_id, token) if token else "no-token"
        log(f"POST chat={chat_id} result={result} age={age}s source={source}")

    print(
        f"このセッションは Discord（chat_id={chat_id}）からの /clear 依頼で始まった新しいセッションです。"
        f"完了通知はフックが投稿済み（結果: {result}）。次のメッセージから通常どおり応対してください。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
