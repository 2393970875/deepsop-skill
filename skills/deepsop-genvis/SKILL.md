---
name: deepsop-genvis
description: |
  DeepSOP GenVis 小美工技能。用于调用 DeepSOP AI Artist 接口提交现有三类生成任务：
  type=9 视频生成、type=10 图像生成、type=12 数字人生成。参数约束必须参考
  trade-staff-admin-front 的 beautifyTool 前端链路，提交前实时读取 consumeSource/list 的
  IMAGE_MODEL、VIDEO_MODEL、HUMAN_MODEL 模型描述和可用状态。
---

# DeepSOP GenVis

本技能通过 `scripts/generate_image.py` 创建 AI 图像、视频、数字人任务。当前范围只包含：

- `type=9`：视频生成，对应前端 `GenerateVideo`
- `type=10`：图像生成，对应前端 `GenerateImage`
- `type=12`：数字人生成，对应前端 `DigitalHuman`

暂不接入小云雀相关业务功能，不接入 `IMAGE_PROCESS`，也不实现 `type=23/24/25/26/27` 等小云雀专用参数链路。

## 授权

所有请求必须携带 `DEEPSOP_API_KEY`，请求头使用 `X-Api-Key` 或 `x-api-key`。

非 OPClaw 环境优先从环境变量读取：

```text
DEEPSOP_API_KEY=sk-your_api_key_here
```

没有 API Key 时，引导用户登录或注册后创建 API Key：

