import asyncio
from typing import Any

import httpx

BASE_URL = "https://discord.com/api/v10"


class DiscordClient:
    def __init__(self, bot_token: str, guild_id: str) -> None:
        self.guild_id = guild_id
        self._headers = {"Authorization": f"Bot {bot_token}"}
        self._http = httpx.AsyncClient(base_url=BASE_URL, headers=self._headers, timeout=10.0)

    async def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        response = await self._http.request(method, path, **kwargs)

        if response.status_code == 429:
            retry_after = response.json().get("retry_after", 1.0)
            await asyncio.sleep(retry_after)
            response = await self._http.request(method, path, **kwargs)

        response.raise_for_status()

        if response.status_code == 204:
            return None
        return response.json()

    async def list_channels(self) -> list[dict[str, Any]]:
        return await self._request("GET", f"/guilds/{self.guild_id}/channels")

    async def create_channel(self, name: str, channel_type: int = 0,
                             category_id: str | None = None, topic: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": name, "type": channel_type}
        if category_id:
            payload["parent_id"] = category_id
        if topic:
            payload["topic"] = topic
        return await self._request("POST", f"/guilds/{self.guild_id}/channels", json=payload)

    async def delete_channel(self, channel_id: str) -> None:
        await self._request("DELETE", f"/channels/{channel_id}")

    async def edit_channel(self, channel_id: str, name: str | None = None,
                           topic: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if topic is not None:
            payload["topic"] = topic
        return await self._request("PATCH", f"/channels/{channel_id}", json=payload)

    async def create_forum_thread(self, channel_id: str, name: str,
                                   content: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"name": name}
        if content:
            payload["message"] = {"content": content}
        return await self._request("POST", f"/channels/{channel_id}/threads", json=payload)

    async def set_thread_archived(self, thread_id: str, archived: bool,
                                  locked: bool | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"archived": archived}
        if locked is not None:
            payload["locked"] = locked
        return await self._request("PATCH", f"/channels/{thread_id}", json=payload)

    async def list_active_threads(self) -> list[dict[str, Any]]:
        data = await self._request("GET", f"/guilds/{self.guild_id}/threads/active")
        return data.get("threads", [])

    async def close(self) -> None:
        await self._http.aclose()
