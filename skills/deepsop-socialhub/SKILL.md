---
name: deepsop-socialhub
description: Deepsop SocialHub 社交平台运营 skill。当前仅支持 Instagram 达人搜索与数据采集：基于 Apify API 搜索 Instagram 用户/达人，返回粉丝数、简介、认证状态、帖子数、类别等信息。后续会加入 Instagram 帖子发布和管理、Facebook 帖子发布和管理。触发词：搜Instagram、找达人、instagram达人、IG达人、IG搜索、搜IG用户、社媒达人搜索、SocialHub。
---

# Deepsop SocialHub

Deepsop SocialHub 用于社交平台账号、内容和达人相关工作流。

当前版本只提供 **Instagram 达人搜索与数据采集** 能力：通过 **Apify Instagram Search Scraper** 在云端搜索 Instagram 用户，无需登录，也不需要浏览器。

## 当前能力

- Instagram 用户/达人搜索
- Instagram 账号基础数据采集
- 输出粉丝数、关注数、帖子数、简介、认证状态、企业账号状态、类别、头像、主页链接等结构化信息

## 后续规划

以下能力暂未在当前版本中实现，后续会逐步加入：

- Instagram 帖子发布和管理
- Facebook 帖子发布和管理

在这些能力上线前，请不要把本 skill 用于 Instagram/Facebook 内容发布、帖子管理、评论管理或私信处理。

## 前置条件

必须配置环境变量 `APIFY_TOKEN`。

使用 `gateway config.patch` 或 config 文件设置：

```yaml
env:
  APIFY_TOKEN: "apify_api_你的Token"
```

Token 从 https://console.apify.com/settings/integrations 获取。
已有免费额度可用，不需付费即可开始使用。

## 脚本

### `scripts/search_instagram.py` - Instagram 搜索脚本

搜索 Instagram 用户/达人，返回结构化数据。

**用法：**

```bash
python scripts/search_instagram.py <关键词> [结果数量]
```

参数：
- `关键词`（必填）：搜索关键词。支持中英文，如 "fashion influencer"、"上海 美妆"
- `结果数量`（选填，默认 20）：最多返回多少个结果

**输出：**
- 控制台打印表格：用户名、粉丝数、帖子数、认证状态、名称、类别、简介
- 保存 `apify_output.json`：结构化 JSON
- 保存 `apify_output_raw.json`：原始数据，调试用

**费用：**
- $2.30/1,000 条结果，按实际返回的结果数量计费
- 一次搜索 20 条大约 $0.046

**返回数据字段：**

| 字段 | 说明 |
|------|------|
| username | `@用户名` |
| name | 显示名称 |
| followers | 粉丝数 |
| following | 关注数 |
| posts | 帖子数 |
| verified | 是否认证 |
| business | 是否企业账号 |
| private | 是否私密账号 |
| category | 商业类别，如 "Digital creator"、"Clothing (Brand)" |
| bio | 个人简介 |
| external_url | 主页链接的外链 |
| profile_url | `https://instagram.com/用户名` |
| profile_pic | 头像 URL |
| related_profiles | 相关推荐账号 |

## 使用示例

**用户说**：帮我搜一下深圳的潮牌主理人

执行：

```bash
python scripts/search_instagram.py "深圳潮牌" 30
```

**用户说**：找 100 个洛杉矶的健身博主

执行：

```bash
python scripts/search_instagram.py "fitness coach Los Angeles" 30
# 换关键词再搜两轮扩大覆盖
python scripts/search_instagram.py "personal trainer LA" 20
python scripts/search_instagram.py "gym influencer California" 20
```

**用户说**：看看这个达人的详细信息

如果搜索结果不够详细，可以针对具体用户名调用 Apify Instagram Profile Scraper：

```python
# 在代码中组合使用两个 actor
client.actor("apify/instagram-profile-scraper").call(run_input={"usernames": ["目标用户名"]})
```

## 数据格式说明

搜索结果以 JSON 数组形式输出到 `apify_output.json`，每个条目包含：

```json
{
  "no": 1,
  "username": "@username",
  "name": "显示名",
  "followers": 50000,
  "following": 1200,
  "posts": 350,
  "verified": true,
  "business": false,
  "private": false,
  "category": "Digital creator",
  "bio": "简介文本...",
  "external_url": "",
  "profile_pic": "https://...",
  "profile_url": "https://instagram.com/username"
}
```

## 限制说明

- **搜索结果数量有限**：当前 scraper 基于 Facebook Ads 自动补全接口，每个关键词通常返回 7-15 条结果
- **扩大覆盖方法**：使用多个类似关键词分别搜索并去重，可以用多轮搜索扩大达人库
- **不会消耗你的 Instagram 账号**：全部在 Apify 云端完成，无封号风险
- **无法搜索粉丝列表/关注列表**：如需要深度数据，例如某达人的粉丝列表，需使用 `apify/instagram-profile-scraper` 配合 Instagram 账号 cookies
