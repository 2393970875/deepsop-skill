---
name: human-ai-collab
description: 人机协作台技能。用户输入自然语言销售指令，AI自动分析拆解任务参数，调用 deepsop 平台接口提交任务，等待后查询结果并推送。触发场景：用户说「帮我找客户」「挖掘XXX行业客户」「找XXX个客户」「提交任务」等与客户挖掘、销售任务相关的指令；「发TikTok视频」「生成视频发布到TikTok」等TikTok视频发布指令；或收到包含 [DeepSOP-AutoQuery] 标记的系统定时事件（cron 回调，用于自动查询并推送任务结果）。需要提前配置环境变量 DEEPSOP_API_KEY。⚠️ 调用本 SKILL 前必须先完整阅读 SKILL.md。提交 agentSubmitTask **必须**走 scripts/submit_task.py（通过 heredoc 把 body 喂给 stdin），脚本内部串行跑 validate_employee_params.py + validate_sms_template_params.py + UTF-8 安全 HTTP 提交，**禁止**直接写 curl 命令（会因 Windows cp936 代码页导致 taskName/taskDescription 中文乱码）。脚本退出码 0 才算成功；非 0 必须把 summary/errors 原样回给用户后修正重试，禁止绕过校验或假装成功。
---

# 人机协作台（Human-AI Collaboration）

## 功能简介

人机协作台是基于 deepsop 平台的智能销售任务助手，能够：

- **理解自然语言指令**：直接描述需求，如「帮我找50个美国做服装的客户」
- **智能任务拆解**：自动识别目标数量、行业、地区、执行周期等参数
- **多员工协作**：根据任务类型自动分配对应职能员工
  - **AiWa**：客户挖掘（找客户、行业客户等）
  - **Frank**：邮件销售
  - **Fran**：电话销售
  - **Lisa**：短信销售
  - **Toby**：AI 视频生成并发布到 TikTok
- **自动提交任务**：调用 deepsop API 提交任务，后台异步执行
- **定时查询结果**：任务提交后询问用户期望等待时长，按用户指定时间自动查询并推送结果（默认 8 分钟）
- **生成 xlsx 报表**：AiWa 客户数据自动生成带样式的 Excel 文件返回
- **Frank 邮件统计**：查询邮件发送总数、成功数、已读数、回复数、点击数，并展示发送详情
- **Fran 电话销售**：自动查询号码池与场景库，由用户选择后提交电话销售任务（必须与 AiWa 搭配使用）
- **Lisa 短信统计**：查询短信发送总数、成功数、失败数，并展示发送详情（必须与 AiWa 搭配使用）
- **Toby TikTok 发布统计**：查询视频发布数、播放量、点赞、评论、分享等数据，并展示每条视频明细和 TikTok 链接

---

## 前置条件：获取 API Key

