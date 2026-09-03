# discord-session（Claude Code プラグイン）

Claude Code の公式 Discord プラグインに無い機能を補う自作プラグイン。詳細は README.md、
移植の手順書は docs/migration-plan.md を参照。

## 開発ルール

- 変更したら `.claude-plugin/plugin.json` と `.claude-plugin/marketplace.json` の version を上げてコミットし、
  discord-workspace で `claude plugin update discord-session@ryuki-plugins --scope project` → Discord セッションで `/reload-plugins`
- bash と Python は処理内容で選ぶ。プロセス・tmux・ファイルの操作は bash、JSON や HTTP、日時計算のように
  構造化データを扱う処理は Python。片方の中にもう片方を埋め込む（bash 内の `python3 -c` など）くらいなら一本に寄せる。
  無理に統一しない
- Python を使うときは `uv run --script` で動かす（shebang `#!/usr/bin/env -S uv run --script` と inline metadata を付ける）
- 検証は tmux 内の使い捨てセッションで行う。`--channels` 付きの claude を 2 つ立てない（Discord に二重返信する）
- 作業の区切りごとに「現在の状況」を更新してコミットする
- ユーザー固有の値（Discord のユーザー ID、チャンネル ID、ギルド ID）をスクリプトやスキルに直書きしない。
  `~/.claude/channels/discord/` の設定ファイルか環境変数から読む

## 現在の状況

- 最終更新: 2026-09-03（GitHub へ push 済み）
- 完了済み: v0.1.1。`/discord-session:ctx`、`/discord-session:clear` と完了通知フック、Bot ステータスへの使用量表示
  （アクティビティ表示）、ランチャー `start-discord.sh`（`~/.local/bin/discord-start`）、statusline ラッパー、README。
  discord-workspace にプロジェクトスコープでインストール済みで、稼働中の Discord セッションでも読み込み済み
- 残り・次の一歩: docs/migration-plan.md の手順 1（original-tools のサーバー管理 MCP を `.mcp.json` へ移植）から。
  続けて手順 2（setup-channel とフックの移植）。実施は 2026-09-03 以降にリュウキの合図で
- リモート: https://github.com/ryuki-imachi/claude-code-discord-session（プライベート。公開時は Public に切り替える）
- 関連リソース: discord-workspace の `memory/tasks.md`（台帳の入口）と `docs/discord-context-control.md`（設計メモ）、
  `~/Desktop/work/claude-discord-channel/original-tools/`（移植元）、Discord の雑談チャンネル
