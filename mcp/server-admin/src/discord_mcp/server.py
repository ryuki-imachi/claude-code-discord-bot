import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from .client import DiscordClient
from .tools.channels import register_channel_tools

# 環境変数に無ければ、公式 Discord プラグインと共有する .env を読み込む
# (${DISCORD_STATE_DIR:-~/.claude/channels/discord}/.env)
if not os.environ.get("DISCORD_BOT_TOKEN") or not os.environ.get("DISCORD_GUILD_ID"):
    _state_dir = Path(os.environ.get("DISCORD_STATE_DIR", str(Path.home() / ".claude" / "channels" / "discord")))
    load_dotenv(_state_dir / ".env", override=False)

bot_token = os.environ.get("DISCORD_BOT_TOKEN", "")
guild_id = os.environ.get("DISCORD_GUILD_ID", "")

if not bot_token or bot_token == "your_bot_token_here":
    print(
        "DISCORD_BOT_TOKEN が設定されていません。"
        "~/.claude/channels/discord/.env に DISCORD_BOT_TOKEN を書いてください。",
        file=sys.stderr,
    )
    sys.exit(1)


def detect_guild_id(token: str) -> str:
    """DISCORD_GUILD_ID が無いとき、Bot の参加サーバーが 1 つだけならそれを使う"""
    import httpx

    from .client import BASE_URL

    try:
        response = httpx.get(
            f"{BASE_URL}/users/@me/guilds",
            headers={"Authorization": f"Bot {token}"},
            timeout=10.0,
        )
        response.raise_for_status()
        guilds = response.json()
    except Exception as e:  # noqa: BLE001
        print(f"Bot の参加サーバーを取得できませんでした（{e}）。トークンを確認するか、DISCORD_GUILD_ID を設定してください。", file=sys.stderr)
        sys.exit(1)
    if len(guilds) == 1:
        return str(guilds[0]["id"])
    if not guilds:
        print("Bot がどのサーバーにも参加していません。サーバーに招待するか、DISCORD_GUILD_ID を設定してください。", file=sys.stderr)
    else:
        names = ", ".join(f"{g.get('name')} ({g.get('id')})" for g in guilds)
        print(f"Bot が複数のサーバーに参加しています: {names}。DISCORD_GUILD_ID でどれを使うか指定してください。", file=sys.stderr)
    sys.exit(1)


if not guild_id or guild_id == "your_guild_id_here":
    guild_id = detect_guild_id(bot_token)

mcp = FastMCP("server-admin")
client = DiscordClient(bot_token, guild_id)

register_channel_tools(mcp, client)

if __name__ == "__main__":
    mcp.run(transport="stdio")
