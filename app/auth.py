"""本地推送接口的 token 鉴权：优先 header，其次请求体。"""
from __future__ import annotations

import hmac

from fastapi import HTTPException, Request

from .config import Settings, settings


def verify_token(request: Request, body_token: str | None = None, conf: Settings | None = None) -> None:
    """校验调用方 token。

    支持：
    - Header：``Authorization: Bearer <token>`` 或 ``X-Token: <token>``
    - 请求体/表单字段：``token``（JSON 接口在 body 中，multipart 接口在表单中）

    配置文件里 auth.tokens 为空时跳过校验；支持配置多个 token。
    """
    conf = conf or settings
    if not conf.auth_enabled:
        return

    provided = (body_token or "").strip()
    if not provided:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            provided = auth[7:].strip()
    if not provided:
        provided = request.headers.get("X-Token", "").strip()

    for expected in conf.auth_tokens:
        if hmac.compare_digest(provided, expected):
            return

    raise HTTPException(status_code=401, detail="invalid token")
