---
name: deepsop-social-comment-reply
description: 用于用户明确要求在抖音或腾讯视频号按关键词寻找热门作品、读取评论、生成评论回复草稿，或在人工确认后提交评论回复时。
version: 0.3.0
author: OPClaw Team
metadata:
  openclaw:
    emoji: "\U0001F4AC"
---

# 社媒热门作品评论回复

本技能用于抖音、腾讯视频号的评论互动辅助：按关键词寻找相关作品，读取可见评论上下文，生成自然回复草稿，并在用户确认后提交。不要把普通平台研究、热点分析、社媒文案创作、视频发布/上传任务交给此技能；发布/上传应使用对应发布技能。

## 功能概览

| 功能 | 契约动作 | 说明 |
| --- | --- | --- |
| 环境检查 | `check-session` | 检查登录态、浏览器可用性和风控提示 |
| 目标搜索 | `search-targets` | 按关键词筛选作品和可见评论上下文 |
| 回复起草 | `draft-replies` | 生成绑定上下文的评论回复草稿 |
| 确认提交 | `confirm-submit` | 仅在用户确认后输入或发送评论 |
| 结果记录 | `execution-log` | 记录尝试目标、草稿、发送结果和跳过原因 |

## 默认模式

| 模式 | 是否输入评论框 | 是否点击发送 | 使用条件 |
| --- | --- | --- | --- |
| `draft-only` | 否 | 否 | 默认模式，只输出候选目标和回复草稿 |
| `confirm-send` | 是 | 用户最终确认后才发送 | 用户明确要求可以确认后提交 |
| `manual-review-batch` | 可选 | 每条都需确认 | 多目标任务，但仍逐条人工审核 |

不要执行无确认的 `auto-send`。如果用户要求全自动批量评论，先说明本技能不支持无人值守刷评，只能按安全规则执行草稿或确认发送流程。

## 默认工作流

1. **先确认运行前提**：见 `references/runtime-requirements.md`。
2. **再确认评论契约**：见 `references/comment-contract.md`。
3. 根据用户输入确定平台、关键词、语气、数量和执行模式。
4. 执行 `search-targets`，只选择与关键词强相关、评论上下文清晰的目标。
5. 执行 `draft-replies`，每个目标生成一条具体、自然、不重复的回复。
6. **如需浏览器提交**：走 CDP（Chrome DevTools Protocol），不要用 DOM click。具体实现见 `references/douyin-cdp-guide.md`。
7. 默认停在 `draft-only`；只有用户确认目标和最终文案后，才进入 `confirm-submit`。
8. 遇到登录、验证码、实名验证、风控提示或评论入口不稳定，立即停止并说明原因。
9. 结束时输出 `execution-log` 摘要。

## 必要输入

只在当前任务缺少必要信息时追问：

- 平台：抖音、腾讯视频号，或两者都做。
- 关键词或赛道，例如 AI Agent、企业 AI、自动化、创作者工具。
- 回复目标和语气，例如专业、自然、创始人口吻、轻推广、中立互动。
- 数量限制；未提供时最多处理 3 个作品，每个作品最多 1 条回复。
- 执行模式：默认 `draft-only`，或用户确认后使用 `confirm-send`。

## 执行前必做检查

- 把用户已登录的浏览器会话视为敏感状态，不询问密码、验证码、Cookie 或会话信息。
- 检查页面是否已登录；未登录时让用户自行登录，不代填账号密码。
- 如果出现验证码、短信验证、实名验证、异常登录、账号风险或平台风控提示，停止执行。
- 执行前阅读 `references/safety-rules.md`，确认不会生成重复、刷屏、误导、骚扰、政治、医疗、金融、冒充真人或垃圾营销内容。

## 平台流程

### 抖音

#### 1. 搜索作品

抖音 PC 版搜索页面（`https://www.douyin.com/search/<关键词>?type=general`）使用 React 虚拟列表渲染搜索结果：

- 作品卡片 class 为 `.search-result-card`，虚拟列表容器 id 为 `waterFallScrollContainer`
- 卡片在视口外时会被 React 销毁，必须先滚动到目标位置
- 点击卡片不会直接跳转，而是打开一个 modal overlay，URL 变为 `...?modal_id=<视频ID>`
- 从 URL 提取 `modal_id` 后，使用 `Page.navigate` 导航到 `https://www.douyin.com/video/<modal_id>`

**搜索作品最佳实践**：

1. 打开搜索 URL 后，等待 3 秒让页面加载
2. 使用 `window.scrollBy(0, 1000)` 循环滚动 5-8 次，每次等待 1-1.5 秒
3. 用 `document.body.innerText` 提取完整搜索结果文本
4. 从文本中解析出作品标题、作者、点赞数
5. 选择 3 个与关键词最相关、互动量最高的未回复作品

#### 2. 导航到视频详情页

