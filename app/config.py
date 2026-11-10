"""配置加载：从 config.toml 读取（标准库 tomllib）。"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.toml"


@dataclass
class Settings:
    app_id: str = ""
    app_secret: str = ""
    api_base: str = "https://api.bot.qq.com"
    intents: int = 1 << 25  # GROUP_AND_C2C_EVENT
    host: str = "0.0.0.0"
    port: int = 8000
    auth_tokens: set[str] = field(default_factory=set)
    names: dict[str, str] = field(default_factory=dict)
    picurls: dict[str, str] = field(default_factory=dict)
    log_level: str = "INFO"
    log_file: str = "logs/bot.log"
    gateway_retry_seconds: int = 5
    config_path: Path = field(default=DEFAULT_CONFIG_PATH, repr=False, compare=False)

    @classmethod
    def load(cls, path: Path | str = DEFAULT_CONFIG_PATH) -> "Settings":
        p = Path(path)
        data: dict[str, Any] = {}
        if p.exists():
            with p.open("rb") as f:
                data = tomllib.load(f)

        qq = data.get("qq", {}) or {}
        server = data.get("server", {}) or {}
        auth = data.get("auth", {}) or {}
        auth_tokens: set[str] = set()
        if isinstance(auth.get("tokens"), list):
            for t in auth["tokens"]:
                t = str(t).strip()
                if t:
                    auth_tokens.add(t)
        legacy_token = str(auth.get("token", "") or "").strip()
        if legacy_token:
            auth_tokens.add(legacy_token)
        gateway = data.get("gateway", {}) or {}
        logging_ = data.get("logging", {}) or {}
        names = data.get("names", {}) or {}
        picurls = data.get("picurls", {}) or {}

        return cls(
            app_id=str(qq.get("app_id", "") or "").strip(),
            app_secret=str(qq.get("app_secret", "") or "").strip(),
            api_base=str(qq.get("api_base", "https://api.bot.qq.com")).rstrip("/"),
            intents=int(qq.get("intents", 1 << 25)),
            host=str(server.get("host", "0.0.0.0")),
            port=int(server.get("port", 8000)),
            auth_tokens=auth_tokens,
            names={str(k): str(v).strip() for k, v in names.items()},
            picurls={str(k): str(v).strip() for k, v in picurls.items()},
            log_level=str(logging_.get("level", "INFO")),
            log_file=str(logging_.get("file", "logs/bot.log")),
            gateway_retry_seconds=int(gateway.get("retry_seconds", 5)),
            config_path=p,
        )

    def reload(self) -> "Settings":
        """重新读取 config.toml，并原地更新当前实例（保持对象引用不变）。"""
        fresh = Settings.load(self.config_path)
        for key in (
            "app_id", "app_secret", "api_base", "intents",
            "host", "port", "auth_tokens", "names", "picurls",
            "log_level", "log_file", "gateway_retry_seconds",
        ):
            setattr(self, key, getattr(fresh, key))
        return self

    @property
    def auth_enabled(self) -> bool:
        return bool(self.auth_tokens)

    def resolve_target(self, value: str) -> str:
        """把 openid/touid 的原始值解析为实际 ID（支持配置的 name 映射）。"""
        raw = value.strip()
        if raw in self.names:
            return self.names[raw]
        return raw

    def resolve_picurl(self, value: str) -> str:
        """把 pic_url 的原始值解析为实际链接（支持配置的 [picurls] 映射）。"""
        raw = value.strip()
        if raw in self.picurls:
            return self.picurls[raw]
        return raw


settings = Settings.load()
