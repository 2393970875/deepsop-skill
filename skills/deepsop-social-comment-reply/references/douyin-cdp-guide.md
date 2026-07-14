# 抖音 CDP 评论发送技术指南

> 版本：v1.0 | 更新：2026-07-13
> 基于 2026-07-09 / 2026-07-13 两轮实战验证（6/6 成功）

## 核心原理

抖音 PC 版（douyin.com）评论区使用 **Draft.js + React** 架构：

- 评论输入组件没有传统 HTML `<button>` 发送按钮
- 发送逻辑由 React 组件 `handlePublishClick` 处理
- 编辑器状态（editorState）由 Draft.js + React onChange 管理
- 直接 DOM 操作不会同步 editorState，导致 `handlePublishClick` 内部校验失败

**因此，必须通过 React Fiber 走完整的 onChange → handlePublishClick 链路。**

---

## 完整发送流程

### 步骤 1：激活评论输入框

```javascript
// 滚动到评论区底部
var c = document.querySelector('.yP5MkONE.llbV_Rqp.VaW6TeYk');
if(c) c.scrollTop = c.scrollHeight;

// 点击评论输入占位文字「善语结善缘，恶言伤人心」
var placeholder = document.querySelector('._x9Gwl7G');
if (placeholder) {
    placeholder.scrollIntoView({behavior:'instant', block:'center'});
    placeholder.click();
}

// 聚焦 Draft.js 编辑器
var editor = document.querySelector('.public-DraftEditor-content');
if (editor) { editor.focus(); editor.click(); }
```

### 步骤 2：清除已有文字并填入新文字

通过 CDP 键盘事件 + insertText：

```python
# Ctrl+A 全选
await cmd(ws, "Input.dispatchKeyEvent", {
    "type":"keyDown","key":"a","code":"KeyA","windowsVirtualKeyCode":65,"modifiers":2
})
await cmd(ws, "Input.dispatchKeyEvent", {
    "type":"keyUp","key":"a","code":"KeyA","windowsVirtualKeyCode":65,"modifiers":2
})

# 填入新文字
await cmd(ws, "Input.insertText", {"text": reply_text})
```

### 步骤 3：通过 React Fiber 更新状态并提交

React Fiber 树结构（从编辑器 DOM 节点向上追溯）：

| 层级 | 组件 | 可用 props |
|------|------|-----------|
| Level 3 | Draft.js Editor | `editorState`, `onChange` |
| Level 6 | Comment Input Wrapper | `onChange`, `handlePublishClick` |

**关键代码**：

```javascript
(function(){
    var e = document.querySelector('.public-DraftEditor-content');
    if (!e) return JSON.stringify({error:'no editor'});

    // 找到 React Fiber
    var key = Object.keys(e).find(function(k){return k.startsWith('__reactFiber')});
    var fiber = e[key], esF = null, sbF = null, f = fiber;

    // 遍历 Fiber 树找到 editorState/onChange 和 handlePublishClick
    for (var i = 0; i < 80 && f; i++) {
        var p = f.memoizedProps || {};
        if (p.editorState && p.onChange && !esF) esF = {props: p};
        if (p.handlePublishClick && !sbF) sbF = {props: p};
        f = f.return;
    }

    if (!esF || !sbF) return JSON.stringify({error:'fibers not found'});

    // 用编辑器中的实际文字创建新 content state
    var es = esF.props.editorState;
    var nc = es.getCurrentContent().constructor.createFromText(e.textContent||'');
    var ns = es.constructor.push(es, nc, 'replace-text');

    // 调用 onChange 更新 React 状态
    esF.props.onChange(ns);

    // 等待状态更新后提交
    return new Promise(function(resolve) {
        setTimeout(function() {
            try {
                sbF.props.handlePublishClick();
                resolve(JSON.stringify({ok:true}));
            } catch(ex) {
                resolve(JSON.stringify({error:ex.message}));
            }
        }, 400);
    });
})()
```

---

## 搜索页导航技术

### 虚拟列表问题

抖音搜索页使用 React 虚拟列表（`waterFallScrollContainer`），卡片在视口外会被销毁，DOM 中不存在。

### 解决方案

1. 搜索页加载后，滚动加载数据：`window.scrollBy(0, 1000)` × 5-8 次
2. 从 `document.body.innerText` 提取搜索结果文本
3. 解析文本提取作品标题、作者、点赞数
4. 用 `waterFallScrollContainer.scrollTop` 定位目标卡片区域
5. `scrollIntoView` + CDP mouse event + JS click 点击卡片
6. 从 `window.location.href` 提取 `modal_id`
7. `Page.navigate` 到 `https://www.douyin.com/video/<modal_id>`

### 注意事项

- CDP 浏览器端口默认为 18800
- 页面 tab 可能被关闭，每次操作前检查 CDP 可用 tab
- 搜索页的 body text 包含完整搜索结果，包含时长、点赞数、标题、作者、日期
- 不同搜索词可能返回不同结果，可多轮尝试
- 虚拟列表的 `.search-result-card` 没有 `onClick` prop（事件委托在更上层）

---

## CDP 连接管理

```python
CDP_PORT = 18800

async def get_ws_url(pattern):
    req = urllib.request.Request(f'http://127.0.0.1:{CDP_PORT}/json')
    with urllib.request.urlopen(req) as r:
        pages = json.loads(r.read())
    for p in pages:
        if pattern in p.get('url',''):
            return p['webSocketDebuggerUrl']
    return None

async def cmd(ws, method, params=None):
    await ws.send(json.dumps({"id":1,"method":method,"params":params or {}}))
    while True:
        d = json.loads(await ws.recv())
        if d.get("id")==1: return d
```

---

## 排错指南

| 问题 | 原因 | 解决 |
|------|------|------|
| `no editor` | 评论输入框未激活 | 先点 `._x9Gwl7G` 占位文字 |
| `fibers not found` | React Fiber 层级变化 | 打印 trace 日志确认层级号 |
| `handlePublishClick` 调用但未发送 | editorState 未同步 | 确认 onChange 在 Level 3 被正确调用 |
| 搜索页卡片找不到 | 虚拟列表销毁 | 先滚动到目标区域再查找 |
| CDP 连接拒绝 | 浏览器进程退出 | 重新打开抖音搜索页 |
| `modal_id` 相同 | 点击到了已打开的 modal | 先 `Page.navigate` 回搜索页刷新 |

---

*基于 OPClaw + CDP 实战验证*