由于抖音搜索使用 modal overlay 而非 a 标签导航，需要通过以下方式跳转：

1. 在搜索结果页，用 CDP `Input.dispatchMouseEvent` 点击目标卡片
2. 从 `window.location.href` 提取 `modal_id` 参数
3. 使用 `Page.navigate` 导航到 `https://www.douyin.com/video/<modal_id>`
4. 等待 3-4 秒让视频详情页加载

**注意事项**：
- 虚拟列表在快速滚动时卡片可能不在 DOM 中，需通过 `waterFallScrollContainer.scrollTop` 精确定位
- 点击前先 `scrollIntoView({behavior:'instant', block:'center'})`
- 同时使用 CDP mouse event + JS `.click()` 提高命中率

#### 3. 读取评论区

在视频详情页加载完成后：

1. 评论容器 class 为 `.yP5MkONE.llbV_Rqp.VaW6TeYk`
2. 设置 `scrollTop = 0` 回到顶部，再 `scrollTop = scrollHeight` 到底部加载评论
3. 从容器 `textContent` 中提取评论行（过滤长度 > 5 的行）
4. 同时从 `document.title` 提取视频标题，从 `document.body.textContent` 提取互动数据

#### 4. 发送评论（CDP 方式）

抖音 PC 版评论区使用 Draft.js 编辑器 + React。**不要尝试 DOM click 发送按钮**，评论区没有传统发送按钮。正确方式：

**步骤一：激活编辑器并填入文字**

```javascript
// 滚动评论区到底部
var c = document.querySelector('.yP5MkONE.llbV_Rqp.VaW6TeYk');
if(c) c.scrollTop = c.scrollHeight;
// 点击评论输入占位符
var p = document.querySelector('._x9Gwl7G');
if(p) { p.scrollIntoView({behavior:'instant',block:'center'}); p.click(); }
// 聚焦编辑器
var e = document.querySelector('.public-DraftEditor-content');
if(e) { e.focus(); e.click(); }
```

使用 CDP `Input.dispatchKeyEvent` (Ctrl+A) + `Input.insertText` 填入文字。

**步骤二：通过 React Fiber 更新 editorState 并提交**

```
走 React Fiber 树：
- Level 3 组件：有 editorState + onChange（Draft.js 编辑器）
- Level 6 组件：有 handlePublishClick（评论包装组件）

操作：
1. 从 Level 3 获取 editorState 和 onChange
2. 用 ContentState.createFromText() 创建新内容
3. 用 EditorState.push() 生成新 state
4. 调用 onChange(newState) 更新 React 状态
5. 等待 400ms 后调用 Level 6 的 handlePublishClick()
```

**完整 CDP 提交代码示例**参见 `references/douyin-cdp-guide.md`。

**已验证**：该方式在 2026-07-09 和 2026-07-13 的两轮执行中，6/6 条评论全部成功发送。

#### 5. 结果验证

发送完成后：
- 评论编辑器中的文字可能仍存在（Draft.js 行为），这不代表失败
- 检查是否有 toast 提示（class 含 `toast` 或 `Toast`）
- 手动刷新页面检查评论数是否增加
- 或在抖音 App 中查看「我 → 消息 → 互动消息」确认

### 腾讯视频号

1. 使用当前 OPClaw 环境可用的浏览器或桌面自动化路径。
2. 进入用户可访问的视频号入口，并确认账号已经登录。
3. 按用户给定关键词或赛道搜索、浏览作品。
4. 沿用抖音筛选规则：内容相关、评论上下文真实、不是重复营销泛滥的评论区。
5. 回复前读取可见作品信息和评论上下文。
6. 先生成草稿，去重，再请求确认。
7. 如果当前入口无法稳定暴露评论区或评论输入框，停止并说明限制。

## 回复质量规则

- 每条回复都要绑定可见信息：标题、视频主题、文案、标签或具体评论。
- 像真实从业者交流，不像广告投放。
- 优先给具体观察、小建议、自然提问或轻量共鸣。
- 如果提到 OPClaw 或 AI 自动化，只在上下文相关时轻描淡写地提，不强推。
- 不要跨目标复用同一句话；每条回复都要变换表达。

## 输出格式

提交任何评论前，先展示：

- 平台和作品 URL/标题。
- 选中的评论或上下文。
- 回复草稿。
- 为什么该目标与用户任务相关。
- 当前模式：`draft-only`、`confirm-send` 或 `manual-review-batch`。
- 是否需要用户确认发送。

执行结束后，总结：

- 尝试过的目标。
- 生成的回复草稿。
- 已发送的回复，如果有。
- 跳过的目标和原因。

## 参考文档

- 运行前提：`references/runtime-requirements.md`
- 评论契约：`references/comment-contract.md`
- 安全规则：`references/safety-rules.md`
- 抖音 CDP 技术指南：`references/douyin-cdp-guide.md`
- 浏览器脚本：`scripts/comment_reply.py`
