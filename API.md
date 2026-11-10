# qq-push-bot API 文档

基于 FastAPI 的 QQ 私聊 / 群聊消息推送服务。调用方通过 HTTP 接口把消息推送到指定的 QQ 用户（私聊）或 QQ 群（群聊）。

## 1. 基础信息

| 项目 | 说明 |
| --- | --- |
| 默认地址 | ` ` |
| 协议 | HTTP / HTTPS |
| 交互式文档 | `/docs`（Swagger UI） |
| 健康检查 | `GET /health` |

### 内容类型

| 接口类型 | Content-Type |
| --- | --- |
| JSON 接口 | `application/json` |
| multipart 接口 | `multipart/form-data` |

## 2. 鉴权

配置文件中 `auth.tokens` 非空时，所有接口都必须鉴权。支持配置多个 token（任一匹配即通过），兼容旧的单个 `auth.token`。传入方式（任选其一）：

| 方式 | 位置 | 示例 |
| --- | --- | --- |
| Header | `Authorization` | `Authorization: Bearer <token>` |
| Header | `X-Token` | `X-Token: <token>` |
| 请求体 | `token` 字段 | JSON 接口在 body 里，multipart 接口在表单里 |

> 优先级：请求体 `token` > `Authorization: Bearer` > `X-Token`。
> `auth.tokens` 为空（且无 `auth.token`）时跳过鉴权（仅建议调试用，生产务必设置）。

## 3. 公共参数

所有接口通用：

| 参数 | 类型 | 必填 | 默认 | 说明 |
| --- | --- | --- | --- | --- |
| `openid` | string | 是 | - | 接收者：用户 openid（私聊）或群 openid（群聊） |
| `touid` | string | 否 | - | `openid` 的别名，二选一即可（同时传时以 `openid` 为准） |
| `group` | boolean | 否 | `false` | `false`=私聊，`true`=群聊 |
| `token` | string | 否 | - | 调用鉴权 token，见上节 |

### 名字映射（names）

`config.toml` 里可配置 `[names]` 表：

```toml
[names]
shingyu = "0000xxxxxxx"
```

当 `openid` / `touid` 传入的值命中表里的名字时，服务端自动替换为对应 ID。例：`"openid": "shingyu"` 实际发给 `0000xxxxxxx`。

### 图片链接映射（picurls）

`config.toml` 里可配置 `[picurls]` 表，用于 `/sendimagecard` 的 `pic_url`：

```toml
[picurls]
gmail = "https://img.shingyu.cn/gmail-square-pad.webp"
```

当 `pic_url` 传入的值命中表里的名字时，自动替换为对应链接。例：`"pic_url": "gmail"` 实际使用上面配置的 URL。

## 4. 通用返回格式

### 成功

```json
{
  "ok": true,
  "group": false,
  "openid": "0000xxxxxxx",
  "msg_id": "ROBOT1.0_xxxxxxxx...",
  "timestamp": "2026-07-21T10:30:00+08:00"
}
```

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `ok` | boolean | 固定 `true` |
| `group` | boolean | 实际发送目标：`false` 私聊 / `true` 群聊 |
| `openid` | string | 解析后的实际接收者 ID（名字映射已替换） |
| `msg_id` | string | QQ 返回的消息 ID |
| `timestamp` | string | QQ 返回的发送时间 |

### 失败

HTTP 状态码非 2xx，响应体为：

```json
{ "detail": "错误描述" }
```

常见本地错误码见第 9 节。

---

## 5. 文本消息 `POST /sendmessage`

发送纯文本消息（QQ `msg_type=0`）。

### 请求体（JSON）

```json
{
  "token": "可选，鉴权token",
  "content": "发送的文本内容",
  "group": false,
  "openid": "接收者用户ID/群聊ID"
}
```

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `content` | string | 是 | 文本内容，不能为空 |
| `openid` | string | 是 | 接收者，可用 `touid` 别名 |
| `group` | boolean | 否 | 默认 `false`（私聊） |
| `token` | string | 否 | 鉴权 token |

