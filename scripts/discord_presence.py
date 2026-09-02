#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["discord.py>=2.4"]
# ///
"""
discord_presence.py — Claude Code の Discord セッションのコンテキスト使用量を Bot のステータスに出す常駐スクリプト

仕組み
  ~/.claude/statusline.py が描画のたびに保存する ~/.claude/tmp/statusline/<session_id>.json を
  一定間隔で読み、cwd がこのプロジェクトで、かつ Claude Code プロセスが生きているセッションのうち
  最新のものを選んで、Bot のカスタムステータスに「ctx 54% (545K/1M) | 5h 48% | 7d 13%」と表示する。
  --channels 付きで起動されたセッション（Discord に繋がっているセッション）を優先する。
  ctx が 80% 以上なら取り込み中（赤）、対象セッションが無ければ退席中（黄）にする。

起動
  uv run scripts/discord_presence.py        （tmux の別ウィンドウで動かす。scripts/start-discord.sh が面倒を見る）
環境変数
  DISCORD_BOT_TOKEN          無ければ ~/.claude/channels/discord/.env から読む
  DISCORD_PRESENCE_CWD       対象プロジェクト（Discord セッションの cwd）。既定はカレントディレクトリ
  DISCORD_PRESENCE_INTERVAL  更新間隔（秒）。既定 20
  DISCORD_PRESENCE_MODE      表示のしかた。既定 playing
      playing / watching / listening / competing
          アクティビティとして表示。メンバー一覧では「ctx 52% · 5h 21% · 7d 15% をプレイ中」、
          プロフィールでは専用カードに 2 行（1 行目: 使用率、2 行目: トークン数・モデル・更新時刻）
      custom
          カスタムステータス（名前の横の吹き出し）に 1 行で表示
"""

import asyncio
import glob
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import discord

JST = timezone(timedelta(hours=9))
HOME = os.path.expanduser("~")
DUMP_DIR = os.path.join(HOME, ".claude", "tmp", "statusline")
PROJECT_DIR = os.environ.get("DISCORD_PRESENCE_CWD") or os.getcwd()
INTERVAL = int(os.environ.get("DISCORD_PRESENCE_INTERVAL", "20"))
MODE = os.environ.get("DISCORD_PRESENCE_MODE", "playing").lower()
WARN_PCT = 80


def log(msg: str) -> None:
    print(f"{datetime.now(JST):%m/%d %H:%M:%S} {msg}", flush=True)


def load_token() -> str | None:
    if os.environ.get("DISCORD_BOT_TOKEN"):
        return os.environ["DISCORD_BOT_TOKEN"]
    try:
        with open(os.path.join(HOME, ".claude", "channels", "discord", ".env")) as f:
            for line in f:
                m = re.match(r"^DISCORD_BOT_TOKEN=(.*)$", line.strip())
                if m:
                    return m.group(1)
    except OSError:
        pass
    return None


def proc_command(pid) -> str | None:
    """PID が生きていればコマンドラインを返す。死んでいれば None"""
    if not pid:
        return None
    try:
        out = subprocess.run(["ps", "-o", "command=", "-p", str(int(pid))],
                             capture_output=True, text=True, timeout=2).stdout.strip()
    except Exception:
        return None
    return out or None


def pick_session() -> dict | None:
    """対象プロジェクトの生きているセッションのうち、--channels 付き > 最新 の順で1つ選ぶ"""
    target = os.path.realpath(PROJECT_DIR)
    cands = []
    for path in glob.glob(os.path.join(DUMP_DIR, "*.json")):
        try:
            with open(path) as f:
                d = json.load(f)
        except Exception:
            continue
        if os.path.realpath(d.get("cwd") or "") != target:
            continue
        try:
            ts = datetime.fromisoformat(d["_dumped_at"])
        except Exception:
            ts = datetime.fromtimestamp(os.path.getmtime(path), tz=timezone.utc)
        pid = d.get("_claude_pid")
        if pid:
            cmd = proc_command(pid)
            if cmd is None:
                continue  # そのセッションのプロセスはもう居ない
        else:
            # _claude_pid が無い古い形式のダンプは、30分以内に更新されたものだけ生きているとみなす
            if datetime.now(timezone.utc) - ts > timedelta(minutes=30):
                continue
            cmd = ""
        cands.append(("--channels" in cmd, ts, d))
    if not cands:
        return None
    cands.sort(key=lambda c: (c[0], c[1]), reverse=True)
    return cands[0][2]


