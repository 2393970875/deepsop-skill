# 评论执行契约

本契约定义 `deepsop-social-comment-reply` 的动作、输入输出和结果记录。浏览器执行层由 `scripts/comment_reply.py` 提供，脚本应保持本文件字段兼容。

## 输入参数

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `platform` | 是 | `douyin`、`wechat-channels` 或 `both` |
| `keyword` | 是 | 搜索关键词或赛道 |
| `tone` | 否 | 回复语气；默认自然、专业、轻互动 |
| `mode` | 否 | `draft-only`、`confirm-send`、`manual-review-batch`；默认 `draft-only` |
| `maxTargets` | 否 | 最大作品数；默认 3 |
| `maxRepliesPerTarget` | 否 | 每个作品最大回复数；默认 1 |
| `brandMention` | 否 | 是否允许轻量提及 OPClaw 或品牌；默认仅上下文相关时允许 |

## search-targets

目标：按关键词找到可评论的作品和评论上下文。

输出字段：

```json
{
  "platform": "douyin",
  "keyword": "AI Agent",
  "targets": [
    {
      "targetId": "local-1",
      "url": "https://www.douyin.com/...",
      "title": "作品标题",
      "visibleText": "可见文案或标签",
      "selectedComment": "选中的可见评论",
      "reason": "与任务相关的原因",
      "status": "candidate"
    }
  ]
}
```

筛选规则：

- 作品标题、标签、可见文案或评论内容必须与关键词相关。
- 跳过评论区已经被重复营销淹没的目标。
- 跳过无法读取评论上下文的目标。
- 不从隐藏评论或不可见页面状态中猜测信息。

## draft-replies

目标：为每个候选目标生成一条可审核的回复草稿。

输出字段：

```json
{
  "targetId": "local-1",
  "replyDraft": "这个角度很实用，尤其是把流程先拆清楚再自动化，落地会稳很多。",
  "qualityChecks": {
    "contextBound": true,
    "notDuplicate": true,
    "notSpam": true,
    "needsUserConfirmation": true
  }
}
```

草稿必须：

- 绑定作品标题、可见文案、标签或具体评论。
- 短句优先，避免广告腔。
- 不跨目标复用同一句话。
- 不承诺效果，不冒充真实用户经历。

## confirm-submit

目标：在用户明确确认后输入或发送评论。

进入条件：

1. 已展示平台、作品 URL/标题、选中评论、回复草稿和相关原因。
2. 用户确认目标和最终回复文本。
3. 模式为 `confirm-send` 或 `manual-review-batch`。
4. 当前页面未出现登录、验证或风控提示。

提交规则：

- 默认只把草稿展示给用户，不输入评论框。
- 输入评论框前需要用户确认。
- 点击最终发送按钮前再次确认；除非用户已明确说“确认后可直接发送”。
- 每个目标最多发送 1 条，除非用户逐条确认。

## execution-log

任务结束时输出简洁记录：

```json
{
  "platform": "douyin",
  "keyword": "AI Agent",
  "mode": "draft-only",
  "attemptedTargets": 3,
  "draftedReplies": 3,
  "submittedReplies": 0,
  "skipped": [
    {
      "target": "作品标题或 URL",
      "reason": "评论区不可见"
    }
  ]
}
```

不要记录密码、Cookie、验证码、私信内容或其他敏感会话信息。

## CLI 示例

默认只找目标并输出草稿记录，不点击发送：

```bash
python skills/deepsop-social-comment-reply/scripts/comment_reply.py \
  --platform douyin \
  --keyword "AI Agent" \
  --reply-text "这个角度很实用，尤其是先拆清楚流程再自动化，落地会稳很多。"
```

确认发送必须显式传 `--confirm-send`。如果没有 `--yes`，脚本会对每个目标要求输入 `SEND` 再点击发送：

```bash
python skills/deepsop-social-comment-reply/scripts/comment_reply.py \
  --platform douyin \
  --keyword "AI Agent" \
  --reply-file reply.txt \
  --mode confirm-send \
  --confirm-send \
  --max-targets 1
```

如果已有具体作品 URL，可用 `--start-url` 直接打开目标页；脚本会用通用评论框选择器尝试填入回复。
