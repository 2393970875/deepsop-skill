---
name: deepsop-socialhub
description: DeepSOP SocialHub 社交平台运营技能。用户输入自然语言社媒/达人/Instagram 搜索指令，AI 自动分析关键词和结果数量，调用 DeepSOP 平台接口搜索 Apify Store 中可用的 Actor / Scraper / 数据采集工具并返回结果。触发场景：用户说「搜Instagram」「搜索Instagram」「找Instagram达人」「找IG达人」「IG搜索」「搜IG用户」「搜达人数据」「找达人数据」「Instagram达人数据」「社媒达人搜索」「帮我搜索某某关键词的达人数据多少多少」「找某地区/行业 Instagram 达人」「SocialHub」「Apify Instagram scraper」「Instagram数据采集工具」等与社媒达人或社媒数据采集工具搜索相关的指令。当前新版本流程不直连 Instagram，不要求 APIFY_TOKEN，也不直接调用 Apify SDK/Actor；只通过 DeepSOP 后端代理接口 `/ai/apify/store?search={keyword}&limit={limit}&offset={offset}&responseFormat=agent` 搜索工具/Actor。在 OPClaw 项目中运行时直接读取项目设置里的 DEEPSOP_API_KEY；非 OPClaw 运行时，引导用户授权后把 DEEPSOP_API_KEY 配置为共享环境变量或 ~/.openclaw/.env，让其他 DeepSOP 技能也能复用。⚠️ 调用本 SKILL 前必须先完整阅读 SKILL.md。执行搜索 **必须**走 scripts/search_instagram.py，脚本内部负责读取共享 DEEPSOP_API_KEY、拼接固定 responseFormat=agent、UTF-8 安全请求并保存原始结果；**禁止**直接写 curl 命令绕过脚本，禁止要求用户配置 APIFY_TOKEN，禁止把 Apify Store 工具结果伪造成 Instagram 达人账号明细。脚本退出码 0 才算成功；非 0 必须把错误信息原样反馈给用户后修正重试。
---

# DeepSOP SocialHub

## 功能简介

DeepSOP SocialHub 是基于 DeepSOP 平台的社交平台运营与数据采集工具搜索助手，能够：

- **理解自然语言指令**：直接描述需求，如「帮我搜索深圳潮牌主理人达人数据 30 个」。
- **智能改写搜索词**：把达人、IG、KOL、行业、地区等意图改写成适合 Apify Store 的查询词。
- **搜索采集工具**：通过 DeepSOP 后端代理查询 Apify Store 中的 Actor / Scraper / 数据采集工具。
- **结构化展示结果**：返回名称、作者、计费信息、简介等适合 agent 阅读的摘要。
- **保存原始响应**：保存 `apify_store_output.json`，便于后续筛选、调试或继续翻页。

当前新版本仅提供 **DeepSOP Apify Store 搜索** 能力：使用 `scripts/search_instagram.py` 通过 DeepSOP 后端代理查询 Apify Store，帮助找到 Instagram / 社媒数据采集相关的 Apify Actor、Scraper 或工具。脚本会把用户关键词、分页参数和固定 `responseFormat=agent` 拼到 `/ai/apify/store` 查询接口，并在请求头里传 `X-Api-Key: <DEEPSOP_API_KEY>`。

> 注意：旧版文档里的“直接搜索 Instagram 用户/达人并返回粉丝数、简介、认证状态、帖子数”等能力，当前版本暂未开放。遇到这类请求时，本技能仍应被触发，但应按新流程搜索相关 Apify Store 工具，不要伪造达人账号数据。

---

## 前置条件：DEEPSOP_API_KEY

本技能需要 **API Key 授权**才能调用 DeepSOP 接口。

- OPClaw 项目运行时直接读取项目设置里的 `DEEPSOP_API_KEY`。
- 非 OPClaw 运行时，引导用户授权后把 `DEEPSOP_API_KEY` 配置为共享环境变量或 `~/.openclaw/.env`，让其他 DeepSOP 技能也能复用。
- API Key 通常以 `sk-` 开头。

共享配置示例：

