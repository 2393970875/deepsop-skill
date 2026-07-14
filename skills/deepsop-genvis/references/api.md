# DeepSOP GenVis API Reference

当前技能只使用三类生成任务：

- `type=9` 视频生成
- `type=10` 图像生成
- `type=12` 数字人生成

暂不接入 `IMAGE_PROCESS` 和小云雀 `23/24/25/26/27` 业务 payload。

## 模型列表

```http
POST /ai/consumeSource/list?pageNum=1&pageSize=999
Content-Type: application/json
X-Api-Key: <api_key>

{"sourceTypeList":["IMAGE_MODEL","VIDEO_MODEL","HUMAN_MODEL"]}
```

使用规则：

- `IMAGE_MODEL` 用于 `type=10`。
- `VIDEO_MODEL` 用于 `type=9`。
- `HUMAN_MODEL` 用于 `type=12`。
- `sourceValue` 作为提交 payload 的 `methodType`。
- 只提交 `hiddenState == "0"` 的模型。

## 费用预估

```http
POST /ai/estimate/cost
Content-Type: application/json
X-Api-Key: <api_key>
```

请求体必须和创建任务 payload 保持一致：

```json
{
  "type": "10",
  "methodType": "10",
  "parameter": "{\"methodType\":\"10\",\"prompt\":\"产品宣传图\",\"image\":[],\"quality\":\"1K\",\"size\":\"1:1\",\"ratiocination\":\"high\",\"n\":1,\"targetMaxSize\":50}",
  "saveToDatabase": true
}
```

成功响应：

```json
{
  "code": 200,
  "msg": "操作成功",
  "data": {
    "estimatedCost": 60,
    "sufficientBalance": true
  }
}
```

`estimatedCost` 单位是算力。余额不足时不能继续提交任务。

## 创建任务

```http
POST /ai/AiArtistRecord
Content-Type: application/json
X-Api-Key: <api_key>
```

统一请求体：

```json
{
  "type": "9",
  "methodType": "3",
  "parameter": "{\"methodType\":\"3\",\"text\":\"让参考图中的人物轻微点头\",\"generationType\":\"REFERENCE\",\"imageUrlList\":[\"https://example.com/ref.png\"],\"resolution\":\"720p\",\"ratio\":\"16:9\",\"duration\":8}",
  "saveToDatabase": true
}
```

成功响应：

```json
{
  "code": 200,
  "msg": "操作成功",
  "data": ["<task_id>"]
}
```

## 数字人参数

`type=12` 的 `parameter` 示例：

```json
{
  "req_key": "jimeng_realman_avatar_picture_omni_v15",
  "methodType": "1",
  "prompt": "",
  "image_url": null,
  "video_url": "https://example.com/person.mp4",
  "audio_url": "https://example.com/audio.mp3",
  "duration": 12.5,
  "output_resolution": "720",
  "pe_fast_mode": true
}
```

约束：

- `methodType=0` 必填 `image_url`，并追加 `targetMaxSize=5`、`targetMaxLength=4096`。
- `methodType=1` 必填 `video_url`。
- 两种模式都必填 `audio_url`。
- `output_resolution=720` 对应 `pe_fast_mode=true`；`1080` 对应 `false`。

## 查询任务

```http
GET /ai/AiArtistImage/getInfoByArtistId/<task_id>
X-Api-Key: <api_key>
```

常见状态：

| status | 含义 |
| --- | --- |
| `PENDING` | 等待中 |
| `RUNNING` / `GENERATING` | 生成中 |
| `SUCCESS` | 生成成功 |
| `FAILED` | 生成失败 |
