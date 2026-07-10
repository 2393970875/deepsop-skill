# AI Artist API 详细文档

## API 端点

### 1. 预估生成费用

**POST** `/ai/estimate/cost`

**请求头:**
```
Content-Type: application/json
X-Api-Key: <api_key>
```

**请求体:**
```json
{
  "type": "10",
  "methodType": "4",
  "parameter": "{...}"
}
```

说明：请求体与创建生成任务时使用的参数完全一致，需要在正式创建任务前先调用本接口。

**成功响应:**
```json
{
  "msg": "操作成功",
  "code": 200,
  "data": {
    "estimatedCost": 3.500000,
    "sufficientBalance": true
  }
}
```

说明：`estimatedCost` 的单位是算力，不是人民币；详情展示应写为 `{estimatedCost} 算力`。如果需要人民币估算，按 `1元 = 10算力` 另行换算并明确标注，不能把算力数值直接显示为“元”。

当 `sufficientBalance` 为 `false` 时，表示余额不足，不应继续提交创建任务，需要提醒用户先充值 算力。

### 2. 创建生成任务

**POST** `/ai/AiArtistRecord`

**请求头:**
```
Content-Type: application/json
X-Api-Key: <api_key>
```

**请求体:**
```json
{
  "type": "10",
  "methodType": "4",
  "parameter": "{...}"
}
```

**模型列表来源：**

`POST /ai/consumeSource/list?pageNum=1&pageSize=999`

Body 示例：
```json
{
  "sourceTypeList": ["IMAGE_MODEL", "VIDEO_MODEL", "HUMAN_MODEL"]
}
```

规则：
- 图片模型使用接口返回的图片类型模型，提交任务时 `type="10"`。
- 视频模型使用接口返回的视频类型模型，提交任务时 `type="9"`。
- 模型名称、可用状态、排序和运行时默认选中值都以接口返回为准；本文不维护可对用户展示的模型清单。
- 未指定模型时，先按用户 prompt 匹配接口返回的 `sourceName/sourceDescription/remark/sourceKey`；没有匹配项时，取对应类型中 `sourceValue != "auto"` 且 `hiddenState == "0"` 的返回顺序第一项作为本次运行的选中值，不把它声明为固定默认模型。
- 选中模型后，把接口返回的 `sourceValue` 作为 `methodType`，再按本技能本地 methodType 规则组装参数；methodType 规则仅用于参数生成/校验。
- 查询模型列表或状态只用于回答用户的信息请求，不代表可以自动创建生成任务；只有用户明确要求生成/提交时才进入费用预估和创建任务。

**parameter 字段说明（图片）:**

| 字段 | 类型 | 说明 |
|------|------|------|
| `methodType` | string | API `sourceValue`，仅用于触发本地 methodType 参数生成/校验规则 |
| `prompt` | string | 图片生成提示词 |
| `image` | array | 参考图片（可选） |
| `quality` | string | 图片质量，按 methodType 白名单提交 |
| `size` | string | 尺寸/比例，部分 methodType 会转换成 `WxH` 或 `W*H` |
| `webSearch` | boolean | 联网搜索，仅 methodType `4/8` |
| `imageSearch` | boolean | 图像搜索，仅 methodType `8` |
| `ratiocination` | string | 渲染质量预设，仅 methodType `10`：`low` / `medium` / `high` |
| `n` | number | 生成数量，仅 methodType `10`，范围 `1-10` |
| `targetMaxSize` | number | 目标最大尺寸（MB）|
| `targetMaxLength` | number | 目标最大长度（像素）|
| `duration` | number | 持续时间；图片侧仅 methodType `4` 会额外提交 `duration=10` |

**成功响应:**
```json
{
  "msg": "操作成功",
  "code": 200,
  "data": ["<task_id>"]
}
```

**失败响应:**
```json
{
  "msg": "错误信息",
  "code": 400,
  "data": null
}
```

### 3. 查询任务状态

**GET** `/ai/AiArtistImage/getInfoByArtistId/{artistId}`

**成功响应:**
```json
{
  "msg": "操作成功",
  "code": 200,
  "data": {
    "message": "生成成功",
    "url": "https://...",
    "status": "SUCCESS"
  }
}
```

**状态值说明:**

| 状态 | 含义 |
|------|------|
| `PENDING` | 等待中 |
| `RUNNING` / `GENERATING` | 生成中 |
| `SUCCESS` | 生成成功 |
| `FAILED` | 生成失败 |

## 错误码

| Code | 含义 |
|------|------|
| 200 | 成功 |
| 400 | 请求参数错误 |
| 401 | 未授权（token无效） |
| 429 | 请求过于频繁 |
| 500 | 服务器内部错误 |

## 完整请求示例

```bash
# 使用图片 methodType=4 创建图片任务
curl -X POST "https://ai.deepsop.com/prod-api/ai/AiArtistRecord" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: <api_key>" \
  -d '{
    "type": "10",
    "methodType": "4",
    "parameter": "{\"methodType\":\"4\",\"prompt\":\"风景画\",\"image\":[],\"quality\":\"2K\",\"size\":\"2048x2048\",\"webSearch\":false,\"targetMaxSize\":10,\"targetMaxLength\":6000,\"duration\":10}"
  }'

# 使用图片 methodType=2 创建图片任务
curl -X POST "https://ai.deepsop.com/prod-api/ai/AiArtistRecord" \
  -H "Content-Type: application/json" \
  -H "X-Api-Key: <api_key>" \
  -d '{
    "type": "10",
    "methodType": "2",
    "parameter": "{\"methodType\":\"2\",\"prompt\":\"生成一只狗\",\"image\":[],\"quality\":\"2K\",\"size\":\"1:1\",\"webSearch\":false,\"targetMaxSize\":10,\"targetMaxLength\":6000}"
  }'

# 查询状态
curl -X GET "https://ai.deepsop.com/prod-api/ai/AiArtistImage/getInfoByArtistId/<task_id>" \
  -H "X-Api-Key: <api_key>"
```
