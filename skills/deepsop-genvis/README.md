# DeepSOP GenVis

基于 AI Artist API 的图片/视频异步生成技能。

本技能不维护、声明或向用户展示模型名称清单、可用模型清单、展示顺序或本地默认模型。模型列表和运行时默认选中值都从 `consumeSource/list` 获取：

- 图片：未指定模型时，取接口中图片类型、`sourceValue != "auto"`、`hiddenState == "0"` 的返回顺序第一项作为本次运行的选中值。
- 视频：未指定模型时，取接口中视频类型、`sourceValue != "auto"`、`hiddenState == "0"` 的返回顺序第一项作为本次运行的选中值。
- 用户选中模型后，用接口返回的 `sourceValue` 作为 `methodType`，触发本地参数规则；这些规则不等同于模型清单。

## API Key

在 OPClaw 项目中运行时，技能直接读取项目设置里的 `DEEPSOP_API_KEY`。非 OPClaw 运行时，请用户授权后设置共享 Key，其他 DeepSOP 技能也能复用。

读取不到 Key 时，引导用户登录/注册并新建 API Key：

- 已有账号 → [https://ai.deepsop.com/login?source=2](https://ai.deepsop.com/login?source=2)
- 没有账号 → [https://ai.deepsop.com/register?source=2](https://ai.deepsop.com/register?source=2)

配置示例：

```powershell
[System.Environment]::SetEnvironmentVariable('DEEPSOP_API_KEY', 'sk-your_api_key_here', 'User')
```

也兼容写入 `~/.openclaw/openclaw.json`：

```ini
DEEPSOP_API_KEY=sk-your_api_key_here
```

## 快速命令

```bash
# 内部调试：读取服务端当前返回的模型列表
python3 scripts/generate_image.py --list-models

# 不指定模型时，由接口返回值决定本次实际使用的 sourceValue
python3 scripts/generate_image.py "一只可爱的猫"
python3 scripts/generate_image.py "生成一段城市夜景延时视频"

# 指定接口返回的 sourceValue/methodType
python3 scripts/generate_image.py "产品宣传图" --model 10 --n 4 --ratiocination high
python3 scripts/generate_image.py "城市夜景延时" --model 20 --ratio "16:9" --resolution "1080p" --duration 10
```

## 本地维护什么

- `methodType` 对应的参数默认值。
- 每个 `methodType` 支持哪些参数、参数选项、隐藏字段、必填校验。
- 本地图片/视频/音频素材能上传什么格式，上传后写入哪个 payload 参数。
- 创建任务前的费用预估、余额不足拦截、任务轮询。

模型有哪些、模型名叫什么、本次默认选中哪个值，都只以接口为准；不要用本文档里的 methodType 规则向用户枚举模型或承诺默认模型。
用户只查询模型列表、停用状态、参数、分辨率、时长或素材规则时，只返回信息；不要因为查询结果显示某个模型可用而自动继续或重新发起生成任务。

完整规则见 [SKILL.md](SKILL.md)，API 请求格式见 [references/api.md](references/api.md)。
