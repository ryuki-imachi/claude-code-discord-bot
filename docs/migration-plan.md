# 自作機能の discord-session プラグインへの集約 手順書

作成: 2026-09-03（実施は 9/3 以降）

## 方針

公式 Discord プラグインに無い自作機能のうち、汎用的なものをこのプラグインへ集め、
kuroko-chan の運用ルールと台帳に依存するものは discord-workspace に残す。

| 対象 | 行き先 | 理由 |
| --- | --- | --- |
| サーバー管理 MCP（original-tools、9 ツール） | プラグイン `.mcp.json` | 公式に無い機能で汎用。今はグローバル登録のため無関係なセッションでも起動している |
| setup-channel スキル + remind-channel-access フック | プラグイン | 公式プラグインの access.json 受信設定の穴を塞ぐ汎用ワークフロー。ユーザー ID の直書きだけ直す |
| sync-threads / close-article-thread / save-knowledge / task-memo / inject-ledgers | discord-workspace に残す | memory/ の台帳、knowledge/、#記事の種 のチャンネル ID に依存した運用そのもの |

## 手順 1. サーバー管理 MCP の移植

現状: `~/Desktop/work/claude-discord-channel/original-tools/`（Python 3.10+、FastMCP、httpx、python-dotenv、uv）。
`~/.claude.json` の `mcpServers.discord-server-admin` にグローバル登録。トークンとギルド ID は original-tools 直下の `.env`
（`DISCORD_BOT_TOKEN`、`DISCORD_GUILD_ID`）から `load_dotenv` で読んでいる。
ツール: list_channels / create_channel / create_category / edit_channel / delete_channel /
create_forum_thread / list_threads / close_thread / reopen_thread。

1. ソースを移動する: `original-tools/{pyproject.toml,uv.lock,src/,docs/}` → `discord-session/mcp/server-admin/`。
   `.env` は移動しない（後述のとおり共有の場所から読む）。`.venv` は作り直す
2. `server.py` のトークン読み込みを直す。優先順は「環境変数 → `${DISCORD_STATE_DIR:-~/.claude/channels/discord}/.env`」
   にして、公式プラグインと同じファイルを共有する。`DISCORD_GUILD_ID` も同じファイルに書けるようにする
   （代案: 未設定なら `GET /users/@me/guilds` で Bot の参加サーバーを取り、1 つだけならそれを使う）
3. `.mcp.json` をプラグイン直下に置く

```json
{
  "mcpServers": {
    "server-admin": {
      "command": "uv",
      "args": ["run", "--directory", "${CLAUDE_PLUGIN_ROOT}/mcp/server-admin", "python", "-m", "discord_mcp.server"]
    }
  }
}
```

4. ツール名が変わる。`mcp__discord-server-admin__<tool>` → `mcp__plugin_discord-session_server-admin__<tool>`
   （公式の `mcp__plugin_discord_discord__reply` と同じ規則。実際の名前は `/mcp` かツール一覧で確認してから置換する）。
   discord-workspace 側で書き換える場所:
   - `.claude/settings.json` の `permissions.allow`（8 ルール）と PostToolUse フックの matcher
   - `.claude/skills/setup-channel/SKILL.md`、`sync-threads/SKILL.md`、`close-article-thread/SKILL.md` の allowed-tools と本文
   - `CLAUDE.md` の「利用可能なツール」表、`docs/discord-context-control.md`
5. グローバル登録を外す: `claude mcp remove discord-server-admin -s user`（`~/.claude.json` から消える）
6. `plugin.json` と `marketplace.json` の version を 0.2.0 に上げてコミット →
   discord-workspace で `claude plugin update discord-session@ryuki-plugins --scope project` → Discord セッションで `/reload-plugins`
7. 検証
   - discord-workspace の使い捨てセッションで `list_channels` が動く（tmux 内、`--channels` は付けない）
   - 別ディレクトリのセッションで server-admin の MCP が起動しない（子プロセス一覧で確認）
   - Discord から「テスト用チャンネル作って」→ setup-channel の流れが通る（受信テストまで）
8. 片付け: `original-tools/` を削除し、`claude-discord-channel/README.md` の表を更新。`qiita-article/` の記事に
   MCP のパスが書かれていないか確認する

## 手順 2. setup-channel とフックの移植

1. `discord-workspace/.claude/skills/setup-channel/` → `discord-session/skills/setup-channel/`
   - allowed-tools のツール名を新しい名前に
   - `allowFrom` へのユーザー ID の直書きをやめ、`~/.claude/channels/discord/access.json` の
     トップレベル `allowFrom` をそのまま使う手順に書き換える
   - 「CLAUDE.md のチャンネル構成表を更新」「memory/active-threads.md にセクション追加」は
     「プロジェクトの CLAUDE.md や台帳にチャンネル一覧があれば更新する」という一般化した表現にする
