# DeepSOP GenVis

基于 AI Artist API 的图片/视频异步生成技能。

本技能不维护模型名称清单，也不维护本地默认模型。模型列表、模型名称、展示顺序和默认模型都从 `consumeSource/list` 获取：

- 图片：取接口中图片类型、`sourceValue != "auto"`、`hiddenState == "0"` 的返回顺序第一个作为默认图片模型。
- 视频：取接口中视频类型、`sourceValue != "auto"`、`hiddenState == "0"` 的返回顺序第一个作为默认视频模型。
- 用户选中模型后，用接口返回的 `sourceValue` 作为 `methodType`，触发本地参数规则。

## API Key

在 OPClaw 项目中运行时，技能直接读取项目设置里的 `DEEPSOP_API_KEY`。非 OPClaw 运行时，请用户授权后设置共享 Key，其他 DeepSOP 技能也能复用。

读取不到 Key 时，引导用户登录/注册并新建 API Key：

- 已有账号 → [https://ai.deepsop.com/login?source=2](https://ai.deepsop.com/login?source=2)
- 没有账号 → [https://ai.deepsop.com/register?source=2](https://ai.deepsop.com/register?source=2)

配置示例：

```powershell
[System.Environment]::SetEnvironmentVariable('DEEPSOP_API_KEY', 'sk-your_api_key_here', 'User')
```

也兼容写入 `~/.openclaw/.env`：

```ini
DEEPSOP_API_KEY=sk-your_api_key_here
```

## 快速命令

```bash
# 查看服务端当前启用模型
python3 scripts/generate_image.py --list-models

# 不指定模型时，由接口顺序选择默认图片/视频模型
python3 scripts/generate_image.py "一只可爱的猫"
python3 scripts/generate_image.py "生成一段城市夜景延时视频"

# 指定 methodType/sourceValue
python3 scripts/generate_image.py "产品宣传图" --model 10 --n 4 --ratiocination high
python3 scripts/generate_image.py "城市夜景延时" --model 20 --ratio "16:9" --resolution "1080p" --duration 10
```

## 本地维护什么

- `methodType` 对应的参数默认值。
- 每个 `methodType` 支持哪些参数、参数选项、隐藏字段、必填校验。
- 本地图片/视频/音频素材能上传什么格式，上传后写入哪个 payload 参数。
- 创建任务前的费用预估、余额不足拦截、任务轮询。

模型有哪些、模型名叫什么、默认用哪个模型，都以接口为准。

完整规则见 [SKILL.md](SKILL.md)，API 请求格式见 [references/api.md](references/api.md)。
