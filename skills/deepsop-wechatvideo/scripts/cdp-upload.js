#!/usr/bin/env node
/**
 * 微信视频号 CDP 上传辅助脚本。
 *
 * 用法：
 *   node cdp-upload.js "C:/path/to/video.mp4"
 *   node cdp-upload.js "C:/path/to/video.mp4" --target <target-id>
 *   node cdp-upload.js "C:/path/to/video.mp4" --port 18800
 */
const fs = require("fs");
const path = require("path");
const http = require("http");
const WebSocketImpl = globalThis.WebSocket;

const args = process.argv.slice(2);

function usage(exitCode = 1) {
  const text = [
    "用法: node cdp-upload.js <video-path> [--target <target-id>] [--port <cdp-port>]",
    "示例: node cdp-upload.js \"C:/Users/Administrator/Desktop/video.mp4\"",
    "示例: node cdp-upload.js \"C:/Users/Administrator/Desktop/video.mp4\" --target C5AB87ED",
  ].join("\n");
  (exitCode === 0 ? console.log : console.error)(text);
  process.exit(exitCode);
}

function parseArgs(argv) {
  const options = {
    videoPath: null,
    targetId: null,
    port: Number(process.env.CDP_PORT || 18800),
    timeoutMs: 30000,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--help" || arg === "-h") usage(0);
    if (arg === "--target") {
      options.targetId = argv[++i];
    } else if (arg === "--port") {
      options.port = Number(argv[++i]);
    } else if (arg === "--timeout") {
      options.timeoutMs = Number(argv[++i]);
    } else if (!options.videoPath) {
      options.videoPath = arg;
    } else {
      console.error(`未知参数: ${arg}`);
      usage(1);
    }
  }

  if (!options.videoPath) usage(1);
  if (!Number.isInteger(options.port) || options.port <= 0) {
    throw new Error(`无效 CDP 端口: ${options.port}`);
  }
  return options;
}

function normalizeVideoPath(inputPath) {
  const absolute = path.resolve(inputPath);
  if (!fs.existsSync(absolute)) {
    throw new Error(`视频文件不存在: ${absolute}`);
  }
  const stat = fs.statSync(absolute);
  if (!stat.isFile()) {
    throw new Error(`路径不是文件: ${absolute}`);
  }
  return absolute.replace(/\\/g, "/");
}

function getJson(url) {
  return new Promise((resolve, reject) => {
    const req = http.get(url, (res) => {
      let body = "";
      res.setEncoding("utf8");
      res.on("data", (chunk) => {
        body += chunk;
      });
      res.on("end", () => {
        if (res.statusCode < 200 || res.statusCode >= 300) {
          reject(new Error(`HTTP ${res.statusCode}: ${body.slice(0, 200)}`));
          return;
        }
        try {
          resolve(JSON.parse(body));
        } catch (error) {
          reject(new Error(`解析 CDP JSON 失败: ${error.message}`));
        }
      });
    });
    req.on("error", (error) => {
      reject(new Error(`无法连接 CDP 端口 ${new URL(url).port}：${error.message}。请先启动 OPClaw 内置浏览器并打开 https://channels.weixin.qq.com。`));
    });
    req.setTimeout(5000, () => {
      req.destroy(new Error("连接 CDP 端口超时"));
    });
  });
}

async function findTarget(port, explicitTargetId) {
  if (explicitTargetId) {
    return {
      id: explicitTargetId,
      webSocketDebuggerUrl: `ws://127.0.0.1:${port}/devtools/page/${explicitTargetId}`,
    };
  }

  const targets = await getJson(`http://127.0.0.1:${port}/json`);
  const pages = targets.filter((target) => target.type === "page");
  const channelPage =
    pages.find((target) => /channels\.weixin\.qq\.com\/platform\/post\/create/.test(target.url || "")) ||
    pages.find((target) => /channels\.weixin\.qq\.com/.test(target.url || ""));

  if (!channelPage) {
    throw new Error(
      "未找到微信视频号页面。请先在 OPClaw 内置浏览器打开 https://channels.weixin.qq.com 并完成登录授权。"
    );
  }

  return {
    id: channelPage.id,
    title: channelPage.title,
    url: channelPage.url,
    webSocketDebuggerUrl:
      channelPage.webSocketDebuggerUrl || `ws://127.0.0.1:${port}/devtools/page/${channelPage.id}`,
  };
}