2. `discord-workspace/.claude/hooks/remind-channel-access.sh` → `discord-session/hooks/remind-channel-access.sh`
   - 注入する文面のユーザー ID を access.json から読むように（`python3` か `jq` で `allowFrom` を取る）
   - `hooks/hooks.json` に PostToolUse（matcher: 新しい create_channel のツール名）を追加
3. discord-workspace 側から skill と hook、settings.json の PostToolUse エントリを削除。CLAUDE.md の
   「新規作成時は必ず /setup-channel の手順に従い」を `/discord-session:setup-channel` に書き換える
4. version を上げて update → `/reload-plugins` → Discord から「テスト用チャンネル作って」で通しテスト → テストチャンネル削除

## 注意

- `--channels` 付きの claude を検証用に 2 つ立てない（二重返信）。検証は `--channels` 無しの使い捨てセッションで行う
- プラグインの MCP サーバーは `/reload-plugins` で再起動される。Discord ブリッジ（公式プラグイン）も一瞬つなぎ直る
- ツール名の置換漏れがあると、スキルが古い名前を呼んで許可プロンプトや失敗になる。
  `grep -rn discord-server-admin ~/Desktop/work/discord-workspace --include='*.md' --include='*.json' --include='*.sh'` で最後に確認する
- 作業の区切りごとに、このプラグインの `CLAUDE.md`「現在の状況」と discord-workspace の `memory/tasks.md` を更新する

## その後の候補

- GitHub に公開し、marketplace をリポジトリ経由にする（`claude plugin marketplace add ryuki-imachi/<repo>`）
- 公式プラグインの `server.ts` をフォークしてプレゼンス更新を統合する（Gateway 接続を 1 本にできる）
- Developer Portal で Presence Intent を有効にし、`discord_presence_check.py` で表示を自動確認できるようにする

## 公開前チェックリスト（権利・個人情報）

2026-09-03 に確認した内容。公開作業のときにこの節を上から順に見る。

### ライセンス

- 自作コードのライセンスを決めて `LICENSE` を置く。MIT を推奨（依存と公式プラグインのどちらとも矛盾しない）
- 依存ライブラリは配布に含めず `uv run` で取得するので、表記義務は実質無い。参考: discord.py は MIT、mcp は MIT、
  httpx は BSD-3-Clause、python-dotenv は BSD-3-Clause、aiohttp は Apache-2.0 と MIT
- 公式 Discord プラグイン（`anthropics/claude-plugins-official`）は Apache-2.0。今のプラグインは公式のコードを含んで
  いないので義務は無い。将来 `server.ts` をフォークして同梱する場合は、Apache-2.0 の条件に従う。
  具体的には、元の LICENSE ファイル（と NOTICE があればそれ）を同梱し、改変したファイルに「変更した」旨と元の著作権表示を残す。
  MIT のリポジトリに Apache-2.0 のファイルが混ざるのは問題ないが、README にファイル単位でライセンスを書き分ける

### 商標・名乗り方

- 「Discord」「Claude Code」を製品名として使わず、README の冒頭に「非公式のコミュニティ製プラグインで、Discord 社
  および Anthropic 社とは無関係」と明記する。`discord-session` のような技術的な名前自体は discord.py などと同じ使い方で問題ない
- Discord のロゴ・アイコン画像は同梱しない

### 個人情報・秘密情報

- Bot トークンを絶対に含めない。`.env` と `.venv/` は `.gitignore` 済み。MCP を移植するとき `original-tools/.env` は移動しない
- Discord のユーザー ID・チャンネル ID・ギルド ID は個人のサーバーを特定できるので、コードにも文書にも書かない
  （2026-09-03 に文書から除去し、コミット履歴も書き換え済み）。設定は `~/.claude/channels/discord/` から読む
- `/Users/ryuki/...` のような絶対パスは `<plugin>` や `~/path/to/...` に置き換える。Bot 名 kuroko-chan も「あなたの Bot」に直す
- `plugin.json` の author email は GitHub の noreply アドレスなのでそのままでよい
- 公開直前に `git log --all -p | grep -E '[0-9]{17,19}|sk-ant|DISCORD_BOT_TOKEN='` で履歴ごと確認する。
  不安なら orphan ブランチで履歴を一本化してから push する

### 規約

- Discord Developer Policy: 自分の Bot トークンで自分のサーバーを操作する通常の Bot なのでセルフボットには当たらない。
  プレゼンス更新は変化時のみ・最短 20 秒間隔で、Gateway のレート制限（120 イベント/60 秒）に十分収まる
- Anthropic: Claude Code のプラグイン仕様は公開されており、自作プラグインの公開・配布は自由。
  `claude-plugins-official` へ投稿する場合は別途レビューがある

### 同梱物の確認

- `original-tools/docs/design.md` などに個人サーバーの情報が無いか読む
- `qiita-article/` の画像は記事用なので公開リポジトリに入れない
