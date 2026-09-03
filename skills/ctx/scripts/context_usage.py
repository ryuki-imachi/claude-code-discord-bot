#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///
"""
context_usage.py — 今動いている Claude Code セッションのコンテキスト使用量を表示する

Discord から「/ctx」と送られたときに、Claude が Bash で実行して結果を reply する想定。
（discord-bot プラグイン同梱。単体でも動く）

データソース（優先順）
  1. ~/.claude/tmp/statusline/<session_id>.json
       ~/.claude/statusline.py が描画のたびに保存している生JSON。
       ターミナル下部のステータスラインと同じ数値（ctx / 5h / 7d）が取れる
  2. ~/.claude/projects/<cwdをエンコードしたディレクトリ>/<session_id>.jsonl
       会話トランスクリプト。最後の assistant メッセージの usage から算出する
       （statusline のダンプが無いとき用のフォールバック。5h/7d は取れない）

セッションIDは --session-id、無ければ環境変数 CLAUDE_CODE_SESSION_ID を使う
（Claude Code の Bash ツール内では自動で設定されている。/clear 後は新IDに切り替わる）
"""

import argparse
import glob
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))
HOME = os.path.expanduser("~")
STATUSLINE_DIR = os.environ.get("DISCORD_BOT_STATUSLINE_DIR") or os.path.join(HOME, ".claude", "tmp", "statusline")
PROJECTS_DIR = os.path.join(HOME, ".claude", "projects")


def make_bar(pct: float, width: int = 10) -> str:
    filled = max(0, min(width, round(pct / 100 * width)))
    return "■" * filled + "□" * (width - filled)


def fmt_k(n: float) -> str:
    return f"{n / 1000:.1f}K" if n >= 1000 else str(int(n))


def fmt_jst(dt: datetime, fmt: str) -> str:
    return dt.astimezone(JST).strftime(fmt)


def encode_project_dir(cwd: str) -> str:
    """Claude Code が ~/.claude/projects/ 配下に作るディレクトリ名（英数字以外を - に置換）"""
    return re.sub(r"[^A-Za-z0-9]", "-", cwd)


def guess_window_size() -> int:
    """フォールバック用。settings.json の model に [1m] が付いていれば 1M、それ以外は 200K とみなす"""
    try:
        with open(os.path.join(HOME, ".claude", "settings.json")) as f:
            model = str(json.load(f).get("model", ""))
        if "[1m]" in model:
            return 1_000_000
    except Exception:
        pass
    return 200_000


