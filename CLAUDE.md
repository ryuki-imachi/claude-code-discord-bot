# discord-bot（Claude Code プラグイン）

Claude Code の公式 Discord プラグインに無い機能を補う自作プラグイン。詳細は README.md、
移植の手順書は docs/migration-plan.md を参照。

## 開発ルール

- 作業は GitHub の issue 単位で進める（https://github.com/ryuki-imachi/claude-code-discord-bot/issues）。
  issue ごとに `main` から `issue-<番号>-<短い英語>` のブランチを切り、終わったら PR を作って `main` にマージする。
  `main` に直接コミットしない
- issue には推奨モデルをラベルで付けてある（`model:sonnet` / `model:opus` / `model:fable`）。ラベルより上のモデルで
  やる分には構わない。着手時にそのモデルで難しいと感じたら、無理に進めず issue にコメントを残して止める
- 着手時に issue の「やること」を読み、完了時に受け入れ条件を実際に確認してから PR を出す。PR 本文に `Closes #<番号>` を書く
- 変更したら `.claude-plugin/plugin.json` と `.claude-plugin/marketplace.json` の version を上げてコミットし、
  discord-workspace で `claude plugin update discord-bot@ryuki-plugins --scope project` → Discord セッションで `/reload-plugins`
- bash と Python は処理内容で選ぶ。プロセス・tmux・ファイルの操作は bash、JSON や HTTP、日時計算のように
  構造化データを扱う処理は Python。片方の中にもう片方を埋め込む（bash 内の `python3 -c` など）くらいなら一本に寄せる。
  無理に統一しない
- Python を使うときは `uv run --script` で動かす（shebang `#!/usr/bin/env -S uv run --script` と inline metadata を付ける）
- 検証は tmux 内の使い捨てセッションで行う。`--channels` 付きの claude を 2 つ立てない（Discord に二重返信する）
- 作業の区切りごとに「現在の状況」を更新してコミットする
- ユーザー固有の値（Discord のユーザー ID、チャンネル ID、ギルド ID）をスクリプトやスキルに直書きしない。
  `~/.claude/channels/discord/` の設定ファイルか環境変数から読む

## 現在の状況

- 最終更新: 2026-09-03（issue #3 対応。PR 作成済み・未マージ）
- 完了済み: v0.1.1 の基本機能（`/discord-bot:ctx`、`/discord-bot:clear` と完了通知フック、Bot ステータスへの使用量表示、
  ランチャー `start-discord.sh`、statusline ラッパー、README）に加え、issue #1（サーバー管理 MCP の取り込み）、
  #2（discord-workspace の切り替え）、#4（ギルド ID 自動判定）、#9（statusline ダンプの掃除）、
  #3（`/discord-bot:setup-channel` スキルと `remind-channel-access.py` フックの移植）
- issue #3: `skills/setup-channel/SKILL.md` を移植し、ユーザー ID の直書きを access.json のトップレベル `allowFrom`
  参照に置き換えた。`hooks/remind-channel-access.py`（PostToolUse、access.json を読んで受信設定の注意書きを注入）を追加
- 残り・次の一歩: issue #3 の PR マージ後、issue #5（公式フォークとプレゼンス統合）に進む
- リモート: https://github.com/ryuki-imachi/claude-code-discord-bot（プライベート。公開時は Public に切り替える）
- 関連リソース: discord-workspace の `memory/tasks.md`（台帳の入口）と `docs/discord-context-control.md`（設計メモ）、
  Discord の雑談チャンネル