- 登录：[https://ai.deepsop.com/login?source=2](https://ai.deepsop.com/login?source=2)
- 注册：[https://ai.deepsop.com/register?source=2](https://ai.deepsop.com/register?source=2)

## 模型来源

模型名称、描述、状态、顺序和推荐选择必须来自实时接口：

```http
POST /ai/consumeSource/list?pageNum=1&pageSize=999
Content-Type: application/json
X-Api-Key: <api_key>

{"sourceTypeList":["IMAGE_MODEL","VIDEO_MODEL","HUMAN_MODEL"]}
```

规则：

- 只读取 `IMAGE_MODEL`、`VIDEO_MODEL`、`HUMAN_MODEL`。
- 不读取或提交 `IMAGE_PROCESS`。
- 只允许使用 `hiddenState == "0"` 的模型提交任务。
- `sourceValue` 写入提交 payload 的 `methodType`。
- 用户没有指定模型时，先按用户描述匹配接口返回的 `sourceName/sourceDescription/remark/sourceKey`；没有匹配时，取对应类型中第一个 `sourceValue != "auto"` 且可用的模型。
- 回答“用什么模型/哪个模型适合”时，必须先调用 `scripts/generate_image.py "<用户原话>" --recommend-model --json-output`，不能凭本地文档或记忆回答。

## 前端提交链路

对齐 `trade-staff-admin-front/src/views/production/beautifyTool/function.vue`：

```json
{
  "type": "9 | 10 | 12",
  "methodType": "<sourceValue>",
  "parameter": "<JSON string>",
  "saveToDatabase": true
}
```

正式提交前必须先用同一个 payload 调 `/ai/estimate/cost` 预估费用；余额不足或预估失败时不能继续提交 `/ai/AiArtistRecord`。

费用单位是“算力”，不是“元”。对外展示应写成 `费用：{estimatedCost} 算力`。

## type=12 数字人

前端参考：

- `component-digital-human.vue`
- `common/generateParameter.js#validateHumanGeneration`
- `common/restrictions.js` 的 `12` 节点

基础参数：

```json
{
  "req_key": "jimeng_realman_avatar_picture_omni_v15",
  "methodType": "0 | 1",
  "prompt": "",
  "image_url": null,
  "video_url": null,
  "audio_url": null,
  "duration": null,
  "output_resolution": "720",
  "pe_fast_mode": true
}
```

约束：

- `methodType=0`：必须有 `image_url`；可有 `prompt`；`output_resolution` 可为 `720` 或 `1080`。
- `methodType=1`：必须有 `video_url`。
- 两种模式都必须有 `audio_url`。
- `output_resolution=720` 时 `pe_fast_mode=true`；`output_resolution=1080` 时 `pe_fast_mode=false`。
- `methodType=0` 追加素材限制：`targetMaxSize=5`、`targetMaxLength=4096`，`prompt` 最长 300 字。
- `methodType=1` 不追加图片素材限制。

CLI 示例：

```bash
python scripts/generate_image.py --media-type human --model 1 \
  --human-video-url "https://example.com/person.mp4" \
  --human-audio-url "https://example.com/audio.mp3" \
  --human-duration 12.5 \
  --json-output
```

## type=9 视频生成

前端参考：

- `component-generate-video.vue`
- `common/generateParameter.js#validateVideoGeneration`
- `common/generateParameter.js#buildVideoParams`

关键约束：

- 基础字段包括 `methodType`、`text`、`generationType`、`resolution`、`ratio`、`size`、`duration`、`generateAudio`、`shotType`、`mode`。
- 默认值按前端模型切换逻辑生成，不按本地固定模型名生成。
- `methodType=3` 的 V3.1FB 默认 `generationType=REFERENCE`，不是 `TEXT`；参考生成必须提供 `imageUrlList`。如果用户明确要求纯文本生成，才传 `--generation-type TEXT`。
- `methodType=3` 固定 `resolution=720p`、`duration=8`。
- `FIRST&LAST` 必须有 `firstImageUrl`，传 `lastImageUrl` 时也必须有 `firstImageUrl`。
- `REFERENCE` 按对应 methodType 要求传 `imageUrlList`、`videoUrlList` 或 `firstClipUrl`。
- `methodType=10` 的多镜头 `shotType=multi` 提交时转为 `shotType=intelligence`，有 `firstClipUrl` 时构造 `videoList` 并关闭 `generateAudio`。
- 小云雀 `23/24/25/26/27` 暂不接入；即使前端有分支，本技能不要提交这些业务 payload。

CLI 示例：

```bash
python scripts/generate_image.py "让参考图中的人物轻微点头" \
  --model V3.1FB \
  --generation-type REFERENCE \
  --image-url-list "https://example.com/ref.png" \
  --json-output
```

## type=10 图像生成

前端参考：

- `component-generate-image.vue`
- `common/generateParameter.js#validateImageGeneration`
- `common/generateParameter.js#buildImageParams`

关键约束：

- `prompt` 必填。
- 基础字段包括 `methodType`、`prompt`、`image`、`quality`、`size`、`webSearch`、`imageSearch`、`ratiocination`、`n`。
- `methodType=0/4` 的 `size` 提交为 `WxH`。
- `methodType=6/7` 的 `size` 提交为 `W*H`。
- `methodType=10/11` 参考图最多 16 张、单张 50MB，`prompt` 最长 16000 字。
- `methodType=10` 支持 `ratiocination=low|medium|high` 和 `n=1..10`。
- 字段必须按前端显隐白名单过滤，不要把不支持的字段传给后端。

CLI 示例：

```bash
python scripts/generate_image.py "产品宣传图，现代科技风" \
  --media-type image \
  --model 10 \
  --n 4 \
  --ratiocination high \
  --json-output
```

## 输出要求

- 正常生成必须使用 `--json-output`，方便上层读取结果 URL 和费用字段。
- 成功结果包含 `estimatedCost` 和 `costUnit: "算力"`。
- 提交任务后返回 `task_id`；轮询接口返回 `SUCCESS` 后直接把结果 URL 返回给用户。
- 不要在生成成功后自动调用视觉分析工具检查图片或视频，除非用户明确要求分析。

## 错误处理

- `DEEPSOP_API_KEY` 缺失：提示用户授权或配置 API Key。
- 模型不存在或 `hiddenState != "0"`：停止提交，反馈接口真实状态。
- 费用预估失败或余额不足：停止提交，不要创建任务。
- 后端 4xx/5xx：反馈实际状态码和错误信息，不自动切换模型重试。
