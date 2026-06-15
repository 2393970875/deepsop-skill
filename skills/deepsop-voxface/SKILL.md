---
name: deepsop-voxface
description: 数字人生成与参考音频技能。用于调用 deepsop / AI Artist 相关接口创建数字人视频任务，按前端现有规则读取 HUMAN_MODEL 模型列表，校验人像图片/人像视频/参考音频/渲染质量等参数，并在创建任务前先调用 `/ai/estimate/cost` 预估费用与余额；同时支持“预设音色 + 文字”或“克隆音色 + 文字”单独生成参考音频，并支持查询/创建/修改/删除音色。触发场景：用户说“创建数字人”“生成数字人视频”“做一个数字人讲解”“上传人像图片/视频/音频生成视频”“先帮我预估一下费用”“音色合成”“用预设音色生成一段音频”“克隆这个声音”“创建我的音色”“查询音色列表”等与数字人或音频合成相关的指令。调用本 SKILL 前必须先完整阅读 SKILL.md。凡是后端提交接口、轮询接口、脚本名或参数映射未在本文明确写出的，不得自行猜测，必须先向用户确认或回到前端代码补证据。
---

# DeepSOP VoxFace

数字人生成技能，面向“人像图片/人像视频 + 参考音频 + 数字人模型 + 生成提示词/渲染质量”的任务流。

## 已确认的前端行为

- 模型列表来自现有前端接口返回值，按 `sourceTypeList: ['IMAGE_PROCESS', 'IMAGE_MODEL', 'VIDEO_MODEL', 'HUMAN_MODEL']` 取数。
- 数字人可用模型只使用 `HUMAN_MODEL` 分类；展示时过滤 `hiddenState !== '0'` 的项。
- 用户选择模型后，前端只依据该模型的 `sourceValue` / `methodType` 触发本地参数规则。
- 提交生成前会先做费用预估，调用 `/ai/estimate/cost`。
- 默认表单里的 `req_key` 是 `jimeng_realman_avatar_picture_omni_v15`。
- 数字人创建任务通过 `/ai/AiArtistRecord` 提交。
- 数字人任务结果轮询与 `deepsop-genvis` 保持同一套逻辑和接口。
- 参考音频既可以由预设音色合成，也可以由克隆音色合成。

## 前置条件：DEEPSOP_API_KEY

本技能需要 `DEEPSOP_API_KEY` 才能调用 DeepSOP / AI Artist 接口。

- OPClaw 项目运行时直接读取项目设置里的 `DEEPSOP_API_KEY`。
- 非 OPClaw 运行时，先引导用户授权，再把 `DEEPSOP_API_KEY` 配到共享环境变量或 `~/.openclaw/openclaw.json`。
- 读取不到 Key 时，引导用户登录/注册并新建 API Key。

## 脚本入口

统一使用 `scripts/voxface.py`，它负责：

- `--list-models`
- `--estimate`
- `--create`
- `--submit-only`
- `--poll TASK_ID`
- `--list-preset-voices`
- `--list-clone-voices`
- `--synthesize-preset`
- `--synthesize-clone`
- `--create-voice`
- `--update-voice`
- `--delete-voice`

生成数字人时，可以直接使用以下组合：

- 图片 + 音频 + 文字
- 视频 + 音频 + 文字
- 预设音色 + 文字 -> 先合成参考音频，再进入数字人生成
- 克隆音色 + 文字 -> 先合成参考音频，再进入数字人生成

`deepsop-synth-clone` 的查询音色、创建音色、克隆音色合成能力已经并入本技能；新的音色相关调用优先使用 `deepsop-voxface/scripts/voxface.py`。

## 生成流程

1. 先确认用户要的是数字人任务，而不是普通图片/视频生成。
2. 读取数字人模型列表，优先使用 `HUMAN_MODEL`。
3. 根据所选模型校验参数可见性。
4. 在提交前调用 `/ai/estimate/cost` 预估费用。
5. 余额不足时立即拦截，不进入创建任务。
6. 余额充足时再进入实际提交。
7. 任务提交后按项目现有轮询逻辑查询结果并返回。

## 模型列表

### 已确认来源

前端获取模型时调用模型来源列表接口，查询范围包含：

```json
{
  "sourceTypeList": [
    "IMAGE_PROCESS",
    "IMAGE_MODEL",
    "VIDEO_MODEL",
    "HUMAN_MODEL"
  ]
}
```

拿到 `rows` 后按 `sourceType` 拆分：

- `IMAGE_PROCESS` -> `sys_tool_function`
- `IMAGE_MODEL` -> `sys_generate_image_model`
- `VIDEO_MODEL` -> `sys_generate_video_model`
- `HUMAN_MODEL` -> `sys_generate_human_model`

