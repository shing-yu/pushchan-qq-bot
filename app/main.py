"""FastAPI 入口：接收本地推送请求，转发到 QQ 私聊/群聊。"""
from __future__ import annotations

import asyncio
import contextlib
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from loguru import logger

from .auth import verify_token
from .config import settings
from .gateway import GatewayClient
from .qq_client import QQAPIError, QQClient
from .schemas import SendCardIn, SendImageCardIn, SendMarkdownIn, SendMessageIn


def configure_logging() -> None:
    logger.remove()
    logger.add(sys.stderr, level=settings.log_level, colorize=True)
    log_file = Path(settings.log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)
    logger.add(str(log_file), level=settings.log_level, rotation="10 MB",
               retention=7, encoding="utf-8", enqueue=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    logger.info("qq-push-bot 启动中 ...")
    if not settings.auth_enabled:
        logger.warning("auth.tokens 未配置：本地接口鉴权已关闭，请勿在生产环境这样使用！")
    if not settings.app_id or not settings.app_secret:
        logger.warning("QQ app_id / app_secret 未配置：发消息与网关将无法正常工作")

    qq = QQClient(settings)
    app.state.qq = qq
    gateway = GatewayClient(settings, qq)
    gateway_task = asyncio.create_task(gateway.run())
    app.state.gateway_task = gateway_task

    try:
        yield
    finally:
        gateway.request_stop()
        gateway_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await gateway_task
        await qq.aclose()
        logger.info("qq-push-bot 已关闭")


app = FastAPI(title="QQ Push Bot", version="0.1.0", lifespan=lifespan)


# ----------------------------------------------------------------------
# 辅助函数
# ----------------------------------------------------------------------

def _resolve(openid: str | None, touid: str | None) -> str:
    raw = (openid or touid or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="缺少 openid（可用 touid 作为别名）")
    return settings.resolve_target(raw)


def _ok(result: dict, *, group: bool, openid: str) -> dict:
    return {
        "ok": True,
        "group": group,
        "openid": openid,
        "msg_id": result.get("id"),
        "timestamp": result.get("timestamp"),
    }


def _guard_qq_error(exc: Exception) -> HTTPException:
    if isinstance(exc, QQAPIError):
        return HTTPException(status_code=502, detail=str(exc))
    logger.exception("未预期异常")
    return HTTPException(status_code=500, detail="internal error")


# ----------------------------------------------------------------------
# 基础
# ----------------------------------------------------------------------

@app.get("/health")
async def health() -> dict:
    return {"ok": True}


@app.get("/")
async def root() -> dict:
    return {"service": "qq-push-bot", "docs": "/docs"}


@app.post("/reload")
async def reload_config(request: Request, token: str | None = None):
    """热重载 config.toml（token 通过 header 或 ?token= 传入）。"""
    verify_token(request, token)
    try:
        settings.reload()
    except Exception as e:  # noqa: BLE001
        logger.exception("重载配置失败")
        raise HTTPException(status_code=500, detail=f"重载配置失败: {e}")
    configure_logging()
    logger.info("配置已重载: auth_enabled={}, names={}", settings.auth_enabled, len(settings.names))
    return {
        "ok": True,
        "auth_enabled": settings.auth_enabled,
        "names_count": len(settings.names),
        "api_base": settings.api_base,
        "intents": settings.intents,
    }


# ----------------------------------------------------------------------
# 文本 / Markdown / 卡片
# ----------------------------------------------------------------------

@app.post("/sendmessage")
async def send_message(req: SendMessageIn, request: Request):
    verify_token(request, req.token)
    target = _resolve(req.openid, req.touid)
    content = req.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="content 不能为空")

    try:
        result = await request.app.state.qq.send_message(req.group, target, {"msg_type": 0, "content": content})
    except Exception as e:  # noqa: BLE001
        raise _guard_qq_error(e)
    return _ok(result, group=req.group, openid=target)


