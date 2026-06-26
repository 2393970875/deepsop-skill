# WUJIE Shadow DOM 文件上传指南

## 背景

微信视频号后台 (`channels.weixin.qq.com`) 使用 WUJIE 微前端框架。主要发布表单挂载在 `<wujie-app>` 自定义标签下，内部 DOM 在 Shadow DOM 中渲染。

这意味着：

- 普通 `document.querySelector('input[type="file"]')` 常常找不到真实上传控件。
- CDP 查询需要设置 `pierce: true` 才能穿透 Shadow DOM。
- 大视频不要用 base64 注入，应该直接把本地绝对路径交给 `DOM.setFileInputFiles`。

## 推荐方案

使用 CDP `DOM.setFileInputFiles`。

```json
{"id":1,"method":"DOM.getDocument","params":{"depth":0,"pierce":true}}
{"id":2,"method":"DOM.querySelector","params":{"nodeId":1,"selector":"wujie-app"}}
{"id":3,"method":"DOM.describeNode","params":{"nodeId":2,"depth":1,"pierce":true}}
{"id":4,"method":"DOM.querySelector","params":{"nodeId":3,"selector":"input[type=\"file\"]"}}
{"id":5,"method":"DOM.setFileInputFiles","params":{"nodeId":4,"files":["C:/path/to/video.mp4"]}}
```

仓库脚本已经封装了这些步骤：

```powershell
node skills/deepsop-wechatvideo/scripts/cdp-upload.js "C:/path/to/video.mp4"
```

## 路径要求

- 必须使用绝对路径。
- Windows 路径建议转成正斜杠，例如 `C:/Users/Administrator/Desktop/video.mp4`。
- 不要传 `~`、相对路径或 URL。
- 文件必须位于本机，浏览器进程能够读取。

## 失败处理

| 问题 | 常见原因 | 处理 |
| --- | --- | --- |
| 找不到视频号 tab | 未打开平台页或 CDP 端口不同 | 先用 OPClaw 浏览器打开 `https://channels.weixin.qq.com`，必要时传 `--port` |
| 找不到 `wujie-app` | 发布页尚未加载完成 | 等待页面稳定后重试 |
| 找不到 file input | 平台 UI 变更或上传区未出现 | 检查是否在 `/platform/post/create`，重新获取 snapshot |
| 上传后无预览 | 页面仍在处理或未触发事件 | 等待数秒；必要时重新注入或手动检查页面 |
| 登录页反复出现 | Cookie 失效或未授权 | 回到根地址让用户扫码登录 |

## 备用方案

仅当文件很小且 CDP 上传不可用时，才考虑 base64 + `DataTransfer` 注入。普通视频发布不推荐该方式，因为体积大、慢且容易超时。
