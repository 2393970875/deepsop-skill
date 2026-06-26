---
name: deepsop-shipinhao
description: 微信视频号自动发布 skill。当用户需要发布视频到微信视频号时使用。基于 OpenClaw 内置浏览器 + CDP 协议，通过 WUJIE 微前端 Shadow DOM 完成文件上传和表单填写。
---

# 微信视频号发布 Skill

本 skill 通过 OpenClaw 内置浏览器 + CDP (Chrome DevTools Protocol) 协议，直接操作微信视频号后台页面 (`channels.weixin.qq.com/platform/post/create`) 完成视频上传和发布。

**不依赖任何第三方 CLI 工具**，只需用户已在浏览器中登录视频号账号。

## 功能概览

| 功能 | 说明 |
| --- | --- |
| 视频上传 | 将本地 MP4 文件上传到视频号 |
| 描述填写 | 设置视频描述（含话题标签 #话题） |
| 短标题设置 | 设置短标题以获得更多流量推荐 |
| 发布 | 立即发布视频 |

## 前置条件

1. **OpenClaw 内置浏览器已启动**（`browser action="start"`，使用 `target="host"`）
2. **用户已登录微信视频号**，登录态有效（账号 Cookie 未过期）
3. 视频文件路径已知，视频格式为 MP4/H.264，大小不超过 20GB

## 默认工作流

1. **启动浏览器**
   - 使用 `browser action="start" target="host"`
   - 确认 CDP 就绪

2. **导航到发布页面**
   ```
   https://channels.weixin.qq.com/platform/post/create
   ```

3. **上传视频文件**
   - 通过 CDP `DOM.setFileInputFiles` 方法操作 WUJIE Shadow DOM 中的 `<input type="file">`
   - 视频上传到 WUJIE 微前端框架的 Shadow DOM
   - **禁止直接操作 `document.querySelector('input[type="file"]')`** — 因为 file input 在 `<wujie-app>` 的 Shadow DOM 内

4. **填写描述**
   - 视频描述（含话题标签）
   - 第一行：视频标题
   - 第二行：话题标签（空格分隔，如 `#AI #数字人 #带货`）

5. **设置短标题**
   - 短标题输入框 (`input[placeholder*="短标题"]`) — 填写后有机会获得更多流量

6. **点击发表**

## 执行步骤详解

### Step 1: 启动浏览器

```javascript
browser.start("host")
```

确认浏览器已运行且 CDP 就绪（`cdpReady: true`）。

### Step 2: 导航到发布页

```javascript
browser.navigate("https://channels.weixin.qq.com/platform/post/create")
```

检查页面快照（`browser.snapshot()`）确认已登录：
- 页面应显示 `一路向北7387`（或对应账号名）
- 应显示 "视频管理/发表动态" 标题
- 应有上传按钮、描述框、短标题框、发表按钮等 UI 元素

### Step 3: 检查账号登录态

从页面快照中确认：
- 右上角头像和用户名可见
- 左侧菜单完整（内容管理、互动管理、直播等）
- 发布表单完整可见

**如果未登录**，告知用户打开浏览器手动扫码登录视频号后台。

**如果已登录**，继续下一步。

### Step 4: 构造标题文件

在视频同目录创建 `.txt` 标题文件，格式：
```
第一行 → 视频标题
第二行 → 话题标签（空格分隔）
```

**不要直接传递标题字符串给浏览器** — 推荐用 evaluate 直接注入。

### Step 5: 上传视频（关键步骤）

**重要：不得使用常规的 `fileInput.setInputFiles()` 或 `click + type` 方式。**

视频号页面使用 **WUJIE 微前端框架**，file input 在 `<wujie-app>` 标签的 **Shadow DOM** 中。

正确方法：通过 **CDP `DOM.setFileInputFiles`** 设置文件路径。

```javascript
// 1. 获取 CDP WebSocket URL
ws://127.0.0.1:18800/devtools/page/<TARGET_ID>

// 2. CDP 调用链
// DOM.getDocument → 获取根节点
// DOM.querySelector 选择 'wujie-app' → 获取 wujie 节点
// DOM.describeNode (pierce: true) → 获取 shadowRoot
// DOM.querySelector 选择 'input[type="file"]' → 获取 file input 节点
// DOM.setFileInputFiles → 设置文件路径
```

**必须使用本地文件系统的绝对路径**（如 `C:/Users/.../video.mp4`），不要使用 base64 编码传输 — 16MB 的视频 base64 后约 21MB，通过 evaluate 传输容易超时且效率低。

### Step 6: 填写视频描述

使用 `browser.evaluate()` 操作 Shadow DOM 中的 `div.input-editor`（contenteditable 元素）：

