"""本地推送接口的请求体模型（JSON 接口使用）。"""
from __future__ import annotations

from pydantic import BaseModel, field_validator


class SendMessageIn(BaseModel):
    token: str | None = None
    content: str
    group: bool = False
    openid: str | None = None
    touid: str | None = None


class SendMarkdownIn(BaseModel):
    token: str | None = None
    content: str
    group: bool = False
    openid: str | None = None
    touid: str | None = None


class ImageCardContent(BaseModel):
    title: str
    description: str = ""
    url: str
    pic_url: str

    @field_validator("url")
    @classmethod
    def _url_must_be_https(cls, v: str) -> str:
        if not v.strip().startswith("https://"):
            raise ValueError("url 必须是 https 链接")
        return v.strip()

    @field_validator("pic_url")
    @classmethod
    def _pic_url_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("pic_url 不能为空")
        return v.strip()


class SendImageCardIn(BaseModel):
    token: str | None = None
    content: ImageCardContent
    group: bool = False
    openid: str | None = None
    touid: str | None = None


class SendCardIn(BaseModel):
    token: str | None = None
    title: str
    description: str = ""
    url: str | None = None
    btntxt: str = "详情"
    group: bool = False
    openid: str | None = None
    touid: str | None = None
