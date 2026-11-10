"""QQ 开放平台 OpenAPI 客户端：token、发消息、富媒体上传。"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import time
from typing import Any

import httpx
from loguru import logger

from .config import Settings

# 直传（file_data base64）的大小上限
DIRECT_UPLOAD_LIMIT = 5 * 1024 * 1024
# md5_10m：文件前 10002432 字节（约 9.54MB）的 MD5
MD5_10M_BYTES = 10_002_432


class QQAPIError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None, code: int | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.code = code


class QQClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._http = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))
        self._token: str | None = None
        self._token_expires_at = 0.0
        self._token_lock = asyncio.Lock()

    async def aclose(self) -> None:
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Access Token
    # ------------------------------------------------------------------

    async def access_token(self) -> str:
        now = time.time()
        if self._token and now < self._token_expires_at - 60:
            return self._token

        async with self._token_lock:
            now = time.time()
            if self._token and now < self._token_expires_at - 60:
                return self._token

            resp = await self._http.post(
                f"{self.settings.api_base}/app/getAppAccessToken",
                json={"appId": self.settings.app_id, "clientSecret": self.settings.app_secret},
                headers={"Content-Type": "application/json", "Accept": "application/json"},
            )
            try:
                data = resp.json()
            except Exception:
                data = {}

            # 该接口失败时 HTTP 仍可能为 200，必须看 body 里的 code/access_token
            if resp.status_code != 200 or not data.get("access_token"):
                code = data.get("code") if isinstance(data, dict) else None
                message = data.get("message") if isinstance(data, dict) else resp.text[:200]
                raise QQAPIError(
                    f"获取 access_token 失败: code={code} message={message}",
                    status_code=resp.status_code,
                    code=code,
                )

            self._token = data["access_token"]
            self._token_expires_at = now + int(data.get("expires_in", 7200))
            logger.info("QQ access_token 已刷新，有效期 {}s", data.get("expires_in", 7200))
            return self._token

    # ------------------------------------------------------------------
    # 通用请求
    # ------------------------------------------------------------------

    async def _request(self, method: str, path: str, *, json: dict[str, Any] | None = None,
                       timeout: float = 30.0) -> dict[str, Any]:
        token = await self.access_token()
        headers = {
            "Authorization": f"QQBot {token}",
            "Accept": "application/json",
            "User-Agent": "qq-push-bot/0.1.0",
        }
        if json is not None:
            headers["Content-Type"] = "application/json"

        resp = await self._http.request(
            method, f"{self.settings.api_base}{path}", json=json, headers=headers, timeout=timeout
        )
        try:
            data = resp.json()
        except Exception:
            data = {}

        code = data.get("code") if isinstance(data, dict) else None
        if resp.status_code >= 400 or (code not in (None, 0)):
            message = data.get("message") if isinstance(data, dict) else resp.text[:200]
            raise QQAPIError(
                f"QQ 接口错误 {method} {path}: code={code} message={message}",
                status_code=resp.status_code,
                code=code,
            )
        return data if isinstance(data, dict) else {}

    # ------------------------------------------------------------------
    # 消息
    # ------------------------------------------------------------------

    async def send_message(self, group: bool, openid: str, body: dict[str, Any]) -> dict[str, Any]:
        base = f"/v2/groups/{openid}" if group else f"/v2/users/{openid}"
        return await self._request("POST", f"{base}/messages", json=body)

    # ------------------------------------------------------------------
    # 富媒体上传
    # ------------------------------------------------------------------

    async def upload_media(self, group: bool, openid: str, file_type: int,
                           file_name: str, data: bytes) -> str:
        """上传媒体，返回 file_info（用于 msg_type=7 的 media 字段）。"""
        base = f"/v2/groups/{openid}" if group else f"/v2/users/{openid}"

        if len(data) <= DIRECT_UPLOAD_LIMIT:
            body = {
                "file_type": file_type,
                "file_name": file_name or "file",
                "file_data": base64.b64encode(data).decode("ascii"),
                "srv_send_msg": False,
            }
            resp = await self._request("POST", f"{base}/files", json=body, timeout=60.0)
        else:
            resp = await self._chunked_upload(base, file_type, file_name, data)

        file_info = resp.get("file_info") or ""
        if not file_info:
            raise QQAPIError(f"上传成功但未返回 file_info: {resp}")
        return file_info

    async def _chunked_upload(self, base: str, file_type: int, file_name: str, data: bytes) -> dict[str, Any]:
        md5_full = hashlib.md5(data).hexdigest()
        sha1_full = hashlib.sha1(data).hexdigest()
        md5_10m = hashlib.md5(data[:MD5_10M_BYTES]).hexdigest()

        prep = await self._request("POST", f"{base}/upload_prepare", json={
            "file_type": file_type,
            "file_name": file_name or "file",
            "file_size": len(data),
            "md5": md5_full,
            "sha1": sha1_full,
            "md5_10m": md5_10m,
        }, timeout=60.0)

        upload_id = prep.get("upload_id")
        block_size = int(prep.get("block_size") or 5 * 1024 * 1024)
        parts = prep.get("parts") or []
        if not upload_id or not parts:
            raise QQAPIError(f"upload_prepare 响应缺少 upload_id/parts: {prep}")

        offset = 0
        for i, part in enumerate(parts, start=1):
            index = int(part.get("index", i))
            url = part.get("presigned_url")
            size = int(part.get("block_size") or block_size)
            if not url:
                raise QQAPIError(f"upload_prepare 分片 {index} 缺少 presigned_url")
            chunk = data[offset:offset + size]
            offset += size
            if not chunk:
                break

            put_resp = await self._http.put(url, content=chunk, timeout=120.0)
            if put_resp.status_code >= 400:
                raise QQAPIError(
                    f"分片 PUT 失败 index={index}: HTTP {put_resp.status_code} {put_resp.text[:200]}"
                )

            chunk_md5 = hashlib.md5(chunk).hexdigest()
            finish_body = {
                "upload_id": upload_id,
                "part_index": index,
                "block_size": len(chunk),
                "md5": chunk_md5,
            }
            for attempt in range(5):
                try:
                    await self._request("POST", f"{base}/upload_part_finish", json=finish_body, timeout=60.0)
                    break
                except QQAPIError as e:
                    # 40093001 为可重试错误
                    if e.code == 40093001 and attempt < 4:
                        await asyncio.sleep(1.0 * (2 ** attempt))
                        continue
                    raise

        return await self._request("POST", f"{base}/files", json={"upload_id": upload_id}, timeout=120.0)

    async def get_gateway_url(self) -> str:
        data = await self._request("GET", "/gateway")
        url = data.get("url") or ""
        if not url:
            raise QQAPIError(f"网关响应缺少 url: {data}")
        return url