@app.post("/sendmarkdown")
async def send_markdown(req: SendMarkdownIn, request: Request):
    verify_token(request, req.token)
    target = _resolve(req.openid, req.touid)
    if not req.content.strip():
        raise HTTPException(status_code=400, detail="content 不能为空")

    try:
        result = await request.app.state.qq.send_message(
            req.group, target, {"msg_type": 2, "markdown": {"content": req.content}}
        )
    except Exception as e:  # noqa: BLE001
        raise _guard_qq_error(e)
    return _ok(result, group=req.group, openid=target)


@app.post("/sendimagecard")
async def send_image_card(req: SendImageCardIn, request: Request):
    verify_token(request, req.token)
    target = _resolve(req.openid, req.touid)
    c = req.content
    pic_url = settings.resolve_picurl(c.pic_url)
    if not pic_url.startswith("https://"):
        raise HTTPException(status_code=400, detail="pic_url 必须是 https 链接")
    try:
        result = await request.app.state.qq.send_message(req.group, target, {
            "msg_type": 8,
            "card": {
                "type": "tuwen",
                "content": {
                    "title": c.title,
                    "description": c.description,
                    "url": c.url,
                    "pic_url": pic_url,
                },
            },
        })
    except Exception as e:  # noqa: BLE001
        raise _guard_qq_error(e)
    return _ok(result, group=req.group, openid=target)


@app.post("/sendcard")
async def send_card(req: SendCardIn, request: Request):
    verify_token(request, req.token)
    target = _resolve(req.openid, req.touid)
    title = req.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="title 不能为空")

    # 标题 + 描述；链接用 keyboard 按钮呈现（不再拼文字超链接）
    lines = [f"### {title}"]
    if req.description.strip():
        lines.append(req.description)
    md = "\n".join(lines)

    body: dict = {"msg_type": 2, "markdown": {"content": md}}
    if req.url:
        label = (req.btntxt or "详情").strip()
        body["keyboard"] = {
            "content": {
                "rows": [
                    {
                        "buttons": [
                            {
                                "id": "btn_link",
                                "render_data": {
                                    "label": label,
                                    "visited_label": label,
                                    "style": 1,
                                },
                                "action": {
                                    "type": 0,  # 跳转按钮：http 或 小程序 scheme
                                    "permission": {"type": 2},
                                    "data": req.url,
                                    "unsupport_tips": "当前版本不支持跳转",
                                },
                            }
                        ]
                    }
                ]
            }
        }

    try:
        result = await request.app.state.qq.send_message(req.group, target, body)
    except Exception as e:  # noqa: BLE001
        raise _guard_qq_error(e)
    return _ok(result, group=req.group, openid=target)


# ----------------------------------------------------------------------
# 富媒体（multipart 上传）
# ----------------------------------------------------------------------

async def _send_media(request: Request, file: UploadFile, group: bool,
                      openid: str, file_type: int) -> dict:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="上传文件为空")
    try:
        qq: QQClient = request.app.state.qq
        file_info = await qq.upload_media(group, openid, file_type, file.filename or "file", data)
        result = await qq.send_message(group, openid, {"msg_type": 7, "media": {"file_info": file_info}})
    except Exception as e:  # noqa: BLE001
        raise _guard_qq_error(e)
    return _ok(result, group=group, openid=openid)


@app.post("/sendimage")
async def send_image(
    request: Request,
    file: UploadFile = File(...),
    token: str | None = Form(None),
    group: bool = Form(False),
    openid: str | None = Form(None),
    touid: str | None = Form(None),
):
    verify_token(request, token)
    target = _resolve(openid, touid)
    return await _send_media(request, file, group, target, file_type=1)


@app.post("/sendvoice")
async def send_voice(
    request: Request,
    file: UploadFile = File(...),
    token: str | None = Form(None),
    group: bool = Form(False),
    openid: str | None = Form(None),
    touid: str | None = Form(None),
):
    verify_token(request, token)
    target = _resolve(openid, touid)
    return await _send_media(request, file, group, target, file_type=3)


@app.post("/sendfile")
async def send_file(
    request: Request,
    file: UploadFile = File(...),
    token: str | None = Form(None),
    group: bool = Form(False),
    openid: str | None = Form(None),
    touid: str | None = Form(None),
):
    verify_token(request, token)
    target = _resolve(openid, touid)
    return await _send_media(request, file, group, target, file_type=4)