1. 访问 [https://ai.deepsop.com](https://ai.deepsop.com) 注册并登录账号
2. 登录后进入「设置」或「API 管理」页面
3. 新建 API Key，复制以 `sk-` 开头的密钥
4. 在 OpenClaw 中配置环境变量：

```
DEEPSOP_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxx
```

> 所有 API 请求头需携带：`x-api-key: $DEEPSOP_API_KEY`
> API Base URL：`https://ai.deepsop.com/prod-api/`

---

## 完整执行流程

### Step 0：触发类型判断（每次进入技能必须首先执行）

检查当前输入内容是否包含 `[DeepSOP-AutoQuery]` 标记：

- **包含该标记**：这是 cron 定时回调。**不得询问用户是否继续，不得等待确认，不得说「我将开始查询」。立即从输入文本中解析变量（`taskId`、`aiwaDagTaskId`、`aiwaCustomerPoolId`、`frankDagTaskId`、`franDagTaskId`、`franCustomerPoolId`、`lisaDagTaskId`、`lisaCustomerPoolId`、`tobyDagTaskId`、`tobyCustomerPoolId`、`taskName`、`totalTarget`、`employeeList`、`feishuChatId`），跳过 Step 1～4 直接执行 Step 5 的全部内容（查询接口 → 生成 xlsx → 发送文件 → 回复文字摘要），直到所有参与员工的结果都处理完毕。
- **不包含该标记**：这是用户主动指令，继续执行 Step 1。

---

### Step 1：第一轮 AI 分析（任务拆解）

用以下 prompt 分析用户指令，严格返回 JSON，不含任何额外文字：

```
根据【指令】描述，Json格式返回数据
不需要多余的描述，不要过度解读，没有提及的内容请不要擅自理解，识别结果除了Json数据其他文字不要出现
规则如下：{
  "taskName": "根据描述总结出一个简洁的任务名称"
  "executionMode": "判断描述中是否明确提及每日/每天/周期性，如果提及则返回周期性任务，未提及则返回定额任务"
  "totalTarget": "提取描述中提及的数量（无单位纯数字）"
  "employeeList": "首先将描述按逗号、顿号等分隔符拆分成多个子任务，然后为每个子任务匹配对应员工：
    - 挖掘客户职能（AiWa）：匹配任何包含“找”、“开发”、“行业”、“客户”等与客户挖掘相关的描述，以及没有明确匹配其他职能的单子任务
    - 邮件销售职能（Frank）：匹配包含“邮件”、“发邮件”等关键词的描述
    - 电话销售职能（Fran）：匹配包含“电话”、“打电话”、“电话销售”等关键词的描述
    - 短信销售职能（Lisa）：匹配包含“短信”、“发短信”等关键词的描述
    - TikTok职能（Toby）：匹配包含“TikTok”、“抖音国际版”等关键词的描述
    - 生产视频职能（Jack）：匹配包含“视频”、“生产视频”等关键词的描述
    - 智能SEO优化职能（Sophia）：匹配包含“SEO”、“优化”、“搜索引擎”等关键词的描述
    - AI剪辑师职能（Alex）：匹配包含“剪辑”、“视频剪辑”等关键词的描述
    - 独立站客服职能（Leo）：匹配包含“客服”、“客户服务”、“咨询”等关键词的描述
    如果拆分后只有一个子任务且没有匹配上员工，则默认匹配挖掘客户职能（AiWa）
    最后汇总所有匹配到的员工名称组成一个,拼接的字符串并返回（去重）",
  "language": "判断描述中是否明确提及国家或地区，若提及了国家或地区但和中国没有关联则返回'英文'其他情况返回'中文'",
  "tiktokContent": "根据描述总结出一个TikTok内容发布的内容主题"
}
```

解析结果字段（**注意：这些只是 SKILL 内部用的解析变量，不要原样塞到最终 API 请求体里**）：
- `totalTarget`：目标数量（数字）— 仅作为 `employeeParams.AiWa.totalTarget` 或 `employeeParams.Toby.totalTarget` 的值来源，**不得**作为根级字段
- `employeeList`：参与员工逗号字符串，如 `"AiWa"` 或 `"AiWa,Frank"` — **仅本 SKILL 内部用于决定要构造哪些 `employeeParams.{Name}` 子对象，绝不允许出现在最终请求体的任何层级**
- `language`：`"中文"` 或 `"英文"` — **仅作为 `employeeParams.Frank.language` 的值，不得挂到根级或其他员工子对象**
- `taskName`：任务名称（→ `collaborationSubmitTaskParam.taskName`）
- `executionMode`：中文字符串 `"定额任务"` 或 `"周期性任务"` — **这是 LLM 返回的内部变量，提交请求体时必须转换为数字**：
  - 后端枚举：`"周期性任务" = 0`，`"定额任务" = 1`
  - 🔒 **当前阶段强制规则：无论 LLM 识别结果是定额还是周期性，提交请求体时 `executionMode` 一律硬编码为数字 `1`（即按定额任务下达）**。
  - **绝不允许**把中文字符串直接塞进请求体（如 `"executionMode": "定额任务"`），会被后端 schema 校验拒绝；也不得写成 `"1"`（带引号字符串）、`true`、`null`。
- `tiktokContent`：任务描述中涉及 TikTok 发布的内容主题（仅作为 `employeeParams.Toby.content` 与 `employeeParams.Toby.param.text` 的值来源，**不得**作为独立字段出现在请求体中）

**员工组合校验：**

1. **不支持的员工拦截**：当 `employeeList` 包含 `Jack`、`Leo`、`Sophia`、`Alex` 中的任意一个时，**终止任务**，回复：
   > ⚠️ 数字员工「{员工名}」尚未接入人机协作台，当前支持的员工为：AiWa、Frank、Fran、Lisa、Toby。请调整指令后重试。

2. **销售员工必须搭配 AiWa**：当 `employeeList` 包含 `Frank`、`Fran`、`Lisa` 中的任意一个或多个，但**不包含** `AiWa` 时，**禁止**继续下任务，直接回复用户（`{缺失员工}` 替换为实际缺失的员工名称列表，如 `Frank`、`Frank、Fran`）：
   > ⚠️ {缺失员工}（邮件/电话/短信销售）必须与 AiWa（客户挖掘）一起使用，无法单独执行销售动作。请在指令中补充客户挖掘需求，例如「帮我找50个美国做服装的客户并发邮件/打电话/发短信」。

   并终止当前流程，等待用户补充指令后重新从 Step 1 开始。

3. **Toby 可独立执行**：Toby（TikTok 视频发布）不依赖 AiWa 客户池，可以单独执行或与其他员工组合使用。

> 说明：Frank（邮件）、Fran（电话）、Lisa（短信）均属于“销售动作”员工，必须依赖 AiWa 产出的客户池，因此不能脱离 AiWa 单独下任务。Toby 不受此限制。

---

### Step 1.5：数字员工可用性校验（Step 1 完成后立即执行，所有任务均须）

**接口：** `GET https://ai.deepsop.com/prod-api/ai/presetEmployee/list`

**请求头：** `x-api-key: $DEEPSOP_API_KEY`

响应 `data` 数组中每条记录关键字段：
- `name`：员工名称（与 employeeList 中的名称对应，如 `AiWa`、`Frank`、`Fran`、`Lisa`、`Toby`）
- `status`：启用状态，`0` = 启用，`1` = 禁用
- `remainingDays`：剩余可用天数（可为 null）

**逐一检查 employeeList 中每个员工，规则如下：**

1. **禁用状态（status = 1）→ 终止任务**，回复：
   > ⚠️ 数字员工「{name}」当前处于禁用状态，无法执行任务。请联系管理员启用后再试。

2. **剩余天数耗尽（status = 0 且 remainingDays ≤ 0）→ 警告并终止任务**，回复：
   > ⚠️ 数字员工「{name}」的使用天数已耗尽（剩余 {remainingDays} 天），请前往 https://ai.deepsop.com 购买/续费后再执行任务。

3. **剩余天数不足（status = 0 且 remainingDays > 0 且 remainingDays ≤ 7）→ 提醒用户，但允许继续**：
   > ⚡ 提示：数字员工「{name}」剩余可用天数仅剩 **{remainingDays} 天**，建议尽快前往 https://ai.deepsop.com 续费，以免中断服务。

4. **正常（status = 0 且 remainingDays > 7 或 remainingDays 为 null）→ 继续流程**

**所有员工均通过校验后，方可继续后续步骤。任一员工触发规则 1 或规则 2 立即停止，不得继续下任务。**

---

### Step 2：第二轮 AI 分析（仅当 employeeList 包含 AiWa）

用以下 prompt 对同一用户指令做第二轮分析，严格返回 JSON：

```
根据【指令】描述，Json格式返回数据，其中数值部分用字符串输出
涉及数值规则仅处理描述中明确出现的数字和比较词，最小值规则为 'X以上'=X，'X以下'=空，'X左右'=X; 最大值规则为 'X以上'=空，'X以下'=X，'X左右'=X;
涉及七大洲和国家，如果提及了详细某些国家，七大洲则不用去识别，如果没提及国家则去识别有没有提及七大洲
涉及地址，如果是中国地址的则原文放入，如果是非中国的地址则以英文放入
不需要多余的描述，不要过度解读，没有提及的内容请不要擅自理解，识别结果除了Json数据其他文字不要出现
规则如下：{
  "keywordList": "首先识别描述中与客户挖掘相关的部分（匹配‘找’、‘开发’、‘挖掘’、‘拓展’、‘寻找’等关键词），仅从该部分提取核心名词作为关键词；若描述中无客户挖掘相关内容，则识别整个描述来提取核心名词作为关键词。提取核心名词后，排除地理位置相关的关键词（如省、市、区、县、镇、国家、大洲名称），然后添加这些关键词相关的中文同义词和英文对应词，最终返回关键词用英文逗号分隔的结果（如：眼镜店,optical shop,眼镜零售,eyewear store）",
  "continent": "明确提及的七大洲（如：亚洲）",
  "country": "明确提及的国家，多个用英文逗号分隔（如：中国,英国）",
  "countryCodeList": "对应国家的ISO代码，多个用英文逗号分隔（如：CN,GB）",
  "addressObjList": "优先识别并排除所有出现在公司名称、品牌名称、企业全称、组织机构名称中的地理位置（如【巨龙光学（福建）有限公司】中的福建、【XX上海分公司】中的上海），这些地理位置不参与提取。排除后，仅从剩余描述中提取明确提及的国家层级之下的地理位置（如：描述为【找中国浙江眼镜店】排除福建后，仅提取浙江）；并拆分为一级地址（如：省）二级地址（如：市）三级地址（如：区、县、镇）最后把一二三级中的有效地址通过,拼接返回（如：【浙江宁波】提取返回 浙江,宁波）。若排除公司名称后无其他地理位置，则返回空字符串",
  "employeeNumberRangeStart": "只有当描述中明确提及员工数量并且使用'员工X人以上/以下/左右'等范围描述时，按照最小值规则提取数字；否则为空字符串",
  "employeeNumberRangeEnd": "只有当描述中明确提及员工数量并且使用'员工X人以上/以下/左右'等范围描述时，按照最大值规则提取数字；否则为空字符串",
  "storeNumberRangeStart": "只有当描述中明确提及门店数量并且使用'门店X家以上/以下/左右'或'X家门店以上/以下/左右'等范围描述时，按照最小值规则提取数字；否则为空字符串。单纯的'找X家门店'属于目标数量，不在此字段提取",
  "storeNumberRangeEnd": "只有当描述中明确提及门店数量并且使用'门店X家以上/以下/左右'或'X家门店以上/以下/左右'等范围描述时，按照最大值规则提取数字；否则为空字符串。单纯的'找X家门店'属于目标数量，不在此字段提取",
  "industryList": "根据以上字段推断行业分类，多个用英文逗号分隔（如：服装,数码,家居）"
}
```

---

### Step 3：构建并提交任务

> 🧷 **下任务参数总规约（最高优先级，所有员工通用）**
>
> 提交任务时 `collaborationSubmitTaskParam` 对象**有且仅有以下 5 个根级键**，键名、类型、取值规则严格如下：
>
> ```ts
> {
>   "taskName":        String,   // AI 总结出的任务名称（来自 Step 1 的 taskName，非空字符串）
>   "currentModule":   "content",// 字符串字面量，永远是 "content"（不分员工组合，无任何例外）
>   "executionMode":   Number,   // 永远写数字 1（当前阶段一律按定额任务下达；后端枚举：周期性=0、定额=1）
>   "employeeParams":  Object,   // 见下方规约
>   "taskDescription": String    // 用户最初下达的原始任务描述，原文透传，不要改写/精简/翻译
> }
> ```
>
> 同时与 `collaborationSubmitTaskParam` **同级**必须再带：
> - `completed`: `true`（布尔字面量）
> - `sourceSettings`: 见下方「员工组合 → sourceSettings 对照表」（含 Fran/Lisa 时为完整对象，否则为 `null`）
>
> **`employeeParams` 规约：**
> - 是一个对象，key 为参与员工的 PascalCase 名称（`AiWa` / `Frank` / `Fran` / `Lisa` / `Toby`），value 为该员工自己的参数对象。
> - **包含哪些员工**由 Step 1 解析出的 `taskDescription` + `employeeList` 共同决定：任务里识别出几个员工，`employeeParams` 就有几个对应的 key，**多一个、少一个、错一个都不允许**。
> - 例：任务里同时有 AiWa 和 Frank → `employeeParams: { "AiWa": {...}, "Frank": {...} }`，两个员工的参数都是各自独立的对象，不得混合到同一个对象里，也不得只挂一个员工的参数。
>
> **每个员工子对象内部参数清单（按员工查阅下文「{员工} 参数构建规则」与「{员工} 结构强约束」获取必填键、固定值、示例）：**
> - `AiWa`: `totalTarget` / `incrementalTarget` / `upperLimitTarget` / `keywordList` / `continent` / `country` / `countryCodeList` / `addressObjList` / `industryList`（外加可选范围字段 `employeeNumberRangeStart` / `employeeNumberRangeEnd` / `storeNumberRangeStart` / `storeNumberRangeEnd`，仅当 Step 2 提取到值时才放入）。
> - `Frank`: `incrementalTarget` / `upperLimitTarget` / `senderEmail` / `language` / `templateId` / `emailPlanList`（`emailPlanList` 元素含 `delayDay` / `emailSubject` / `emailText` / `loading`）。
> - `Fran`: `priority` / `scriptId` / `callingNumber` / `agentProfileId` / `minConcurrency` / `ringingDuration` / `incrementalTarget` / `upperLimitTarget`。
> - `Lisa`: `signName` / `templateCode` / `templateType` / `templateContent` / `incrementalTarget` / `upperLimitTarget` / `qualificationName` / `templateParamList`。
> - `Toby`: `param`（嵌套对象）/ `content` / `videoItems` / `totalTarget` / `publishTemplates` / `upperLimitTarget` / `accountConfigList` / `incrementalTarget` / `staffId`。
>
> **必须遵守的硬规则（违反任意一条，后端立即拒绝）：**
> 1. `currentModule` 永远等于字符串 `"content"`，禁止写 `"analysis"` / `"Content"` / `null` / 省略。
> 2. `executionMode` 永远等于数字 `1`，禁止写 `0` / `2` / `"1"` / `true` / `"定额任务"` / `"周期性任务"`。
> 3. `taskDescription` 透传用户原始指令文本，禁止改写为 AI 总结后的简短描述（那是 `taskName` 的活儿）。
> 4. `employeeParams` 子键必须是 PascalCase 原样（`AiWa` / `Frank` / `Fran` / `Lisa` / `Toby`），不得改成 `aiwa` / `aiwaParam` / `aiwaParams` 等任何变体。
> 5. Step 1/Step 2 的内部解析变量（`employeeList` / `language` / `tiktokContent` / 根级 `totalTarget`）一律不得出现在最终请求体中——它们只能流到对应员工子对象内的指定字段。
>
> **下方各员工的"参数构建规则"、"结构强约束"、"请求体示例"是上述规约的展开细节，构建请求体时必须先按本规约确定整体形状，再按对应员工的小节填充值。**

**接口：** `POST https://ai.deepsop.com/prod-api/ai/presetEmployee/submitTask`

**请求头：**
```
Content-Type: application/json; charset=utf-8
x-api-key: $DEEPSOP_API_KEY
```

> ⚠️ **强制规则：** 请求体根级必须包含 `"completed": true`（布尔字面量）。**严禁省略、写成 `null`、`"true"` 字符串或 `false`**，否则后端会直接返回 500。该字段与 `collaborationSubmitTaskParam` 同级，不在其内部。

> 🔒 **强制使用 `submit_task.py` 提交，禁止直接 `curl`：**
>
> ```bash
> python3 scripts/submit_task.py <<'TASK_BODY_EOF'
> {
>   "completed": true,
>   "collaborationSubmitTaskParam": { ...完整请求体... }
> }
> TASK_BODY_EOF
> ```
>
> 原因：直接在 bash 命令行写 `curl -d '{"taskName":"家纺..."}'` 会触发 Windows ANSI 代码页（cp936）与 UTF-8 之间的转码歧义，导致 `taskName` / `taskDescription` 含中文时**间歇性提交为乱码**。`submit_task.py` 通过 stdin 字节流 + 显式 UTF-8 解码 + `Content-Type: application/json; charset=utf-8` 显式声明，**彻底闭合编码链路**，并内置两层 pre-flight 校验（`validate_employee_params.py` + `validate_sms_template_params.py`），校验未过自动阻塞 HTTP 提交。
>
> 行为约束：
> - **必须**通过 heredoc（`<<'TASK_BODY_EOF'` ... `TASK_BODY_EOF`）把请求体喂给 stdin；**禁止**用 argv 传 JSON（如 `python3 submit_task.py "$(echo {...})"`），argv 仍受 shell 编码影响。
> - heredoc 定界符**必须用单引号包裹**（`'TASK_BODY_EOF'` 而不是 `TASK_BODY_EOF`），否则 bash 会做变量展开，破坏 JSON 中的 `$` 字符。
> - 若运行时不支持 heredoc（极少见），退路：用 `python3 -c` 把 body 写到 UTF-8 文件，再 `python3 scripts/submit_task.py --file /tmp/task_body.json`。
> - 脚本输出单行 JSON：`{ok, stage, status, summary, response, body_preview, errors?}`；退出码 `0`=成功、`1`=校验失败、`2`=网络失败、`3`=服务端非 2xx、`4`=输入格式错误。
> - 退出码 ≠ 0 时，**必须**把 `summary` + `errors`/`response` 原样回复给用户，不得直接重试或假装成功。

> ⛔ **字段名零改写规则（极高优先级，违反必返回 500）：**
> 后端通过精确字段名解析参数，**所有键名必须与本文档示例 JSON 中的拼写完全一致（大小写、连写、单复数都不能改）**。在生成请求体时：
>
> 1. **不得做大小写转换**：`scriptId` ≠ `scriptID` ≠ `ScriptId` ≠ `script_id`；`agentProfileId` ≠ `agentProfileID` ≠ `AgentProfileId`。
> 2. **不得做命名风格转换**：禁止把 camelCase 改成 snake_case 或 kebab-case。
>    - ❌ `template_param_list` / `template-param-list` → ✅ `templateParamList`
>    - ❌ `email_plan_list` → ✅ `emailPlanList`
>    - ❌ `country_code_list` → ✅ `countryCodeList`
>    - ❌ `address_obj_list` → ✅ `addressObjList`
>    - ❌ `industry_list` / `keyword_list` → ✅ `industryList` / `keywordList`
>    - ❌ `account_config_list` → ✅ `accountConfigList`
>    - ❌ `publish_templates` → ✅ `publishTemplates`
>    - ❌ `current_module` → ✅ `currentModule`
>    - ❌ `execution_mode` → ✅ `executionMode`
>    - ❌ `task_name` / `task_description` → ✅ `taskName` / `taskDescription`
>    - ❌ `source_settings` / `employee_params` → ✅ `sourceSettings` / `employeeParams`
>    - ❌ `total_target` / `incremental_target` / `upper_limit_target` → ✅ `totalTarget` / `incrementalTarget` / `upperLimitTarget`
>    - ❌ `sender_email` → ✅ `senderEmail`
>    - ❌ `calling_number` / `ringing_duration` / `min_concurrency` → ✅ `callingNumber` / `ringingDuration` / `minConcurrency`
>    - ❌ `template_code` / `template_content` / `template_type` / `sign_name` / `qualification_name` → ✅ `templateCode` / `templateContent` / `templateType` / `signName` / `qualificationName`
>    - ❌ `variable_label` / `variable_attribute` / `variable_value` → ✅ `variableLabel` / `variableAttribute` / `variableValue`
>    - ❌ `method_type` / `image_url_list` / `first_image_url` / `last_image_url` / `keep_original_sound` / `generate_audio` / `enhance_prompt` / `negative_prompt` / `prompt_extend` / `shot_type` / `duration_switch` / `person_generation` / `resize_mode` → 全部保持 camelCase
>    - ❌ `account_id` / `privacy_level` / `comment_disabled` / `duet_disabled` / `stitch_disabled` / `disable_comment` / `disable_duet` / `disable_stitch` / `is_public_account` / `brand_content_toggle` / `brand_organic_toggle` → 全部保持 camelCase
>    - ❌ `release_type` / `time_zone` / `interval_type` / `start_time` / `publish_count` / `publish_interval` → 全部保持 camelCase
>    - ❌ `delay_day` / `email_subject` / `email_text` → ✅ `delayDay` / `emailSubject` / `emailText`
>    - ❌ `country_id` / `address_id` / `file_list` / `update_support` / `seas_group_ids` / `group_id` / `stage_id` / `label_id` → 全部保持 camelCase（`groupId` / `stageId` / `labelId` / `seasGroupIds` / `fileList` / `updateSupport` / `addressId` / `countryId`）
>    - ❌ `staff_id` / `video_items` → ✅ `staffId` / `videoItems`
> 3. **不得做单复数改造**：复数字段必须保留 `List` / 复数后缀，单数字段不得加 `s`。
>    - `emailPlanList` 不得写成 `emailPlans` / `emailPlan`
>    - `callingNumber` 不得写成 `callingNumbers`
>    - `publishTemplates` 不得写成 `publishTemplate` / `publishTemplateList`
>    - `accountConfigList` 不得写成 `accountConfigs`
>    - `templateParamList` 不得写成 `templateParams`
> 4. **不得做语义改名**：禁止用同义词替换字段名。
>    - `agentProfileId` ≠ `agentId` / `chatbotId` / `profileId` / `botId`
>    - `senderEmail` ≠ `fromEmail` / `mailFrom` / `email`
>    - `callingNumber` ≠ `callerNumber` / `phone` / `outboundNumber`
>    - `templateCode` ≠ `smsTemplateCode` / `code`
>    - `signName` ≠ `signature` / `signatureName`（注意：模板列表返回的字段叫 `signatureName`，但**提交时的字段名必须是 `signName`**）
>    - `qualificationName` ≠ `qualification` / `qualifications`
>    - `taskName` / `taskDescription` ≠ `name` / `description` / `title`
> 5. **校验流程**：构建完请求体后，**必须把 JSON 字符串与本文档对应的示例 JSON 逐字段对位检查一遍**——示例里有的键，请求体必须有；示例里键名怎么拼，请求体就照样拼；任何一个键名拼错都视为构建失败，重新构建后再提交。
>
> 不允许"我觉得 snake_case 更规范所以转一下"或"复数加 s 更自然"这类自作主张。

**参数构建规则：**

**前置 A：Fran 号码池与场景库查询（当 employeeList 包含 Fran 时必须先执行）**

**0. 检查外呼实例可用性**

接口：`GET https://ai.deepsop.com/prod-api/ai/outBound/describeInstance`

请求头：`x-api-key: $DEEPSOP_API_KEY`

检查 `data.body.instance.maxConcurrentConversation`：
- 大于 0：继续执行步骤 1（查询号码池）
- 等于 0：**终止任务**，回复用户：
  > ⚠️ 当前外呼账号并发数为 0，无法提交电话销售任务，请联系管理员开通并发资源后再试。

**1. 查询号码池**

接口：`GET https://ai.deepsop.com/prod-api/ai/outBound/callerNumber/list`

请求头：`x-api-key: $DEEPSOP_API_KEY`

返回示例：
```json
{
  "total": 1,
  "rows": [
    {
      "id": 7,
      "callNumber": "30350903",
      "nickName": "Kocgo"
    }
  ],
  "code": 200,
  "msg": "查询成功"
}
```

处理规则：
- `rows` 为空（`total=0`）：**终止任务**，回复用户：
  > ⚠️ 当前账号下没有可用的外呼号码，无法提交电话销售任务，请联系管理员开通号码后再试。
- `rows` 只有 1 条：自动选用该 `callNumber`，无需用户确认。
- `rows` 有多条：列出所有号码供用户选择（支持多选），格式：
  ```
  检测到多个可用外呼号码，请选择本次任务要使用的号码（可多选，用逗号分隔序号）：
  1. {callNumber}（{nickName}）
  2. {callNumber}（{nickName}）
  ...
  ```
  **等待用户回复后**，解析出被选中的 `callNumber` 列表（数组形式），赋值给 `callingNumber`。未收到选择不得继续。

**2. 查询场景库**

接口：`POST https://ai.deepsop.com/prod-api/ai/outBound/listScripts`

请求头：
```
Content-Type: application/json
x-api-key: $DEEPSOP_API_KEY
```

请求体：
```json
{"pageNumber": 1, "pageSize": 20, "scriptName": ""}
```

返回结构（重点字段）：
- `data.body.scripts.list[]`：场景库列表
  - `scriptId`：场景库 ID
  - `scriptName`：场景库名称
  - `industry` / `scene`：行业 / 场景
  - `status`：状态，**必须为 `PUBLISHED` 才可用**
- `data.chatbotIdList[]`：与场景库配套的 chatbot id 列表，取第一个作为 `agentProfileId`

处理规则：
- `list` 为空，或过滤后无 `status === "PUBLISHED"` 的场景：**终止任务**，回复用户：
  > ⚠️ 当前账号下没有可用（已发布）的场景库，请先登录 https://ai.deepsop.com 创建场景库，并将其状态发布为 `PUBLISHED` 后再试。
- 仅 1 条 `PUBLISHED` 场景：**不得自动选用**，必须列出并等待用户明确确认，格式：
  ```
  检测到以下可用场景库，请确认是否使用（回复「确认」即可）：
  1. {scriptName}（行业：{industry}，场景：{scene}）
  ```
  **等待用户明确回复「确认」后**，取对应 `scriptId`。未收到确认不得继续。
- 多条 `PUBLISHED` 场景：列出供用户**单选**，格式：
  ```
  请选择本次电话销售任务要使用的场景库（回复序号）：
  1. {scriptName}（行业：{industry}，场景：{scene}）
  2. ...
  ```
  **等待用户回复后**，取对应 `scriptId`。未收到选择不得继续。
- `agentProfileId` 统一取 `data.chatbotIdList[0]`（若为空数组则终止并提示联系管理员）。

**前置 B0：Frank 邮箱绑定检查（当 employeeList 包含 Frank 时必须先执行）**

接口：`GET https://ai.deepsop.com/prod-api/ai/emailconfig/list?pageSize=1000&pageNum=1&status=1`

请求头：`x-api-key: $DEEPSOP_API_KEY`

检查 `rows` 列表：
- `rows` 不为空（至少 1 条）：继续执行前置 B（获取用户 Profile）
- `rows` 为空（`total=0`）：**终止任务**，回复用户：
  > ⚠️ 当前账号未绑定可用邮箱，无法提交邮件销售任务，请先登录 https://ai.deepsop.com 前往「邮件配置」绑定邮箱后再试。

**前置 B：获取用户 Profile（当 employeeList 包含 Frank 时必须先执行）**

```bash
curl -s -H "x-api-key: $DEEPSOP_API_KEY" 'https://ai.deepsop.com/prod-api/ai/user/profile'
```

提取以下字段用于邮件署名：
- `nickName`：发件人姓名
- `position`：职位（可能为空，直接取 profile 中的 `position` 字段）
- `dept.deptName`：公司名称
- `phonenumber`：电话（注意字段名全小写）
- `email`：邮箱（作为 `senderEmail`）

**前置 C：AI 生成邮件内容（当 employeeList 包含 Frank 时必须先执行）**

根据用户指令和 profile 信息，用 LLM 生成邮件主题和正文，严格返回 JSON 数组：

```
生成对应语言【{language}】的内容，请直接输出纯净的JSON数组，不包含任何额外文本、代码标记、说明或包装。
输出示例：[{"emailSubject": "邮件主题", "emailText": "邮件内容"}]

邮件生成规则：
1. 开头：使用标准问候语（中文："尊敬的先生/女士："）
2. 正文：根据【{taskDescription}】生成开发信，必须至少包含以下一项：
   - 产品关键词：从 taskDescription 中提取
   - 价值主张：包含「功能+场景+风格」三要素（如：【防风防水】男士户外工装夹克 春秋季通勤休闲外套）
   - 痛点：具体描述需求未被满足的场景
   - 解决方案：突出技术/设计优势与使用场景
   - 行动呼吁：包含「稀缺性+权益+行动指令」（如：区域独家授权：仅开放3个地区代理名额！签约即享首单5%折扣→ 立即WhatsApp发送需求）
   - 证明点：包含「原始痛点+解决方案+量化结果」的客户案例
   - 服务吸引物：分点列出，覆盖供应链/物流/市场支持/售后/定制化5大类
3. 结尾：自然添加对应语言祝福语
4. 署名（每项另起一行，共4行）：
   {nickName}（{position}）
   {companyName}（若 nickName 与 companyName 相同则省略此行）
   {phoneNumber}
   {email}
5. 风格：专业、直接、有帮助且富有亲和力；避免使用「免费」「优惠」「限时」等推销词汇
6. 主题：简洁引人入胜，避免垃圾邮件词汇
7. 禁止出现 [Name] 等变量占位符
```

生成结果提取 `emailSubject` 和 `emailText` 用于 Frank 参数。

**前置 D：Lisa 短信模板查询与变量填写（当 employeeList 包含 Lisa 时必须先执行）**

**1. 查询短信模板列表**

接口：`GET https://ai.deepsop.com/prod-api/ai/sms/querySmsTemplateList?pageNum=1&pageSize=20&pageNumber=1`

请求头：`x-api-key: $DEEPSOP_API_KEY`

关键字段：
- `data.smsTemplateList[]`：模板列表
  - `auditStatus`：必须为 `AUDIT_STATE_PASS` 才可用
  - `templateCode`：模板编码
  - `templateName`：模板名称
  - `templateContent`：模板内容（含 `${xxx}` 占位符）
  - `signatureName`：签名名称
  - `templateType`：模板类型（0=通知, 1=推广, 2=验证码）
  - `outerTemplateType`：提交时使用的模板类型参数

处理规则：
- 过滤后无 `auditStatus === "AUDIT_STATE_PASS"` 的模板：**终止任务**，回复用户：
  > ⚠️ 当前账号下没有已审核通过的短信模板，请先登录 https://ai.deepsop.com 创建并审核通过短信模板（状态需为 `AUDIT_STATE_PASS`）后再试。
- 仅 1 条 `AUDIT_STATE_PASS` 模板：**不得自动选用**，必须列出并等待用户明确确认，格式：
  ```
  检测到以下可用短信模板，请确认是否使用（回复「确认」即可）：
  1. {templateName}（类型：{templateType中文}）
     内容：{templateContent}
  ```
  **等待用户明确回复「确认」后**，取该模板。未收到确认不得继续。
- 多条 `AUDIT_STATE_PASS` 模板：列出供用户**单选**，格式：
  ```
  请选择本次短信销售要使用的模板（回复序号）：
  1. {templateName}（类型：{templateType中文}）
     内容：{templateContent}
  2. ...
  ```

**2. 模板变量填写**

选定模板后，解析 `templateContent` 中的 `${xxx}` 占位符，就每个变量告知用户并求其填写。如模板无变量，跳过此步。

根据 `templateType` 匹配对应变量规则集并告知用户填写要求：

| templateType | 模板类型 | 应用变量规则集 |
|---|---|---|
| 2 | 验证码短信 | verify（验证码类规则） |
| 0 | 通知短信 | notify（通知类规则） |
| 1 | 推广短信 | market（推广类规则） |

**主要变量类型与校验规则：**

| 变量类型名 | code | 适用范围 | 校验规则 |
|---|---|---|---|
| 仅数字（验证码） | numberCaptcha | verify | 纯数字4–6位 |
| 数字+字母组合或仅字母 | characterWithNumber2 | verify | 长度4–6位 |
| 验证码时间（1–2位数字） | verifyTime | verify | 1–99的整数 |
| 时间/日期 | time | notify/market | YYYY-MM-DD、hh:mm、上午/下午等标准时间格式 |
| 金额/数量 | money | notify/market | 纯数字或小数，不含单位符号 |
| 用户昵称 | user_nick | notify/market | 不超过20个字符，不含表情/QQ/微信号 |
| 个人姓名 | name | notify/market | 2–5个简体中文 |
| 企业/组织名称 | unit_name | notify | 仅中文，不超过20字符 |
| 地址 | address | notify | 不超过30字符，不含 QQ/微信号 |
| 车牌号 | license_plate_number | notify | 省份简称+字母+数字组合，不超过10字符 |
| 快递单号 | tracking_number | notify | 8–16位数字，或字母开头+数字字母 |
| 取件码 | pick_up_code | notify | 4–8位数字/短横线/下划线 |
| 其他号码 | other_number2 | notify | 不超过35字符字母数字组合 |
| 电话号码 | phone_number2 | notify | 3–12位纯数字，每模板最多2个号码变量 |
| 链接参数 | link_param | notify/market | 1–8位英文数字，不含完整链接/IP |
| 邮筱地址 | email_address | notify | 7–30字符，包含@ |
| 其他 | others | notify/market | 不超过35字符，不含 QQ/微信/手机/网址 |

**变量匹配逻辑：**
1. 根据变量名（如 `conference`、`address`、`time`）在对应规则集中按变量类型名称匹配：
   - `time`/`date`/`day`/`year`/`month` 类 → `time`
   - `money`/`price`/`amount` 类 → `money`
   - `phone`/`tel`/`mobile` 类 → `phone_number2`
   - `address`/`addr`/`location` 类 → `address`
   - `name`/姓名类 → `name`
   - `user_nick`/昵称类 → `user_nick`
   - `conference`/`unit`/组织类 → `unit_name`
   - 其他 → `others`
2. 求用户为每个变量填写具体值。**必须**同时给出"✅ 正确示例"和"❌ 错误示例"，让用户一眼看到雷区。格式：
   > 模板内容为：「{templateContent}」
   > 包含以下变量需要填写（请严格按格式，否则短信会全部发送失败）：
   > - `${conference}`：企业/组织名称（仅中文，不超过20字符）
   >   - ✅ 例：`库阔数字科技`
   >   - ❌ 例：`Kocgo Tech`（含英文）、`库阔数字科技股份有限公司（杭州）`（超长）
   > - `${address}`：地址（不超过30字符）
   >   - ✅ 例：`杭州萧山万豪酒店三楼`
   >   - ❌ 例：`https://maps.example.com/...`（含网址）
   > - `${time}`：时间（仅允许 `YYYY-MM-DD`、`hh:mm`、`上午/下午X点` 等标准格式）
   >   - ✅ 例：`2026-05-15 14:00`、`5月15日 下午2点`
   >   - ❌ 例：`2026年5月15日 14:00`（含中文"年月日"会被运营商网关拒绝）
   > 请为每个变量填写具体内容。
3. 🔒 **强制变量校验（pre-flight gate，违反任意一条都不得继续）：**

   ✅ **首选方式：调用本 SKILL 自带的校验脚本**（代码级校验，结果机器可读，比 LLM 自查可靠）：

   ```bash
   python3 scripts/validate_sms_template_params.py '<templateParamList JSON 字符串>'
   ```

   - 入参：和最终请求体里的 `templateParamList` 同形状的 JSON 数组（仅含 `variableLabel` / `variableAttribute` / `variableValue` 三键）。
   - stdout 输出单行 JSON：`{ok, summary, results: [{label, attribute, value, status, reason, suggestion?}]}`。
   - 退出码：`0` 全 PASS、`1` 至少一项 FAIL、`2` 输入格式错误。
   - 行为约束：
     - 退出码 ≠ 0 时，**禁止**继续；必须把 `results` 中每条 FAIL 的 `reason` + `suggestion` 原样回复给用户，要求其重新填写后再次构建 `templateParamList` 并**重新调用本脚本**。
     - 退出码 = 0 时才进入第 4 步。
     - **不得**自己规整后跳过脚本（例如把 `2026年5月15日` 改成 `2026-05-15` 然后直接提交），必须让用户确认修改后的值再走一次校验。

   ⚠️ **退路：脚本调用失败时（极少见，例如 python3 不可用）**，按下列规则人工逐个变量校验，规则与脚本完全一致：

   a. 按变量的 `variableAttribute`（即上一步匹配到的 `code`）查上方"主要变量类型与校验规则"表，取出"校验规则"列。
   b. 用规则对值做逐字符校验，**必须**判定是 PASS 还是 FAIL。不得"差不多就算过"，不得"用户写得清楚就提交"。
   c. **任意一个变量 FAIL** → 立即向用户回复不合规的变量、违反的具体规则、合法示例，并要求重新填写。**不得**：
      - 调用提交任务接口（`agentSubmitTask`）
      - 自己擅自规整格式（如把 `2026年5月15日` 改写成 `2026-05-15` 后偷偷提交——必须让用户确认）
      - 把"用户写得很明确"作为跳过校验的理由
   d. **全部 PASS** 才能进入第 4 步构建 `templateParamList` 并继续后续提交流程。

   **🚨 高频错误案例（已发生过真实事故，每次提交前必须自查）：**

   | 变量类型 | 用户实际填写 | AI 错误处理 | 后果 | 正确处理 |
   |---|---|---|---|---|
   | `time` | `2026年5月15日 14:00` | 直接提交 | 短信网关拒绝，13 条全部失败 | 提醒用户改成 `2026-05-15 14:00` 后再提交 |
   | `unit_name` | `Kocgo Tech` | 直接提交 | 模板审核为"仅中文"被拒 | 提醒用户改成中文名称 |
   | `phone_number2` | `+86 138-1234-5678` | 直接提交 | 含非数字字符被拒 | 提醒用户改成 `13812345678` |

4. 校验通过后，构建 `templateParamList`：
   ```json
   [
     {"variableLabel": "conference", "variableAttribute": "unit_name", "variableValue": "用户填写的值"},
     {"variableLabel": "address",    "variableAttribute": "address",   "variableValue": "用户填写的值"},
     {"variableLabel": "time",       "variableAttribute": "time",      "variableValue": "用户填写的值"}
   ]
   ```
   其中 `variableLabel` = 占位符名（不含 `${}`），`variableAttribute` = 匹配到的 code。

**前置 E：Toby TikTok 账号与发布参数配置（当 employeeList 包含 Toby 时必须先执行）**

**E-1：查询 TikTok 绑定账号**

接口：`GET https://ai.deepsop.com/prod-api/ai/authaccount/list?pageNum=1&pageSize=999&platform=1&status=1`

请求头：`x-api-key: $DEEPSOP_API_KEY`

关键字段：
- `rows[].id`：账号 ID
- `rows[].account`：TikTok 账号名
- `rows[].fansNum`：粉丝数
- `rows[].groupNames`：分组名称
- `rows[].expiredTime`：授权过期时间

处理规则：
- `rows` 为空：**终止任务**，回复：
  > ⚠️ 当前账号未绑定任何 TikTok 授权账号，请先登录 https://ai.deepsop.com 添加 TikTok 授权账号后再试。
- `rows` 只有 1 条：付列出并等待用户确认，格式：
  ```
  检测到以下 TikTok 账号，请确认是否使用（回复「确认」即可）：
  1. @{account}（粉丝：{fansNum}，分组：{groupNames}）
  ```
- `rows` 有多条：列出供用户多选，格式：
  ```
  检测到以下 TikTok 授权账号，请选择本次要发布的账号（可多选，用逗号分隔序号）：
  1. @{account}（粉丝：{fansNum}，分组：{groupNames}）
  2. ...
  ```

**等待用户确认/选择后**，将选中账号的 `id` 列表记为 `selectedAccountIds`。未收到确认不得继续。

**E-2：获取账号权限信息**

针对第一个选中账号调用：
接口：`GET https://ai.deepsop.com/prod-api/ai/auth/tiktok/getCreatorInfo?authAccountId={selectedAccountIds[0]}`

请求头：`x-api-key: $DEEPSOP_API_KEY`

提取字段（用于构建 `accountConfigList`）：
- `data.privacyLevelOptions[]`：可用隐私级别列表
- `data.commentDisabled`：是否禁评
- `data.duetDisabled`：是否禁合拍
- `data.stitchDisabled`：是否禁缝合

若 `privacyLevelOptions` 有多个选项，让用户选择隐私级别，格式：
```
请选择该账号的视频隐私设置（回复序号）：
1. PUBLIC_TO_EVERYONE — 全公开
2. MUTUAL_FOLLOW_FRIENDS — 互关好友
3. SELF_ONLY — 仅自己可见
```

**E-3：AI 视频生成模型（默认）**

`param.methodType` **默认固定为 `"3"`**，无需用户选择。如需查看全部可用模型，可调用以下接口获取列表并告知用户当前默认模型名称（展示对应 `sourceValue === "3"` 的 `sourceName`）：

接口：`POST https://ai.deepsop.com/prod-api/ai/consumeSource/list?pageNum=1&pageSize=999`
请求体：`{"sourceTypeList":["VIDEO_MODEL"],"hiddenState":"0"}`

视频其他参数亦默认如下，无需用户配置（默认 methodType=`"3"` Veo3.1 Fast Lite 下，详见 Step 3 「Toby 参数构建规则」与「methodType → 取值约束表」）：
- `resolution`：`720p`
- `ratio`：`16:9`
- `duration`：`8` 秒（methodType=`"3"` 唯一允许值）
- `generationType`：`"FIRST&LAST"`
- `shotType`：`"single"`
- `mode`：`"pro"`
- `keepOriginalSound`：`"yes"`
- `personGeneration`：`"allow_adult"`
- `resizeMode`：`"pad"`
- `n`：`1`
- `generateAudio`：`true`
- `enhancePrompt` / `promptExtend` / `multiShot`：`false`
- `durationSwitch`：`"1"`

> 若用户明确要求换其他视频模型（如指定 `Veo3.1 Pro` / `Sora2 Pro` / `kling-v3-omni` 等），先调上面的 `consumeSource/list` 接口拿到候选模型的 `sourceValue`，让用户回复选定的 sourceValue，再据此 methodType 去 Step 3 的「methodType → 取值约束表」校正 `generationType` / `resolution` / `ratio` / `duration` / `shotType` 等依赖字段，**不得**沿用 methodType=`"3"` 的默认值。

**E-4：视频生成提示词确认（必题用户，禁止跳过）**

以 Step 1 解析出的 `tiktokContent` 作为默认提示词，强制询问用户是否需要修改：

```
当前 AI 视频生成提示词为：「{tiktokContent}」
是否需要修改？（回复「不用」直接使用，或直接输入新的提示词）
```

- 用户回复「不用」或类似否定语：保持 `tiktokContent` 不变
- 用户输入新提示词：将 `content` 和 `param.text` 替换为用户输入的内容

**未收到用户回复不得继续。**

**E-5：发布参数配置（必须由用户指定，禁止自动填充）**

针对每个选中的账号，强制用户指定以下参数（如选了多个账号，依次询问每个）：
```
请为账号 @{account} 配置发布参数：
- 每天发布视频数（publishCount，如 3）：
- 定时发布开始时间（startTime，HH:mm 格式，如 09:30）：
- 视频发布间隔（publishInterval，分钟，如 60）：
```

**等待用户回复后**，构建该账号的 `publishTemplates` 条目。未收到所有账号的参数不得继续。

**AiWa 参数构建规则：**
- `totalTarget`：定额模式下填 Step 1 的 totalTarget，周期模式下为 null
- `incrementalTarget`：必填，固定填 5000（不可为 null）
- `upperLimitTarget`：固定填 5000
- `keywordList`：Step 2 的 keywordList **必须用 `.split(",")` 拆分成数组**（绝不可保留为逗号字符串）
- `continent`：Step 2 的 continent，**无则填 `null`，不得填 `""`**
- `country`：Step 2 的 country，**无则填 `null`，不得填 `""`**
- `countryCodeList`：Step 2 的 countryCodeList **必须用 `.split(",")` 拆分成数组**，无则填 `[]`（**不得填 `""` 或 `null`**）
- `addressObjList`：根据 Step 2 的 `addressObjList`（逗号字符串）构建，规则如下：
  - **情况 1（无地址）**：Step 2 返回空字符串。必须填占位 `[{"type":1,"province":"","city":"","county":"","address":""}]`，**不得填 `[]`**。
  - **情况 2（中文结构化地址）**：Step 2 返回如 `"浙江,宁波"`。拆分后填 `type=1` + 对应层级字段、`address` 留空：
    `[{"type":1,"province":"浙江","city":"宁波","county":"","address":""}]`
  - **情况 3（非中国 / 自由文本地址）**：如输入为英文完整地址（`"123 Main St, London"`）、拆不出省/市/县层级。填 `type=0` + `province/city/county` 留空、`address` 填全文：
    `[{"type":0,"province":"","city":"","county":"","address":"123 Main St, London"}]`
  - **多个地址**：array 中可多条对象，但 `type` 需与各自的地址形式匹配。
  - **`type` 取值语义**：`1` = 中文结构化拆分地址（期望填到 `province/city/county`）；`0` = 自由文本地址（期望填到 `address`）。**不得两者同时填**（`type=1` 时 `address` 须为 `""`；`type=0` 时 `province/city/county` 须全为 `""`）。
- `industryList`：Step 2 的 industryList **必须用 `.split(",")` 拆分成数组**

> ⛔ **AiWa 结构强约束（违反必返回 500 / 后端识别不到参数）：**
>
> 1. AiWa 子对象的 key 是 **`AiWa`**（**P**ascal**C**ase 三个字母原样），不是 `aiwa` / `Aiwa` / `aiWa` / `aiwaParam` / `aiWaParams`。
> 2. AiWa 子对象**必须**嵌在 `collaborationSubmitTaskParam.employeeParams.AiWa` 之下，**绝对禁止**直接挂到 `collaborationSubmitTaskParam.aiwaParam` / `collaborationSubmitTaskParam.AiWa` 这种少一层的位置。
> 3. **以下来自 Step 1/Step 2 的"内部解析变量"是给本 SKILL 内部流程用的，绝不允许出现在最终请求体的任何层级**：
>    - `employeeList`（Step 1 用来分发员工，请求体只关心 `employeeParams` 里的子键）
>    - `language`（仅在 `employeeParams.Frank` 子对象内部使用，禁止挂到根级或 AiWa 子对象内）
>    - `tiktokContent`（仅在构建 `employeeParams.Toby.content` / `param.text` 时取值，禁止挂到请求体任何层级）
>    - `totalTarget`（**只能**作为 `employeeParams.AiWa.totalTarget` 或 `employeeParams.Toby.totalTarget`，**不得**挂到 `collaborationSubmitTaskParam` 根级）
> 4. AiWa 必填的 9 个键：`totalTarget` / `incrementalTarget` / `upperLimitTarget` / `keywordList` / `continent` / `country` / `countryCodeList` / `addressObjList` / `industryList`，**一个都不能漏**。
> 5. `currentModule` 必须在 `collaborationSubmitTaskParam` 内，**值固定为 `"content"`**（任何员工组合下都不得写 `"analysis"`）。

**AiWa 任务请求体示例（仅 AiWa 单独执行 — 直接对照拷贝，不要自由发挥）：**

```json
{
  "collaborationSubmitTaskParam": {
    "taskName": "家纺客户挖掘",
    "taskDescription": "帮我找10个做家纺的客户",
    "executionMode": 1,
    "employeeParams": {
      "AiWa": {
        "totalTarget": 10,
        "incrementalTarget": 5000,
        "upperLimitTarget": 5000,
        "keywordList": ["家纺", "纺织", "床上用品", "毛巾", "窗帘", "home textile", "bedding"],
        "continent": null,
        "country": null,
        "countryCodeList": [],
        "addressObjList": [{"type": 1, "province": "", "city": "", "county": "", "address": ""}],
        "industryList": ["家纺", "纺织"]
      }
    },
    "sourceSettings": null,
    "currentModule": "content"
  },
  "completed": true
}
```

> 🚫 **错误示例（曾经真实出现过的错传，禁止再生成此种结构）：**
>
> ```json
> {
>   "completed": true,
>   "collaborationSubmitTaskParam": {
>     "taskName": "家纺客户挖掘",
>     "executionMode": 1,
>     "totalTarget": 10,                       // ❌ 不应在根级
>     "employeeList": "AiWa",                  // ❌ Step 1 内部变量，不应出现
>     "language": "中文",                       // ❌ Step 1 内部变量，不应出现
>     "aiwaParam": {                           // ❌ 应是 employeeParams.AiWa
>       "keywordList": "家纺,纺织,床上用品,毛巾,窗帘",  // ❌ 应是数组
>       "industryList": "家纺,纺织",              // ❌ 应是数组
>       "continent": "",                         // ❌ 应是 null
>       "country": "",                           // ❌ 应是 null
>       "countryCodeList": "",                   // ❌ 应是 []
>       "addressObjList": []                     // ❌ 必须放占位对象
>     }
>     // ❌ 缺 employeeParams 包装层
>     // ❌ 缺 incrementalTarget / upperLimitTarget
>     // ❌ 缺 currentModule / sourceSettings
>   }
> }
> ```
>
> 上面这个错例犯了 7 项错误，**任何一项都会让后端识别不到参数**。生成请求体前请把上面的"正确示例"拷过来再替换具体值，不要从头自由编写。

**Frank 参数构建规则：**
- `incrementalTarget`：固定填 1000
- `upperLimitTarget`：固定填 1000
- `senderEmail`：来自 profile 的 `email`
- `language`：来自 Step 1 的 `language`（`"中文"` 或 `"英文"`）
- `templateId`：固定为 null
- `emailPlanList`：包含一个对象，字段：
  - `delayDay`：0
  - `emailSubject`：AI 生成的邮件主题
  - `emailText`：AI 生成的邮件正文（HTML 格式）
  - `loading`：0

> ⛔ **Frank 结构强约束：**
> 1. 子对象 key 必须是 **`Frank`**（首字母大写），不是 `frank` / `FRANK` / `frankParam` / `frankParams`。
> 2. 必须嵌在 `collaborationSubmitTaskParam.employeeParams.Frank` 之下。
> 3. `language` **只能**作为 `employeeParams.Frank.language`，**不得**挂到根级或其他员工子对象。
> 4. `emailPlanList` 必须是**长度为 1 的数组**，元素是对象，且对象内 4 个键 `delayDay` / `emailSubject` / `emailText` / `loading` 一个都不能漏。**不得**写成 `emailPlan`（单数）或 `emailPlans`（错误复数）或直接把对象本身赋给 `emailPlanList`（少一层数组）。
> 5. `senderEmail` 必须是字符串，不得写成对象 `{email: "..."}`，也不得改名为 `email` / `fromEmail` / `mailFrom`。
> 6. 必填 6 个键：`incrementalTarget` / `upperLimitTarget` / `senderEmail` / `language` / `templateId` / `emailPlanList`，一个都不能漏。

**Fran 参数构建规则：**
- `ringingDuration`：固定填 25
- `incrementalTarget`：固定填 1000
- `upperLimitTarget`：固定填 1000
- `minConcurrency`：固定填 1
- `priority`：固定填 `"Daily"`
- `callingNumber`：前置 A 第 1 步用户选定的号码**数组**（如 `["30350903"]`），**单号码也必须是数组形式**
- `scriptId`：前置 A 第 2 步用户选定的场景库 `scriptId`
- `agentProfileId`：前置 A 第 2 步 `data.chatbotIdList[0]`

> ⛔ **Fran 结构强约束：**
> 1. 子对象 key 必须是 **`Fran`**（首字母大写、4 个字母原样），不是 `fran` / `FRAN` / `franParam` / `franParams`。
> 2. 必须嵌在 `collaborationSubmitTaskParam.employeeParams.Fran` 之下。
> 3. `callingNumber` **必须是数组**（`["30350903"]`），即使只有一个号码也不得写成裸字符串 `"30350903"`，也不得改名为 `callingNumbers` / `callerNumber` / `phone` / `outboundNumber`。
> 4. `scriptId` 与 `agentProfileId` 必须是 **接口返回的字符串原值**（保留原始大小写如 `"chatbot-cn-RYRmV3jjzb"`），不得自行拼接、改名、加引号包裹两次。`agentProfileId` ≠ `agentId` / `chatbotId` / `profileId`。
> 5. `priority` 是字符串 `"Daily"`（**首字母大写**），不是 `"daily"` / `"DAILY"` / 整数。
> 6. 必填 8 个键：`ringingDuration` / `incrementalTarget` / `upperLimitTarget` / `minConcurrency` / `priority` / `callingNumber` / `scriptId` / `agentProfileId`，一个都不能漏。

**Fran 任务请求体示例（AiWa + Fran 联合任务）：**
```json
{
  "collaborationSubmitTaskParam": {
    "taskName": "启动财务课程电话销售",
    "taskDescription": "帮我找客户并启动电话销售",
    "executionMode": 1,
    "employeeParams": {
      "AiWa": { "...": "同上" },
      "Fran": {
        "ringingDuration": 25,
        "incrementalTarget": 1000,
        "upperLimitTarget": 1000,
        "callingNumber": ["30350903"],
        "minConcurrency": 1,
        "priority": "Daily",
        "scriptId": "c92d016f-03c8-47a3-95d9-61d75e192181",
        "agentProfileId": "chatbot-cn-RYRmV3jjzb"
      }
    },
    "sourceSettings": {
      "groupId": [], "stageId": [], "labelId": [], "level": [],
      "seasGroupIds": [], "addressId": [], "fileList": [],
      "updateSupport": 1, "cascader": null, "aiMining": null,
      "customerMining": null, "seasMining": null, "uploadMining": null,
      "countryId": null, "addressMining": null
    },
    "currentModule": "content"
  },
  "completed": true
}
```

> ⚠️ 当 `employeeList` 包含 `Fran` 或 `Lisa` 时，`sourceSettings` 必须按上述完整对象填充（不能为 `null`），且 `currentModule` 固定为 `"content"`。

**Lisa 参数构建规则：**
- `incrementalTarget`：固定填 100
- `upperLimitTarget`：固定填 100
- `signName`：选定模板的 `signatureName`（**接口返回字段叫 `signatureName`，但请求体提交时必须叫 `signName`，自行改名**）
- `qualificationName`：同 `signName`（如两者不同由用户确认）
- `templateCode`：选定模板的 `templateCode`
- `templateContent`：选定模板的 `templateContent`
- `templateType`：选定模板的 `outerTemplateType`（注意：值取自模板对象的 `outerTemplateType` 字段，但请求体的键名仍叫 `templateType`）
- `templateParamList`：前置 D 第 2 步构建的变量数组（无变量则为 `[]`）

> ⛔ **Lisa 结构强约束：**
> 1. 子对象 key 必须是 **`Lisa`**（首字母大写、4 个字母原样），不是 `lisa` / `LISA` / `lisaParam` / `lisaParams`。
> 2. 必须嵌在 `collaborationSubmitTaskParam.employeeParams.Lisa` 之下。
> 3. `templateParamList` **必须是数组**，每个元素是含 **`variableLabel` / `variableAttribute` / `variableValue`** 三个键的对象。**禁止**改成键值映射形式（如 `{conference: "库阔科技", address: "杭州"}`）；**禁止**漏 `variableAttribute`（即使值与 `variableLabel` 同名也必须显式写出）。无变量时填 `[]`，**不要省略此键**。
> 4. `signName` ≠ `signatureName`（提交字段名）；`signName` 不得改名为 `signature` / `sign`。
> 5. `templateCode` 必须保留接口返回的原值（如 `"SMS_500460013"`），不得改名为 `code` / `smsTemplateCode`。
> 6. `templateType` 是数字（取自 `outerTemplateType`），不是字符串。
> 7. 必填 8 个键：`incrementalTarget` / `upperLimitTarget` / `signName` / `qualificationName` / `templateCode` / `templateContent` / `templateType` / `templateParamList`，一个都不能漏。

**Lisa 任务请求体示例（AiWa + Lisa 联合任务）：**
```json
{
  "collaborationSubmitTaskParam": {
    "taskName": "双十一老客户短信推广",
    "taskDescription": "帮我找客户并给老客户发短信",
    "executionMode": 1,
    "employeeParams": {
      "AiWa": { "...": "同上" },
      "Lisa": {
        "incrementalTarget": 100,
        "upperLimitTarget": 100,
        "qualificationName": "杭州库阔数字科技",
        "signName": "杭州库阔数字科技",
        "templateCode": "SMS_500460013",
        "templateParamList": [
          {"variableLabel": "conference", "variableAttribute": "unit_name", "variableValue": "库阔科技"},
          {"variableLabel": "address",    "variableAttribute": "address",   "variableValue": "杭州"},
          {"variableLabel": "time",       "variableAttribute": "time",      "variableValue": "2026-04-20"}
        ],
        "templateType": 1,
        "templateContent": "温馨提醒：${conference}会议将在${address}地点，于${time}时间开始，请您准时参加。"
      }
    },
    "sourceSettings": {
      "groupId": [], "stageId": [], "labelId": [], "level": [],
      "seasGroupIds": [], "addressId": [], "fileList": [],
      "updateSupport": 1
    },
    "currentModule": "content"
  },
  "completed": true
}
```

**Toby 参数构建规则：**
- `totalTarget`：定额模式下填 Step 1 的 totalTarget，周期模式下为 null
- `incrementalTarget`：周期模式下填用户指定的每天发布数，定额模式下固定填 10
- `upperLimitTarget`：固定 10
- `content`：来自 Step 1 的 `tiktokContent`
- `staffId`：固定为空字符串 `""`
- `param`：嵌套对象，**有且仅有以下 27 个键**，必须按官方默认模板的键集与顺序构建（`text` 取自 E-4 确认后的最终提示词；`methodType` 默认 `"3"` Veo3.1 Fast Lite，来自 E-3）。**注意：当前 methodType 下 UI 不显的字段也必须传默认值，禁止裁剪 key**：

  | 字段 | 默认值 | 类型 | 说明 |
  |---|---|---|---|
  | `methodType` | `"3"` | string | 视频生成模型，默认 Veo3.1 Fast Lite；其他可选值见下方 methodType 约束表 |
  | `multiShot` | `false` | boolean | 是否多镜头（仅 methodType=`"10"` 实际生效，其他模型固定 `false`） |
  | `generationType` | `"FIRST&LAST"` | string | 生成类型；可选值受 methodType 约束（见下表） |
  | `text` | `""` → 取 E-4 提示词 | string | 视频生成提示词，与 `Toby.content` 相同 |
  | `multiPrompt` | `[]` | string[] | 多镜头分镜提示词（仅 `shotType="customize"` 时填） |
  | `negativePrompt` | `""` | string | 反向提示词（仅 methodType ∈ {5,6,7,8,9,14,15,16} 实际生效） |
  | `imageUrlList` | `[]` | string[] | 参考图（仅 `generationType` ∈ {REFERENCE,EDIT,FEATURE} 时填） |
  | `firstImageUrl` | `null` | string\|null | 首帧图（仅 `generationType="FIRST&LAST"` 时填） |
  | `lastImageUrl` | `null` | string\|null | 尾帧图（仅 `generationType="FIRST&LAST"` 且 methodType ∉ {auto,1,8,11,12} 时填） |
  | `firstClipUrl` | `null` | string\|null | 续写/编辑/参考视频（仅 methodType ∈ {10,14} 且 `generationType` ∈ {CONTINUATION,EDIT,FEATURE} 时填） |
  | `elementList` | `[]` | array | 参考主体（仅 methodType=`"10"` 时填） |
  | `videoUrlList` | `[]` | string[] | 参考视频（仅 methodType ∈ {9,16,17,18} 时填） |
  | `audioUrl` | `null` | string\|null | 参考音频单（仅 methodType ∈ {7,8,14,15,16} 时填） |
  | `keepOriginalSound` | `"yes"` | string | 保留视频原声（仅 methodType=`"10"` 时实际生效） |
  | `durationList` | `[]` | array | 多段时长配置 |
  | `mode` | `"pro"` | string | 生成模式（仅 methodType=`"10"` 时实际生效） |
  | `resolution` | `"720p"` | string | 分辨率；可选值受 methodType 约束（见下表） |
  | `ratio` | `"16:9"` | string | 画面比例；可选值受 methodType 约束（见下表） |
  | `generateAudio` | `true` | boolean | 是否生成声音（仅 methodType ∈ {2,5,6,10,17,18} 实际生效） |
  | `enhancePrompt` | `false` | boolean | 是否翻译为英文（仅 methodType ∈ {3,4,5,6} 实际生效） |
  | `n` | `1` | number | 生成数量（仅 methodType ∈ {5,6} 实际生效） |
  | `personGeneration` | `"allow_adult"` | string | 是否允许人物（仅 methodType ∈ {5,6} 实际生效） |
  | `resizeMode` | `"pad"` | string | 图像缩放模式（仅 methodType ∈ {5,6} 实际生效） |
  | `promptExtend` | `false` | boolean | 智能改写（仅 methodType ∈ {7,8,9,14,15,16} 实际生效） |
  | `shotType` | `"single"` | string | 镜头模式；可选值受 methodType 约束（见下表） |
  | `durationSwitch` | `"1"` | string | 生成时长模式（仅 methodType ∈ {2,17,18} 实际生效） |
  | `duration` | 由 methodType 决定，默认 `8`（case `"3"`） | number | 视频时长（秒）；范围与默认值受 methodType 约束（见下表） |
- `videoItems`：固定为 `[]`
- `publishTemplates`：每个选中账号一条，字段：
  - `publishCount`：用户指定（字符串）
  - `releaseType`：固定 `"1"`
  - `timeZone`：固定 `"1"`
  - `intervalType`：固定 `"1"`
  - `startTime`：用户指定（HH:mm）
  - `accountId`：对应账号的 `id`（字符串）
  - `publishInterval`：用户指定（整数，分钟）
- `accountConfigList`：仅一条，取前置 E-2 中第一个选中账号的权限信息，字段：
  - `accountId`：`selectedAccountIds[0]`（字符串）
  - `privacyLevel`：用户选定的隐私级别
  - `disableDuet`：来自 `data.duetDisabled`（布尔转字符串）
  - `disableStitch`：来自 `data.stitchDisabled`
  - `disableComment`：来自 `data.commentDisabled`
  - `expand`：固定 `false`
  - `brandContentToggle`：固定 `"false"`
  - `brandOrganicToggle`：固定 `"false"`
  - `isPublicAccount`：固定 `true`
  - `commentDisabled`：同 `data.commentDisabled`（布尔转字符串）
  - `duetDisabled`：同 `data.duetDisabled`
  - `stitchDisabled`：同 `data.stitchDisabled`

> ⛔ **Toby 结构强约束：**
> 1. 子对象 key 必须是 **`Toby`**（首字母大写、4 个字母原样），不是 `toby` / `TOBY` / `tobyParam` / `tobyParams`。
> 2. 必须嵌在 `collaborationSubmitTaskParam.employeeParams.Toby` 之下。
> 3. **`param` 必须保持为嵌套对象**：所有视频生成参数（`methodType` / `text` / `resolution` / `ratio` / `duration` / `multiShot` / `generationType` / `negativePrompt` / `imageUrlList` / `firstImageUrl` / `lastImageUrl` / `firstClipUrl` / `elementList` / `videoUrlList` / `audioUrl` / `keepOriginalSound` / `durationList` / `mode` / `generateAudio` / `enhancePrompt` / `n` / `personGeneration` / `resizeMode` / `promptExtend` / `shotType` / `durationSwitch` / `multiPrompt`）都是 `param` **对象内部**的键，**禁止**把它们提升到 Toby 根部（错例：`Toby.methodType`、`Toby.text`）。
> 4. `tiktokContent` **不是请求体字段**，它的值要落到 `Toby.content` 与 `Toby.param.text` 两处（同一个字符串），但不得自己再加一个 `tiktokContent` 键。
> 5. `publishTemplates` 必须是数组，每个选中账号一条，每条对象必填 7 个键：`publishCount` / `releaseType` / `timeZone` / `intervalType` / `startTime` / `accountId` / `publishInterval`。
> 6. `accountConfigList` 必须是数组（即使只有一条），每条对象必填 12 个键（见示例）。
> 7. `staffId` 必填，空字符串 `""` 也得给（不得省略此键）。
> 8. `videoItems` 必填，空数组 `[]` 也得给。
> 9. Toby 根部必填 8 个键：`totalTarget` / `incrementalTarget` / `upperLimitTarget` / `content` / `staffId` / `param` / `videoItems` / `publishTemplates` / `accountConfigList`（注意 `param` 内部还有自己的必填子键集）。
> 10. **`param` 27 个键全量传**：即使当前 `methodType` 在 UI 上隐藏了某些字段（如 methodType=`"3"` 时 `audioUrl` / `firstClipUrl` / `elementList` / `videoUrlList` / `mode` / `durationSwitch` / `multiShot` / `negativePrompt` / `keepOriginalSound` / `promptExtend` / `shotType` 等不显），**请求体仍按上表的默认值传值，不得裁剪 key**。后端依赖固定的字段集合做反序列化。

**📐 methodType → 取值约束表（构建 `param` 时必须参照此表选取/校验各依赖字段的合法值）：**

下表中"固定值"列表示该 methodType 下唯一可用值，"可选值"列以英文逗号分隔，"默认值"列为本 SKILL 在用户未指定时的默认选择。

| methodType | 模型 | `generationType` 可选 | `resolution` 可选 | `ratio` 可选 | `duration`（步长/最小/最大/默认） | `shotType` 可选 |
|---|---|---|---|---|---|---|
| `"auto"` | Auto | `FIRST&LAST` | `720p` | `16:9`,`9:16` | 由模型自动决定，**不传 `duration`**（仍保留键，值给默认 `8`） | `single` |
| `"1"` | Sora2 BetaMax | `TEXT`,`FIRST&LAST` | `720p` | `16:9`,`9:16` | step=5, 10–15, 默认 `10` | `single` |
| `"2"` | Seedance1.5 Pro | `TEXT`,`FIRST&LAST` | `480p`,`720p`,`1080p` | `adaptive`,`1:1`,`3:4`,`4:3`,`16:9`,`9:16`,`21:9` | step=1, 4–12, 默认 `4` | `single` |
| `"3"`（**默认**） | Veo3.1 Fast Lite | `TEXT`,`FIRST&LAST`,`REFERENCE` | `720p`,`1080p`,`4K` | `adaptive`,`16:9`,`9:16` | step=1, 8–8, 默认 `8`（**唯一允许 8**） | `single` |
| `"4"` | Veo3.1 Pro Lite | `TEXT`,`FIRST&LAST` | `720p`,`1080p`,`4K` | `adaptive`,`16:9`,`9:16` | step=1, 8–8, 默认 `8` | `single` |
| `"5"` | Veo3.1 Fast | `TEXT`,`FIRST&LAST` | `720p`,`1080p`,`4K` | `adaptive`,`16:9`,`9:16` | step=2, 4–8, 默认 `4` | `single` |
| `"6"` | Veo3.1 Pro | `TEXT`,`FIRST&LAST` | `720p`,`1080p`,`4K` | `adaptive`,`16:9`,`9:16` | step=2, 4–8, 默认 `4` | `single` |
| `"7"` | Wan2.6 t2v | `TEXT` | `720p`,`1080p` | `1:1`,`3:4`,`4:3`,`16:9`,`9:16` | step=1, 3–15, 默认 `3` | `single`,`multi` |
| `"8"` | Wan2.6 i2v | `FIRST&LAST` | `720p`,`1080p` | **不传 `ratio`** | step=1, 3–15, 默认 `3` | `single`,`multi` |
| `"9"` | Wan2.6 r2v | `REFERENCE` | `720p`,`1080p` | `1:1`,`3:4`,`4:3`,`16:9`,`9:16` | step=1, 3–10, 默认 `3` | `single`,`multi` |
| `"10"` | kling-v3-omni | `TEXT`,`FIRST&LAST`,`REFERENCE`,`EDIT`,`FEATURE` | **不传 `resolution`** | `1:1`,`16:9`,`9:16` | step=1, 3–15, 默认 `3` | `single`,`multi`,`customize` |
| `"11"` | Sora2 | `TEXT`,`FIRST&LAST` | `720p` | `16:9`,`9:16` | step=4, 4–12, 默认 `4` | `single` |
| `"12"` | Sora2 Pro | `TEXT`,`FIRST&LAST` | `720p`,`2K` | `16:9`,`9:16`,`7:4`,`4:7` | step=4, 4–12, 默认 `4` | `single` |
| `"14"` | Wan2.7 i2v | `FIRST&LAST`,`CONTINUATION` | `720p`,`1080p` | **不传 `ratio`** | step=1, 3–15, 默认 `3` | `single` |
| `"15"` | Wan2.7 t2v | `TEXT` | `720p`,`1080p` | `1:1`,`3:4`,`4:3`,`16:9`,`9:16` | step=1, 3–15, 默认 `3` | `single` |
| `"16"` | Wan2.7 r2v | `REFERENCE` | `720p`,`1080p` | `1:1`,`3:4`,`4:3`,`16:9`,`9:16` | 有 `videoUrlList` 时 step=1, 3–10；否则 step=1, 3–15；默认 `3` | `single` |
| `"17"` | Seedance2.0 | `TEXT`,`FIRST&LAST`,`REFERENCE` | `480p`,`720p`,`1080p` | `adaptive`,`1:1`,`3:4`,`4:3`,`16:9`,`9:16`,`21:9` | step=1, 4–15, 默认 `4` | `single` |
| `"18"` | Seedance2.0 Fast | `TEXT`,`FIRST&LAST`,`REFERENCE` | `480p`,`720p` | `adaptive`,`1:1`,`3:4`,`4:3`,`16:9`,`9:16`,`21:9` | step=1, 4–15, 默认 `4` | `single` |

> 🔒 **填值硬规则：**
> 1. `generationType` / `resolution` / `ratio` / `shotType` 必须从该 methodType 行内的"可选值"中取，**不得**取该行未列出的值（例如 methodType=`"3"` 时 `ratio` 不得写 `1:1`，`generationType` 不得写 `EDIT`）。
> 2. `duration` 必须落在该行的[最小, 最大]闭区间内，且 `(duration - 最小) % 步长 === 0`；用户未指定时取该行默认值。methodType=`"3"` 时只能是 `8`。
> 3. methodType=`"8"` / `"14"` 时**不传 `ratio` 字段**（请求体里仍保留键，值给默认 `"16:9"`，但后端会忽略）；methodType=`"10"` 时**不传 `resolution` 字段**（同上，键保留、值给默认 `"720p"`）；methodType=`"auto"` 时 `duration` 由后端自动决定（键保留、值给默认 `8`）。即"不传"指**业务上不生效**，结构上**键仍必填**（呼应规则 10：27 个键全量传）。
> 4. 字段间依赖：
>    - `generationType="FIRST&LAST"` → `firstImageUrl` 必填、`lastImageUrl` 必填（除非 methodType ∈ {auto,1,8,11,12} 则 `lastImageUrl` 留 `null`）。
>    - `generationType ∈ {REFERENCE, EDIT, FEATURE}` → `imageUrlList` 至少 1 项。
>    - `generationType ∈ {CONTINUATION, EDIT, FEATURE}` → `firstClipUrl` 必填（仅 methodType ∈ {10,14} 才支持这些类型）。
>    - `shotType="customize"` → `multiPrompt` 至少 1 项；同时 `text` 可留空。
>    - `methodType ∈ {9,16,17,18}` → 视业务需要填 `videoUrlList`。
> 5. 默认 methodType=`"3"` 下，本 SKILL 的合法 `param` 默认快照为：`generationType="FIRST&LAST"`、`resolution="720p"`、`ratio="16:9"`、`duration=8`、`shotType="single"`、`enhancePrompt=false`，其他依赖字段（`firstImageUrl` / `lastImageUrl` / `imageUrlList` / `firstClipUrl` / `videoUrlList` / `audioUrl` / `elementList` / `multiPrompt`）保持空值（`null` 或 `[]`）。

**Toby 任务请求体示例：**
```json
{
  "collaborationSubmitTaskParam": {
    "taskName": "AI宣传视频TikTok分发",
    "taskDescription": "生成库阔AI宣传视频分发到tiktok",
    "executionMode": 1,
    "employeeParams": {
      "Toby": {
        "totalTarget": 1,
        "incrementalTarget": 10,
        "upperLimitTarget": 10,
        "content": "库阔AI宣传视频",
        "staffId": "",
        "param": {
          "methodType": "3",
          "multiShot": false,
          "generationType": "FIRST&LAST",
          "text": "库阔AI宣传视频",
          "multiPrompt": [],
          "negativePrompt": "",
          "imageUrlList": [],
          "firstImageUrl": null,
          "lastImageUrl": null,
          "firstClipUrl": null,
          "elementList": [],
          "videoUrlList": [],
          "audioUrl": null,
          "keepOriginalSound": "yes",
          "durationList": [],
          "mode": "pro",
          "resolution": "720p",
          "ratio": "16:9",
          "generateAudio": true,
          "enhancePrompt": false,
          "n": 1,
          "personGeneration": "allow_adult",
          "resizeMode": "pad",
          "promptExtend": false,
          "shotType": "single",
          "durationSwitch": "1",
          "duration": 8
        },
        "videoItems": [],
        "publishTemplates": [
          {
            "publishCount": "1",
            "releaseType": "1",
            "timeZone": "1",
            "intervalType": "1",
            "startTime": "15:10",
            "accountId": "130",
            "publishInterval": 60
          }
        ],
        "accountConfigList": [
          {
            "accountId": "130",
            "privacyLevel": "PUBLIC_TO_EVERYONE",
            "disableDuet": "false",
            "disableStitch": "false",
            "disableComment": "false",
            "expand": false,
            "brandContentToggle": "false",
            "brandOrganicToggle": "false",
            "isPublicAccount": true,
            "commentDisabled": "false",
            "duetDisabled": "false",
            "stitchDisabled": "false"
          }
        ]
      }
    },
    "sourceSettings": null,
    "currentModule": "content"
  },
  "completed": true
}
```

---

**📋 员工组合 → `currentModule` / `sourceSettings` 对照表**

构建请求体前，按本次任务实际包含的员工组合从下表查 `currentModule` 与 `sourceSettings` 的取值，**严禁自行推断**：

> 🔒 **`currentModule` 全局固定为 `"content"`**：无论员工组合是哪种、是否含销售员工、是否含 Toby，`currentModule` 字段都是字符串字面量 `"content"`，**不得**写成 `"analysis"` / `"Content"` / `"CONTENT"` / `null` / 省略。

| 员工组合 | `currentModule` | `sourceSettings` | 备注 |
|---|---|---|---|
| 仅 AiWa | `"content"` | `null` | 单纯客户挖掘 |
| 仅 Toby | `"content"` | `null` | 单纯 TikTok 发布 |
| AiWa + Toby | `"content"` | `null` | 挖客户 + 同步 TikTok 发布 |
| AiWa + Frank | `"content"` | `null` | 挖客户 + 邮件销售 |
| AiWa + Fran | `"content"` | 完整 sourceSettings 对象（见 Fran 示例） | 挖客户 + 电话销售 |
| AiWa + Lisa | `"content"` | 完整 sourceSettings 对象（见 Lisa 示例） | 挖客户 + 短信销售 |
| AiWa + Frank + Fran | `"content"` | 完整 sourceSettings 对象 | 多通道销售 |
| AiWa + Frank + Lisa | `"content"` | 完整 sourceSettings 对象 | 多通道销售 |
| AiWa + Fran + Lisa | `"content"` | 完整 sourceSettings 对象 | 多通道销售 |
| AiWa + Frank + Fran + Lisa | `"content"` | 完整 sourceSettings 对象 | 全通道销售 |
| AiWa + Frank + Toby | `"content"` | `null` | 邮件销售 + TikTok |
| AiWa + Fran + Toby | `"content"` | 完整 sourceSettings 对象 | 电话销售 + TikTok |
| AiWa + Lisa + Toby | `"content"` | 完整 sourceSettings 对象 | 短信销售 + TikTok |

> 🔍 **快速判定规则**：
> - `currentModule` 始终为 `"content"`（无任何例外分支）。
> - 含 `Fran` 或 `Lisa` → `sourceSettings` **必须是完整对象**（不能为 `null`）；
> - 不含 `Fran` 也不含 `Lisa` → `sourceSettings` 为 `null`。

> 🚫 **组合场景常见错例：**
>
> 1. 仅 AiWa / 仅 Toby / AiWa+Toby 任务把 `currentModule` 写成 `"analysis"`：错。**任何组合**都必须 `"content"`。
> 2. AiWa+Fran 联合任务把 `sourceSettings` 写成 `null`：错。含 Fran 必须填完整对象。
> 3. AiWa+Toby 联合任务把 `sourceSettings` 写成 `{}`：错。应为 `null`。
> 4. 多员工组合时把不同员工塞进同一个员工 key（如 `employeeParams.AiWaFrank: {...}`）：错。每个员工是 `employeeParams` 下独立的同级 key。
> 5. 多员工组合时漏掉某个员工的子对象（仅在 `employeeList` 字符串里出现，但 `employeeParams` 里没有对应键）：错。`employeeList` 里写了的员工，`employeeParams` 必须有对应子对象。

---

**⚠️ 提交前必须执行参数完整性校验（缺少任意一项禁止提交）**

> 🔒 **第 0 步（前置硬闸）：字段名逐键对位检查**
> 把刚构建好的 `body` JSON 字符串和本文件对应员工的示例 JSON 并排放置，**逐键比对拼写**：
> 1. 示例里出现的每一个键名（含 `taskName`、`taskDescription`、`executionMode`、`employeeParams`、`sourceSettings`、`currentModule`、`completed`，以及各员工子对象内部的全部 key），在 body 中必须**原样存在**，不得改写大小写、不得改 snake_case、不得改单复数、不得换同义词。
> 2. 任何键名只要与示例不一致（哪怕只差一个字母大小写），立即停止提交，回头修正后再走本清单。
> 3. 这一步在所有员工字段值校验之前完成，因为字段名错了，值再对也没用。

根据本次任务包含的员工，逐项对照以下清单检查构建好的请求体，确认每个字段都存在且有合法值：

**根结构（必须）：**
- `collaborationSubmitTaskParam.taskName`：非空字符串
- `collaborationSubmitTaskParam.taskDescription`：非空字符串
- `collaborationSubmitTaskParam.executionMode`：**当前阶段一律硬编码为数字 `1`**（即使 Step 1 识别为周期性任务也写 1；不得写 `0` / `2` / `"1"` / `"定额任务"`）
- `collaborationSubmitTaskParam.employeeParams`：对象，包含至少一个员工
- `collaborationSubmitTaskParam.sourceSettings`：取值严格按上文「员工组合 → `currentModule` / `sourceSettings` 对照表」填（**不要在这里推断**）。快速规则：含 `Fran` 或 `Lisa` → 完整对象；不含 `Fran` 也不含 `Lisa` → `null`
- `collaborationSubmitTaskParam.currentModule`：**全局固定为字符串 `"content"`**，无任何例外（不得写 `"analysis"` / `"Content"` / `null`）
- `completed`：**必传**，布尔字面量 `true`，与 `collaborationSubmitTaskParam` 同级；不得为 `null`、缺省、字符串 `"true"` 或 `false`，否则接口返回 500

**AiWa（当 employeeList 包含 AiWa 时）：**
- `totalTarget`：用户指定的目标数量（正整数）
- `incrementalTarget`：`5000`
- `upperLimitTarget`：`5000`
- `keywordList`：非空数组
- `continent`：字符串或 `null`
- `country`：字符串或 `null`
- `countryCodeList`：数组（可为空数组 `[]`）
- `addressObjList`：包含至少一个对象，每个对象含 `type`/`province`/`city`/`county`/`address` 五个字段
- `industryList`：非空数组

**Frank（当 employeeList 包含 Frank 时）：**
- `incrementalTarget`：`1000`
- `upperLimitTarget`：`1000`
- `senderEmail`：来自 profile 的 email，非空字符串
- `language`：`"中文"` 或 `"英文"`
- `templateId`：`null`
- `emailPlanList`：包含一个对象，该对象必须含以下四个字段：
  - `delayDay`：`0`
  - `emailSubject`：AI 生成的主题，非空字符串
  - `emailText`：AI 生成的正文 HTML，非空字符串
  - `loading`：`0`

**Fran（当 employeeList 包含 Fran 时）：**
- `ringingDuration`：`25`
- `incrementalTarget`：`1000`
- `upperLimitTarget`：`1000`
- `minConcurrency`：`1`
- `priority`：`"Daily"`
- `callingNumber`：非空数组，来自号码池选择
- `scriptId`：非空字符串，来自场景库选择
- `agentProfileId`：非空字符串，来自 `data.chatbotIdList[0]`

**Lisa（当 employeeList 包含 Lisa 时）：**
- `incrementalTarget`：`100`
- `upperLimitTarget`：`100`
- `signName`：非空字符串，来自模板 `signatureName`
- `qualificationName`：非空字符串，与 `signName` 相同
- `templateCode`：非空字符串，来自模板 `templateCode`
- `templateContent`：非空字符串，来自模板 `templateContent`
- `templateType`：数字，来自模板 `outerTemplateType`
- `templateParamList`：数组（无变量时为 `[]`，不可缺少此字段）

**Toby（当 employeeList 包含 Toby 时）：**
- `totalTarget`：定额模式下为正整数，周期模式下为 null
- `incrementalTarget`：正整数
- `upperLimitTarget`：`10`
- `content`：非空字符串，来自 `tiktokContent`
- `staffId`：空字符串 `""`
- `param`：嵌套对象，**全量 27 个键齐全**（按 Step 3「Toby 参数构建规则」表中默认值快照填充，未指定 methodType 时全部按 methodType=`"3"` 默认快照传）
- `param.methodType`：非空字符串，默认 `"3"`；若用户切换模型，必须从 E-3 接口拿到的 `sourceValue` 取值
- `param.text`：非空字符串（与 `Toby.content` 同值）
- `param.generationType` / `resolution` / `ratio` / `duration` / `shotType`：取值必须与 `param.methodType` 在「methodType → 取值约束表」内的可选值完全匹配，否则停止提交并校正
- `publishTemplates`：非空数组，每个账号一条，且 `publishCount`/`startTime`/`publishInterval`/`accountId` 均非空
- `accountConfigList`：包含且仅一条，`accountId`/`privacyLevel` 非空

> ⚠️ **`sourceSettings` 与 `currentModule` 是根级字段，取值取决于本次任务的员工组合，请查阅上文「员工组合 → `currentModule` / `sourceSettings` 对照表」，不能因为含 Toby 就一律写成 `null`/`"analysis"`。**例如 `AiWa+Lisa+Toby` 时，`sourceSettings` 必须是完整对象、`currentModule` 为 `"content"`。

**发现任何字段缺失或值不合法时，停止提交，先补全后再执行提交。**

**🔒 强制提交：直接走 `scripts/submit_task.py`（一站式：校验 + UTF-8 安全 HTTP）**

`submit_task.py` 已串联以下三件事，**LLM 只需调一次**即可完成"校验 + 提交"，不需要再单独调 `validate_employee_params.py` 或 `validate_sms_template_params.py`：

1. 内部调用 `validate_employee_params.py`（结构 + 取值，覆盖 AiWa/Frank/Fran/Lisa/Toby 全员）
2. 含 Lisa 模板变量时，自动调用 `validate_sms_template_params.py` 做内容校验
3. 任一步校验失败立即退出（退出码 1），**不会**触发 HTTP 提交
4. 校验全过才以 `Content-Type: application/json; charset=utf-8` POST 到 `/ai/presetEmployee/submitTask`

```bash
python3 scripts/submit_task.py <<'TASK_BODY_EOF'
{
  "completed": true,
  "collaborationSubmitTaskParam": { ...完整请求体... }
}
TASK_BODY_EOF
```

**校验覆盖范围**（详见 `validate_employee_params.py` / `validate_sms_template_params.py` 源码）：
- Step 1/2 内部变量（`employeeList` / `language` / `tiktokContent` / 根级 `totalTarget`）泄漏到根或 `collaborationSubmitTaskParam` 层
- 员工 key 大小写错（`aiwa` / `aiwaParam` / `franParam` 等都会被纠错为 PascalCase）
- `executionMode` 必须是数字 `1`（拦截 `"1"` / `true` / `"定额任务"` 等）
- `currentModule` 必须固定为 `"content"`；含 `Fran`/`Lisa` 时 `sourceSettings` 必须是完整对象
- 各员工必填键、固定值（如 AiWa.incrementalTarget=5000、Frank.upperLimitTarget=1000、Fran.priority="Daily"、Lisa.incrementalTarget=100、Toby.upperLimitTarget=10）
- 数组类字段类型（`keywordList` / `industryList` / `countryCodeList` / `callingNumber` / `templateParamList` / `publishTemplates` / `accountConfigList`）
- AiWa.addressObjList 占位规则与 `type=0/1` 与 `address` / `province/city/county` 的互斥
- Frank.emailPlanList 长度恰为 1 与子键完整
- Lisa.templateParamList 数组结构 + 每项三键齐全 + 变量内容合规（如 `time` 类禁止含中文"年"）
- Toby.param 必须包含全部 27 个键、`methodType` 与 `generationType` / `resolution` / `ratio` / `duration` / `shotType` 的依赖关系（依据「methodType → 取值约束表」）

**行为约束：**
- **必须**用 heredoc + 单引号定界符（`<<'TASK_BODY_EOF'`），不能用 argv 传 JSON。
- 脚本输出单行 JSON（含 `summary` / `errors` / `body_preview` / `response`）。
- 退出码：`0` 提交成功 / `1` 校验失败 / `2` 网络失败 / `3` HTTP 非 2xx / `4` 输入格式错误或 API key 缺失。
- 退出码 ≠ 0 时，**必须**把 `summary`、`errors`/`response` 原样回给用户，按提示修正请求体再重跑；**不允许**跳过校验、不允许"我这次写得很标准"为由绕过。

> ℹ️ 仅在排查时可先用 `python3 scripts/submit_task.py --dry-run <<'TASK_BODY_EOF' ...` 跑校验而不发 HTTP；正式提交禁止 `--dry-run`。

**用户确认清单（以下各项必须已获得用户明确确认，缺一不可提交）：**
- Fran 参与时：✅ `callingNumber` 非空（多号码时用户已选择）
- Fran 参与时：✅ 用户已选择/确认场景库（`scriptId` 非空，且用户有明确回复确认）
- Lisa 参与时：✅ 用户已选择/确认短信模板（`templateCode` 非空，且用户有明确回复确认）
- Lisa 参与时（模板含变量）：✅ 已通过 `scripts/submit_task.py` 完成提交（脚本内部已串行跑过 `validate_employee_params.py` + `validate_sms_template_params.py`）；脚本退出码 ≠ 0 时禁止重试，必须把脚本返回的 `summary`/`errors` 原样回给用户、修正后再重跑。**禁止**绕过 `submit_task.py` 自己拼 curl。**特别注意 `time` 类变量**——值中**不得**出现中文"年"，脚本会直接拒绝
- Frank 参与时：✅ 用户 profile 已获取（`senderEmail` 非空），邮件内容已 AI 生成
- Toby 参与时：✅ 用户已选择/确认 TikTok 账号（`selectedAccountIds` 非空）
- Toby 参与时：✅ 用户已确认或修改视频生成提示词（`content` 已确定）
- Toby 参与时：✅ 用户已为每个账号填写 `publishCount`、`startTime`、`publishInterval`
- Toby 参与时：✅ 用户已选择隐私级别（`privacyLevel` 非空）

**若上述任一项未完成，禁止调用提交接口。**

---

**请求体示例（AiWa + Frank 联合任务）：**
```json
{
  "collaborationSubmitTaskParam": {
    "taskName": "找服装客户并发邮件",
    "taskDescription": "帮我找10个做服装的客户并发邮件",
    "executionMode": 1,
    "employeeParams": {
      "AiWa": {
        "totalTarget": 10,
        "incrementalTarget": 5000,
        "upperLimitTarget": 5000,
        "keywordList": ["服装", "clothing"],
        "continent": null,
        "country": null,
        "countryCodeList": [],
        "addressObjList": [{"type": 1, "province": "", "city": "", "county": "", "address": ""}],
        "industryList": ["服装"]
      },
      "Frank": {
        "incrementalTarget": 1000,
        "upperLimitTarget": 1000,
        "senderEmail": "{profile.email}",
        "language": "中文",
        "templateId": null,
        "emailPlanList": [{
          "delayDay": 0,
          "emailSubject": "{AI生成的邮件主题}",
          "emailText": "{AI生成的邮件正文HTML}",
          "loading": 0
        }]
      }
    },
    "sourceSettings": null,
    "currentModule": "content"
  },
  "completed": true
}
```

**成功响应：**
```json
{
  "msg": "操作成功",
  "code": 200,
  "data": {
    "employeeList": [
      {
        "dagTaskId": "<frankDagTaskId>",
        "nodeType": "FRANK",
        "customerPoolId": 1065
      },
      {
        "dagTaskId": "<aiwaDagTaskId>",
        "nodeType": "AIWA",
        "customerPoolId": 1066
      }
    ],
    "taskId": "<taskId>"
  }
}
```

**响应字段提取规则：**
- `taskId`：取 `data.taskId`
- `aiwaDagTaskId`：遍历 `data.employeeList`，找到 `nodeType === "AIWA"` 的条目，取其 `dagTaskId`，用于 **AiWa** 客户查询；无则为 null
- `aiwaCustomerPoolId`：遍历 `data.employeeList`，找到 `nodeType === "AIWA"` 的条目，取其 `customerPoolId`，用于 **AiWa** 客户查询；无则为 null
- `frankDagTaskId`：遍历 `data.employeeList`，找到 `nodeType === "FRANK"` 的条目，取其 `dagTaskId`，用于 **Frank** 邮件查询；无则为 null
- `franDagTaskId`：遍历 `data.employeeList`，找到 `nodeType === "FRAN"` 的条目，取其 `dagTaskId`，用于 **Fran** 电话查询；无则为 null
- `franCustomerPoolId`：遍历 `data.employeeList`，找到 `nodeType === "FRAN"` 的条目，取其 `customerPoolId`，用于 **Fran** 电话统计/详情查询；无则为 null
- `lisaDagTaskId`：遍历 `data.employeeList`，找到 `nodeType === "LISA"` 的条目，取其 `dagTaskId`，用于 **Lisa** 短信查询；无则为 null
- `lisaCustomerPoolId`：遍历 `data.employeeList`，找到 `nodeType === "LISA"` 的条目，取其 `customerPoolId`，用于 **Lisa** 短信统计/详情查询；无则为 null
- `tobyDagTaskId`：遍历 `data.employeeList`，找到 `nodeType === "TOBY"` 的条目，取其 `dagTaskId`，用于 **Toby** 任务查询；无则为 null
- `tobyCustomerPoolId`：遍历 `data.employeeList`，找到 `nodeType === "TOBY"` 的条目，取其 `customerPoolId`，用于 **Toby** 视频统计/列表查询；无则为 null

> ⚠️ **`nodeType` 大写统一**：后端返回的 `nodeType` 是**全大写**（`AIWA` / `FRANK` / `FRAN` / `LISA` / `TOBY`），不是 PascalCase 的 `AiWa` / `Frank` 。上面 5 条提取规则里的字符串只能是大写形式。如果某次调用发现某个员工总拿不到 `dagTaskId`，优先检查是不是这里的大写写错了。

提交成功后，告知用户并询问等待时间：
> 任务已提交！任务名：{taskName}，目标数量：{totalTarget}，任务ID：{taskId}。
>
> 后台正在执行，**你希望多久后查询结果并推送给你？**（直接告诉我时间，例如「8分钟」「半小时」「20分钟后」，直接回复「好」或不填则默认8分钟）

---

### Step 3.5：解析用户指定的等待时间

等待用户回复后，解析其意图为秒数：

| 用户说 | 解析为秒数 |
|--------|----------|
| N分钟 / N分 | N × 60 |
| N小时 | N × 3600 |
| 半小时 | 1800 |
| 一刻钟 | 900 |
| 好 / 默认 / ok / 回车 / 不填 | 480（8分钟）|
| 无法识别 | 再询问一次，若仍无效则使用 480 |

解析成功后，回复确认：
> 好的，将在 {用户指定时间描述}（约 {N} 分钟）后为你查询结果，请稍候 ☕

---

### Step 4：按用户指定时间设置自动查询

根据 Step 3.5 解析出的秒数（变量：`waitSeconds`），使用 `cron` 工具设置一次性定时任务：

```json
{
  "action": "add",
  "job": {
    "name": "aiwa-query-{taskId前8位}",
    "schedule": { "kind": "at", "at": "{当前时间 + waitSeconds 的ISO8601字符串，如2026-03-19T15:00:00+08:00}" },
    "sessionTarget": "main",
    "wakeMode": "now",
    "payload": {
      "kind": "systemEvent",
      "text": "[DeepSOP-AutoQuery] 人机协作台定时结果推送，请立即跳转 Step 5 执行结果查询并主动推送，不要等待用户提问，不要执行 Step 1-4。taskId={taskId}，aiwaDagTaskId={aiwaDagTaskId}，aiwaCustomerPoolId={aiwaCustomerPoolId}，frankDagTaskId={frankDagTaskId}，franDagTaskId={franDagTaskId}，franCustomerPoolId={franCustomerPoolId}，lisaDagTaskId={lisaDagTaskId}，lisaCustomerPoolId={lisaCustomerPoolId}，tobyDagTaskId={tobyDagTaskId}，tobyCustomerPoolId={tobyCustomerPoolId}，任务名：{taskName}，目标数量：{totalTarget}，参与员工：{employeeList}，feishuChatId={feishuChatId}。【AiWa部分，仅当employeeList包含AiWa时执行】1. 调用 POST https://ai.deepsop.com/prod-api/ai/presetEmployee/getCustomerPoolDetail?pageNum=1&pageSize=10 查询结果，参数 {"taskId":"{aiwaDagTaskId}","customerPoolId":{aiwaCustomerPoolId},"startTime":null,"endTime":null}；2. 将完整响应JSON传给脚本生成xlsx：python3 ~/.openclaw/workspace/skills/deepsop-human-ai-collab/scripts/format_customers.py '<JSON>' '/tmp/aiwa_{aiwaDagTaskId前8位}.xlsx'；3. 执行 cp /tmp/aiwa_{aiwaDagTaskId前8位}.xlsx ~/.openclaw/workspace/aiwa_{aiwaDagTaskId前8位}.xlsx 并执行 openclaw message send --channel feishu --target {feishuChatId} --media ~/.openclaw/workspace/aiwa_{aiwaDagTaskId前8位}.xlsx --message 'AiWa 客户挖掘完成，共找到客户数据，详见附件' 将文件发送到飞书群；4. 同时在当前会话回复前5条客户摘要。【Toby部分，仅当employeeList包含Toby且tobyDagTaskId不为null时执行】1. 调用 GET https://ai.deepsop.com/prod-api/ai/data/count?taskId={tobyDagTaskId}&customerPoolId={tobyCustomerPoolId}&platform=1 查询统计；2. 调用 GET https://ai.deepsop.com/prod-api/ai/data/list?pageNum=1&pageSize=10&taskId={tobyDagTaskId}&customerPoolId={tobyCustomerPoolId}&platform=1 查询视频列表；3. 展示统计数据（播放、点赞、评论、分享、发布总数）并列出每条视频的titleName、platformUrl、播放量、点赞数、评论数、转发数、displayCreateTime；4. 在当前会话回复结果摘要。【Frank部分，仅当employeeList包含Frank且frankDagTaskId不为null时执行】1. 调用 GET https://ai.deepsop.com/prod-api/ai/email/getTaskEmailCount?taskId={frankDagTaskId} 查询邮件统计（使用frankDagTaskId）；2. 调用 GET https://ai.deepsop.com/prod-api/ai/email/taskList?pageNum=1&pageSize=2000&taskId={frankDagTaskId} 查询邮件列表（使用frankDagTaskId）；3. 生成xlsx：python3 ~/.openclaw/workspace/skills/deepsop-human-ai-collab/scripts/format_emails.py '<JSON>' '/tmp/frank_{frankDagTaskId前8位}.xlsx'；4. 执行 cp /tmp/frank_{frankDagTaskId前8位}.xlsx ~/.openclaw/workspace/frank_{frankDagTaskId前8位}.xlsx 并执行 openclaw message send --channel feishu --target {feishuChatId} --media ~/.openclaw/workspace/frank_{frankDagTaskId前8位}.xlsx --message 'Frank 邮件发送完成，详见附件' 将文件发送到飞书群；5. 同时在当前会话回复邮件统计摘要和前5条详情。【Lisa部分，仅当employeeList包含Lisa且lisaCustomerPoolId不为null时执行】1. 调用 POST https://ai.deepsop.com/prod-api/ai/sms/getTaskSmsCount 查询短信统计，参数 {"taskId":"{taskId}","customerPoolId":{lisaCustomerPoolId}}；2. 调用 POST https://ai.deepsop.com/prod-api/ai/sms/getSmsResultList?pageNum=1&pageSize=10 查询短信列表，参数 {"taskId":"{taskId}","customerPoolId":{lisaCustomerPoolId},"success":null,"startTime":null,"endTime":null}；3. 生成xlsx：python3 ~/.openclaw/workspace/skills/deepsop-human-ai-collab/scripts/format_sms.py '<JSON>' '/tmp/lisa_{taskId前8位}.xlsx'；4. 发送文件并在当前会话展示短信统计摘要和前5条短信详情。【Toby部分，仅当employeeList包含Toby且tobyDagTaskId不为null时执行】1. 调用 GET https://ai.deepsop.com/prod-api/ai/data/count?taskId={tobyDagTaskId}&customerPoolId={tobyCustomerPoolId}&platform=1 查询视频统计；2. 调用 GET https://ai.deepsop.com/prod-api/ai/data/list?pageNum=1&pageSize=10&taskId={tobyDagTaskId}&customerPoolId={tobyCustomerPoolId}&platform=1 查询视频列表；3. 在当前会话回复统计概览（发布视频数/播放/点赞/评论/分享）并列出每条视频的标题、链接、各项数据及发布时间。"
    },
    "deleteAfterRun": true
  }
}
```

`schedule.at` = 当前时间 + `waitSeconds`，ISO8601 格式，含时区（如 `+08:00`）。

cron 设置成功后，回复用户确认并进入等待状态：
> ✅ 定时任务已设置！将在 **{N} 分钟后**（{schedule.at}）自动查询结果并推送，请安心等候 ⏰
> 如需提前查询，可说「现在就查结果」，我会立即执行。

> ⚠️ **等待期间处理规则**：
> - cron 设置完成到 [DeepSOP-AutoQuery] 到达之前，**不得主动执行 Step 5**。
> - 如果用户在等待期间间起其他话题，正常回应，但**不要提前查询结果**。
> - 如果用户说「现在就查结果」或「提前查」，立即执行 Step 5（此为唯一允许的提前触发方式）。

---

### Step 5：查询结果并返回给用户

> � **触发锁定：Step 5 只允许在以下两种情况下执行，其他任何情况一律不执行：**
> 1. 收到含 `[DeepSOP-AutoQuery]` 标记的 systemEvent（cron 自动触发）
> 2. 用户在等待期间明确说「现在就查结果」或「提前查」
>
> 🚨 **强制执行规则：执行 Step 5 时，以下规则一条都不得违反：**
> 1. **立即开始执行，不得发出任何询问或确认语句（如「要开始查询了吗」「是否需要推送」）**
> 2. **必须完成全流程：调接口 → 生成 xlsx → 发送文件 → 文字摘要，缺任一不算完成**
> 3. **文件必须透过 `openclaw message send` 主动发送到对应 channel，不得只告知文件路径**
> 4. **发送完成后在当前会话回复结果摘要，让用户对当前分话框也能看到结果**
> 5. **每个参与员工的结果必须按顺序全部处理，不得跳过任一员工**

根据 employeeList 包含的员工依次执行对应的 Step 5-A / 5-B / 5-C / 5-D / 5-E。

---

#### Step 5-A：AiWa 结果处理（仅当 employeeList 包含 AiWa）

> ⚠️ AiWa 查询接口使用 `aiwaDagTaskId`（`nodeType=AIWA` 的 `dagTaskId`）+ `aiwaCustomerPoolId`（同条目的 `customerPoolId`）。

**接口：** `POST https://ai.deepsop.com/prod-api/ai/presetEmployee/getCustomerPoolDetail?pageNum=1&pageSize=10`

**请求头：** `Content-Type: application/json`、`x-api-key: $DEEPSOP_API_KEY`

**请求体：**
```json
{"taskId": "{aiwaDagTaskId}", "customerPoolId": {aiwaCustomerPoolId}, "startTime": null, "endTime": null}
```

**响应关键字段：**
- `total`：总条数
- `rows[]`：客户列表（根层）
  - `personName` / `position`：联系人 / 职位
  - `companyName`：公司名称
  - `systemIndustryName`：标准化行业名称
  - `phone` / `email`：电话 / 邮筱（多个用逗号分隔）
  - `countryName`：国家（如 `中国/China`）
  - `whatsapp` / `linkedin` / `facebook` 等社媒字段
  - `url`：公司网址

**情况一：有数据（rows 非空）**

1. 将完整 API 响应 JSON 传给脚本生成 xlsx 文件：

```bash
python3 ~/.openclaw/workspace/skills/deepsop-human-ai-collab/scripts/format_customers.py '<完整响应JSON>' '/tmp/aiwa_{aiwaDagTaskId前8位}.xlsx'
```

2. 根据当前 channel 决定如何返回文件：

**飞书（feishu）：** 必须执行，不得跳过
```bash
cp /tmp/aiwa_{aiwaDagTaskId前8位}.xlsx ~/.openclaw/workspace/aiwa_{aiwaDagTaskId前8位}.xlsx
openclaw message send --channel feishu --target {feishuChatId} --media ~/.openclaw/workspace/aiwa_{aiwaDagTaskId前8位}.xlsx --message 'AiWa 客户挖掘完成！任务「{taskName}」共找到 {total} 位客户，详情见附件。'
```

**Telegram / WhatsApp：** 必须执行，不得跳过
```
openclaw message send --channel telegram --target {chat_id} --media ~/.openclaw/workspace/aiwa_{aiwaDagTaskId前8位}.xlsx --message 'AiWa 客户挖掘完成！任务「{taskName}」共找到 {total} 位客户，详情见附件。'
```

**webchat 或其他不支持文件的 channel：**
> ✅ xlsx 文件已生成：`/tmp/aiwa_{aiwaDagTaskId前8位}.xlsx`，共 {total} 位客户。请从服务器下载该文件。

3. 同时以文字形式展示前5条客户预览：

```
序号. 👤 {personName}（{position}）
   🏢 公司：{companyName}
   🏭 行业：{systemIndustryName}
   🌍 国家：{countryName}
   📧 邮筱：{email}
   📱 手机：{phone}
   💬 WhatsApp：{whatsapp}
   🔗 LinkedIn：{linkedin}
```

社媒字段若为 null 则整行不显示。超过5条附上：`...共 {N} 位，完整数据见 xlsx 文件`

**情况二：rows 为空或 code 非 200**

> 已到查询时间，暂未获取到客户数据，任务可能仍在执行中。
> aiwaDagTaskId：{aiwaDagTaskId}，aiwaCustomerPoolId：{aiwaCustomerPoolId}
> 你可以告诉我「再查一次」，我会立即重新查询。

---

#### Step 5-C：Fran 结果处理（仅当 employeeList 包含 Fran 且 franDagTaskId 不为 null）

> ⚠️ Fran 的两个查询接口均使用 `franDagTaskId`（来自 `data.employeeList` 中 `nodeType=Fran` 的 `dagTaskId`）+ `franCustomerPoolId`（同条目的 `customerPoolId`）。

**第一步：查询电话任务统计**

接口：`GET https://ai.deepsop.com/prod-api/ai/presetEmployee/collaborationTaskStatistics?taskId={franDagTaskId}&customerPoolId={franCustomerPoolId}`

请求头：`x-api-key: $DEEPSOP_API_KEY`

返回字段说明：
- `taskCallPhoneCount`：总呼叫数
- `taskSuccessCallPhoneCount`：总通话数（接通并成功完成的数量）
- `taskAnswerCount`：总回复数

**第二步：查询电话任务详情列表**

接口：`POST https://ai.deepsop.com/prod-api/ai/presetEmployee/collaborationCallResult?pageNum=1&pageSize=10`

请求头：
```
Content-Type: application/json
x-api-key: $DEEPSOP_API_KEY
```

请求体（默认拉全部呼叫，`status` 可根据需求切换）：
```json
{
  "taskId": "{franDagTaskId}",
  "customerPoolId": {franCustomerPoolId},
  "status": "All",
  "startTime": "",
  "endTime": ""
}
```

`status` 可选值：
- `All`：全部呼叫（默认，对应 `taskCallPhoneCount`）
- `Succeeded`：通话成功记录（对应 `taskSuccessCallPhoneCount`）
- `Answer`：有回复记录（对应 `taskAnswerCount`）

响应关键字段：
- `rows[].jobStatus`：呼叫任务状态（如 `Succeeded`、`Failed`）
- `rows[].jobTaskStatus`：任务执行细分状态（如 `SucceededFinish`）
- `rows[].companyName` / `personName` / `phoneNumber` / `userName`：客户信息（可能为 null）
- `rows[].createTime` / `updateTime`：创建/更新时间
- `rows[].describeJobJson`：完整通话详情 JSON（字符串，需二次解析），关键内容在 `body.job.tasks[]`：
  - `contact.contactName` / `phoneNumber`：联系人与号码
  - `calledNumber` / `callingNumber`：被呼号 / 呼出号
  - `duration` / `realRingingDuration`：通话时长毫秒 / 实际振铃秒
  - `endReason`：挂断原因（如 `FINISHED`）
  - `conversation[]`：对话明细（`speaker`=`Robot`/`Contact`，`script`=话术内容）

**第三步：生成 xlsx 文件**

```bash
curl 结果存 /tmp/fran_{franDagTaskId前8位}_raw.json
python3 ~/.openclaw/workspace/skills/deepsop-human-ai-collab/scripts/format_calls.py "$(cat /tmp/fran_{franDagTaskId前8位}_raw.json)" '/tmp/fran_{franDagTaskId前8位}.xlsx'
```

根据当前 channel 必须发送文件，不得跳过：
- **飞书**：必须执行 `cp /tmp/fran_{franDagTaskId前8位}.xlsx ~/.openclaw/workspace/fran_{franDagTaskId前8位}.xlsx`，再用 `openclaw message send --channel feishu --target {feishuChatId} --media ~/.openclaw/workspace/fran_{franDagTaskId前8位}.xlsx --message 'Fran 电话销售完成！任务「{taskName}」共呼叫 {taskCallPhoneCount} 人，详情见附件。'`
- **Telegram / WhatsApp**：必须执行，media 路径用 workspace 路径，message 同上
- **webchat**：输出文字摘要和文件路径 `/tmp/fran_{franDagTaskId前8位}.xlsx`

**第四步：展示结果**

先展示统计摘要：
```
☎️ Fran 电话销售任务结果 — {taskName}

📊 呼叫统计：
   📞 总呼叫数：{taskCallPhoneCount}
   ✅ 总通话数：{taskSuccessCallPhoneCount}
   💬 总回复数：{taskAnswerCount}
```

再展示列表中前 5 条呼叫详情（从 `rows[].describeJobJson` 解析）：
```
序号. 👤 {contactName}（{contactPhone}）
   🔄 状态：{jobStatus} / {endReason}
   ⏱ 通话时长：{duration_s}s（振铃 {realRingingDuration}s）
   📞 呼出号码：{callingNumber}
   📝 对话摘要：取 conversation 中第一条 Robot 的 script 前80字
```

超过 5 条附上：`...共 {total} 条通话记录，完整数据见 xlsx 文件`。

**情况：统计接口全为 0 或列表为空**

> Fran 电话任务数据暂未就绪，可能仍在拨号或已呼叫但未接通。
> franDagTaskId：{franDagTaskId}，franCustomerPoolId：{franCustomerPoolId}
> 你可以告诉我「再查Fran结果」，我会立即重新查询。

---

#### Step 5-D：Lisa 结果处理（仅当 employeeList 包含 Lisa 且 lisaDagTaskId 不为 null）

> ⚠️ Lisa 的两个查询接口均使用 `lisaDagTaskId`（来自 `data.employeeList` 中 `nodeType=Lisa` 的 `dagTaskId`）+ `lisaCustomerPoolId`（同条目的 `customerPoolId`）。

**第一步：查询短信任务统计**

接口：`POST https://ai.deepsop.com/prod-api/ai/sms/getTaskSmsCount`

请求头：`Content-Type: application/json`、`x-api-key: $DEEPSOP_API_KEY`

请求体：
```json
{"taskId": "{lisaDagTaskId}", "customerPoolId": {lisaCustomerPoolId}}
```

返回字段说明：
- `totalCount`：已发送短信数
- `successCount`：触达短信数（发送成功）
- `failCount`：失败短信数

**第二步：查询短信详情列表**

接口：`POST https://ai.deepsop.com/prod-api/ai/sms/getSmsResultList?pageNum=1&pageSize=10`

请求头：
```
Content-Type: application/json
x-api-key: $DEEPSOP_API_KEY
```

请求体：
```json
{"taskId": "{lisaDagTaskId}", "customerPoolId": {lisaCustomerPoolId}, "success": null, "startTime": null, "endTime": null}
```

关键字段：
- `data.total`：总条数
- `data.rows[].phoneNumber`：手机号码
- `data.rows[].success`：1=发送成功，0=发送失败
- `data.rows[].errMsg`：状态描述（如「用户接收成功」）
- `data.rows[].errCode`：状态码（如 `DELIVERED`）
- `data.rows[].content`：实际发送的短信内容
- `data.rows[].smsSize`：短信条数
- `data.rows[].sendTime`：发送时间
- `data.rows[].reportTime`：回执时间

**第三步：生成 xlsx 文件**

```bash
curl 结果存 /tmp/lisa_{lisaDagTaskId前8位}_raw.json
python3 ~/.openclaw/workspace/skills/deepsop-human-ai-collab/scripts/format_sms.py "$(cat /tmp/lisa_{lisaDagTaskId前8位}_raw.json)" '/tmp/lisa_{lisaDagTaskId前8位}.xlsx'
```

根据当前 channel 必须发送文件，不得跳过：
- **飞书**：必须执行 `cp /tmp/lisa_{lisaDagTaskId前8位}.xlsx ~/.openclaw/workspace/lisa_{lisaDagTaskId前8位}.xlsx`，再用 `openclaw message send --channel feishu --target {feishuChatId} --media ~/.openclaw/workspace/lisa_{lisaDagTaskId前8位}.xlsx --message 'Lisa 短信发送完成！任务「{taskName}」共发送 {totalCount} 条，详情见附件。'`
- **Telegram / WhatsApp**：必须执行，media 路径用 workspace 路径，message 同上
- **webchat**：输出文字摘要和文件路径 `/tmp/lisa_{lisaDagTaskId前8位}.xlsx`

**第四步：展示结果**

先展示统计摘要：
```
📱 Lisa 短信销售任务结果 — {taskName}

📊 发送统计：
   📨 总发送：{totalCount} 条
   ✅ 触达成功：{successCount} 条
   ❌ 发送失败：{failCount} 条
```

再展示列表中前 5 条短信详情：
```
序号. 📱 {phoneNumber}
   🔄 状态：{success中文} / {errCode}
   📝 内容：{content前60字}
   📅 发送：{sendTime}（回执 {reportTime}）
```

超过 5 条附上：`...共 {total} 条短信记录，完整数据见 xlsx 文件`。

**情况：统计接口全为 0 或列表为空**

> Lisa 短信任务数据暂未就绪，可能仍在发送中或等待运营商回执。
> lisaDagTaskId：{lisaDagTaskId}，lisaCustomerPoolId：{lisaCustomerPoolId}
> 你可以告诉我「再查Lisa结果」，我会立即重新查询。

---

#### Step 5-B：Frank 结果处理（仅当 employeeList 包含 Frank 且 frankDagTaskId 不为 null）

> ⚠️ Frank 的两个查询接口均使用 `frankDagTaskId`（来自提交响应 `data.employeeList` 中 `nodeType=FRANK` 的 `dagTaskId`），**不是** `taskId`。

**第一步：查询邮件统计**

接口：`GET https://ai.deepsop.com/prod-api/ai/email/getTaskEmailCount?taskId={frankDagTaskId}`

请求头：`x-api-key: $DEEPSOP_API_KEY`

返回字段说明：
- `taskSendEmailCount`：任务发送邮件总数
- `taskSuccessEmailCount`：发送成功数量
- `taskOpenEmailCount`：已读数量
- `taskReceiveEmailCount`：收到回复数量
- `taskClickEmailCount`：点击链接数量

**第二步：查询邮件列表**

接口：`GET https://ai.deepsop.com/prod-api/ai/email/taskList?pageNum=1&pageSize=2000&taskId={frankDagTaskId}`

请求头：`x-api-key: $DEEPSOP_API_KEY`

关键字段：
- `rows[].recipientEmailAddress`：收件人邮箱
- `rows[].companyName`：公司名称
- `rows[].personName`：联系人姓名
- `rows[].position`：职位
- `rows[].emailSubject`：邮件主题
- `rows[].sendTime`：发送时间
- `rows[].emailStatus`：发送状态（0=未发送，1=发送失败，2=发送成功）
- `rows[].round`：轮次

**第三步：生成 xlsx 文件**

将邮件列表 JSON 传给脚本生成 xlsx：
```bash
curl 结果存 /tmp/frank_{frankDagTaskId前8位}_raw.json
python3 ~/.openclaw/workspace/skills/deepsop-human-ai-collab/scripts/format_emails.py "$(cat /tmp/frank_{frankDagTaskId前8位}_raw.json)" '/tmp/frank_{frankDagTaskId前8位}.xlsx'
```

根据当前 channel 必须发送文件，不得跳过：
- **飞书**：必须执行 `cp /tmp/frank_{frankDagTaskId前8位}.xlsx ~/.openclaw/workspace/frank_{frankDagTaskId前8位}.xlsx`，再用 `openclaw message send --channel feishu --target {feishuChatId} --media ~/.openclaw/workspace/frank_{frankDagTaskId前8位}.xlsx --message 'Frank 邮件发送完成！任务「{taskName}」共发送 {taskSendEmailCount} 封，详情见附件。'`
- **Telegram / WhatsApp**：必须执行，media 路径用 workspace 路径，message 同上
- **webchat**：输出文字摘要和文件路径 `/tmp/frank_{frankDagTaskId前8位}.xlsx`

**第四步：展示结果**

先展示统计摘要：
```
📧 Frank 邮件任务结果 — {taskName}

📊 发送统计：
   📤 总发送：{taskSendEmailCount} 封
   ✅ 发送成功：{taskSuccessEmailCount} 封（emailStatus=2）
   ❌ 发送失败：{taskSendEmailCount - taskSuccessEmailCount} 封（emailStatus=1）
   👁 已读：{taskOpenEmailCount} 封
   💬 收到回复：{taskReceiveEmailCount} 封
   🔗 点击链接：{taskClickEmailCount} 封
```

再展示前5条邮件发送详情：
```
序号. 📧 {emailSubject}
   👤 收件人：{personName}（{position}）
   🏢 公司：{companyName}
   📮 邮箱：{recipientEmailAddress}
   📅 发送时间：{sendTime}
   状态：✅ 成功 / ❌ 失败
```

超过5条附上：`...共 {total} 封，如需完整列表请告知`

**情况：统计接口或列表接口返回非 200 / data 为空**

> Frank 邮件任务数据暂未就绪，可能仍在发送中。
> 任务ID：{taskId}
> 你可以告诉我「再查Frank结果」，我会立即重新查询。

#### Step 5-E：Toby 结果处理（仅当 employeeList 包含 Toby 且 tobyDagTaskId 不为 null）

**5-E-1：查询统计数据**

接口：`GET https://ai.deepsop.com/prod-api/ai/data/count?taskId={tobyDagTaskId}&customerPoolId={tobyCustomerPoolId}&platform=1`

请求头：`x-api-key: $DEEPSOP_API_KEY`

关键字段：
- `data.playCount`：总播放量
- `data.likeCount`：总点赞数
- `data.commentCount`：总评论数
- `data.shareCount`：总分享数
- `data.totalTiktokCount`：已发布视频数

**5-E-2：查询视频列表**

接口：`GET https://ai.deepsop.com/prod-api/ai/data/list?pageNum=1&pageSize=10&taskId={tobyDagTaskId}&customerPoolId={tobyCustomerPoolId}&platform=1`

请求头：`x-api-key: $DEEPSOP_API_KEY`

关键字段：
- `rows[].titleName`：视频标题
- `rows[].platformUrl`：TikTok 链接
- `rows[].url`：视频文件地址
- `rows[].playNum`：播放量
- `rows[].likesNum`：点赞数
- `rows[].commentNum`：评论数
- `rows[].transmitNum`：转发数
- `rows[].displayCreateTime`：发布时间
- `total`：列表总数

**5-E-3：回复结果摘要（在当前会话回复，不需发文件）**

格式：
```
🎥 Toby TikTok 视频发布结果
任务：{taskName}

� 数据概览：
   发布视频数：{totalTiktokCount}
   总播放量：{playCount}
   总点赞数：{likeCount}
   总评论数：{commentCount}
   总分享数：{shareCount}

📋 视频明细（共 {total} 条）：
1. 《{titleName}》
   播放：{playNum} | 点赞：{likesNum} | 评论：{commentNum} | 转发：{transmitNum}
   发布时间：{displayCreateTime}
   TikTok 链接：{platformUrl}
2. ...
```

**情况：两个接口均返回非 200 或 data 为空**

> Toby TikTok 视频任务数据暂未就绪，可能仍在生成/发布中。
> 任务ID：{tobyDagTaskId}
> 你可以告诉我「再查Toby结果」，我会立即重新查询。

---

## 实现方式

- **AI 分析**：直接在当前对话中用 LLM 完成，分析时告知用户正在处理
- **HTTP 请求**：使用 `exec` 工具调用 `curl`
- **定时等待**：使用 `cron(action=add)` 设置 8 分钟后触发的 systemEvent
- **xlsx 生成**：使用 `exec` 调用 Python 脚本

---

## 依赖

- Python 3（系统自带）
- openpyxl：`python3 -m pip install openpyxl --user --break-system-packages`
- AiWa 生成脚本：`~/.openclaw/workspace/skills/deepsop-human-ai-collab/scripts/format_customers.py`
- Frank 生成脚本：`~/.openclaw/workspace/skills/deepsop-human-ai-collab/scripts/format_emails.py`
- Fran 生成脚本：`~/.openclaw/workspace/skills/deepsop-human-ai-collab/scripts/format_calls.py`
- Lisa 生成脚本：`~/.openclaw/workspace/skills/deepsop-human-ai-collab/scripts/format_sms.py`

---

## 错误处理

- `DEEPSOP_API_KEY` 未设置：提示用户前往 https://ai.deepsop.com 注册登录后新建 API Key，配置环境变量后再使用
- POST 接口返回非 200：展示错误信息，提示检查参数或稍后重试
- AiWa GET 接口 data 为空：提示任务可能仍在执行，给出 taskId 供用户告知「再查一次」
- Frank 邮件统计/列表接口异常：提示邮件任务可能仍在发送中，给出 taskId 供用户告知「再查Frank结果」
- Frank / Fran / Lisa 单独出现（未与 AiWa 搭配）：终止任务，提示用户补充客户挖掘需求
- Fran 外呼实例并发数为 0：终止任务，提示用户联系管理员开通并发资源
- Fran 号码池为空：终止任务，提示用户联系管理员开通外呼号码
- Frank 邮箱未绑定：终止任务，提示用户登录 https://ai.deepsop.com 前往「邮件配置」绑定邮箱
- Fran 场景库为空或无 `PUBLISHED` 状态：终止任务，提示用户前往 https://ai.deepsop.com 创建并发布场景库
- Lisa 短信模板为空或无 `AUDIT_STATE_PASS` 状态：终止任务，提示用户前往 https://ai.deepsop.com 创建并提交审核短信模板
- Lisa 变量校验失败：明确告知用户不符合的具体规则并要求重新填写，不中断整个流程
- Lisa 统计/详情接口异常或计数全为 0：提示短信任务可能仍在发送中，给出 taskId 和 lisaCustomerPoolId 供用户告知「再查Lisa结果」
- Fran 统计/详情接口异常或计数全为 0：提示电话任务可能仍在拨号中，给出 taskId 和 franCustomerPoolId 供用户告知「再查Fran结果」
- Python 脚本执行失败：直接以文字列表格式返回客户数据，不中断流程
- Toby TikTok 账号为空：终止任务，提示用户登录 https://ai.deepsop.com 添加 TikTok 授权账号
- Toby 视频模型列表为空：终止任务，提示用户联系管理员开通视频生成权限
- Toby 获取账号权限失败：提示用户重新授权该 TikTok 账号
- Toby 统计/列表接口异常或数据为空：提示视频任务可能仍在生成/发布中，给出 tobyDagTaskId 供用户告知「再查Toby结果」
- 数字员工禁用（status=1）：终止任务，提示联系管理员启用该员工
- 数字员工使用天数耗尽（remainingDays≤0）：终止任务，提示前往 https://ai.deepsop.com 购买/续费
- 不支持的员工（Jack/Leo/Sophia/Alex）：终止任务，提示当前仅支持 AiWa、Frank、Fran、Lisa、Toby
- 网络请求失败：展示 curl 错误信息
