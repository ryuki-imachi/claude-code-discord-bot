#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = ["discord.py>=2.4"]
# ///
"""
discord_presence_check.py — Bot 自身のプレゼンス（ステータス・アクティビティ）を Gateway から読んで表示する確認用スクリプト
Presence Intent（Developer Portal の Privileged Gateway Intents）が必要。無効だと PrivilegedIntentsRequired で終了する。
"""
import os
import re
import sys

import discord

HOME = os.path.expanduser("~")


def load_token():
    if os.environ.get("DISCORD_BOT_TOKEN"):
        return os.environ["DISCORD_BOT_TOKEN"]
    with open(os.path.join(HOME, ".claude", "channels", "discord", ".env")) as f:
        for line in f:
            m = re.match(r"^DISCORD_BOT_TOKEN=(.*)$", line.strip())
            if m:
                return m.group(1)


class Checker(discord.Client):
    async def on_ready(self):
        for g in self.guilds:
            me = g.me
            acts = [(a.type.name, getattr(a, "name", None), getattr(a, "state", None)) for a in me.activities]
            print(f"guild={g.name} status={me.status} activities={acts}", flush=True)
        await self.close()


intents = discord.Intents.none()
intents.guilds = True
intents.presences = True
try:
    Checker(intents=intents).run(load_token(), log_handler=None)
except discord.PrivilegedIntentsRequired as e:
    print(f"Presence Intent が無効: {e}", file=sys.stderr)
    sys.exit(3)