```text
DEEPSOP_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxx
```

> 所有 API 请求头需携带：`x-api-key: $DEEPSOP_API_KEY`
> API Base URL：`https://ai.deepsop.com/prod-api/`

---

## 触发场景

用户出现以下意图时使用本技能：

- 搜 Instagram / IG 用户、达人、网红、KOL、KOC、创作者、博主、品牌账号、竞品账号。
- 搜某个地区、行业、标签或关键词相关的“达人数据”，例如“帮我搜索深圳潮牌主理人达人数据 30 个”。
- 查找 Instagram 数据采集、Instagram Search Scraper、Instagram Profile Scraper、社媒爬虫、Apify Actor / Scraper。
- 用户直接提到 SocialHub、社媒达人搜索、搜 IG、找达人、Instagram 达人数据。
- 用户问“有没有能采集 Instagram 达人的工具/Actor/Scraper”。

## 当前能力

- 按关键词搜索 Apify Store 中的 Actor / Scraper / 数据采集工具。
- 支持 Instagram、Facebook、TikTok、LinkedIn、网页抓取等社媒或通用采集工具关键词。
- 返回名称、作者、计费信息、简介等结构化摘要。
- 保存接口原始 JSON，便于后续筛选、调试或继续翻页。

## 暂未实现

以下能力不要在当前版本中承诺或执行：

- 直接搜索 Instagram 达人账号并返回粉丝数、关注数、帖子数、认证状态、简介等账号明细。
- Instagram 帖子发布和管理。
- Facebook 帖子发布和管理。
- 评论管理、私信处理、粉丝列表/关注列表采集。
- 直接使用 `APIFY_TOKEN`、Apify SDK、Apify Actor 或 Instagram 登录态。

## 必须遵守

- OPClaw 项目运行时使用项目设置里的 `DEEPSOP_API_KEY`。
- 非 OPClaw 运行时，让用户授权后设置共享 `DEEPSOP_API_KEY`，优先使用环境变量，也可写入 `~/.openclaw/.env`。
- 不读取、不要求、不保存 `APIFY_TOKEN`。
- 不直接调用 Apify SDK、Apify Actor 或 Apify Console Token。
- 查询接口固定使用 `GET https://ai.deepsop.com/prod-api/ai/apify/store`。
- 查询参数必须包含 `search`、`limit`、`offset`、`responseFormat=agent`。
- 用户没有给分页时，默认 `limit=10`、`offset=0`。
- `search` 必须来自用户意图或明确的关键词改写；不要空关键词查询。
- 接口失败时反馈实际状态码或接口 `msg`，不要伪造结果。

## DEEPSOP_API_KEY 获取逻辑

脚本按其他 DeepSOP 技能的共享 Key 逻辑读取：

1. 先读取当前进程环境变量 `DEEPSOP_API_KEY`。
2. 再读取当前工作目录 `.env`。
3. 再读取技能目录 `skills/deepsop-socialhub/.env`。
4. 最后读取用户共享配置 `~/.openclaw/.env`。

未检测到 Key 时，提示用户先登录 OPClaw 并在项目设置里配置 `DEEPSOP_API_KEY`；如果不是在 OPClaw 中运行，请引导用户授权后手动配置共享 Key：

```powershell
[System.Environment]::SetEnvironmentVariable('DEEPSOP_API_KEY', 'sk-your_api_key_here', 'User')
```

或写入共享配置：

```text
DEEPSOP_API_KEY=sk-your_api_key_here
```

## 快速命令

```bash
# 默认分页：limit=10，offset=0
python scripts/search_instagram.py "instagram scraper"

# 指定分页
python scripts/search_instagram.py "instagram profile scraper" 10 0
python scripts/search_instagram.py "instagram influencer scraper" 10 10
python scripts/search_instagram.py "web scraper" 10 0
```

## 自然语言到查询词

按新版本流程把用户请求改写成 Apify Store 查询词：

