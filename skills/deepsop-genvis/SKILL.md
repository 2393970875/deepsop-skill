---
name: deepsop-genvis
description: |
  DeepSOP AI 图片与视频生成技能。用于调用 AI Artist API 创建图片或视频任务、上传参考图片/视频/音频、预估费用、轮询结果，并按 Vue 前端规则根据接口返回的 sourceValue/methodType 校验 generationType、ratio、resolution、duration、参考素材数量、搜索开关、音频开关等参数约束。

  本技能不写死模型名称清单和默认模型。模型列表、模型名、展示顺序和默认模型全部从服务端 consumeSource/list 获取；默认模型取对应类型中 sourceValue != "auto" 且 hiddenState == "0" 的接口返回顺序第一个。用户选中模型后，只使用该模型的 sourceValue/methodType 触发本地参数规则。

---

# DeepSOP GenVis

使用 `scripts/generate_image.py` 创建 AI 图片或视频任务。脚本会先预估费用，再提交任务并轮询到 `SUCCESS` / `FAILED` / `TIMEOUT`。

## 前置条件：DEEPSOP_API_KEY

本技能需要 **API Key 授权**才能调用 DeepSOP 接口。

- OPClaw 项目运行时直接读取项目设置里的 `DEEPSOP_API_KEY`。
- 非 OPClaw 运行时，引导用户授权后把 `DEEPSOP_API_KEY` 配置为共享环境变量或 `~/.openclaw/openclaw.json`，让其他 DeepSOP 技能也能复用。
- 读取不到 Key 时，引导用户登录/注册并新建 API Key：
  - 已有账号 → [https://ai.deepsop.com/login?source=2](https://ai.deepsop.com/login?source=2)
  - 没有账号 → [https://ai.deepsop.com/register?source=2](https://ai.deepsop.com/register?source=2)
- API Key 通常以 `sk-` 开头。

共享配置示例：

```text
DEEPSOP_API_KEY=sk-your_api_key_here
```

## 必须遵守

- OPClaw 项目运行时使用项目设置里的 `DEEPSOP_API_KEY`；非 OPClaw 运行时，让用户授权后设置共享 `DEEPSOP_API_KEY`。
- 模型列表、模型名称、模型顺序、默认模型全部来自 `consumeSource/list`。
- 未指定模型时，先按 prompt 判断图片或视频，再取对应类型下 `sourceValue != "auto"` 且 `hiddenState == "0"` 的接口返回顺序第一个。
- 指定模型时，优先传接口返回的 `sourceValue/methodType`，例如 `--model 10`。脚本保留友好别名只是兼容旧调用，不作为技能文档依据。
- 选中模型或切换模型后，只根据 `methodType` 触发本地规则：默认值、可见字段、字段选项、必填校验、payload 组装。
- 任务失败时，不要自动切换模型重试。必须反馈实际使用的 `methodType`、状态和失败原因。
- 用户给本地参考图/视频/音频时，先上传成可访问 URL，再放入对应参数。

## 快速命令

```bash
# 查看接口当前启用模型
python3 scripts/generate_image.py --list-models

# 图片/视频默认模型都由接口返回顺序决定
python3 scripts/generate_image.py "一只可爱的猫"
python3 scripts/generate_image.py "生成一段城市夜景延时视频"

# 指定 methodType/sourceValue
python3 scripts/generate_image.py "产品宣传图 4 种风格" --model 10 --n 4 --ratiocination high
python3 scripts/generate_image.py "城市夜景延时短片" --model 20 --ratio "16:9" --resolution "1080p" --duration 10

# 调试 payload，不提交任务
python3 scripts/generate_image.py "测试" --model 15 --dry-run --json-output
```

## 先问什么

当用户信息不足且会影响成本或结果时，一次只问 2-3 个关键问题：

- 图片：是否有参考图、比例/尺寸、质量档位。
- 视频：生成类型、时长、比例/分辨率、是否生成声音。
- 参考/编辑/续写视频：必须问素材 URL 或本地文件路径。
- 多镜头：确认单镜头、智能分镜或自定义分镜；自定义分镜必须有每个镜头的描述和时长。

用户说“随便/快速来一个”时，可以按接口默认模型和脚本默认参数直接生成，并在结果里说明实际使用的 `methodType` 和默认参数。

## 图片 methodType 规则

切换图片模型后触发前端默认逻辑：

- `quality`: methodType `1/10/11` 默认 `1K`，其他默认 `2K`。
- `size`: methodType `2/8/9/10/11` 默认 `auto`，其他默认 `1:1`。
- `webSearch`: methodType `4/8` 默认开启。

| methodType | quality | size/ratio 规则 | 特殊参数 | 参考素材规则 |
| --- | --- | --- | --- | --- |
| `0` | `2K/4K` | 不支持 `auto`；提交为 `WxH`，如 `2048x2048` | 无 | 标准图片参考 |
| `1` | `1K` | 禁用 `1:2/2:1/1:3/3:1/1:4/4:1/1:8/8:1/4:5/5:4/9:21/21:9` | 无 | 标准图片参考 |
| `2` | `1K/2K/4K` | 支持 `auto`；禁用 `1:2/2:1/1:3/3:1/1:4/4:1/1:8/8:1/9:21` | 无 | 参考图最多 10 张，单张 10MB |
| `3` | `1K/2K/4K` | 禁用 `auto/1:2/2:1/1:3/3:1/1:4/4:1/1:8/8:1/9:21` | 无 | 标准图片参考 |
| `4` | `2K/3K` | 不支持 `auto`；提交为 `WxH`，如 `2048x2048` | `webSearch` | 标准图片参考，额外提交 `duration=10` |
| `5` | `1K/2K/4K` | 同 `3` | 无 | 标准图片参考 |
| `6` | `1K/2K` | 禁用 `auto/9:21/21:9`；提交为 `W*H` | 无 | 最多 9 张；单张 20MB；最短边 240，最长边 8000 |
| `7` | `1K/2K` | 同 `6` | 无 | 同 `6` |
| `8` | `1K/2K/4K` | 支持 `auto`；禁用 `1:2/2:1/1:3/3:1/9:21` | `webSearch`、`imageSearch` | 单张 20MB；最长边 6000 |
| `9` | `1K/2K/4K` | 同 `8` | 无 | 参考图最多 14 张，单张 10MB |
| `10` | `1K/2K/4K` | 支持 `auto`；禁用 `1:4/4:1/1:8/8:1` | `ratiocination=low/medium/high`、`n=1-10`；不提交 `webSearch/imageSearch` | 参考图最多 16 张；单张 50MB；prompt 上限 16000 字 |
| `11` | 前端隐藏 `quality` | 支持 `auto`；禁用 `1:4/4:1/1:8/8:1/4:5/5:4` | 不提交 `quality` | 参考图最多 16 张；单张 50MB；prompt 上限 16000 字 |

图片上传映射：

| 本地素材 | 允许格式 | 上传后参数 | 备注 |
| --- | --- | --- | --- |
| 参考图 | JPEG/JPG/PNG/WEBP | `image` | methodType `6/7` 使用更高图片尺寸限制；methodType `10/11` 单张 50MB |

## 视频 methodType 规则

切换视频模型后触发前端默认逻辑：

- 基础重置：`resolution=720p`、`ratio=16:9`、`duration=10`、`generateAudio=true`、`shotType=single`、`mode=pro`。
- methodType `3/4/5/6/11/12` 默认 `duration=8`。
- methodType `10` 默认 `shotType=multi`。
- 默认 `generationType`: `7/15` 为 `TEXT`；`1/4/5/6/8/14` 为 `FIRST&LAST`；其他为 `REFERENCE`。之后按白名单校正。

| methodType | generationType | ratio | resolution | duration | 关键规则 |
| --- | --- | --- | --- | --- | --- |
| `1` | `TEXT/FIRST&LAST` | `16:9/9:16` | `720p` | `10-15s` | 首尾帧模式用 `firstImageUrl` |
| `2` | `TEXT/FIRST&LAST` | `adaptive/1:1/4:3/3:4/16:9/9:16/21:9` | `480p/720p/1080p` | `4-12s` | 支持 `durationSwitch` |
| `3` | `TEXT/FIRST&LAST/REFERENCE` | `adaptive/16:9/9:16` | `720p/1080p/4K` | 固定 `8s` | `REFERENCE` 至少一张参考图 |
| `4` | `TEXT/FIRST&LAST` | `adaptive/16:9/9:16` | `720p/1080p/4K` | 固定 `8s` | 默认首尾帧 |
| `5` | `TEXT/FIRST&LAST` | `adaptive/16:9/9:16` | `720p/1080p/4K` | `4s/8s` | 支持 `n=1-4`、`personGeneration`、`resizeMode` |
| `6` | `TEXT/FIRST&LAST` | `adaptive/16:9/9:16` | `720p/1080p/4K` | `4s/8s` | 同 `5` 的时长规则 |
| `7` | `TEXT` | `1:1/4:3/3:4/16:9/9:16` | `720p/1080p` | `3-15s` | `size` 提交为 `W*H`，支持 `negativePrompt/promptExtend/shotType` |
| `8` | `FIRST&LAST` | 由首帧决定，不提交 ratio | `720p/1080p` | `3-15s` | 必须传首帧；不支持尾帧 |
| `9` | `REFERENCE` | `1:1/4:3/3:4/16:9/9:16` | `720p/1080p` | `3-10s` | 参考图片+参考视频总数 `1-5`，`size` 提交为 `W*H` |
| `10` | `TEXT/FIRST&LAST/REFERENCE/EDIT/FEATURE` | `1:1/16:9/9:16`，部分模式隐藏 | 无 | `3-15s` | 支持 `shotType=single/multi/customize`、`mode`、`keepOriginalSound`；`EDIT/FEATURE` 需要视频 |
| `11` | `TEXT/FIRST&LAST` | `adaptive/1:1/4:3/3:4/7:4/4:7/16:9/9:16/21:9` | `720p` | `4-12s` | 默认 `8s` |
| `12` | `TEXT/FIRST&LAST` | `16:9/9:16/7:4/4:7` | `720p/2K` | `4-12s` | 默认 `8s` |
| `13` | `TEXT/FIRST&LAST/REFERENCE` | `adaptive/1:1/4:3/3:4/7:4/4:7/16:9/9:16/21:9` | `720p/2K` | `4-12s` | `REFERENCE` 可用参考图 |
| `14` | `FIRST&LAST/CONTINUATION` | 由首帧决定，不提交 ratio | `720p/1080p` | `3-15s` | `CONTINUATION` 必须有 `firstClipUrl` |
| `15` | `TEXT` | `1:1/4:3/3:4/16:9/9:16` | `720p/1080p` | `3-15s` | 支持 `negativePrompt/promptExtend` |
| `16` | `REFERENCE` | `1:1/4:3/3:4/16:9/9:16` | `720p/1080p` | 有参考视频时 `3-10s`，否则 `3-15s` | 参考图片+参考视频总数 `1-5` |
| `17` | `TEXT/FIRST&LAST/REFERENCE` | `adaptive/1:1/4:3/3:4/16:9/9:16/21:9` | `480p/720p/1080p` | `4-15s` | 支持 `durationSwitch`、`webSearch`、参考图片/视频/音频 |
| `18` | `TEXT/FIRST&LAST/REFERENCE` | 同 `17` | `480p/720p` | `4-15s` | 同 `17` |
| `19` | `TEXT/FIRST&LAST/REFERENCE/EDIT` | `1:1/4:3/3:4/5:4/4:5/16:9/9:16/21:9/9:21`，`EDIT` 时隐藏 | `720p/1080p` | `3-15s`；`EDIT` 由视频决定 | 不支持尾帧、`negativePrompt/generateAudio/enhancePrompt/promptExtend/shotType/webSearch`；`EDIT` 必须有 `firstClipUrl` |
| `20` | `TEXT/FIRST&LAST/REFERENCE` | 同 `17` | `480p/720p/1080p` | `4-15s` | 同 `17` |
| `21` | `TEXT/FIRST&LAST/REFERENCE` | 同 `17` | `480p/720p` | `4-15s` | 同 `17` |

## 视频素材上传与参数映射

| 本地素材 | 允许格式/限制摘要 | 上传后参数 | 适用规则 |
| --- | --- | --- | --- |
| 首帧图 | JPEG/JPG/PNG/WEBP；按 methodType 图片尺寸限制校验 | `firstImageUrl` | `FIRST&LAST`、部分首帧/图生视频必填 |
| 尾帧图 | JPEG/JPG/PNG/WEBP | `lastImageUrl` | 传尾帧时必须同时传首帧；methodType `8/19` 不支持尾帧 |
| 参考图 | JPEG/JPG/PNG/WEBP | `imageUrlList` | `REFERENCE` 或多模态参考；methodType `9/16` 与参考视频合计 `1-5` |
| 参考主体图 | JPEG/JPG/PNG | `elementList` | methodType `10` 的主体参考 |
| 续写/编辑/参考视频 | MP4/MOV；Wan r2v 通常 100MB、1-30s；methodType `10` 200MB、3-10s；methodType `17/18/20/21` 50MB、2-15s；methodType `19` 100MB、3-60s | `firstClipUrl` 或 `videoUrlList` / `videoList` | `CONTINUATION/EDIT/FEATURE/REFERENCE` |
| 音频 | WAV/MP3；Wan 单音频 15MB、3-30s；methodType `17/18/20/21` 最多 3 个、2-15s、总时长不超过 15s | `audioUrlList` | methodType `17/18/20/21` 使用音频时，必须同时提供参考图或参考视频 |

## 输出契约

- stdout 只输出最终一行结果：默认 URL，`--json-output` 为单行 JSON，`--markdown-output` 为 Markdown 图片链接。
- stderr 输出进度、费用、任务 ID、警告和失败原因。
- 退出码：`0` 成功，`1` 失败或超时。

## 错误处理

- `DEEPSOP_API_KEY` 未设置：提示用户需要 API Key 授权。
  - OPClaw 项目运行时检查项目设置里的 `DEEPSOP_API_KEY`。
  - 非 OPClaw 运行时，引导用户登录/注册获取 Key：已有账号 [login?source=2](https://ai.deepsop.com/login?source=2)，没有账号 [register?source=2](https://ai.deepsop.com/register?source=2)。
  - 配置共享环境变量或 `~/.openclaw/openclaw.json` 后再重试。
- `401`：提示 API Key 无效或过期，按上面的登录/注册入口重新获取 Key。
- `4xx/5xx`：反馈实际状态码和接口错误信息，不要自动切换模型或伪造结果。

## 参考文件

- `scripts/generate_image.py`: 可执行脚本与本地 methodType 规则矩阵。
- `references/api.md`: API 端点、请求格式、素材字段映射。
- `references/chat-integration.md` / `references/feishu-integration.md`: 对话和飞书集成说明。
