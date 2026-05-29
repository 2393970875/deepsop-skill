---
name: deepsop-instagramflow
description: Instagram 达人搜索与数据采集 skill。基于 Apify API 搜索 Instagram 用户/达人，返回粉丝数、简介、认证状态、帖子数、类别等详细信息。当用户需要搜索 Instagram 达人或采集 Instagram 用户数据时使用。触发词：搜Instagram、找达人、instagram达人、IG达人、IG搜索、搜IG用户。
---

# Instagram 达人搜索 Skill

本 skill 通过 **Apify Instagram Search Scraper** 在云端搜索 Instagram 用户，无需登录也不需要任何浏览器。

## 前置条件

⚠️ **必须：配置环境变量 `APIFY_TOKEN`**

使用 `gateway config.patch` 或 config 文件设置：

```yaml
env:
  APIFY_TOKEN: "apify_api_你的Token"
```

Token 从 https://console.apify.com/settings/integrations 获取。
已有免费额度可用，不需付费即可开始使用。

## 脚本

### `scripts/search_instagram.py` — 主搜索脚本

搜索 Instagram 用户/达人，返回结构化数据。

**用法：**

```bash
python scripts/search_instagram.py <关键词> [结果数量]
```

参数：
- `关键词`（必填）— 搜索关键词。支持中英文，如 "fashion influencer"、"上海 美妆"
- `结果数量`（选填，默认 20）— 最多返回多少个结果

**输出：**
- 控制台打印表格（用户名、粉丝数、帖子数、认证状态、名称、类别、简介）
- 保存 `apify_output.json`（结构化 JSON）
- 保存 `apify_output_raw.json`（原始数据，调试用）

**费用：**
- $2.30/1,000条结果（按实际返回的结果数量计费）
- 一次搜索 20 条大约 $0.046

**返回数据字段：**

| 字段 | 说明 |
|------|------|
| username | `@用户名` |
| name | 显示名称 |
| followers | 粉丝数 |
| following | 关注数 |
| posts | 帖子数 |
| verified | 是否认证 ✅ |
| business | 是否企业账号 🏢 |
| private | 是否私密账号 |
| category | 商业类别（如 "Digital creator"、"Clothing (Brand)"） |
| bio | 个人简介 |
| external_url | 主页链接的外链 |
| profile_url | `https://instagram.com/用户名` |
| profile_pic | 头像 URL |
| related_profiles | 相关推荐账号 |

## 使用示例

**用户说**：帮我搜一下深圳的潮牌主理人

→ 执行：
```bash
python scripts/search_instagram.py "深圳潮牌" 30
```

**用户说**：找 100 个洛杉矶的健身博主

→ 执行：
```bash
python scripts/search_instagram.py "fitness coach Los Angeles" 30
# 换关键词再搜两轮扩大覆盖
python scripts/search_instagram.py "personal trainer LA" 20
python scripts/search_instagram.py "gym influencer California" 20
```

**用户说**：看看这个达人的详细信息

→ 如果搜索结果不够详细，可以针对具体用户名调用 Apify Instagram Profile Scraper：
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

- **搜索结果数量有限**：当前 scraper 基于 Facebook Ads 自动补全接口，每个关键词通常返回 7~15 条结果
- **扩大覆盖方法**：使用多个类似关键词分别搜索去重，可以用多轮搜索扩大达人库
- **不会消耗你的 Instagram 账号**：全部在 Apify 云端完成，无封号风险
- **无法搜索粉丝列表/关注列表**：如需要深度数据（某达人的粉丝列表），需使用 `apify/instagram-profile-scraper` 配合 Instagram 账号 cookies

## 补充：Instagram 内容发布

此 skill 专注于**搜索和数据采集**。

如果你需要**发布内容**（发帖、发 Reels、管理评论），请参考 ClawHub 上的 `@clawbus/instagram-publish` skill，它支持：
- 发布图片/Reels/轮播帖子
- 私信收发
- 发布状态查询

安装命令：
```bash
npx clawhub install clawbus-instagram-publish
```
