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
  `/reload-plugins` で入れ替わるのはスキルとフックだけ。channel/ や mcp/ のコード、commands.json を変えたときは
  セッションを再起動する（`discord-start --resume <session-id>`）。再起動しないと古いコードが動き続ける
- bash と Python は処理内容で選ぶ。プロセス・tmux・ファイルの操作は bash、JSON や HTTP、日時計算のように
  構造化データを扱う処理は Python。片方の中にもう片方を埋め込む（bash 内の `python3 -c` など）くらいなら一本に寄せる。
  無理に統一しない
- Python を使うときは `uv run --script` で動かす（shebang `#!/usr/bin/env -S uv run --script` と inline metadata を付ける）
- 検証は tmux 内の使い捨てセッションで行う。`--channels` 付きの claude を 2 つ立てない（Discord に二重返信する）
- 作業の区切りごとに「現在の状況」を更新してコミットする
- ユーザー固有の値（Discord のユーザー ID、チャンネル ID、ギルド ID）をスクリプトやスキルに直書きしない。
  `~/.claude/channels/discord/` の設定ファイルか環境変数から読む

## 現在の状況

- 最終更新: 2026-09-03
- 完了済み: #1 サーバー管理 MCP の取り込み、#2 discord-workspace の切り替え、#3 setup-channel とフックの移植、#4 ギルド ID 自動判定、
  #9 ダンプ掃除、#5 公式 Discord プラグインのフォーク（channel/、Apache-2.0）とプレゼンス統合、#6 スラッシュコマンド /ctx /clear、
  #7 ワークスペース用コマンド（追加定義 ~/.claude/discord-bot/commands.json）、#8 のうち個人環境の記述の一般化と履歴走査（v0.6.1）
- 残り・次の一歩: フォーク版を channel にするには承認リスト対応が必要（管理者設定 allowedChannelPlugins、要 sudo。README セットアップ 4）。
  それまで channel は公式プラグイン（ランチャー既定 official）。承認後に `DISCORD_BOT_CHANNEL_MODE=fork` で再起動して
  受信・スラッシュコマンドを確認する。#8 の Public 化は開発者の確認待ち
- リモート: https://github.com/ryuki-imachi/claude-code-discord-bot（プライベート。公開時は Public に切り替える）
- 関連リソース: discord-workspace の `memory/tasks.md`（台帳の入口）と `docs/discord-context-control.md`（設計メモ）
