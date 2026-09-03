import json
from pathlib import Path
from typing import Any

from ..client import DiscordClient

ACCESS_JSON = Path.home() / ".claude" / "channels" / "discord" / "access.json"

CHANNEL_TYPE_NAMES = {
    0: "テキスト",
    4: "カテゴリ",
    5: "アナウンス",
    15: "フォーラム",
}


def _format_channel(ch: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": ch["id"],
        "name": ch["name"],
        "type": CHANNEL_TYPE_NAMES.get(ch["type"], f"その他({ch['type']})"),
        "position": ch.get("position", 0),
        "parent_id": ch.get("parent_id"),
        "topic": ch.get("topic"),
    }


def _read_access() -> dict[str, Any]:
    if ACCESS_JSON.exists():
        return json.loads(ACCESS_JSON.read_text())
    return {}


def _write_access(data: dict[str, Any]) -> None:
    ACCESS_JSON.write_text(json.dumps(data, indent=2) + "\n")


def _add_channel_to_access(channel_id: str) -> None:
    data = _read_access()
    groups = data.setdefault("groups", {})
    if channel_id not in groups:
        allow_from = data.get("allowFrom", [])
        groups[channel_id] = {"requireMention": True, "allowFrom": allow_from}
        _write_access(data)


def _remove_channel_from_access(channel_id: str) -> None:
    data = _read_access()
    groups = data.get("groups", {})
    if channel_id in groups:
        del groups[channel_id]
        _write_access(data)


def register_channel_tools(mcp: Any, client: DiscordClient) -> None:

    @mcp.tool()
    async def list_channels() -> str:
        """サーバーのチャンネル一覧を取得する"""
        channels = await client.list_channels()

        categories = {ch["id"]: ch["name"] for ch in channels if ch["type"] == 4}
        result: list[dict[str, Any]] = []
        for ch in sorted(channels, key=lambda c: (c.get("position", 0))):
            formatted = _format_channel(ch)
            if ch.get("parent_id") and ch["parent_id"] in categories:
                formatted["category"] = categories[ch["parent_id"]]
            result.append(formatted)

        return json.dumps(result, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def create_channel(
        name: str,
        channel_type: int = 0,
        category_id: str | None = None,
        topic: str | None = None,
    ) -> str:
        """新しいチャンネルを作成する

        Args:
            name: チャンネル名
            channel_type: チャンネルタイプ（0=テキスト, 4=カテゴリ, 5=アナウンス, 15=フォーラム）
            category_id: 親カテゴリの ID（任意）
            topic: チャンネルのトピック（任意）
        """
        ch = await client.create_channel(name, channel_type, category_id, topic)
        if ch["type"] in (0, 5, 15):
            _add_channel_to_access(ch["id"])
        return json.dumps(_format_channel(ch), ensure_ascii=False, indent=2)

    @mcp.tool()
    async def delete_channel(channel_id: str) -> str:
        """チャンネルを削除する

        Args:
            channel_id: 削除するチャンネルの ID
        """
        _remove_channel_from_access(channel_id)
        await client.delete_channel(channel_id)
        return f"チャンネル {channel_id} を削除しました"

    @mcp.tool()
    async def edit_channel(
        channel_id: str,
        name: str | None = None,
        topic: str | None = None,
    ) -> str:
        """チャンネルの名前やトピックを変更する

        Args:
            channel_id: 編集するチャンネルの ID
            name: 新しい名前（任意）
            topic: 新しいトピック（任意）
        """
        ch = await client.edit_channel(channel_id, name, topic)
        return json.dumps(_format_channel(ch), ensure_ascii=False, indent=2)

    @mcp.tool()
    async def create_category(name: str) -> str:
        """チャンネルカテゴリを作成する

        Args:
            name: カテゴリ名
        """
        ch = await client.create_channel(name, channel_type=4)
        return json.dumps(_format_channel(ch), ensure_ascii=False, indent=2)

    @mcp.tool()
    async def list_threads(channel_id: str) -> str:
        """指定チャンネル（フォーラム等）のアクティブなスレッド一覧を取得する

        Args:
            channel_id: 親チャンネルの ID
        """
        threads = await client.list_active_threads()
        filtered = [
            {
                "id": t["id"],
                "name": t["name"],
                "parent_id": t.get("parent_id"),
                "created_at": t.get("thread_metadata", {}).get("create_timestamp"),
                "archived": t.get("thread_metadata", {}).get("archived", False),
                "message_count": t.get("message_count", 0),
            }
            for t in threads
            if t.get("parent_id") == channel_id
        ]
        filtered.sort(key=lambda t: t.get("created_at") or "", reverse=True)
        return json.dumps(filtered, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def close_thread(thread_id: str, lock: bool = False) -> str:
        """スレッドをクローズ（アーカイブ）する

        Args:
            thread_id: クローズするスレッドの ID
            lock: True にするとロックも行い、モデレーター以外は再開できなくなる（任意）
        """
        thread = await client.set_thread_archived(thread_id, archived=True, locked=lock or None)
        meta = thread.get("thread_metadata", {})
        return json.dumps({
            "id": thread["id"],
            "name": thread["name"],
            "archived": meta.get("archived", True),
            "locked": meta.get("locked", False),
        }, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def reopen_thread(thread_id: str) -> str:
        """クローズ済みのスレッドを再開（アーカイブ解除・ロック解除）する

        Args:
            thread_id: 再開するスレッドの ID
        """
        thread = await client.set_thread_archived(thread_id, archived=False, locked=False)
        meta = thread.get("thread_metadata", {})
        return json.dumps({
            "id": thread["id"],
            "name": thread["name"],
            "archived": meta.get("archived", False),
            "locked": meta.get("locked", False),
        }, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def create_forum_thread(
        channel_id: str,
        name: str,
        content: str | None = None,
    ) -> str:
        """フォーラムチャンネルにスレッドを作成する

        Args:
            channel_id: フォーラムチャンネルの ID
            name: スレッド名
            content: 初期メッセージの内容（任意）
        """
        thread = await client.create_forum_thread(channel_id, name, content)
        return json.dumps({
            "id": thread["id"],
            "name": thread["name"],
            "parent_id": thread.get("parent_id"),
        }, ensure_ascii=False, indent=2)
