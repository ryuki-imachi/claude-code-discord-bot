#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///
"""
notify-restart-done.py — SessionStart(startup|resume) フック

Discord からの /restart 依頼（restart スキル）でスーパーバイザーが起動し直したセッションなら、
依頼元のチャンネルへ完了通知を投稿する。
  - スーパーバイザー（scripts/start-discord.sh --supervise）が claude を起動し直す直前に
    ~/.claude/discord-bot/restart-done.json を置く
  - ターミナルで手動で起動し直した場合はマーカーが無いので何もしない
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

STATE_DIR = os.environ.get("DISCORD_BOT_STATE_DIR") or os.path.expanduser("~/.claude/discord-bot")
DISCORD_STATE_DIR = os.environ.get("DISCORD_STATE_DIR") or os.path.expanduser("~/.claude/channels/discord")
MARKER = os.path.join(STATE_DIR, "restart-done.json")
LOG = os.path.join(STATE_DIR, "restart-notify.log")
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


def build_message(marker: dict) -> str:
    old = str(marker.get("old_version") or "").strip()
    new = str(marker.get("new_version") or "").strip()
    if old and new and old != new:
        head = f"再起動したよ（{old} → {new}）。"
    elif old or new:
        head = f"再起動したよ（{old or new}、更新なし）。"
    else:
        head = "再起動したよ。"
    tail = "直前の会話を引き継いでいるよ。" if marker.get("resumed") else "ここからは新しいセッションで応対するね。"
    return head + tail


def post_message(chat_id: str, token: str, content: str) -> str:
    req = urllib.request.Request(
        f"https://discord.com/api/v10/channels/{chat_id}/messages",
        data=json.dumps({"content": content}).encode(),
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "discord-bot (Claude Code plugin)",
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

    message = build_message(marker)
    if marker.get("dry_run"):
        result = "dry-run"
        log(f"DRY-RUN POST /channels/{chat_id}/messages {json.dumps({'content': message}, ensure_ascii=False)} (source={source})")
    else:
        token = load_token()
        result = post_message(chat_id, token, message) if token else "no-token"
        log(f"POST chat={chat_id} result={result} age={age}s source={source}")

    resumed = "直前の会話を引き継いでいます" if marker.get("resumed") else "会話は引き継いでいません（まっさらな状態です）"
    print(
        f"このセッションは Discord（chat_id={chat_id}）からの /restart 依頼で起動し直したセッションです（{resumed}）。"
        f"完了通知「{message}」はフックが投稿済み（結果: {result}）。次のメッセージから通常どおり応対してください。"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
