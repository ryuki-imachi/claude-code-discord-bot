#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# ///
"""
switch_setting.py — Discord から届いた「モデルを切り替えて」「effort を上げて」を、このセッションが
動いている tmux ペインへ /model or /effort として送り込み、切り替わったことを検知したら Discord へ通知する。
（discord-bot プラグイン同梱。skills/model, skills/effort から呼ばれる）

使い方
  switch_setting.py --kind model  --value sonnet --chat-id <id>   送信 + 監視プロセスを起動
  switch_setting.py --kind effort --value low    --dry-run        検証だけ（送信・監視はしない）
  switch_setting.py --kind model  --show                          現在値だけ表示

引数の検証
  --kind model  : best / fable / opus / sonnet / haiku / sonnet[1m] / opus[1m] / opusplan、
                   または claude- で始まる完全なモデルID
  --kind effort : low / medium / high / xhigh / max / auto
  無効な --value は NG を出して exit 2 で終わる（何も送らない）

現在値の取得
  ~/.claude/tmp/statusline/<CLAUDE_CODE_SESSION_ID>.json（DISCORD_BOT_STATUSLINE_DIR で上書き可）から
  model.display_name / model.id / effort.level / _dumped_at を読む。無ければ「不明」として続行する

送信・監視
  scripts/tmux_send_slash.sh で '/model <v>' または '/effort <v>' を送る。--chat-id があれば、
  自分自身を --watch で再実行する監視プロセスを Popen(start_new_session=True) で切り離して起動する
  （Bash ツールの子プロセス掃除に巻き込まれないようにするため）。--watch は最大90秒、2秒おきに
  ダンプを読み直し、送信時刻より新しい更新で対象の値が変わった（または指定値と一致した）ら
  Discord へ投稿して終了する。検知できなければ何も投稿せずログにだけ残す
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

MODEL_ALIASES = {"best", "fable", "opus", "sonnet", "haiku", "sonnet[1m]", "opus[1m]", "opusplan"}
EFFORT_LEVELS = {"low", "medium", "high", "xhigh", "max", "auto"}

HOME = os.path.expanduser("~")
STATUSLINE_DIR = os.environ.get("DISCORD_BOT_STATUSLINE_DIR") or os.path.join(HOME, ".claude", "tmp", "statusline")
STATE_DIR = os.environ.get("DISCORD_BOT_STATE_DIR") or os.path.join(HOME, ".claude", "discord-bot")
DISCORD_STATE_DIR = os.environ.get("DISCORD_STATE_DIR") or os.path.join(HOME, ".claude", "channels", "discord")
LOG = os.path.join(STATE_DIR, "switch-notify.log")
WATCH_TIMEOUT_SEC = 90
WATCH_INTERVAL_SEC = 2


def log(msg: str) -> None:
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}\n")


def is_valid_model(value: str) -> bool:
    return value in MODEL_ALIASES or value.startswith("claude-")


def is_valid_effort(value: str) -> bool:
    return value in EFFORT_LEVELS


def validate(kind: str, value: str) -> bool:
    return is_valid_model(value) if kind == "model" else is_valid_effort(value)


def session_id() -> str | None:
    return os.environ.get("CLAUDE_CODE_SESSION_ID")


def load_dump(sid: str | None) -> dict | None:
    if not sid:
        return None
    path = os.path.join(STATUSLINE_DIR, f"{sid}.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def current_values(dump: dict | None) -> dict:
    model = (dump or {}).get("model") or {}
    effort = (dump or {}).get("effort") or {}
    return {
        "model_display": model.get("display_name"),
        "model_id": model.get("id"),
        "effort_level": effort.get("level"),
        "dumped_at": (dump or {}).get("_dumped_at"),
    }


def fmt_current(vals: dict) -> str:
    disp = vals.get("model_display") or "不明"
    eff = vals.get("effort_level") or "不明"
    return f"{disp} / effort {eff}"


def resolve_common_script() -> str:
    """tmux_send_slash.sh の場所。プラグインとして動くときは CLAUDE_PLUGIN_ROOT を優先し、
    無ければこのファイルと同じ scripts/ ディレクトリを見る。"""
    root = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if root:
        return os.path.join(root, "scripts", "tmux_send_slash.sh")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "tmux_send_slash.sh")


def send(slash: str, value: str, dry_run: bool) -> tuple[bool, str]:
    script = resolve_common_script()
    args = [script]
    if dry_run:
        args.append("--dry-run")
    args.append(f"/{slash} {value}")
    try:
        proc = subprocess.run(args, capture_output=True, text=True, timeout=10)
    except Exception as e:  # noqa: BLE001
        return False, f"共通スクリプトの実行に失敗: {e!r}"
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    detail = out or err
    for prefix in ("OK: ", "NG: ", "DRY-RUN: "):
        if detail.startswith(prefix):
            detail = detail[len(prefix):]
            break
    return proc.returncode == 0, detail


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


def post_message(chat_id: str, text: str) -> str:
    token = load_token()
    if not token:
        return "no-token"
    req = urllib.request.Request(
        f"https://discord.com/api/v10/channels/{chat_id}/messages",
        data=json.dumps({"content": text}).encode(),
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


def spawn_watcher(kind: str, value: str, chat_id: str, sent_at: datetime, prev_vals: dict) -> None:
    script = os.path.abspath(__file__)
    args = [
        sys.executable,
        script,
        "--kind", kind,
        "--value", value,
        "--chat-id", chat_id,
        "--watch",
        "--since", sent_at.isoformat(),
        "--prev-model-id", prev_vals.get("model_id") or "",
        "--prev-model-display", prev_vals.get("model_display") or "",
        "--prev-effort-level", prev_vals.get("effort_level") or "",
    ]
    sid = session_id()
    if sid:
        args += ["--session-id", sid]
    os.makedirs(STATE_DIR, exist_ok=True)
    log(f"spawn watcher pid待ち: kind={kind} value={value} chat_id={chat_id}")
    with open(LOG, "a") as logf:
        subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=logf,
            stderr=logf,
            start_new_session=True,
            close_fds=True,
        )


def detect_change(kind: str, value: str, vals: dict, args: argparse.Namespace) -> bool:
    if kind == "model":
        cur_id = (vals.get("model_id") or "").lower()
        cur_disp = (vals.get("model_display") or "").lower()
        if not cur_id and not cur_disp:
            return False
        prev_id = (args.prev_model_id or "").lower()
        prev_disp = (args.prev_model_display or "").lower()
        changed = cur_id != prev_id or cur_disp != prev_disp
        matches_target = value.lower() in cur_id or value.lower() in cur_disp
        return changed or matches_target
    cur_level = (vals.get("effort_level") or "").lower()
    if not cur_level:
        return False
    prev_level = (args.prev_effort_level or "").lower()
    changed = cur_level != prev_level
    matches_target = cur_level == value.lower()
    return changed or matches_target


def build_notify_message(kind: str, value: str, vals: dict) -> str:
    disp = vals.get("model_display") or "不明"
    eff = vals.get("effort_level") or value
    if kind == "model":
        return f"モデルを {disp} に切り替えたよ（effort {eff}）"
    return f"effort を {eff} に切り替えたよ（{disp}）"


def cmd_watch(args: argparse.Namespace) -> int:
    log(f"watch start kind={args.kind} value={args.value} chat_id={args.chat_id} since={args.since}")
    sid = args.session_id or session_id()
    try:
        since = datetime.fromisoformat(str(args.since))
    except Exception:  # noqa: BLE001
        log(f"watch abort: --since が不正です: {args.since}")
        return 2

    deadline = time.time() + WATCH_TIMEOUT_SEC
    while time.time() < deadline:
        dump = load_dump(sid)
        if dump:
            vals = current_values(dump)
            dumped_at = vals.get("dumped_at")
            dumped_dt = None
            if dumped_at:
                try:
                    dumped_dt = datetime.fromisoformat(str(dumped_at).replace("Z", "+00:00"))
                except Exception:  # noqa: BLE001
                    dumped_dt = None
            if dumped_dt and dumped_dt > since and detect_change(args.kind, args.value, vals, args):
                message = build_notify_message(args.kind, args.value, vals)
                result = post_message(args.chat_id, message)
                log(f"posted: chat_id={args.chat_id} message={message!r} result={result}")
                return 0
        time.sleep(WATCH_INTERVAL_SEC)

    log(f"timeout: kind={args.kind} value={args.value} chat_id={args.chat_id} "
        f"({WATCH_TIMEOUT_SEC}秒以内に変化を検知できず。投稿はしない）")
    return 0


def cmd_show(kind: str, vals: dict, dump: dict | None) -> int:
    if not dump:
        print("現在値が分からないよ（ステータスラインのダンプが見つからない）")
        return 0
    if kind == "model":
        print(f"現在のモデル: {vals['model_display'] or '不明'}（id: {vals['model_id'] or '不明'}） / effort {vals['effort_level'] or '不明'}")
    else:
        print(f"現在の effort: {vals['effort_level'] or '不明'}（モデル {vals['model_display'] or '不明'}）")
    return 0


def cmd_main(args: argparse.Namespace) -> int:
    dump = load_dump(session_id())
    vals = current_values(dump)

    if args.show:
        return cmd_show(args.kind, vals, dump)

    if not args.value:
        print("NG: --value を指定してください（現在値だけなら --show）", file=sys.stderr)
        return 2

    value = args.value
    if not validate(args.kind, value):
        if args.kind == "model":
            print(
                f"NG: 無効なモデル指定です: {value}"
                f"（有効なエイリアス: {' '.join(sorted(MODEL_ALIASES))}、または claude- で始まる完全なモデルID）",
                file=sys.stderr,
            )
        else:
            print(f"NG: 無効な effort レベルです: {value}（有効: {' '.join(sorted(EFFORT_LEVELS))}）", file=sys.stderr)
        return 2

    slash = args.kind
    cur = fmt_current(vals)

    if args.dry_run:
        ok, detail = send(slash, value, dry_run=True)
        if not ok:
            print(f"NG: {detail}", file=sys.stderr)
            return 1
        print(f"DRY-RUN: '/{slash} {value}' を送る予定。現在値: {cur}。（{detail}）")
        return 0

    sent_at = datetime.now(timezone.utc)
    ok, detail = send(slash, value, dry_run=False)
    if not ok:
        print(f"NG: {detail}", file=sys.stderr)
        return 1

    watching = False
    if args.chat_id:
        spawn_watcher(args.kind, value, args.chat_id, sent_at, vals)
        watching = True

    suffix = "検知できたら通知するね" if watching else "通知はしない（--chat-id 未指定）"
    print(f"OK: /{slash} {value} を送ったよ。今は {cur}。切り替えはこのターンが終わったあと。{suffix}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--kind", choices=["model", "effort"], required=True)
    ap.add_argument("--value", help="model なら alias/完全ID、effort なら low/medium/high/xhigh/max/auto")
    ap.add_argument("--chat-id", help="Discord のチャンネルID。指定すると切り替わりを検知して通知する")
    ap.add_argument("--dry-run", action="store_true", help="送信・監視をせず検証結果と現在値だけ出す")
    ap.add_argument("--show", action="store_true", help="現在値だけ表示する（送信しない）")
    # 以下は内部用（自分自身を監視プロセスとして再実行するときに使う）
    ap.add_argument("--watch", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--since", help=argparse.SUPPRESS)
    ap.add_argument("--prev-model-id", default="", help=argparse.SUPPRESS)
    ap.add_argument("--prev-model-display", default="", help=argparse.SUPPRESS)
    ap.add_argument("--prev-effort-level", default="", help=argparse.SUPPRESS)
    ap.add_argument("--session-id", help=argparse.SUPPRESS)
    return ap


def main() -> int:
    args = build_parser().parse_args()
    if args.watch:
        if not args.chat_id or not args.since or not args.value:
            print("NG: --watch には --chat-id --since --value が必要です", file=sys.stderr)
            return 2
        return cmd_watch(args)
    return cmd_main(args)


if __name__ == "__main__":
    sys.exit(main())
