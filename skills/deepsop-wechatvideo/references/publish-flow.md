# 视频号发布流程参考

## 完整操作流程

```
用户指令
    │
    ▼
启动 OpenClaw 内置浏览器 (target="host")
    │
    ▼
导航到 https://channels.weixin.qq.com/platform/post/create
    │
    ▼
检查页面快照 → 已登录?
    ├── 否 → 告知用户手动扫码登录
    │
    ▼
   是
    │
    ▼
CDP上传：DOM.setFileInputFiles（WUJIE Shadow DOM）
    │
    ▼
等待上传完成（检查页面预览元素）
    │
    ▼
填写视频描述（div.input-editor, contenteditable）
    │
    ▼
设置短标题（input[placeholder*="短标题"]）
    │
    ▼
点击"发表"按钮
    │
    ▼
验证：页面跳转到 /platform/post/list ✓
```

## 页面元素映射

| 功能 | DOM 选择器 | 所在位置 |
| --- | --- | --- |
| 文件上传 | `input[type="file"][accept*="video"]` | WUJIE Shadow DOM |
| 视频描述 | `div.input-editor`（contenteditable） | WUJIE Shadow DOM |
| 短标题 | `input[placeholder*="短标题"]` | 主 DOM（表单外层） |
| 话题标签 | `#话题` 按钮 | WUJIE Shadow DOM |
| 发表按钮 | `button:has-text("发表")` | 主 DOM |
| 保存草稿 | `button:has-text("保存草稿")` | 主 DOM |

> 注意：文件上传和描述编辑在 Shadow DOM 中，短标题和发表按钮在主 DOM 中。

## 描述格式

在 `div.input-editor` 中设置 `innerHTML`：

```html
视频标题
#标签1 #标签2 #标签3
```

示例：
```html
快速生成数字人带货视频<br>#AI #数字人 #带货 #短视频
```

使用 `<br>` 或 `\n` 换行均可。

## 短标题

目的：获得更多流量推荐
- 同标题时可复用视频标题
- 最多约 20 字

## 发布模式

- **立即发布**：默认，选 "不定时"
- **定时发布**：选 "定时" 并设置时间

## 验证发布成功

1. 点击"发表"后，页面 URL 跳转到 `/platform/post/list`（视频管理列表）
2. 列表顶部出现刚发布的视频
3. 状态显示 "发表成功"

## 重复发布

- 同样视频可以重复发布，视频号允许
- 建议修改标题/描述以区分不同版本
