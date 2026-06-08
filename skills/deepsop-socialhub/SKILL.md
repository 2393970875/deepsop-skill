---
name: deepsop-socialhub
description: |
  DeepSOP SocialHub 社交平台运营技能。当前提供 Apify Store 搜索能力，用于按关键词查询可用的 Apify Actor / Scraper，并返回适合 agent 阅读的结果。调用 DeepSOP 后端接口 `/ai/apify/store?search={keyword}&limit={limit}&offset={offset}&responseFormat=agent`，必须携带共享 `DEEPSOP_API_KEY` 作为 `X-Api-Key` 请求头。

  在 OPClaw 项目中运行时直接读取项目设置里的 DEEPSOP_API_KEY；非 OPClaw 运行时，引导用户授权后把 DEEPSOP_API_KEY 配置为共享环境变量或 ~/.openclaw/.env，让其他 DeepSOP 技能也能复用。不要要求用户配置 APIFY_TOKEN，也不要直接调用 Apify SDK 或 Apify Actor。
---

# DeepSOP SocialHub

使用 `scripts/search_instagram.py` 通过 DeepSOP 后端代理查询 Apify Store。脚本会把用户关键词、分页参数和固定 `responseFormat=agent` 拼到 `/ai/apify/store` 查询接口，并在请求头里传 `X-Api-Key: <DEEPSOP_API_KEY>`。

## 必须遵守

- OPClaw 项目运行时使用项目设置里的 `DEEPSOP_API_KEY`；非 OPClaw 运行时，让用户授权后设置共享 `DEEPSOP_API_KEY`。
- 不读取、不要求、不保存 `APIFY_TOKEN`。
- 不直接调用 Apify SDK、Apify Actor 或 Apify Console Token。
- 查询接口固定使用 `GET https://ai.deepsop.com/prod-api/ai/apify/store`。
- 查询参数必须包含 `search`、`limit`、`offset`、`responseFormat=agent`。
- 用户没有给分页时，默认 `limit=10`、`offset=0`。
- `search` 必须来自用户意图或明确的关键词改写；不要空关键词查询。
- 接口失败时反馈实际状态码或接口 `msg`，不要伪造结果。

## 快速命令

```bash
# 默认分页：limit=10，offset=0
python scripts/search_instagram.py "web scraper"

# 指定分页
python scripts/search_instagram.py "instagram scraper" 10 0
python scripts/search_instagram.py "linkedin scraper" 10 10
```

## API 端点

**GET** `/ai/apify/store?search={keyword}&limit={limit}&offset={offset}&responseFormat=agent`

完整示例：

```bash
curl -X GET "https://ai.deepsop.com/prod-api/ai/apify/store?search=web%20scraper&limit=10&offset=0&responseFormat=agent" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: <api_key>"
```

请求头：

```text
Content-Type: application/json
X-Api-Key: <api_key>
```

查询参数：

| 参数 | 必填 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `search` | 是 | 无 | 查询关键词，例如 `web scraper`、`instagram scraper` |
| `limit` | 否 | `10` | 本页最多返回条数 |
| `offset` | 否 | `0` | 分页偏移量 |
| `responseFormat` | 是 | `agent` | 固定传 `agent`，让后端返回适合 agent 阅读的结果 |

## 脚本

### `scripts/search_instagram.py`

脚本名称保留以兼容旧入口；当前语义是查询 DeepSOP Apify Store，不再直连 Instagram 或 Apify。

用法：

```bash
python scripts/search_instagram.py <关键词> [limit] [offset]
```

参数：

- `关键词`：必填，Apify Store 查询关键词。支持中英文和空格，例如 `"web scraper"`。
- `limit`：选填，默认 `10`。
- `offset`：选填，默认 `0`。

输出：

- 控制台打印简表：名称、作者、计费信息、简介。
- 保存 `apify_store_output.json`：接口原始 JSON 响应，便于后续筛选和调试。

## 使用示例

用户说：帮我找网页抓取相关的 Apify 工具。

执行：

```bash
python scripts/search_instagram.py "web scraper" 10 0
```

用户说：再看下一页。

执行：

```bash
python scripts/search_instagram.py "web scraper" 10 10
```

用户说：找 Instagram 数据采集相关工具。

执行：

```bash
python scripts/search_instagram.py "instagram scraper" 10 0
```

## 返回处理

- 如果接口返回标准 DeepSOP 包装结构，优先读取 `data.rows`、`data.list`、`data.items`、`data.records` 或 `data` 数组。
- 如果接口直接返回数组，则直接作为结果列表。
- 如果没有可识别列表，保留原始 JSON 到 `apify_store_output.json`，并说明未识别到列表结构。
- 展示结果时优先使用 `name/title/actorId/id`、`username/userName/authorUsername/ownerUsername`、`pricing/pricingModel/pricePerUnitUsd`、`description/shortDescription/summary` 等字段。

## 错误处理

- `DEEPSOP_API_KEY` 未设置：提示用户在 OPClaw 项目设置中配置；非 OPClaw 运行时配置共享环境变量或 `~/.openclaw/.env`。
- `401`：提示 API Key 无效或过期。
- `429`：提示请求过于频繁，稍后重试。
- `4xx/5xx`：返回接口状态码和错误信息，停止本次查询。

## 参考文件

- `scripts/search_instagram.py`：可执行脚本和本地结果格式化逻辑。
