"""
bot_client.py – WebSocket client that connects to the Mineflayer bot layer.

Receives game-state events and forwards them to the planner, then sends
back action commands returned by the planner.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from typing import Any

import websockets
from websockets.exceptions import ConnectionClosedError

log = logging.getLogger("mineai.bot_client")


class BotClient:
    """
    Maintains the WebSocket connection to the Node.js bot and drives the
    planner's think/act cycle.
    """

    RECONNECT_DELAY = 5  # seconds

    def __init__(self, uri: str, planner) -> None:
        self._uri     = uri
        self._planner = planner
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._pending: dict[str, asyncio.Future] = {}
        self._running  = True
        self._game_state: dict[str, Any] = {}

    # ── Public ────────────────────────────────────────────────────────────────

    async def run(self) -> None:
        """Connect (with auto-reconnect) and start the event + think loops."""
        while self._running:
            try:
                async with websockets.connect(self._uri, ping_interval=20) as ws:
                    self._ws = ws
                    log.info("Connected to bot WebSocket at %s", self._uri)
                    await asyncio.gather(
                        self._recv_loop(),
                        self._think_loop(),
                    )
            except (ConnectionRefusedError, OSError):
                log.warning("Could not connect to bot – retrying in %ss…", self.RECONNECT_DELAY)
            except ConnectionClosedError as exc:
                log.warning("Connection closed (%s) – reconnecting…", exc)
            finally:
                self._ws = None

            if self._running:
                await asyncio.sleep(self.RECONNECT_DELAY)

    async def close(self) -> None:
        self._running = False
        if self._ws:
            await self._ws.close()

    async def send_action(
        self, action: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Send an action to the bot and await its result (timeout: 30 s)."""
        if not self._ws:
            return {"success": False, "error": "Not connected"}
        action_id = str(uuid.uuid4())
        fut: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending[action_id] = fut
        msg = json.dumps({"type": "action", "action": action, "params": params or {}, "id": action_id})
        await self._ws.send(msg)
        try:
            return await asyncio.wait_for(fut, timeout=30)
        except asyncio.TimeoutError:
            self._pending.pop(action_id, None)
            return {"success": False, "error": "Action timed out"}

    # ── Private ───────────────────────────────────────────────────────────────

    async def _recv_loop(self) -> None:
        async for raw in self._ws:
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                continue

            match msg.get("type"):
                case "event":
                    await self._handle_event(msg["event"], msg.get("data", {}))
                case "action_result":
                    fut = self._pending.pop(msg.get("id"), None)
                    if fut and not fut.done():
                        fut.set_result(msg)

    async def _handle_event(self, event: str, data: dict[str, Any]) -> None:
        log.debug("Event: %s", event)
        if event in ("state", "spawned"):
            self._game_state = data
        elif event == "health":
            self._game_state.update(data)
        elif event == "chat":
            log.info("[Chat] <%s> %s", data.get("username"), data.get("message"))
        elif event == "death":
            log.warning("[Bot] Died – respawning.")
            self._game_state["health"] = 0
        elif event == "disconnected":
            raise ConnectionClosedError(None, None)

        # Let the planner react to events too
        await self._planner.on_event(event, data, self)

    async def _think_loop(self) -> None:
        """Periodic 'think' trigger for autonomous goal pursuit."""
        from mineai.config import load_config
        cfg = load_config()
        while self._running:
            await asyncio.sleep(cfg.think_interval)
            if self._game_state:
                await self._planner.think(self._game_state, self)