```javascript
const wujie = document.querySelector('wujie-app');
const shadow = wujie.shadowRoot;
const descEditor = shadow.querySelector('div.input-editor');
descEditor.innerHTML = '视频标题\n#标签1 #标签2 #标签3';
```

### Step 7: 设置短标题

使用 `browser.act({kind:"click", ref:"..."})` 聚焦短标题输入框，然后 `browser.act({kind:"type", ref:"...", text:"..."})` 输入短标题。

短标题输入框的 ref 来自 page snapshot。

### Step 8: 点击发布

点击"发表"按钮（ref 来自 page snapshot）。
发布成功后页面会自动跳转到 `/platform/post/list`（视频管理列表页）。

## CDP 上传示例

以下是一个完整的 Node.js 脚本模板，用于通过 CDP 上传视频：

```javascript
const WebSocket = require('ws');
const ws = new WebSocket('ws://127.0.0.1:18800/devtools/page/<TARGET_ID>');
let msgId = 1;

ws.on('open', () => {
  // Step 1: 获取文档根节点
  ws.send(JSON.stringify({id: msgId++, method: 'DOM.getDocument', params: {depth: 0, pierce: true}}));
});

ws.on('message', (data) => {
  const msg = JSON.parse(data.toString());
  if (msg.id === 1) {
    const rootId = msg.result.root.nodeId;
    // Step 2: 查找 wujie-app
    ws.send(JSON.stringify({id: msgId++, method: 'DOM.querySelector', params: {nodeId: rootId, selector: 'wujie-app'}}));
  } else if (msg.id === 2) {
    const wujieId = msg.result.nodeId;
    // Step 3: 获取 Shadow Root
    ws.send(JSON.stringify({id: msgId++, method: 'DOM.describeNode', params: {nodeId: wujieId, depth: 1, pierce: true}}));
  } else if (msg.id === 3) {
    const shadowRootId = msg.result.node.shadowRoots[0].nodeId;
    // Step 4: 查找 file input
    ws.send(JSON.stringify({id: msgId++, method: 'DOM.querySelector', params: {nodeId: shadowRootId, selector: 'input[type="file"]'}}));
  } else if (msg.id === 4) {
    const fileInputId = msg.result.nodeId;
    // Step 5: 设置文件路径
    ws.send(JSON.stringify({id: msgId++, method: 'DOM.setFileInputFiles', params: {
      nodeId: fileInputId,
      files: ['C:/path/to/your/video.mp4']
    }}));
  } else if (msg.id === 5) {
    console.log('上传成功:', JSON.stringify(msg));
    process.exit(0);
  }
});
```

## 注意事项

### 浏览器管理
- 使用 OpenClaw **内置浏览器** (`target="host"`)，不要启动新的浏览器实例
- 使用同一个 Tab 完成所有操作，避免打开多个视频号页面

### WUJIE 微前端特性
- 视频号后台使用 WUJIE 微前端框架
- 所有表单元素位于 `<wujie-app>` 的 Shadow DOM 中
- 常规的 `document.querySelector` 无法操作内部元素
- 必须使用 CDP `DOM.setFileInputFiles` 上传视频
- 描述框 `div.input-editor` 可以使用 `evaluate` 注入内容（因为 evaluate 运行在页面主 realm 中，CDP 可以穿透 Shadow DOM）

### 文件大小控制
- 12MB 视频 base64 编码后约 16MB，通过 `evaluate` 传输容易超时
- 推荐使用 `DOM.setFileInputFiles` 直接设置本地路径（无文件大小限制）
- 只有小文件（< 2MB）才考虑用 base64 传输

### cookie 有效期
- 视频号的登录态在浏览器 Cookie 中持久保存
- 只要用户不主动登出，登录状态长期有效
- 登录态失效时，导航到发布页会跳转到登录页，需要用户手动扫码

## 故障排查

| 问题 | 原因 | 处理 |
| --- | --- | --- |
| 页面跳转到登录页 | Cookie 过期 | 用户手动扫码登录 |
| `DOM.setFileInputFiles` 找不到节点 | WUJIE 尚未加载 | 先 snapshot 确认页面状态，等加载完成 |
| 上传后无预览 | 页面处理中 | 等待几秒后 snapshot 检查 |
| file input 节点 ID 为 0 | 选择器错误 | 确认 `input[type="file"]` 在 Shadow DOM 中 |
| 描述框无响应 | 未找到 `div.input-editor` | 检查 WUJIE Shadow DOM 中 contenteditable 元素 |
| 发表按钮无法点击 | 页面未完全加载 | 等待后重试 snapshot 获取最新 ref |