数字人只使用 `sys_generate_human_model`，并过滤 `hiddenState === '0'`。

### 默认模型

当前 Vue 片段中，`humanModelOptions` 变化后直接把第一项的 `sourceValue` 写入 `form.methodType`。

```js
this.form.methodType = newVal && newVal[0]?.sourceValue || ''
```

因此不要在技能里写死模型名、模型 ID 或默认模型；默认值以服务端返回顺序为准。

## 已确认的数字人参数规则

- `methodType`：数字人模型标识，来自接口返回的 `sourceValue`。
- `req_key`：默认 `jimeng_realman_avatar_picture_omni_v15`。
- `prompt`：生成视频提示词，非必填。
- `image_url`：人像图片，仅部分模型需要。
- `video_url`：人像视频，仅部分模型需要。
- `audio_url`：参考音频，必填。
- `duration`：参考音频时长，上传/选择参考音频后由前端素材信息写入。
- `output_resolution`：渲染质量，当前前端选项值是 `720` / `1080`，展示文案是 `720p` / `1080p`。
- `pe_fast_mode`：前端根据 `output_resolution === '720'` 自动切换；720 为 `true`，1080 为 `false`。

## 前端已确认的显隐规则

- `methodType === '0'`：OmniHuman1.5，显示 `prompt`、`image_url`、`output_resolution`。
- `methodType === '1'`：HeyGem，显示 `video_url`。
- 其他字段按前端现有规则默认处理，不要自行扩展。

## 完整 methodType 白名单

数字人当前完整可用模型只有以下两个 `methodType`：

| methodType | 模型 | 必填素材 | 可见字段 |
| --- | --- | --- | --- |
| `0` | OmniHuman1.5 | `image_url`、`audio_url` | `prompt`、`image_url`、`audio_url`、`output_resolution` |
| `1` | HeyGem | `video_url`、`audio_url` | `video_url`、`audio_url` |

不要接受或编造 `2`、`3` 等其他数字人 `methodType`。如果服务端未来返回新值，需要先补充前端规则和本技能文档后再使用。

## 前端已确认的默认值与重置

初始表单：

```json
{
  "req_key": "jimeng_realman_avatar_picture_omni_v15",
  "methodType": null,
  "prompt": "",
  "image_url": null,
  "video_url": null,
  "audio_url": null,
  "duration": null,
  "output_resolution": "720",
  "pe_fast_mode": true
}
```

切换模型时，前端会重置：

- `prompt` -> `''`
- `image_url` -> `null`
- `video_url` -> `null`
- `output_resolution` -> `'720'`
- `pe_fast_mode` -> `true`

注意：切换模型不会清空 `audio_url`，但如果用户清除参考音频，`duration` 会被置为 `null`。

## 生成前校验

必须按前端规则校验：

- `methodType === '0'` 且缺少 `image_url`：停止，提示用户上传人像图片。
- `methodType === '1'` 且缺少 `video_url`：停止，提示用户上传人像视频。
- 缺少 `audio_url`：停止，提示用户上传参考音频。

`prompt` 非必填，不要因为用户没有填写提示词而阻塞。

## 上传限制

### 数字人 - 人像图片

`uploadImageRestrictions['12']['0']`

- `accept`: `.jpeg,.jpg,.png`
- `textLength`: `300`
- `maxSize`: `5`
- `maxLength`: `4096`
- `uploadTips`: 支持 JPEG/JPG/PNG，5M 以内，最长边不大于 4096 像素

### 数字人 - 参考音频

`uploadAudioRestrictions['12']['0']`

- `accept`: `.mp3,.wav,.flac,.aac,.ogg,.wma`
- `maxLength`: `35`
- `uploadTips`: 支持 MP3/WAV/FLAC/AAC/OGG/WMA，15 秒内效果较好，不能超过 35 秒

`uploadAudioRestrictions['12']['1']`

- `accept`: `.mp3,.wav,.flac,.aac,.ogg`
- `uploadTips`: 支持 MP3/WAV/FLAC/AAC/OGG，15 秒内效果较好

### 数字人 - 人像视频

`uploadVideoRestrictions['12']['1']`

- `accept`: `.mp4,.avi,.mov`
- `uploadTips`: 支持 MP4/AVI/MOV，50M 以内

### 前端用途

这些限制会在上传前传给素材选择器，生成时再由 `buildHumanParams()` 合并进提交参数。

## 预估费用

### 接口

`POST /ai/estimate/cost`

### 请求体

前端当前送入的结构是：

```json
{
  "type": "12",
  "methodType": "0",
  "parameter": "{...}"
}
```

说明：