def load_from_statusline(session_id: str) -> dict | None:
    path = os.path.join(STATUSLINE_DIR, f"{session_id}.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        data = json.load(f)
    ctx = data.get("context_window") or {}
    if ctx.get("used_percentage") is None:
        return None
    used = ctx.get("total_input_tokens") or 0
    size = ctx.get("context_window_size") or guess_window_size()
    dumped_at = data.get("_dumped_at")
    measured = datetime.fromisoformat(dumped_at) if dumped_at else None
    return {
        "source": "statusline",
        "session_id": session_id,
        "cwd": data.get("cwd"),
        "model": (data.get("model") or {}).get("display_name"),
        "context_used": used,
        "context_size": size,
        "used_pct": float(ctx["used_percentage"]),
        "rate_limits": data.get("rate_limits") or {},
        "measured_at": measured,
        "transcript_path": data.get("transcript_path"),
    }


def load_from_transcript(session_id: str, cwd: str, transcript_path: str | None = None) -> dict | None:
    path = transcript_path or os.path.join(PROJECTS_DIR, encode_project_dir(cwd), f"{session_id}.jsonl")
    if not os.path.exists(path):
        # cwd から導いた場所に無ければ、全プロジェクトから同じセッションIDのログを探す
        hits = glob.glob(os.path.join(PROJECTS_DIR, "*", f"{session_id}.jsonl"))
        if not hits:
            return None
        path = hits[0]
    last = None
    with open(path) as f:
        for line in f:
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if d.get("type") != "assistant" or d.get("isSidechain"):
                continue  # サブエージェントの記録は別コンテキストなので除外
            msg = d.get("message") or {}
            usage = msg.get("usage")
            if not usage or msg.get("model") == "<synthetic>":
                continue  # ツール中断時などに入る合成メッセージは usage が空なので除外
            total = (usage.get("input_tokens") or 0) + (usage.get("cache_creation_input_tokens") or 0) + (usage.get("cache_read_input_tokens") or 0)
            if total > 0:
                last = (d, usage)
    if last is None:
        return None
    d, usage = last
    used = (
        (usage.get("input_tokens") or 0)
        + (usage.get("cache_creation_input_tokens") or 0)
        + (usage.get("cache_read_input_tokens") or 0)
    )
    size = guess_window_size()
    ts = d.get("timestamp")
    measured = datetime.fromisoformat(ts.replace("Z", "+00:00")) if ts else None
    return {
        "source": "transcript",
        "session_id": session_id,
        "cwd": cwd,
        "model": (d.get("message") or {}).get("model"),
        "context_used": used,
        "context_size": size,
        "used_pct": used / size * 100,
        "rate_limits": {},
        "measured_at": measured,
        "transcript_path": path,
    }


def render_text(info: dict) -> str:
    lines = ["コンテキスト使用量"]
    pct = info["used_pct"]
    lines.append(
        f"ctx {make_bar(pct)} {pct:.0f}%  {fmt_k(info['context_used'])} / {fmt_k(info['context_size'])} tokens"
    )
    for key, label in (("five_hour", "5h "), ("seven_day", "7d ")):
        rl = info["rate_limits"].get(key)
        if not rl:
            continue
        p = float(rl.get("used_percentage") or 0)
        reset = rl.get("resets_at")
        reset_s = f"  リセット {fmt_jst(datetime.fromtimestamp(reset, tz=timezone.utc), '%m/%d %H:%M')}" if reset else ""
        lines.append(f"{label} {make_bar(p)} {p:.0f}%{reset_s}")
    meta = [f"セッション {info['session_id'][:8]}"]
    if info.get("model"):
        meta.append(str(info["model"]))
    if info.get("measured_at"):
        meta.append(f"計測 {fmt_jst(info['measured_at'], '%m/%d %H:%M:%S')}")
    meta.append(f"source {info['source']}")
    lines.append("  ".join(meta))
    if info["source"] == "transcript":
        lines.append("※ statusline のダンプが無いため会話ログから概算（ウィンドウ幅は設定から推定）")
    if pct >= 80:
        lines.append("※ 残りが少ないよ。区切りのいいところで /clear を検討してね")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--session-id", default=os.environ.get("CLAUDE_CODE_SESSION_ID"))
    ap.add_argument("--cwd", default=os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    ap.add_argument("--source", choices=["auto", "statusline", "transcript"], default="auto")
    ap.add_argument("--json", action="store_true", help="JSONで出力")
    args = ap.parse_args()

    if not args.session_id:
        print("セッションIDが分かりません（--session-id か環境変数 CLAUDE_CODE_SESSION_ID が必要）", file=sys.stderr)
        return 2

    info = None
    if args.source in ("auto", "statusline"):
        info = load_from_statusline(args.session_id)
    if info is None and args.source in ("auto", "transcript"):
        info = load_from_transcript(args.session_id, args.cwd)
    if info is None:
        print(f"セッション {args.session_id} の使用量データが見つかりません", file=sys.stderr)
        return 1

    if args.json:
        out = dict(info)
        out["measured_at"] = info["measured_at"].isoformat() if info["measured_at"] else None
        print(json.dumps(out, ensure_ascii=False, indent=2))
    else:
        print(render_text(info))
    return 0


if __name__ == "__main__":
    sys.exit(main())