def fmt_tokens(n: float) -> str:
    return f"{n / 1_000_000:.1f}M" if n >= 1_000_000 else f"{n / 1000:.0f}K"


def build_presence(d: dict | None) -> tuple[discord.Status, str, str]:
    """(ステータス色, 1行目=使用率, 2行目=詳細) を返す"""
    if d is None:
        return discord.Status.idle, "Claude セッションなし", f"{os.path.basename(PROJECT_DIR)} で claude が動いていません"
    ctx = d.get("context_window") or {}
    used = ctx.get("used_percentage")
    parts = [f"ctx {float(used):.0f}%"] if used is not None else ["ctx 計測前"]
    for key, label in (("five_hour", "5h"), ("seven_day", "7d")):
        v = (d.get("rate_limits") or {}).get(key)
        if v and v.get("used_percentage") is not None:
            parts.append(f"{label} {float(v['used_percentage']):.0f}%")
    line1 = " · ".join(parts)

    details = []
    if used is not None:
        details.append(f"{fmt_tokens(ctx.get('total_input_tokens') or 0)} / {fmt_tokens(ctx.get('context_window_size') or 0)} tokens")
    model = (d.get("model") or {}).get("display_name")
    if model:
        details.append(str(model))
    try:
        details.append(f"更新 {datetime.fromisoformat(d['_dumped_at']).astimezone(JST):%H:%M}")
    except Exception:
        pass
    line2 = " · ".join(details)

    status = discord.Status.dnd if (used or 0) >= WARN_PCT else discord.Status.online
    return status, line1[:128], line2[:128]


def make_activity(line1: str, line2: str) -> discord.BaseActivity:
    if MODE == "custom":
        # Bot のカスタムステータスは state が表示される（name は使われない）ので両方に同じ文字列を入れる
        text = f"{line1} · {line2}" if line2 else line1
        return discord.CustomActivity(name=text[:128], state=text[:128])
    types = {
        "playing": discord.ActivityType.playing,
        "watching": discord.ActivityType.watching,
        "listening": discord.ActivityType.listening,
        "competing": discord.ActivityType.competing,
    }
    # Bot が送れるのは name / type / state / url だけ。name がカード見出しとメンバー一覧、state が 2 行目になる
    return discord.Activity(type=types.get(MODE, discord.ActivityType.playing), name=line1, state=line2 or None)


class PresenceClient(discord.Client):
    def __init__(self) -> None:
        super().__init__(intents=discord.Intents.none())
        self._last: tuple | None = None

    async def setup_hook(self) -> None:
        self.loop.create_task(self.ticker())

    async def on_ready(self) -> None:
        log(f"connected as {self.user} (project={PROJECT_DIR}, interval={INTERVAL}s, mode={MODE})")
        self._last = None  # 再接続後は必ず送り直す

    async def on_resumed(self) -> None:
        self._last = None

    async def ticker(self) -> None:
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                status, line1, line2 = build_presence(pick_session())
                if (status, line1, line2) != self._last:
                    await self.change_presence(status=status, activity=make_activity(line1, line2))
                    self._last = (status, line1, line2)
                    log(f"presence -> [{status}] {line1} / {line2}")
            except Exception as e:  # noqa: BLE001
                log(f"error: {e!r}")
            await asyncio.sleep(INTERVAL)


def main() -> int:
    token = load_token()
    if not token:
        print("DISCORD_BOT_TOKEN が見つかりません（環境変数か ~/.claude/channels/discord/.env）", file=sys.stderr)
        return 2
    if not os.path.isdir(DUMP_DIR):
        log(f"注意: {DUMP_DIR} がまだ無い。statusline.py が一度でも動くと作られる")
    PresenceClient().run(token, log_handler=None)
    return 0


if __name__ == "__main__":
    sys.exit(main())