- `type` 对应数字人模块类型。
- `methodType` 对应当前选中的数字人模型。
- `parameter` 需要传当前表单的完整参数序列化结果。
- `parameter` 里应包含本次表单的 `req_key`、`methodType`、素材 URL、`duration`、`output_resolution`、`pe_fast_mode` 等字段。

### 预估结果

- `estimatedCost`：预估费用。
- `sufficientBalance`：余额是否充足。

余额不足时，必须停止后续提交。

### 触发预估的时机

前端已确认这些动作会重新预估：

- 切换数字人模型。
- 上传/选择参考音频并写入 `duration`。
- 点击生成前使用当前参数做最终预估。

如果脚本化实现本技能，也必须在创建任务前至少做一次最新参数的费用预估。

## 数字人任务提交

### 接口

`POST /ai/AiArtistRecord`

### 请求体

前端当前使用的提交包裹层是：

```json
{
  "type": "12",
  "methodType": "0",
  "parameter": "{...}"
}
```

说明：

- `type`：数字人模块类型，当前前端数字人页使用 `12`。
- `methodType`：当前选中的数字人模型。
- `parameter`：`submitData` 的完整 JSON 字符串。

### 生成前额外校验

如果当前数字人任务的模型类型需要背景引导，先检查：

- `ref_image_url`
- `ref_prompt`

二者至少要有一个值，否则直接阻塞并提示用户补齐参考背景或引导文本。

### 结果轮询

轮询接口与 `deepsop-genvis` 相同：

- `GET /ai/AiArtistImage/getInfoByArtistId/{artistId}`

状态含义：

- `PENDING`：等待中
- `RUNNING` / `GENERATING`：生成中
- `SUCCESS`：生成成功
- `FAILED`：生成失败

调用时把任务 ID 代入 `{artistId}`，成功后返回结果 URL，失败或超时则按 `genvis` 的现有处理继续反馈给用户。

### 命令式两段调用

本技能允许像 `deepsop-genvis` 一样支持两段式调用：

- `submit-only`：只提交数字人任务，拿到 `task_id` 后立即返回，不阻塞等待生成完成。
- `poll`：只根据已有 `task_id` 调用 `/ai/AiArtistImage/getInfoByArtistId/{artistId}` 查询结果，不重新提交任务。

实现脚本时必须保证 `poll` 不会再次调用 `/ai/AiArtistRecord`，避免重复创建任务。

## 参考音频生成

当用户只想要“参考音频”时，可以单独走这条支路，不必先创建数字人任务。

### 入口

- `GET /ai/model/pageByFeatureAndLanguage?pageNum=1&pageSize=999`：查询预设音色。
- `GET /ai/voice/clone/list?pageNum=1&pageSize=999`：查询克隆音色。

### 预设音色 + 文字

流程：

1. 从 `pageByFeatureAndLanguage` 取预设音色。
2. 选择一个音色。
3. 校验文本 `text` 非空，且长度不超过前端上限 `145`。
4. 调用 `POST /ai/voiceGenerate/newcreate`。
5. 若返回的首段结果为空，提示用户当前文本与音色语言不匹配。
6. 再把返回的 `ossUrlList` / `srtUrlList` 传给 `POST /ai/voiceGenerate/save`。
7. 最终取返回数据中的第一条音频作为可插入结果。

`generateVoice` 的关键参数：

```json
{
  "model": "<音色模型>",
  "texts": ["<文本>"],
  "volume": 50,
  "rate": 1.0,
  "pitch": 1.0
}
```

### 克隆音色 + 文字

流程：

1. 先从 `voice/clone/list` 查询克隆音色。
2. 选择一个克隆音色。
3. 校验文本 `text` 非空。
4. 调用 `POST /ai/voice/clone/synthesize`。
5. 成功后直接把返回的音频地址作为参考音频结果。

### 创建克隆音色

接口：

- `POST /ai/voice/clone/sync/create`
- `PUT /ai/voice/clone/update`
- `DELETE /ai/voice/clone/{id}`

创建克隆音色时，上传音频素材必须满足前端校验：

- 格式：`wav` / `mp3` / `m4a`
- 采样率：`16KHz` 及以上
- 时长：至少 `10` 秒
- 文件大小：小于 `10MB`

### 单独调用说明

音色相关能力可以独立触发，用户不需要先说“数字人”：

- “查询音色”
- “创建音色”
- “修改音色名称”
- “删除音色”
- “用预设音色合成一句话”
- “用克隆音色合成一句话”

其中 `预设音色 + 文字` 和 `克隆音色 + 文字` 都可以单独作为音频合成任务使用，不必先进入数字人生成流程；只有当用户明确要“生成数字人视频”时，才把合成出来的音频继续接到数字人任务里。
