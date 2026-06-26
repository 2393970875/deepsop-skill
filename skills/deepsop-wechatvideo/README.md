# 微信视频号发布 Skill

通过 OPClaw 内置浏览器打开微信视频号平台，让用户先完成微信扫码登录/授权，然后自动进入发布页完成视频上传、表单填写和发布。

## 使用方式

直接对 OPClaw 说出需求，例如：

- “把桌面上的 `新品介绍.mp4` 发布到微信视频号，标题叫新品介绍，话题 #新品 #门店”
- “把这个文件夹里最新的视频发到视频号”
- “登录视频号并帮我发布这条视频，发布前让我确认”

OPClaw 会先打开 `https://channels.weixin.qq.com`，等待你在浏览器中扫码登录或确认授权。授权完成后，它会继续进入发布页并执行自动化发布流程。

## 自动化流程

1. 启动或复用 OPClaw 内置浏览器。
2. 打开 `https://channels.weixin.qq.com`。
3. 等待用户扫码登录/授权。
4. 进入 `https://channels.weixin.qq.com/platform/post/create`。
5. 通过 CDP `DOM.setFileInputFiles` 上传本地视频。
6. 填写描述、话题和短标题。
7. 按用户要求直接发表，或停在发布页等待确认。
8. 验证是否跳转到视频管理列表或出现发布成功提示。

## 技术说明

微信视频号后台使用 WUJIE 微前端，上传控件在 `<wujie-app>` 的 Shadow DOM 中。普通 DOM 查询通常找不到文件输入框，所以本 skill 使用 CDP 穿透 Shadow DOM：

```text
DOM.getDocument -> wujie-app -> shadowRoot -> input[type=file] -> DOM.setFileInputFiles
```

仓库内置脚本可自动发现当前视频号 tab：

```powershell
node skills/deepsop-wechatvideo/scripts/cdp-upload.js "C:/path/to/video.mp4"
```

如果自动发现失败，可手动指定 target：

```powershell
node skills/deepsop-wechatvideo/scripts/cdp-upload.js "C:/path/to/video.mp4" --target <target-id>
```

## 安全边界

- 不保存、不索取微信账号密码。
- 登录和授权都在用户可见的官方微信视频号页面完成。
- 只读取用户指定的视频文件用于上传。
- 遇到二维码、验证码、风控或二次确认时，交给用户在浏览器中处理。
