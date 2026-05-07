# DeepSOP Skills

DeepSOP Skills 是一套面向 AI Agent 的技能集合，提供图片/视频生成、声音克隆、社交媒体自动化上传以及人机协作销售等功能。每个 Skill 都是独立的模块，可被 AI Agent 直接调用执行特定任务。

## 📋 目录

- [项目简介](#项目简介)
- [Skills 列表](#skills-列表)
- [快速开始](#快速开始)
- [环境配置](#环境配置)
- [使用指南](#使用指南)
- [项目结构](#项目结构)
- [贡献指南](#贡献指南)
- [许可证](#许可证)

---

## 项目简介

DeepSOP Skills 旨在为 AI Agent 提供丰富的功能扩展能力，涵盖：

- **AI 内容创作**：图片和视频的异步生成，支持多种模型和参数配置
- **声音复刻**：基于 CosyVoice v3.5 Plus 的高质量音色克隆和语音合成
- **社交媒体自动化**：一键发布内容到抖音、快手、小红书、Bilibili 等平台
- **人机协作销售**：自然语言驱动的客户挖掘、邮件/电话/短信营销、TikTok 视频发布

所有 Skills 均遵循统一的接口规范，易于集成和扩展。

---

## Skills 列表

### 1. 🎨 AI Image Generator (deepsop-artist)

**功能描述**：调用 AI Artist API 异步生成图片或视频，自动轮询直到任务完成。

**核心特性**：
- 支持 6 种图片模型（3.1Nano2-Evo、S5.0L、N2、W2.7、W2.7Pro、Nano2-Beta-Evo）
- 支持 11 种视频模型（V3.1FB、S1.5Pro、V3.1PB、V3.1Fast、W2.6t/i/r、klingV3Omni、W2.7t/i/r）
- 自动推断模型类型（根据提示词关键词判断图片或视频）
- 支持参考图/视频上传，自动转换为可访问 URL
- 支持飞书通知、Markdown 输出、本地下载等多种输出方式

**触发场景**：
- "生成一匹狼"、"画一只猫"、"风景画"
- "生成视频"、"文生视频"、"图生视频"
- 指定模型名称如 N2、S5.0L、V3.1FB 等

**快速示例**：
```bash
# 设置 API Key
export AI_ARTIST_TOKEN="sk-your_api_key_here"

# 生成图片（默认 3.1Nano2-Evo）
python3 scripts/generate_image.py "一匹狼"

# 生成视频（默认 V3.1FB）
python3 scripts/generate_image.py "现代轻奢吊灯" --model V3.1FB

# 查看可用模型
python3 scripts/generate_image.py --list-models
```

📖 [详细文档](skills/deepsop-artist/SKILL.md) | [API 文档](skills/deepsop-artist/references/api.md)

---

### 2. 🎙️ Voice Clone (deepsop-voice-clone)

**功能描述**：使用 AI Artist API 进行音色克隆和语音合成，基于 CosyVoice v3.5 Plus 模型。

**核心特性**：
- 查询已有音色列表及状态
- 上传音频创建新音色（支持本地文件和在线 URL）
- 使用指定音色合成语音（支持 ID 或名称）
- 音频下载到本地，支持自定义输出目录

**触发场景**：
- "用蔡总的音色说..."、"生成一段语音"
- "上传音频创建音色"、"复刻这个声音"
- "有哪些音色"、"列出音色"

**快速示例**：
```bash
# 设置 API Key
export AI_ARTIST_TOKEN="sk-your_api_key_here"

# 列出所有可用音色
python scripts/voice_clone.py --list

# 使用音色 ID 合成语音
python scripts/voice_clone.py --synthesize --id 13 --text "你好世界"

# 创建新音色
python scripts/voice_clone.py --create --name "我的音色" --audio "./my_voice.mp3"
```

📖 [详细文档](skills/deepsop-voice-clone/SKILL.md) | [API 文档](skills/deepsop-voice-clone/references/api.md)

---

### 3. 📱 Social Media Upload Skills

#### 3.1 抖音上传 (douyin-upload)

**功能描述**：通过 `sau` CLI 完成抖音登录、cookie 校验、视频/图文上传。

**核心命令**：
- `sau douyin login --account <name>` - 登录抖音
- `sau douyin check --account <name>` - 校验 cookie
- `sau douyin upload-video ...` - 上传视频
- `sau douyin upload-note ...` - 上传图文

📖 [详细文档](skills/douyin-upload/SKILL.md)

---

#### 3.2 快手上传 (kuaishou-upload)

**功能描述**：通过 `sau` CLI 完成快手登录、cookie 校验、视频/图文上传。

**核心命令**：
- `sau kuaishou login --account <name>` - 登录快手
- `sau kuaishou check --account <name>` - 校验 cookie
- `sau kuaishou upload-video ...` - 上传视频
- `sau kuaishou upload-note ...` - 上传图文

📖 [详细文档](skills/kuaishou-upload/SKILL.md)

---

#### 3.3 小红书上传 (xiaohongshu-upload)

**功能描述**：通过 `sau` CLI 完成小红书登录、cookie 校验、视频/图文上传。

**核心命令**：
- `sau xiaohongshu login --account <name>` - 登录小红书
- `sau xiaohongshu check --account <name>` - 校验 cookie
- `sau xiaohongshu upload-video ...` - 上传视频
- `sau xiaohongshu upload-note ...` - 上传图文

📖 [详细文档](skills/xiaohongshu-upload/SKILL.md)

---

#### 3.4 Bilibili 上传 (bilibili-upload)

**功能描述**：通过 `sau` CLI 完成 Bilibili 登录、账号校验、视频上传。程序会自动准备 `biliup`，无需手动安装。

**核心命令**：
- `sau bilibili login --account <name>` - 登录 Bilibili
- `sau bilibili check --account <name>` - 校验账号
- `sau bilibili upload-video ...` - 上传视频

**特点**：
- 自动检查、下载、更新 `biliup`
- 二维码扫码登录，支持打开 `qrcode.png` 扫码

📖 [详细文档](skills/bilibili-upload/SKILL.md)

---

### 4. 🤝 Human-AI Collaboration (human-ai-collab)

**功能描述**：基于 deepsop 平台的智能销售任务助手，理解自然语言指令，自动拆解任务并调用 API 提交。

**核心特性**：
- **自然语言理解**：直接描述需求，如「帮我找50个美国做服装的客户」
- **多员工协作**：
  - **AiWa**：客户挖掘（找客户、行业客户等）
  - **Frank**：邮件销售
  - **Fran**：电话销售
  - **Lisa**：短信销售
  - **Toby**：AI 视频生成并发布到 TikTok
- **自动任务提交**：调用 deepsop API 提交任务，后台异步执行
- **定时查询结果**：按用户指定时间自动查询并推送结果（默认 8 分钟）
- **生成 xlsx 报表**：客户数据自动生成带样式的 Excel 文件
- **统计与详情**：邮件/短信发送统计、TikTok 视频数据分析

**触发场景**：
- "帮我找客户"、"挖掘XXX行业客户"、"找XXX个客户"
- "发TikTok视频"、"生成视频发布到TikTok"
- 包含 `[DeepSOP-AutoQuery]` 标记的系统定时事件

**前置条件**：
```bash
# 设置 API Key
export DEEPSOP_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxx"
```

**快速示例**：
```
用户：帮我找50个美国做服装的客户并发邮件
AI：任务已提交！将在 8 分钟后为你查询结果...

[cron 定时触发后]
AI：AiWa 客户挖掘完成，共找到 50 个客户，详见附件
     Frank 邮件发送完成，发送总数：50，成功：48，已读：12
```

📖 [详细文档](skills/human-ai-collab/SKILL.md)

---

## 快速开始

### 环境要求

- Python 3.8+
- pip（Python 包管理器）
- 各平台所需的 CLI 工具（如 `sau`、`biliup`）

### 安装步骤

1. **克隆仓库**
   ```bash
   git clone https://github.com/your-org/deepsop-skill.git
   cd deepsop-skill
   ```

2. **安装依赖**
   ```bash
   # 根据不同 Skill 安装所需依赖
   pip install requests python-dotenv openpyxl  # human-ai-collab
   ```

3. **配置环境变量**
   
   在项目根目录创建 `.env` 文件：
   ```ini
   # AI Artist API Key（图片/视频生成、声音克隆）
   AI_ARTIST_TOKEN=sk-your_api_key_here
   
   # DeepSOP API Key（人机协作）
   DEEPSOP_API_KEY=sk-your_api_key_here
   
   # 飞书 Webhook URL（可选，用于结果通知）
   FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxx
   ```

4. **验证配置**
   ```bash
   # 测试 AI Artist 配置
   python3 skills/deepsop-artist/scripts/test_config.py
   
   # 测试声音克隆配置
   python skills/deepsop-voice-clone/scripts/voice_clone.py --list
   ```

---

## 环境配置

### API Key 获取

#### AI Artist API Key
- **已有账号** → 前往 [https://ai.deepsop.com/login?source=2](https://ai.deepsop.com/login?source=2) 登录获取
- **没有账号** → 前往 [https://ai.deepsop.com/register?source=2](https://ai.deepsop.com/register?source=2) 注册后获取

登录后在复制您的 API Key（`sk-` 开头）。

适用于：
- deepsop-artist（图片/视频生成）
- deepsop-voice-clone（声音克隆）

#### DeepSOP API Key

- **已有账号** → 前往 [https://ai.deepsop.com/login?source=2](https://ai.deepsop.com/login?source=2) 登录获取
- **没有账号** → 前往 [https://ai.deepsop.com/register?source=2](https://ai.deepsop.com/register?source=2) 注册后获取

登录后在复制您的 API Key（`sk-` 开头）。

适用于：
- human-ai-collab（人机协作）

### 环境变量设置

#### Linux/macOS/Git Bash

```bash
# 临时设置（当前终端有效）
export AI_ARTIST_TOKEN="sk-your_api_key_here"
export DEEPSOP_API_KEY="sk-your_api_key_here"

# 永久设置（添加到 ~/.bashrc 或 ~/.zshrc）
echo 'export AI_ARTIST_TOKEN="sk-your_api_key_here"' >> ~/.bashrc
source ~/.bashrc
```

#### Windows PowerShell

```powershell
# 临时设置（当前终端有效）
$env:AI_ARTIST_TOKEN="sk-your_api_key_here"
$env:DEEPSOP_API_KEY="sk-your_api_key_here"

# 永久设置（系统级）
[System.Environment]::SetEnvironmentVariable('AI_ARTIST_TOKEN', 'sk-your_api_key_here', 'User')
```

#### 使用 .env 文件（推荐）

在项目根目录创建 `.env` 文件，脚本会自动加载：

```ini
AI_ARTIST_TOKEN=sk-your_api_key_here
DEEPSOP_API_KEY=sk-your_api_key_here
FEISHU_WEBHOOK_URL=
```

> ⚠️ **安全提示**：不要将 `.env` 文件提交到代码仓库，确保已加入 `.gitignore`。

---

## 使用指南

### 通用工作流程

大多数 Skills 遵循以下工作流程：

1. **确认运行前提**：查看 `references/runtime-requirements.md`
2. **确认命令契约**：查看 `references/cli-contract.md`
3. **执行匹配命令**：根据需求选择对应命令
4. **故障排查**：如遇问题，查看 `references/troubleshooting.md`

### 意图澄清原则

对于复杂任务（如视频生成、人机协作），AI Agent 会在执行前向用户确认关键参数：

- **优先问对画面/成本影响最大的参数**（生成类型 > 时长 > 分辨率）
- **一次最多问 2-3 个最关键的问题**
- **提供默认建议**，让用户说"就这样"也能继续
- **材料缺失时必须停下来要素材**，不使用占位符

### 错误处理

- 所有 Scripts 均返回结构化结果（JSON 或明确的状态码）
- 失败时提供详细的错误信息和解决建议
- 支持重试机制和网络超时处理

---

## 项目结构

```
deepsop-skill/
├── skills/                      # Skills 根目录
│   ├── bilibili-upload/         # Bilibili 上传技能
│   │   ├── references/          # 参考文档
│   │   │   ├── cli-contract.md
│   │   │   ├── runtime-requirements.md
│   │   │   └── troubleshooting.md
│   │   ├── scripts/examples/    # 示例脚本
│   │   │   ├── bilibili_cli_template.py
│   │   │   ├── bilibili_commands.ps1
│   │   │   └── bilibili_commands.sh
│   │   └── SKILL.md             # 技能定义文件
│   ├── deepsop-artist/          # AI 图片/视频生成技能
│   │   ├── references/
│   │   │   ├── api.md
│   │   │   ├── chat-integration.md
│   │   │   └── feishu-integration.md
│   │   ├── scripts/
│   │   │   └── generate_image.py
│   │   ├── tests/
│   │   │   ├── __init__.py
│   │   │   └── test_generate_image.py
│   │   ├── README.md
│   │   └── SKILL.md
│   ├── deepsop-voice-clone/     # 声音克隆技能
│   │   ├── references/
│   │   │   └── api.md
│   │   ├── scripts/
│   │   │   └── voice_clone.py
│   │   ├── README.md
│   │   └── SKILL.md
│   ├── douyin-upload/           # 抖音上传技能
│   │   ├── references/
│   │   ├── scripts/examples/
│   │   └── SKILL.md
│   ├── kuaishou-upload/         # 快手上传技能
│   │   ├── references/
│   │   ├── scripts/examples/
│   │   └── SKILL.md
│   ├── xiaohongshu-upload/      # 小红书上传技能
│   │   ├── references/
│   │   ├── scripts/examples/
│   │   └── SKILL.md
│   └── human-ai-collab/         # 人机协作技能
│       ├── scripts/
│       │   ├── format_calls.py
│       │   ├── format_customers.py
│       │   ├── format_emails.py
│       │   └── format_sms.py
│       └── SKILL.md
└── README.md                    # 项目说明文档
```

### 文件说明

| 文件/目录 | 说明 |
|----------|------|
| `SKILL.md` | 技能定义文件，包含元数据和详细说明 |
| `references/` | 参考文档目录 |
| `references/api.md` | API 接口详细文档 |
| `references/cli-contract.md` | CLI 命令契约说明 |
| `references/runtime-requirements.md` | 运行前提和环境要求 |
| `references/troubleshooting.md` | 故障排查指南 |
| `scripts/` | 可执行脚本目录 |
| `scripts/examples/` | 示例脚本和命令模板 |
| `tests/` | 单元测试目录 |

---

## 贡献指南

欢迎贡献新的 Skills 或改进现有功能！

### 添加新 Skill

1. 在 `skills/` 目录下创建新的 Skill 文件夹
2. 创建 `SKILL.md` 文件，包含 YAML frontmatter 和详细说明
3. 添加必要的 `references/` 文档
4. 编写可执行脚本放在 `scripts/` 目录
5. 提供示例命令和测试用例
6. 更新本 README 的 Skills 列表

### SKILL.md 模板

```markdown
---
name: your-skill-name
description: 简短描述，说明何时使用此 skill
---

# Your Skill Name

## 功能描述

## 快速开始

## 参数说明

## 使用示例

## 相关文件
```

### 代码规范

- 遵循 PEP 8 Python 代码规范
- 所有脚本必须包含清晰的注释和错误处理
- 提供完整的单元测试
- 保持文档同步更新

---

## 常见问题

### Q1: 如何获取 API Key？

A: 已有账号 → 前往 [https://ai.deepsop.com/login?source=2](https://ai.deepsop.com/login?source=2) 登录获取
B: 没有账号 → 前往 [https://ai.deepsop.com/register?source=2](https://ai.deepsop.com/register?source=2) 注册后获取

### Q2: 为什么命令执行失败？

A: 请检查：
- 环境变量是否正确设置
- 网络连接是否正常
- API Key 是否有效
- 查看详细错误信息并参考 `references/troubleshooting.md`

### Q3: 如何自定义输出目录？

A: 大多数脚本支持 `--output-dir` 参数，例如：
```bash
python3 scripts/generate_image.py "风景画" --download --output-dir "./my_images"
```

### Q4: 支持哪些操作系统？

A: 支持 Windows、macOS、Linux。部分 CLI 工具可能需要额外配置。

---

## 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

---

## 联系方式

- 🌐 官网：[https://ai.deepsop.com/](https://ai.deepsop.com/)
- 📧 邮箱：support@deepsop.com
- 💬 社区：待定

---

**感谢使用 DeepSOP Skills！** 🚀