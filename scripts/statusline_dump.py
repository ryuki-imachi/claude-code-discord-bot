#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///
"""
statusline_dump.py — Claude Code のステータスライン JSON を保存してから、元のステータスラインコマンドへ渡すラッパー

discord-bot プラグインの ctx スキルと presence 常駐は ~/.claude/tmp/statusline/<session_id>.json を読む。
自分の statusline スクリプトを改造したくない場合は、settings.json の statusLine.command をこのラッパー経由にする。

  "statusLine": {
    "type": "command",
    "command": "python3 /path/to/statusline_dump.py -- <元のコマンド...>"
  }

元のコマンドを省略すると、ダンプだけして何も表示しない。
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone

DUMP_DIR = os.environ.get("DISCORD_BOT_STATUSLINE_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "tmp", "statusline")


def find_claude_pid() -> int | None:
    """親プロセスをたどって Claude Code 本体の PID を返す（実行ファイル名で判定）"""
    pid = os.getppid()
    for _ in range(8):
        try:
            out = subprocess.run(["ps", "-o", "ppid=,comm=", "-p", str(pid)], capture_output=True, text=True, timeout=2).stdout.strip()
        except Exception:
            return None
        if not out:
            return None
        ppid_s, _, exe = out.partition(" ")
        if re.search(r"(^|/)claude$|/claude/versions/[0-9]", exe.strip()):
            return pid
        try:
            pid = int(ppid_s)
        except ValueError:
            return None
        if pid <= 1:
            return None
    return None


def main() -> int:
    raw = sys.stdin.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = None
    if data is not None:
        try:
            os.makedirs(DUMP_DIR, exist_ok=True)
            sid = data.get("session_id") or "unknown"
            data["_dumped_at"] = datetime.now(timezone.utc).isoformat()
            data["_claude_pid"] = find_claude_pid()
            tmp = os.path.join(DUMP_DIR, f".{sid}.json.tmp")
            with open(tmp, "w") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, os.path.join(DUMP_DIR, f"{sid}.json"))
        except Exception:
            pass
    args = sys.argv[1:]
    if args and args[0] == "--":
        args = args[1:]
    if args:
        proc = subprocess.run(args, input=raw, text=True, capture_output=True)
        sys.stdout.write(proc.stdout)
        return proc.returncode
    return 0


if __name__ == "__main__":
    sys.exit(main())
