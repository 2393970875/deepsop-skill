# WUJIE 微前端 Shadow DOM 文件上传指南

## 背景

微信视频号后台 (`channels.weixin.qq.com`) 使用 **WUJIE 微前端框架**。主要内容区域以 `<wujie-app>` 自定义标签挂载，其内部 DOM 在 **Shadow DOM** 中渲染。

这意味着：
- `document.querySelector()` 无法访问内部元素
- 必须使用 CDP 协议并设置 `pierce: true` 才能穿透 Shadow DOM
- 常规 Playwright `setInputFiles()` 在 CDP 模式下也无法直接工作

## 文件上传方式对比

| 方式 | 适用场景 | 限制 |
| --- | --- | --- |
| **`DOM.setFileInputFiles`** ✅ 最佳 | 大文件（> 2MB） | 需要 CDP 连接 + 知道节点 ID |
| **base64 + evaluate** | 小文件（< 2MB） | 12MB 视频 base64 后约 16MB，evaluate 传输易超时 |
| **Playwright setInputFiles** | 非 Shadow DOM 场景 | WUJIE Shadow DOM 下不可用 |

## 推荐方案：DOM.setFileInputFiles

### 步骤

1. 通过 CDP WebSocket 连接到目标页面
2. 发送 `DOM.getDocument` 获取根节点 ID
3. 发送 `DOM.querySelector` 获取 `<wujie-app>` 节点
4. 发送 `DOM.describeNode (pierce: true)` 获取 Shadow Root
5. 发送 `DOM.querySelector` 在 Shadow Root 中找到 `input[type="file"]`
6. 发送 `DOM.setFileInputFiles` 设置本地文件路径

### CDP 消息序列

```json
{"id":1, "method":"DOM.getDocument", "params":{"depth":0, "pierce":true}}

{"id":2, "method":"DOM.querySelector", "params":{"nodeId":1, "selector":"wujie-app"}}

{"id":3, "method":"DOM.describeNode", "params":{"nodeId":<wujie-id>, "depth":1, "pierce":true}}

{"id":4, "method":"DOM.querySelector", "params":{"nodeId":<shadow-root-id>, "selector":"input[type=\"file\"]"}}

{"id":5, "method":"DOM.setFileInputFiles", "params":{"nodeId":<file-input-id>, "files":["C:/path/to/video.mp4"]}}
```

### 文件路径格式

- **必须使用绝对路径**
- Windows 用正斜杠：`C:/Users/Administrator/.../video.mp4`
- 路径中不要用反斜杠（`\`），CDP 协议需要 POSIX 风格的路径

## base64 方案（备选）

仅当 `DOM.setFileInputFiles` 不可用时使用，且**只适合小文件**。

```javascript
// 构造 File 对象
const response = await fetch(`data:video/mp4;base64,${BASE64_DATA}`);
const blob = await response.blob();
const file = new File([blob], 'video.mp4', { type: 'video/mp4' });

// 使用 DataTransfer 触发上传
const dt = new DataTransfer();
dt.items.add(file);
const input = shadow.querySelector('input[type="file"]');
input.files = dt.files;
input.dispatchEvent(new Event('change', { bubbles: true }));
```

## 已知问题

- `DOM.setFileInputFiles` 成功后不会自动触发 React/Vue 的 onChange 事件——但视频号的上传逻辑监听的是 `change` 事件或文件属性变化，`setFileInputFiles` 内部会触发该事件
- 如果上传后页面没有反应，可以主动派发一个 `change` 或 `input` 事件