function createCdpClient(wsUrl, timeoutMs) {
  if (!WebSocketImpl) {
    throw new Error("当前 Node.js 不支持内置 WebSocket，请使用 Node.js 22+ 运行。");
  }

  const ws = new WebSocketImpl(wsUrl);
  let nextId = 1;
  const pending = new Map();

  const timeout = setTimeout(() => {
    ws.close();
    for (const { reject } of pending.values()) {
      reject(new Error(`CDP 操作超时 (${timeoutMs}ms)`));
    }
    pending.clear();
  }, timeoutMs);

  ws.addEventListener("message", (event) => {
    const msg = JSON.parse(event.data.toString());
    if (!msg.id || !pending.has(msg.id)) return;
    const { resolve, reject } = pending.get(msg.id);
    pending.delete(msg.id);
    if (msg.error) {
      reject(new Error(msg.error.message || JSON.stringify(msg.error)));
    } else {
      resolve(msg.result);
    }
  });

  ws.addEventListener("error", () => {
    for (const { reject } of pending.values()) {
      reject(new Error("WebSocket 连接出错"));
    }
    pending.clear();
  });

  return new Promise((resolve, reject) => {
    ws.addEventListener(
      "open",
      () => {
        resolve({
          send(method, params = {}) {
            const id = nextId++;
            ws.send(JSON.stringify({ id, method, params }));
            return new Promise((sendResolve, sendReject) => {
              pending.set(id, { resolve: sendResolve, reject: sendReject });
            });
          },
          close() {
            clearTimeout(timeout);
            ws.close();
          },
        });
      },
      { once: true }
    );
    ws.addEventListener(
      "error",
      () => {
        reject(new Error("无法连接 CDP WebSocket"));
      },
      { once: true }
    );
  });
}

async function querySelector(client, nodeId, selector, label) {
  const result = await client.send("DOM.querySelector", { nodeId, selector });
  if (!result.nodeId) {
    throw new Error(`未找到 ${label}: ${selector}`);
  }
  return result.nodeId;
}

async function uploadVideo({ wsUrl, videoPath, timeoutMs }) {
  const client = await createCdpClient(wsUrl, timeoutMs);
  try {
    const documentResult = await client.send("DOM.getDocument", { depth: 0, pierce: true });
    const rootId = documentResult.root.nodeId;
    const wujieId = await querySelector(client, rootId, "wujie-app", "wujie-app");
    const described = await client.send("DOM.describeNode", {
      nodeId: wujieId,
      depth: 1,
      pierce: true,
    });
    const shadowRoot = described.node.shadowRoots && described.node.shadowRoots[0];
    if (!shadowRoot) {
      throw new Error("未找到 wujie-app 的 Shadow Root，请等待发布页加载完成后重试。");
    }

    let fileInputId;
    try {
      fileInputId = await querySelector(
        client,
        shadowRoot.nodeId,
        'input[type="file"][accept*="video"]',
        "视频上传 input"
      );
    } catch (_) {
      fileInputId = await querySelector(client, shadowRoot.nodeId, 'input[type="file"]', "文件上传 input");
    }

    await client.send("DOM.setFileInputFiles", {
      nodeId: fileInputId,
      files: [videoPath],
    });
  } finally {
    client.close();
  }
}

(async () => {
  try {
    const options = parseArgs(args);
    const videoPath = normalizeVideoPath(options.videoPath);
    const target = await findTarget(options.port, options.targetId);

    console.log("已连接微信视频号页面");
    console.log(`Target: ${target.id}`);
    if (target.url) console.log(`URL: ${target.url}`);
    console.log(`Video: ${videoPath}`);

    await uploadVideo({
      wsUrl: target.webSocketDebuggerUrl,
      videoPath,
      timeoutMs: options.timeoutMs,
    });

    console.log("视频文件已注入上传控件，请等待页面完成上传和处理。");
  } catch (error) {
    console.error(`上传失败: ${error.message}`);
    process.exit(1);
  }
})();
