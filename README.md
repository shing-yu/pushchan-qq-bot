# PushChan QQ

接收本地 API 请求，并推送消息到 QQ **私聊 / 群聊** 的机器人服务。

- 框架：FastAPI + websockets（QQ 官方 WebSocket 网关收事件）
- 管理：uv
- 配置：TOML（`config.toml`）
- 日志：loguru

## 目录结构

```
pushchan/
├── app/
│   ├── main.py        # FastAPI 路由（7 个推送接口）
│   ├── qq_client.py   # QQ OpenAPI 客户端（token / 发消息 / 富媒体上传）
│   ├── gateway.py     # WebSocket 网关（收事件 + 回复 openid）
│   ├── auth.py        # 本地接口 token 鉴权
│   ├── config.py      # TOML 配置加载
│   └── schemas.py     # JSON 请求体模型
├── config.toml        # 实际配置（勿提交）
├── config.example.toml
└── pyproject.toml
```

## 快速开始

1. 安装依赖

```bash
uv sync
```

2. 填写配置：复制 `config.example.toml` 为 `config.toml`，填入 QQ 开放平台的 `app_id` / `app_secret`，并设置本地接口鉴权 `token`：

```toml
[qq]
app_id = "你的 AppID"
app_secret = "你的 AppSecret"

[auth]
tokens = ["token1", "token2"]   # 支持多个，任一匹配即通过
# token = "兼容旧配置的单个 token"

[names]
# name -> openid 映射
# shingyu = "0000xxxxxxx"

[picurls]
# name -> 图片链接映射（/sendimagecard 的 pic_url 可用）
# gmail = "https://img.shingyu.cn/gmail-square-pad.webp"
```

3. 启动

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000
```

交互式文档：http://127.0.0.1:8000/docs

## 热重载配置

修改 `config.toml` 后无需重启：

```bash
curl -X POST 'http://127.0.0.1:8000/reload?token=<token>'
# 或
curl -X POST http://127.0.0.1:8000/reload -H 'Authorization: Bearer <token>'
```

生效范围：QQ 票据、`auth.tokens`、`[names]` / `[picurls]` 映射、日志级别/文件、网关重试间隔、`api_base`/`intents`（网关下次重连生效）。`server.host` / `server.port` 需重启进程才生效。

## 鉴权方式

所有接口都要求 `token` 校验（`auth.tokens` 非空时，支持多个，任一匹配即通过）：

- Header：`Authorization: Bearer <token>`，也支持 `X-Token: <token>`
- JSON 接口同时支持请求体里的 `token` 字段；multipart 接口在表单里传 `token`
- 配置里 `auth.tokens` 为空（且无 `auth.token`）时跳过鉴权（不安全，生产务必设置）

## 接口一览

| 接口 | 类型 | 说明 |
| --- | --- | --- |
| `POST /sendmessage` | JSON | 纯文本（msg_type=0） |
| `POST /sendmarkdown` | JSON | Markdown（msg_type=2） |
| `POST /sendimage` | multipart | 图片（msg_type=7） |
| `POST /sendvoice` | multipart | 语音（msg_type=7） |
| `POST /sendfile` | multipart | 文件（msg_type=7） |
| `POST /sendimagecard` | JSON | 图文卡片（msg_type=8, tuwen） |
| `POST /sendcard` | JSON | 兼容接口：Markdown 标题+描述，链接用 keyboard 跳转按钮 |
| `POST /reload` | query/header | 热重载 config.toml |

公共字段：

- `openid`：接收者（用户 openid 或群 openid），所有接口均可用 `touid` 作为别名
- `group`：`true` 发群聊，`false`（默认）发私聊
- 若 `openid`/`touid` 的值命中 `config.toml` 的 `[names]` 里的 name，会自动替换为对应 ID
- 图文卡片 `pic_url` 可传 `[picurls]` 里的名字，自动替换为对应链接

### JSON 接口示例

```bash
# 文本
curl -X POST http://127.0.0.1:8000/sendmessage \
  -H 'Authorization: Bearer <token>' -H 'Content-Type: application/json' \
  -d '{"content":"你好","group":false,"openid":"shingyu"}'

# Markdown
curl -X POST http://127.0.0.1:8000/sendmarkdown \
  -H 'Authorization: Bearer <token>' -H 'Content-Type: application/json' \
  -d '{"content":"# 标题\n\n正文","group":true,"openid":"<群 openid>"}'

# 图文卡片
curl -X POST http://127.0.0.1:8000/sendimagecard \
  -H 'Authorization: Bearer <token>' -H 'Content-Type: application/json' \
  -d '{
    "content": {
      "title": "今日预报",
      "description": "多云转晴",
      "url": "https://example.com",
      "pic_url": "https://example.com/a.png"
    },
    "group": false,
    "openid": "shingyu"
  }'

# 兼容卡片（Markdown 标题+描述，链接为 keyboard 跳转按钮）
curl -X POST http://127.0.0.1:8000/sendcard \
  -H 'Authorization: Bearer <token>' -H 'Content-Type: application/json' \
  -d '{"title":"标题","description":"描述","url":"https://example.com","btntxt":"详情","group":false,"openid":"shingyu"}'
```

### multipart 接口示例

```bash
# 图片
curl -X POST http://127.0.0.1:8000/sendimage \
  -H 'Authorization: Bearer <token>' \
  -F 'file=@./cat.png' -F 'group=false' -F 'openid=shingyu'

# 语音
curl -X POST http://127.0.0.1:8000/sendvoice \
  -H 'Authorization: Bearer <token>' \
  -F 'file=@./voice.silk' -F 'group=true' -F 'openid=<群 openid>'

# 文件
curl -X POST http://127.0.0.1:8000/sendfile \
  -H 'Authorization: Bearer <token>' \
  -F 'file=@./report.pdf' -F 'group=false' -F 'openid=shingyu'
```

## 查询 openid

给机器人发消息即可拿到目标 openid（`openid` 与 `/openid` 效果相同）：

- **私聊**：给机器人发 `openid` 或 `/openid`，机器人回复 `你的 OpenID：xxx`
- **群聊**：`@机器人 openid` 或 `@机器人 /openid`，机器人回复 `本群 OpenID：xxx`

拿到 openid 后建议写进 `config.toml` 的 `[names]`，之后接口传 name 即可。

## 富媒体说明

- 上传接口：私聊 `/v2/users/{openid}/files`，群聊 `/v2/groups/{group_openid}/files`（两者不互通）
- 本地文件 ≤ 5MB 走直传（内部 base64），> 5MB 自动走分片上传
- 图片支持 png/jpg（文档另列 gif/webp/bmp）；语音支持 silk/mp3/wav/ogg；文件任意格式
- 返回的 `file_info` 有 `ttl` 有效期，本项目每次发送前都会重新上传，无需自行维护

## 常见问题

- `401 invalid token`：请求的 token 与 `config.toml` 的 `auth.tokens`（或 `auth.token`）不一致
- `502 获取 access_token 失败 ... appid invalid`：QQ AppID / AppSecret 配置有误
- 主动消息有频控（未认证 Bot 私聊 30/qpm、群聊 30/qpm），超频会收到 `40034100`
- 主动私聊需先与机器人建立好友关系，否则报 `40054004`