### 示例

```bash
curl -X POST http://127.0.0.1:8000/sendmessage \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{"content":"你好，世界","group":false,"openid":"shingyu"}'
```

---

## 6. Markdown 消息 `POST /sendmarkdown`

发送 Markdown 消息（QQ `msg_type=2`）。

### 请求体（JSON）

```json
{
  "token": "可选",
  "content": "发送的md内容",
  "group": false,
  "openid": "接收者ID"
}
```

### 示例

```bash
curl -X POST http://127.0.0.1:8000/sendmarkdown \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{"content":"# 今日推荐\n\n**精选文章**\n> 知识就是力量","group":true,"openid":"<群openid>"}'
```

---

## 7. 图片 `POST /sendimage`

上传并发送图片（QQ `msg_type=7`）。

### 请求（multipart/form-data）

| 字段 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `file` | file | 是 | 图片文件 |
| `openid` | string | 是 | 接收者，可用 `touid` |
| `group` | string | 否 | `true` / `false`，默认 `false` |
| `token` | string | 否 | 鉴权 token |

### 示例

```bash
curl -X POST http://127.0.0.1:8000/sendimage \
  -H 'Authorization: Bearer <token>' \
  -F 'file=@./cat.png' \
  -F 'group=false' \
  -F 'openid=shingyu'
```

---

## 8. 语音 `POST /sendvoice`

上传并发送语音（QQ `msg_type=7`）。

### 请求（multipart/form-data）

字段同 `/sendimage`，`file` 为语音文件。

### 示例

```bash
curl -X POST http://127.0.0.1:8000/sendvoice \
  -H 'Authorization: Bearer <token>' \
  -F 'file=@./voice.silk' \
  -F 'group=true' \
  -F 'openid=<群openid>'
```

---

## 9. 文件 `POST /sendfile`

上传并发送文件（QQ `msg_type=7`）。

### 请求（multipart/form-data）

字段同 `/sendimage`，`file` 为任意文件。

### 示例

```bash
curl -X POST http://127.0.0.1:8000/sendfile \
  -H 'Authorization: Bearer <token>' \
  -F 'file=@./report.pdf' \
  -F 'group=false' \
  -F 'openid=shingyu'
```

---

## 10. 图文卡片 `POST /sendimagecard`

发送图文卡片（QQ `msg_type=8`，`card.type=tuwen`）。

### 请求体（JSON）

```json
{
  "token": "可选",
  "content": {
    "title": "标题",
    "description": "描述",
    "url": "https://example.com",
    "pic_url": "https://example.com/pic.png"
  },
  "group": false,
  "openid": "接收者ID"
}
```

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `content.title` | string | 是 | 标题，1-50 字符 |
| `content.description` | string | 否 | 描述，1-200 字符 |
| `content.url` | string | 是 | 点击跳转链接，**必须 https**，≤1024 字符 |
| `content.pic_url` | string | 是 | 封面图链接，**必须 https**，≤1024 字符；也可传 `[picurls]` 里的名字，自动替换为对应链接 |

### 示例

```bash
curl -X POST http://127.0.0.1:8000/sendimagecard \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{
    "content": {
      "title": "今日天气预报",
      "description": "深圳 多云转晴 24°C~32°C",
      "url": "https://example.com/weather",
      "pic_url": "https://example.com/weather.png"
    },
    "group": false,
    "openid": "shingyu"
  }'
```

---

## 11. 卡片（兼容接口）`POST /sendcard`

兼容接口：以 Markdown（`msg_type=2`）发送标题与描述；`url` 不再拼文字超链接，而是以 **keyboard 跳转按钮**（`action.type=0`）呈现。

### 请求体（JSON）

```json
{
  "token": "可选",
  "title": "标题",
  "description": "描述",
  "url": "可选",
  "btntxt": "按钮文字，默认：详情",
  "group": false,
  "openid": "接收者ID"
}
```

