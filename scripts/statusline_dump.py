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
import time
from datetime import datetime, timezone

DUMP_DIR = os.environ.get("DISCORD_BOT_STATUSLINE_DIR") or os.path.join(os.path.expanduser("~"), ".claude", "tmp", "statusline")
STALE_SECONDS = 24 * 60 * 60


def prune_stale_dumps(dump_dir: str, keep_path: str | None = None, stale_seconds: int = STALE_SECONDS) -> None:
    """dump_dir 内の古いダンプを削除する（ディレクトリ走査は1回だけ）。

    削除条件:
      - `_claude_pid` を持つファイルは「そのPIDが死んでいる」かつ「更新時刻が stale_seconds より前」
      - `_claude_pid` を持たない（読めない）ファイルは更新時刻だけで判定
    keep_path（今回自分が書いたファイル）は対象から除外する。
    例外は握りつぶし、statusline の表示を邪魔しない。
    """
    try:
        now = time.time()
        with os.scandir(dump_dir) as it:
            for entry in it:
                try:
                    if not entry.name.endswith(".json") or entry.name.startswith("."):
                        continue
                    if keep_path and os.path.abspath(entry.path) == os.path.abspath(keep_path):
                        continue
                    st = entry.stat()
                    if now - st.st_mtime <= stale_seconds:
                        continue
                    pid = None
                    try:
                        with open(entry.path) as f:
                            pid = json.load(f).get("_claude_pid")
                    except Exception:
                        pid = None
                    if pid is not None:
                        try:
                            os.kill(pid, 0)
                            continue  # まだ生きている
                        except ProcessLookupError:
                            pass
                        except Exception:
                            continue  # 判定できない場合は消さない
                    os.remove(entry.path)
                except Exception:
                    continue
    except Exception:
        pass


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
            dest = os.path.join(DUMP_DIR, f"{sid}.json")
            os.replace(tmp, dest)
            prune_stale_dumps(DUMP_DIR, keep_path=dest)
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
