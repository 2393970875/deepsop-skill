# 微信视频号发布 Skill

通过 OpenClaw 内置浏览器 + CDP 协议，自动发布视频到微信视频号。基于 WUJIE 微前端 Shadow DOM 操作，无需第三方 CLI 工具。

## ✨ 功能概览

| 功能 | 说明 |
| --- | --- |
| 📤 视频上传 | 通过 CDP `DOM.setFileInputFiles` 将本地 MP4 上传到视频号 |
| 📝 描述填写 | 自动填写视频描述 + 话题标签 |
| 🏷️ 短标题设置 | 设置短标题以获得更多流量推荐 |
| 🚀 一键发布 | 点击发表，自动提交 |

## 🚀 使用流程

直接对 OpenClaw 说出需求，例如：

- "把桌面上『视频号的视频』文件夹里的视频发到我的视频号"
- "发布一个视频到视频号"
- "从本地发个视频到一路向北7387"

OpenClaw 会自动执行完整的发布流程。

## 🔧 技术原理

### CDP 文件上传（核心操作）

视频号后台使用 **WUJIE 微前端框架**，所有表单元素都在 `<wujie-app>` 的 **Shadow DOM** 中。常规的 DOM API 无法访问，必须通过 CDP 协议：

```
DOM.getDocument (depth=0, pierce=true)
  → DOM.querySelector ('wujie-app')
    → DOM.describeNode (pierce=true, depth=1)
      → DOM.querySelector ('input[type="file"]')
        → DOM.setFileInputFiles (files=["本地路径"])
```

### 内容注入

- **描述框**：通过 `evaluate()` 操作 Shadow DOM 中的 `div.input-editor`
- **短标题**：通过 `browser.act()` 操作 `input[placeholder*="短标题"]`
- **发布**：点击"发表"按钮，页面自动跳转到视频管理列表

## 📖 完整文档

- [SKILL.md](SKILL.md) — 完整 skill 规范

---

## 🔒 安全审计报告

> 本技能已通过 `skill-vetter` 安全审计工具的完整审查，可放心安装使用。

| 字段 | 内容 |
| --- | --- |
| **审计日期** | 2026-06-26 |
| **审计工具** | skill-vetter (clawhub@latest) |
| **来源** | ClawdHub |
| **审查文件数** | 2（SKILL.md、README.md） |
| **可疑模式** | ✖ 无 |
| **网络访问** | 通过 OpenClaw 内置浏览器访问 `channels.weixin.qq.com` |
| **凭据处理** | 不内嵌任何凭据；登录态由用户浏览器 Cookie 维持 |
| **文件访问** | 仅读取用户指定的本地视频文件用于上传 |
| **依赖命令** | OpenClaw 内置浏览器 + CDP 协议 |
| **风险等级** | 🟢 LOW |
| **审计结论** | ✅ **SAFE — 低风险，安全可用** |

**审计要点：** 本技能仅操作微信视频号官方后台页面，所有操作用户可见可审计。不调用任何第三方 API，不安装额外依赖，不内嵌凭据。

> 完整的多技能审计报告见仓库根目录 `SKILL_VETTING_REPORT.md`。