| 参数 | 类型 | 必填 | 说明 |
| --- | --- | --- | --- |
| `title` | string | 是 | 标题 |
| `description` | string | 否 | 描述 |
| `url` | string | 否 | 跳转链接，提供后生成 keyboard 跳转按钮（http/https 或小程序 scheme） |
| `btntxt` | string | 否 | 按钮显示文字，默认 `详情` |

### 示例

```bash
curl -X POST http://127.0.0.1:8000/sendcard \
  -H 'Authorization: Bearer <token>' \
  -H 'Content-Type: application/json' \
  -d '{"title":"系统通知","description":"服务已重启","url":"https://example.com","btntxt":"查看","group":false,"openid":"shingyu"}'
```

---

## 12. 查询 openid

拿到目标 openid 后即可用接口推送；也可把它写进 `config.toml` 的 `[names]`。

给机器人发消息即可查询（`openid` 与 `/openid` 效果相同）：

| 场景 | 操作 | 机器人回复 |
| --- | --- | --- |
| 私聊 | 给机器人发 `openid` 或 `/openid` | `你的 OpenID：xxx` |
| 群聊 | `@机器人 openid` 或 `@机器人 /openid` | `本群 OpenID：xxx` |

---

## 13. 热重载配置 `POST /reload`

修改 `config.toml` 后无需重启服务。

鉴权：header（`Authorization: Bearer` / `X-Token`）或 query `?token=`。

```bash
curl -X POST 'http://127.0.0.1:8000/reload?token=<token>'
```

响应示例：

```json
{
  "ok": true,
  "auth_enabled": true,
  "names_count": 2,
  "api_base": "https://api.bot.qq.com",
  "intents": 33554432
}
```

生效范围：`app_id/app_secret`、`auth.tokens`、`[names]` / `[picurls]`、日志级别/文件、网关重试间隔、`api_base/intents`（网关下次重连生效）。`server.host` / `server.port` 需重启进程才生效。

## 14. 错误码

### 本地错误

| HTTP 状态码 | 说明 |
| --- | --- |
| `400` | 参数错误（缺 `openid`、`content` 为空、url 非 https 等） |
| `401` | token 校验失败 |
| `404` | 接口路径不存在 |
| `502` | QQ 平台调用失败（`detail` 中带 QQ 错误码与信息） |
| `500` | 服务内部错误 |

### QQ 常见错误（出现在 `502` 的 `detail` 中）

| QQ 错误码 | 说明 |
| --- | --- |
| `100007` | AppID 无效 |
| `100016` | AppID 或 AppSecret 不正确 |
| `40034100` | 主动消息超频控，稍后重试 |
| `40054004` | 无好友关系，需用户先添加机器人为好友 |
| `40054010` | 群聊不允许发送 URL |
| `40054002` | 机器人被禁言 |
| `40054003` | 机器人不是群成员 |
| `850019` | 上传文件格式不支持 |
| `850031` | 上传文件超过大小限制 |

---

## 15. 富媒体格式与限制

| 类型 | file_type | 格式 | 软限制 | 硬限制 |
| --- | --- | --- | --- | --- |
| 图片 | 1 | png / jpg（文档另列 gif / webp / bmp） | 20 MB | 200 MB |
| 视频 | 2 | mp4 | 30 MB | 200 MB |
| 语音 | 3 | silk / mp3 / wav / ogg | 20 MB | 200 MB |
| 文件 | 4 | 任意 | 200 MB | 200 MB |

- 超过软限制会降级为文件类型上传，超过硬限制报错。
- 本地文件 ≤ 5MB 走直传，> 5MB 自动分片上传，无需调用方处理。
- 私聊与群聊的上传通道相互独立，服务端已自动按 `group` 选择。

## 16. 频控提示

| 场景 | 限制 |
| --- | --- |
| 主动私聊（未认证 Bot） | 5 qps 且 30 qpm |
| 主动群聊（未认证 Bot） | 30 qpm |
| 单个好友 / 单个群 | 20 qpm，每天最多收 1000 条 |
