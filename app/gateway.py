"""WebSocket 网关：接收私聊/群聊事件，并对 “openid” 查询做出回复。"""
from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

import websockets
from loguru import logger

from .config import Settings
from .qq_client import QQClient


class GatewayClient:
    def __init__(self, settings: Settings, qq: QQClient):
        self.settings = settings
        self.qq = qq
        self._stop = asyncio.Event()
        self._session_id: str | None = None
        self._last_seq: int | None = None

    def request_stop(self) -> None:
        self._stop.set()

    async def run(self) -> None:
        while not self._stop.is_set():
            try:
                await self._connect_once()
            except asyncio.CancelledError:
                raise
            except Exception as e:  # noqa: BLE001 - 网关异常需要重连
                logger.error("网关连接异常: {}", e)
            await self._sleep(self.settings.gateway_retry_seconds)

    async def _sleep(self, seconds: float) -> None:
        try:
            await asyncio.wait_for(self._stop.wait(), timeout=seconds)
        except asyncio.TimeoutError:
            pass

    async def _connect_once(self) -> None:
        url = await self.qq.get_gateway_url()
        token = await self.qq.access_token()
        logger.info("连接网关: {}", url)

        async with websockets.connect(url, max_size=8 * 1024 * 1024, ping_interval=None) as ws:
            hello = json.loads(await asyncio.wait_for(ws.recv(), timeout=20))
            heartbeat = int((hello.get("d") or {}).get("heartbeat_interval", 41250))

            if self._session_id:
                await ws.send(json.dumps({
                    "op": 6,
                    "d": {
                        "token": f"QQBot {token}",
                        "session_id": self._session_id,
                        "seq": self._last_seq,
                    },
                }))
                logger.info("已发送 Resume (session={})", self._session_id)
            else:
                await ws.send(json.dumps({
                    "op": 2,
                    "d": {
                        "token": f"QQBot {token}",
                        "intents": self.settings.intents,
                        "shard": [0, 1],
                        "properties": {"$os": "linux", "$browser": "qq-push-bot", "$device": "qq-push-bot"},
                    },
                }))
                logger.info("已发送 Identify (intents={})", self.settings.intents)

            heartbeat_task = asyncio.create_task(self._heartbeat_loop(ws, heartbeat))
            try:
                async for raw in ws:
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        logger.warning("收到无法解析的网关消息: {}", raw[:200])
                        continue
                    await self._on_payload(payload)

                    op = payload.get("op")
                    if op == 7:
                        logger.info("收到 Reconnect，准备重连")
                        break
                    if op == 9:
                        logger.warning("Invalid Session，将重新 Identify")
                        self._session_id = None
                        self._last_seq = None
                        break
            finally:
                heartbeat_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await heartbeat_task

    async def _heartbeat_loop(self, ws: Any, interval_ms: int) -> None:
        interval = max(interval_ms, 1000) / 1000.0
        try:
            while True:
                await asyncio.sleep(interval)
                await ws.send(json.dumps({"op": 1, "d": self._last_seq}))
                logger.debug("发送心跳 seq={}", self._last_seq)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001
            logger.warning("心跳发送失败: {}", e)

    async def _on_payload(self, payload: dict[str, Any]) -> None:
        op = payload.get("op")
        if op != 0:
            return

        if payload.get("s") is not None:
            self._last_seq = payload["s"]

        t = payload.get("t")
        d = payload.get("d") or {}

        if t == "READY":
            self._session_id = (d.get("session_id") or None)
            user = d.get("user") or {}
            logger.info("READY: bot={} session={}", user.get("username"), self._session_id)
        elif t == "RESUMED":
            logger.info("RESUMED")
        elif t in ("C2C_MESSAGE_CREATE", "GROUP_AT_MESSAGE_CREATE"):
            asyncio.create_task(self._handle_message(t, d))

    async def _handle_message(self, t: str, d: dict[str, Any]) -> None:
        try:
            if t == "C2C_MESSAGE_CREATE":
                user_openid = str((d.get("author") or {}).get("user_openid") or "")
                content = (d.get("content") or "").strip().lower()
                if user_openid and content in ("openid", "/openid"):
                    await self.qq.send_message(False, user_openid, {
                        "msg_type": 0,
                        "content": f"你的 OpenID：{user_openid}",
                        "msg_id": d.get("id") or "",
                        "msg_seq": 1,
                    })
                    logger.info("已回复 C2C OpenID 查询: {}", user_openid)
            elif t == "GROUP_AT_MESSAGE_CREATE":
                group_openid = str(d.get("group_openid") or "")
                content = (d.get("content") or "").strip()
                if group_openid and "openid" in content.lower():
                    await self.qq.send_message(True, group_openid, {
                        "msg_type": 0,
                        "content": f"本群 OpenID：{group_openid}",
                        "msg_id": d.get("id") or "",
                        "msg_seq": 1,
                    })
                    logger.info("已回复群 OpenID 查询: {}", group_openid)
        except Exception as e:  # noqa: BLE001 - 事件处理失败不能拖垮网关
            logger.error("处理事件 {} 失败: {}", t, e)
