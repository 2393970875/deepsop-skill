#!/usr/bin/env python3
"""
抖音评论发送脚本
===============
通过 CDP (Chrome DevTools Protocol) 在抖音 PC 版发送评论。

用法：
    python comment_reply.py --text "你的评论内容" [--url "https://www.douyin.com/video/xxx"]

参数：
    --text TEXT       要发送的评论内容（必填）
    --url URL         目标视频 URL（可选，默认使用当前打开的抖音视频页）
    --port PORT       CDP 端口（默认 18800）

退出码：
    0  发送成功
    1  发送失败

基于 2026-07 实战验证：通过 React Fiber 的 onChange + handlePublishClick 链路发送。
"""

import asyncio
import json
import sys
import urllib.request
import argparse

DEFAULT_CDP_PORT = 18800


async def find_douyin_tab(port, pattern="douyin.com/video"):
    """查找匹配的抖音 tab"""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/json")
        with urllib.request.urlopen(req, timeout=5) as r:
            pages = json.loads(r.read())
    except Exception as e:
        return None, f"CDP 连接失败 (端口 {port}): {e}"

    for page in pages:
        url = page.get("url", "")
        if pattern in url:
            return page["webSocketDebuggerUrl"], None

    return None, f"未找到匹配的抖音页面 (pattern={pattern})"


async def send_cmd(ws, method, params=None):
    """发送 CDP 命令并等待响应"""
    cid = 1
    await ws.send(json.dumps({"id": cid, "method": method, "params": params or {}}))
    while True:
        data = json.loads(await ws.recv())
        if data.get("id") == cid:
            return data


async def post_comment(ws_url, text, navigate_url=None):
    """通过 CDP 发送评论"""
    import websockets

    async with websockets.connect(ws_url, max_size=10 * 1024 * 1024) as ws:
        await send_cmd(ws, "Runtime.enable")

        # 如果指定了视频 URL，先导航
        if navigate_url:
            await send_cmd(ws, "Page.navigate", {"url": navigate_url})
            await asyncio.sleep(4)

        # 步骤 1：激活评论输入框
        result = await send_cmd(ws, "Runtime.evaluate", {
            "expression": """
            (function(){
                var c = document.querySelector('.yP5MkONE.llbV_Rqp.VaW6TeYk');
                if(c) c.scrollTop = c.scrollHeight;
                var p = document.querySelector('._x9Gwl7G');
                if(p) { p.scrollIntoView({behavior:'instant',block:'center'}); p.click(); }
                var e = document.querySelector('.public-DraftEditor-content');
                if(e) { e.focus(); e.click(); return 'ok'; }
                return 'no editor';
            })()
            """,
            "returnByValue": True
        })
        status = result.get("result", {}).get("result", {}).get("value", "")
        if "no editor" in str(status):
            return {"error": "评论输入框未找到", "detail": status}

        await asyncio.sleep(0.5)

        # 步骤 2：清除已有文字并填入新文字
        await send_cmd(ws, "Input.dispatchKeyEvent", {
            "type": "keyDown", "key": "a", "code": "KeyA",
            "windowsVirtualKeyCode": 65, "modifiers": 2
        })
        await send_cmd(ws, "Input.dispatchKeyEvent", {
            "type": "keyUp", "key": "a", "code": "KeyA",
            "windowsVirtualKeyCode": 65, "modifiers": 2
        })
        await send_cmd(ws, "Input.insertText", {"text": text})
        await asyncio.sleep(0.4)

        # 步骤 3：通过 React Fiber 更新状态并提交
        submit_result = await send_cmd(ws, "Runtime.evaluate", {
            "expression": """
            (function(){
                var e = document.querySelector('.public-DraftEditor-content');
                if (!e) return JSON.stringify({error:'no editor'});

                var key = Object.keys(e).find(function(k){return k.startsWith('__reactFiber')});
                if (!key) return JSON.stringify({error:'no fiber key'});

                var fiber = e[key], esF = null, sbF = null, f = fiber;
                for (var i = 0; i < 80 && f; i++) {
                    var p = f.memoizedProps || {};
                    if (p.editorState && p.onChange && !esF) esF = {props: p};
                    if (p.handlePublishClick && !sbF) sbF = {props: p};
                    f = f.return;
                }

                if (!esF) return JSON.stringify({error:'editorState fiber not found'});
                if (!sbF) return JSON.stringify({error:'handlePublishClick fiber not found'});

                try {
                    var es = esF.props.editorState;
                    var nc = es.getCurrentContent().constructor.createFromText(e.textContent||'');
                    var ns = es.constructor.push(es, nc, 'replace-text');
                    esF.props.onChange(ns);

                    return new Promise(function(resolve) {
                        setTimeout(function() {
                            try {
                                sbF.props.handlePublishClick();
                                resolve(JSON.stringify({ok: true}));
                            } catch(ex) {
                                resolve(JSON.stringify({error: 'submit error: ' + ex.message}));
                            }
                        }, 400);
                    });
                } catch(ex) {
                    return JSON.stringify({error: 'onChange error: ' + ex.message});
                }
            })()
            """,
            "returnByValue": True,
            "awaitPromise": True
        })

        raw = submit_result.get("result", {}).get("result", {}).get("value", "{}")
        return json.loads(raw)


async def main():
    parser = argparse.ArgumentParser(description="抖音评论发送脚本")
    parser.add_argument("--text", required=True, help="要发送的评论内容")
    parser.add_argument("--url", default=None, help="目标视频 URL")
    parser.add_argument("--port", type=int, default=DEFAULT_CDP_PORT, help="CDP 端口")
    args = parser.parse_args()

    # 找到目标 tab
    ws_url, error = await find_douyin_tab(args.port)
    if error:
        print(json.dumps({"error": error}, ensure_ascii=False))
        sys.exit(1)

    # 发送评论
    result = await post_comment(ws_url, args.text, navigate_url=args.url)

    if result.get("ok"):
        print(json.dumps({"status": "success", "message": "评论发送成功"}, ensure_ascii=False))
        sys.exit(0)
    else:
        print(json.dumps({"status": "failed", "detail": result}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