| 用户说法 | 推荐查询词 |
| --- | --- |
| 帮我搜索深圳潮牌主理人达人数据 30 个 | `instagram influencer scraper`，可补充 `instagram search scraper` |
| 找 100 个洛杉矶健身博主 | `instagram profile scraper` 或 `instagram user scraper` |
| 搜 IG 用户 | `instagram search scraper` |
| 找 Instagram 数据采集工具 | `instagram scraper` |
| 找网页抓取相关的 Apify 工具 | `web scraper` |

如果用户指定“多少个”，优先把数量映射为 `limit`，但受接口分页和 Apify Store 返回能力影响；需要更多结果时使用 `offset` 翻页。

## API 端点

> 🔒 **路径强约束：** 本技能唯一允许调用的业务接口是下方 Apify Store 搜索接口。不得把 `prod-api` 改成其他前缀，不得改写 path，不得漏传 `responseFormat=agent`，不得自行编造其他 Instagram / Apify 接口。

**GET** `/ai/apify/store?search={keyword}&limit={limit}&offset={offset}&responseFormat=agent`

完整示例：

```bash
curl -X GET "https://ai.deepsop.com/prod-api/ai/apify/store?search=instagram%20scraper&limit=10&offset=0&responseFormat=agent" \
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
| `search` | 是 | 无 | 查询关键词，例如 `instagram scraper`、`instagram profile scraper`、`web scraper` |
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

- `关键词`：必填，Apify Store 查询关键词。支持中英文和空格，例如 `"instagram scraper"`。
- `limit`：选填，默认 `10`。用户说“搜索 N 个”时可先传 `N`，若结果不足则说明接口实际返回数量。
- `offset`：选填，默认 `0`。用户说“下一页/继续看”时按上次 `limit` 增加偏移量。

输出：

- 控制台打印简表：名称、作者、计费信息、简介。
- 保存 `apify_store_output.json`：接口原始 JSON 响应，便于后续筛选和调试。

## 使用示例

用户说：帮我搜索深圳潮牌主理人达人数据 30 个。

执行：

```bash
python scripts/search_instagram.py "instagram influencer scraper" 30 0
```

回复时说明：当前版本搜索的是可用于 Instagram 达人/账号采集的 Apify Store 工具，不是直接返回 30 个达人账号。

用户说：找 100 个洛杉矶的健身博主。

执行：

```bash
python scripts/search_instagram.py "instagram profile scraper" 50 0
python scripts/search_instagram.py "instagram search scraper" 50 50
```

用户说：找 Instagram 数据采集相关工具。

执行：

```bash
python scripts/search_instagram.py "instagram scraper" 10 0
```

用户说：再看下一页。

执行：

```bash
python scripts/search_instagram.py "instagram scraper" 10 10
```

## 返回处理

- 如果接口返回标准 DeepSOP 包装结构，优先读取 `data.rows`、`data.list`、`data.items`、`data.records` 或 `data` 数组。
- 如果接口直接返回数组，则直接作为结果列表。
- 如果没有可识别列表，保留原始 JSON 到 `apify_store_output.json`，并说明未识别到列表结构。
- 展示结果时优先使用 `name/title/actorId/id`、`username/userName/authorUsername/ownerUsername`、`pricing/pricingModel/pricePerUnitUsd`、`description/shortDescription/summary` 等字段。
- 如果用户要的是“达人账号数据”，必须明确当前结果是工具/Actor 候选；不要把工具结果包装成达人账号列表。

## 错误处理

- `DEEPSOP_API_KEY` 未设置：提示用户在 OPClaw 项目设置中配置；非 OPClaw 运行时配置共享环境变量或 `~/.openclaw/.env`。
  - OPClaw 项目运行时检查项目设置里的 `DEEPSOP_API_KEY`
  - 非 OPClaw 运行时，引导用户授权后配置共享环境变量或 `~/.openclaw/.env`
  - 配置 `DEEPSOP_API_KEY` 后再重试。
- `401`：提示 API Key 无效或过期。
- `429`：提示请求过于频繁，稍后重试。
- `4xx/5xx`：返回接口状态码和错误信息，停止本次查询。

## 参考文件

- `scripts/search_instagram.py`：可执行脚本和本地结果格式化逻辑。
