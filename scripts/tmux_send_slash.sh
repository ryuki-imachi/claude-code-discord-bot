#!/bin/bash
# tmux_send_slash.sh — このスクリプトを呼び出した Claude Code セッションが動いている
# tmux ペインへ、1行のスラッシュコマンド + Enter を送り込む共通処理。
# clear_session.sh の「ペイン特定 → send-keys」部分を切り出したもの（/model、/effort でも使う）。
#
#   使い方: tmux_send_slash.sh [--dry-run] '<送る1行>'   例: tmux_send_slash.sh '/model sonnet'
#
#   仕組み:
#     CLAUDE_PID（Bashツール内で自動設定）→ そのプロセスの TTY → 同じ TTY を持つ tmux ペイン
#     を特定して tmux send-keys する。スラッシュコマンドはターン実行中でもキューされ、ターンが
#     終わった直後に実行される（2026-09-02 に /clear で検証済み）。
#   成功: 標準出力に `OK: pane=<id> (<session:window.pane>) tty=<tty> pid=<pid>`
#   失敗: 標準エラーに `NG: 理由` を出して exit 1
#   --dry-run: 送信せずペイン特定の結果だけ `DRY-RUN: ...` で出す
set -u

dry_run=0
text=""
while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) dry_run=1; shift ;;
    -h|--help) sed -n '2,15p' "$0"; exit 0 ;;
    --) shift; text="${1:-}"; shift || true ;;
    *)
      if [ -n "$text" ]; then
        echo "NG: 送るテキストは1つだけ指定してください" >&2
        exit 2
      fi
      text="$1"
      shift
      ;;
  esac
done

if [ -z "$text" ]; then
  echo "NG: 送る1行を引数で指定してください（例: '/model sonnet'）" >&2
  exit 2
fi

# 1. 自分を動かしている Claude Code プロセスを特定する
pid="${CLAUDE_PID:-}"
if [ -z "$pid" ]; then
  # 環境変数が無ければ親をたどって claude 本体を探す
  p=$$
  while [ "$p" -gt 1 ]; do
    cmd=$(ps -o command= -p "$p" 2>/dev/null)
    case "$cmd" in *claude*) pid=$p; break ;; esac
    p=$(ps -o ppid= -p "$p" 2>/dev/null | tr -d ' ')
    [ -z "$p" ] && break
  done
fi
if [ -z "$pid" ] || ! kill -0 "$pid" 2>/dev/null; then
  echo "NG: Claude Code のプロセスを特定できません（CLAUDE_PID=${CLAUDE_PID:-unset}）" >&2
  exit 1
fi

# 2. その TTY を持つ tmux ペインを探す
tty=$(ps -o tty= -p "$pid" | tr -d ' ')
if [ -z "$tty" ] || [ "$tty" = "??" ]; then
  echo "NG: PID $pid は端末（TTY）に紐づいていません。リモート/SDK セッションでは送れません" >&2
  exit 1
fi
pane=$(tmux list-panes -a -F '#{pane_id} #{pane_tty} #{session_name}:#{window_index}.#{pane_index}' 2>/dev/null \
  | awk -v t="/dev/$tty" '$2==t{print $1" "$3; exit}')
if [ -z "$pane" ]; then
  echo "NG: /dev/$tty を持つ tmux ペインがありません。このセッションは tmux の外で動いています" >&2
  exit 1
fi
pane_id=${pane%% *}
pane_name=${pane#* }

if [ "$dry_run" = 1 ]; then
  echo "DRY-RUN: pane=$pane_id ($pane_name) tty=$tty pid=$pid text=$text"
  exit 0
fi

# 3. 送る（スラッシュコマンドの補完ポップアップが出るので、少し待ってから Enter）
tmux send-keys -t "$pane_id" -l "$text"
sleep 0.3
tmux send-keys -t "$pane_id" Enter
echo "OK: pane=$pane_id ($pane_name) tty=$tty pid=$pid"
