---
name: deepsop-wechatvideo
description: 微信视频号自动发布 skill。当用户需要把本地视频发布到微信视频号时使用。OPClaw 必须先打开 https://channels.weixin.qq.com 让用户完成微信扫码登录/授权，再继续进入发布页并通过内置浏览器 + CDP + WUJIE Shadow DOM 完成上传、填写和发布。
---

# 微信视频号发布 Skill

本 skill 通过 OPClaw 内置浏览器访问微信视频号平台，并使用 Chrome DevTools Protocol (CDP) 操作视频号后台的 WUJIE Shadow DOM，完成本地视频上传、描述/话题/短标题填写和发布。

核心原则：**先让用户在浏览器里完成微信视频号登录授权，再执行自动化发布流程**。不要绕过登录，不保存或索取用户凭据，不使用第三方账号接口。

## 适用场景

当用户表达以下需求时使用本 skill：

- 发布本地视频到微信视频号
- 自动填写视频号描述、话题、短标题
- 检查视频号后台是否已登录
- 在 OPClaw 中完成微信视频号自动化发布

## 必需输入

| 字段 | 必需 | 说明 |
| --- | --- | --- |
| `video_path` | 是 | 本地视频绝对路径，优先 MP4/H.264 |
| `title` | 是 | 视频标题，也可作为短标题默认值 |
| `description` | 否 | 正文描述；未提供时使用 `title` |
| `tags` | 否 | 话题标签，如 `#AI #数字人 #带货` |
| `short_title` | 否 | 视频号短标题；未提供时用 `title` 截断到平台可接受长度 |
| `publish_mode` | 否 | 默认立即发布；只有用户明确要求时才配置定时发布 |

缺少 `video_path` 或 `title` 时，先从用户指令、当前工作目录、桌面常见目录或同名 `.txt` 元数据文件中推断；仍无法确定时，只向用户追问缺失项。

## OPClaw 默认工作流

1. **启动或复用 OPClaw 内置浏览器**
   - 使用 `browser action="start" target="host"`。
   - 不要启动新的独立浏览器实例。
   - 后续所有操作尽量复用同一个 tab。

2. **先打开视频号平台授权页**
   - 导航到 `https://channels.weixin.qq.com`。
   - 告诉用户在打开的浏览器中使用微信扫码登录/确认授权。
   - 等待用户完成登录；可每隔数秒 `browser.snapshot()` 检查页面状态。
   - 如果看到账号头像、创作者后台、发布入口、内容管理等登录后元素，继续下一步。
   - 如果仍是二维码/登录页，不要开始上传；继续等待或提示用户完成扫码。

3. **进入发布页**
   - 导航到 `https://channels.weixin.qq.com/platform/post/create`。
   - 再次检查是否保持登录。如果被重定向回登录页，回到第 2 步。

4. **上传视频**
   - 使用 `scripts/cdp-upload.js` 或等价 CDP 调用。
   - 优先让脚本自动发现当前 `channels.weixin.qq.com` tab：
     ```powershell
     node skills/deepsop-wechatvideo/scripts/cdp-upload.js "C:/path/to/video.mp4"
     ```
   - 如果自动发现失败，再传入 target id：
     ```powershell
     node skills/deepsop-wechatvideo/scripts/cdp-upload.js "C:/path/to/video.mp4" --target <target-id>
     ```
   - 必须使用本地绝对路径，不要用 base64 传大视频。

5. **等待上传处理完成**
   - 上传后等待页面出现预览、进度完成、封面/描述输入区可编辑等信号。
   - 不要在文件刚注入后立刻点击发表。

6. **填写描述和话题**
   - 通过 `browser.evaluate()` 进入 `<wujie-app>` 的 Shadow DOM。
   - 优先操作 `div.input-editor` / `[contenteditable="true"]`。
   - 描述格式建议：
     ```text
     标题或正文描述
     #话题1 #话题2 #话题3
     ```

7. **填写短标题**
   - 通过 snapshot 找到短标题输入框，再用 `browser.act()` 点击并输入。
   - 找不到主 DOM 输入框时，使用 `evaluate()` 在 Shadow DOM 中搜索 `input[placeholder*="短标题"]`。

8. **发布前确认**
   - 检查视频已上传完成。
   - 检查描述、话题、短标题已填。
   - 只有用户要求“直接发布/自动发布”时点击“发表”。
   - 如果用户要求“准备好让我确认”，则停在发布页等待用户确认。

9. **验证结果**
   - 点击发表后，等待跳转到 `/platform/post/list` 或出现发布成功提示。
   - 如果出现审核、二次确认、风险提示等弹窗，停止并让用户在浏览器中确认。

## 用户授权等待策略

OPClaw 在执行视频号发布时，要主动给用户一个清晰状态：

- “我已打开微信视频号平台，请在浏览器中扫码登录/授权。完成后我会继续发布。”
- 登录期间只做页面状态检查，不上传、不填写表单。
- 用户完成扫码后，继续自动化流程，不要求用户重新下达命令。
- 如果二维码过期，刷新 `https://channels.weixin.qq.com` 并提示用户重新扫码。

## OPClaw 指令顺畅度约定

为了让用户一句话下达发布任务更顺畅，agent 应按以下方式处理：

- 用户说“发到视频号”但没给标题：优先用视频文件名去扩展名作为 `title`。
- 用户给了同目录 `.txt`：第一行作为标题，后续行作为描述/话题。
- 用户给了多个视频：按用户顺序逐个发布；每条发布前复用同一登录会话。
- 用户只给了文件夹：选择文件夹中最近修改的 MP4；若有多个候选且无法判断，再询问。
- 用户没有明确“定时发布”：保持立即发布。
- 用户没有明确“保存草稿”：默认发布前完成表单并按用户原始意图发布。
- 遇到登录、平台风控、二次确认、验证码：停下来让用户在浏览器中处理，处理后继续。

## WUJIE / CDP 要点

微信视频号后台使用 WUJIE 微前端，上传控件和部分表单元素位于 `<wujie-app>` 的 Shadow DOM 中。常规 `document.querySelector('input[type="file"]')` 可能找不到真实上传控件。

正确上传链路：

```text
DOM.getDocument(depth=0, pierce=true)
  -> DOM.querySelector('wujie-app')
  -> DOM.describeNode(depth=1, pierce=true)
  -> DOM.querySelector('input[type="file"]')
  -> DOM.setFileInputFiles(files=[absolute_video_path])
```

## 参考文档

- 发布流程：`references/publish-flow.md`
- WUJIE 上传说明：`references/wujie-upload.md`
- CDP 上传脚本：`scripts/cdp-upload.js`
