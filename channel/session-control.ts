/**
 * session-control.ts — Discord から届いた /model と /effort を、この channel サーバーを起動した
 * Claude Code が動いている tmux ペインへスラッシュコマンドとして送り込む。
 *
 * Claude のターンを使わずに channel サーバー（別プロセス）が直接 tmux を操作する。
 * 送り先は presence.ts と同じ方法で特定する。
 *   findClaudePid()（親をたどって claude 本体の PID）→ その PID の TTY → 同じ TTY を持つ tmux ペイン
 * スラッシュコマンドはターン実行中でもキューされ、ターン終了直後に実行される。
 * そのため送信した時点では切り替わっていないので、ステータスラインのダンプを最大 90 秒監視し、
 * 値が変わったのを見つけたら依頼元のチャンネルへ「切り替えたよ」を投稿する。
 *
 * 環境変数
 *   DISCORD_BOT_STATUSLINE_DIR  ダンプの場所（presence.ts と共通）
 */
import type { Client } from 'discord.js'
import { findClaudePid, pickSession, type Dump } from './presence'

/** /model の引数に使えるエイリアス。これ以外は claude- で始まる完全なモデル ID だけ受ける */
export const MODEL_ALIASES = ['best', 'fable', 'opus', 'sonnet', 'haiku', 'sonnet[1m]', 'opus[1m]', 'opusplan']
/** /effort の引数に使えるレベル */
export const EFFORT_LEVELS = ['low', 'medium', 'high', 'xhigh', 'max', 'auto']

const WATCH_TIMEOUT_MS = 90_000
const WATCH_INTERVAL_MS = 2_000
const SEND_KEYS_DELAY_MS = 300

export type SettingKind = 'model' | 'effort'
export type PaneInfo = { paneId: string; paneName: string; tty: string }
/** 呼び出し側（server.ts）はこれを見て ephemeral か通常メッセージかを決める */
export type ControlResult = { ok: boolean; message: string }

export function log(msg: string): void {
  process.stderr.write(`discord channel: session-control: ${msg}\n`)
}

function run(cmd: string[]): { ok: boolean; out: string } {
  try {
    const p = Bun.spawnSync(cmd)
    return { ok: p.exitCode === 0, out: p.stdout.toString() }
  } catch (e) {
    log(`spawn failed: ${cmd.join(' ')}: ${e}`)
    return { ok: false, out: '' }
  }
}

/** 引数の検証。問題なければ null、駄目なら Discord にそのまま出す理由を返す */
export function validateValue(kind: SettingKind, value: string): string | null {
  const v = value.trim()
  if (!v) return kind === 'model' ? 'モデル名が空だよ。' : 'effort のレベルが空だよ。'
  if (kind === 'model') {
    if (MODEL_ALIASES.includes(v) || v.startsWith('claude-')) return null
    return `「${v}」は使えないモデル指定だよ。使えるのは ${MODEL_ALIASES.join(' / ')}、または claude- で始まる完全なモデル ID。`
  }
  if (EFFORT_LEVELS.includes(v)) return null
  return `「${v}」は使えない effort レベルだよ。使えるのは ${EFFORT_LEVELS.join(' / ')}。`
}

/** claude が動いている tmux ペインを探す。見つからなければ理由を返す（clear_session.sh と同じ手順） */
export function findClaudePane(pid: number): PaneInfo | { error: string } {
  const tty = run(['ps', '-o', 'tty=', '-p', String(pid)]).out.trim()
  if (!tty || tty === '??') {
    return { error: `claude（PID ${pid}）が端末に紐づいていないよ。tmux の外やリモートのセッションでは操作できないんだ。` }
  }
  const list = run(['tmux', 'list-panes', '-a', '-F', '#{pane_id} #{pane_tty} #{session_name}:#{window_index}.#{pane_index}'])
  for (const line of list.out.split('\n')) {
    const [paneId, paneTty, paneName] = line.trim().split(' ')
    if (paneId && paneTty === `/dev/${tty}` && paneName) return { paneId, paneName, tty }
  }
  return { error: `/dev/${tty} を持つ tmux ペインが見つからないよ。このセッションは tmux の外で動いているみたい。` }
}

/** ペインへスラッシュコマンドを打ち込む。補完ポップアップが出るので少し待ってから Enter */
export async function sendSlashCommand(paneId: string, text: string): Promise<void> {
  run(['tmux', 'send-keys', '-t', paneId, '-l', text])
  await Bun.sleep(SEND_KEYS_DELAY_MS)
  run(['tmux', 'send-keys', '-t', paneId, 'Enter'])
}

