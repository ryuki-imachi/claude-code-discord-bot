#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///
"""
remind-channel-access.py — PostToolUse(create_channel) フック

チャンネル作成直後、access.json の受信設定（requireMention / allowFrom）を忘れずに
登録するよう注意書きを additionalContext として注入する。access.json のトップレベル
allowFrom を読んで文面に埋め込む（値が読めなくても落とさず、空欄の文面を出す）。
"""

import json
import os
import sys

DISCORD_STATE_DIR = os.environ.get("DISCORD_STATE_DIR") or os.path.expanduser("~/.claude/channels/discord")
ACCESS_JSON = os.path.join(DISCORD_STATE_DIR, "access.json")


def load_allow_from() -> str:
    try:
        with open(ACCESS_JSON) as f:
            data = json.load(f)
        allow_from = data.get("allowFrom")
        if isinstance(allow_from, list) and allow_from:
            return json.dumps(allow_from, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        pass
    return ""


def main() -> int:
    try:
        json.load(sys.stdin)
    except Exception:  # noqa: BLE001
        pass

    allow_from = load_allow_from()

    message = (
        "Discordチャンネルを作成した直後です。必ず次を実施してください: "
        f"(1) {ACCESS_JSON} の groups に新チャンネルIDを "
        f"requireMention: false / allowFrom: {allow_from or '[]'} "
        "（access.json のトップレベル allowFrom の値をそのまま使う）で登録する"
        "（自動生成済みエントリが requireMention: true なら false に修正）。"
        "怠るとメンション無しの投稿がClaudeに届きません。"
        "(2) プロジェクトの CLAUDE.md や台帳にチャンネル一覧・構成表があれば更新する。"
        "(3) ユーザーにテスト投稿してもらい受信を確認する。"
        "詳細手順: setup-channel スキル"
    )

    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": message}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
