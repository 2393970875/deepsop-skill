# Voice Clone - 声音复刻技能

AI Artist API 驱动的声音克隆与语音合成工具。

## 🚀 快速开始

### 1. 获取 API Key

访问 [https://ai.deepsop.com/](https://ai.deepsop.com/) 注册并登录，然后在控制台创建你的 API Key。

### 2. 设置 API Key

```bash
# Windows PowerShell
$env:AI_ARTIST_TOKEN="sk-your_api_key_here"

# Linux/macOS
export AI_ARTIST_TOKEN="sk-your_api_key_here"
```

### 3. 验证配置

```bash
python scripts/voice_clone.py --list
```

### 4. 使用示例

```bash
# 列出所有可用音色
python scripts/voice_clone.py --list

# 使用音色合成语音
python scripts/voice_clone.py --synthesize --id 10 --text "你好，这是测试语音"

# 使用音色名称合成
python scripts/voice_clone.py --synthesize --name "蔡总的音色" --text "你好世界"

# 创建新音色
python scripts/voice_clone.py --create --name "我的音色" --audio "./my_voice.mp3"
```

## 📖 完整文档

详细使用说明请查看 [SKILL.md](SKILL.md)

## 🎯 功能特性

- **查询音色** - 列出系统中所有可用音色
- **语音合成** - 使用指定音色生成语音
- **音色克隆** - 上传音频创建新的音色
- **自动上传** - 本地音频自动上传到 OSS 获取 URL

## 🔧 环境要求

- Python 3.6+
- requests 库

## 📄 许可证

请遵守 AI Artist API 的使用条款。