function dumpedAtMs(d: Dump | null): number {
  const t = d?._dumped_at ? Date.parse(d._dumped_at) : NaN
  return Number.isNaN(t) ? 0 : t
}

function fmtCurrent(d: Dump | null): string {
  return `${d?.model?.display_name ?? '不明'} / effort ${d?.effort?.level ?? '不明'}`
}

/** 送信前の値と比べて切り替わったか。指定値そのものに一致した場合も切り替わりとみなす */
export function detectChange(kind: SettingKind, value: string, before: Dump | null, now: Dump): boolean {
  const target = value.toLowerCase()
  if (kind === 'model') {
    const id = (now.model?.id ?? '').toLowerCase()
    const disp = (now.model?.display_name ?? '').toLowerCase()
    if (!id && !disp) return false
    const changed = id !== (before?.model?.id ?? '').toLowerCase() || disp !== (before?.model?.display_name ?? '').toLowerCase()
    return changed || id.includes(target) || disp.includes(target)
  }
  const level = (now.effort?.level ?? '').toLowerCase()
  if (!level) return false
  return level !== (before?.effort?.level ?? '').toLowerCase() || level === target
}

export function buildNotifyMessage(kind: SettingKind, value: string, now: Dump): string {
  const disp = now.model?.display_name ?? '不明'
  const level = now.effort?.level ?? value
  return kind === 'model' ? `モデルを ${disp} に切り替えたよ（effort ${level}）` : `effort を ${level} に切り替えたよ（${disp}）`
}

async function postToChannel(client: Client, chatId: string, text: string): Promise<void> {
  try {
    const ch = await client.channels.fetch(chatId)
    if (!ch || !ch.isTextBased() || !('send' in ch)) throw new Error('channel is not sendable')
    await ch.send(text)
  } catch (e) {
    log(`failed to post to ${chatId}: ${e}`)
  }
}

/** 送信後、ダンプが更新されて値が変わるのを最大 90 秒待つ。見つけたら投稿、駄目ならログだけ */
function watchChange(kind: SettingKind, value: string, chatId: string, client: Client, claudePid: number, before: Dump | null, sentAt: number): void {
  const deadline = Date.now() + WATCH_TIMEOUT_MS
  const timer = setInterval(() => {
    let now: Dump | null = null
    try {
      now = pickSession(claudePid)
    } catch (e) {
      log(`watch read failed: ${e}`)
    }
    if (now && dumpedAtMs(now) > sentAt && detectChange(kind, value, before, now)) {
      clearInterval(timer)
      const message = buildNotifyMessage(kind, value, now)
      log(`detected: ${kind}=${value} -> ${message}`)
      void postToChannel(client, chatId, message)
      return
    }
    if (Date.now() >= deadline) {
      clearInterval(timer)
      log(`timeout: ${kind}=${value} の切り替わりを ${WATCH_TIMEOUT_MS / 1000} 秒以内に確認できなかった（投稿はしない）`)
    }
  }, WATCH_INTERVAL_MS)
  // 監視が残っていてもサーバーの終了を妨げないようにする
  timer.unref()
}

/** /model と /effort の本体。検証 → ペイン特定 → 送信 → 受付メッセージを返し、裏で切り替わりを監視する */
export async function switchSetting(kind: SettingKind, value: string, chatId: string, client: Client): Promise<ControlResult> {
  const invalid = validateValue(kind, value)
  if (invalid) return { ok: false, message: invalid }
  const v = value.trim()

  const pid = findClaudePid()
  if (!pid) return { ok: false, message: 'claude 本体のプロセスを特定できなかったよ。ターミナルで確認してね。' }
  const pane = findClaudePane(pid)
  if ('error' in pane) return { ok: false, message: pane.error }

  const before = pickSession(pid)
  const sentAt = Date.now()
  await sendSlashCommand(pane.paneId, `/${kind} ${v}`)
  log(`sent /${kind} ${v} to ${pane.paneId} (${pane.paneName}, pid ${pid})`)

  watchChange(kind, v, chatId, client, pid, before, sentAt)

  const head = `/${kind} ${v} を送ったよ（今は ${fmtCurrent(before)}）。次のメッセージから切り替わるよ。`
  let tail = ''
  if (kind === 'model') tail = 'ターミナルで新しく開くセッションのデフォルトも変わるよ。'
  else if (v === 'max') tail = 'max はこのセッション限りだよ。'
  else if (v === 'auto') tail = 'auto は保存した設定をクリアするよ。'
  return { ok: true, message: head + tail }
}
