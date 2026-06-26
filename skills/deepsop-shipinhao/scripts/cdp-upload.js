/**
 * 微信视频号 CDP 上传辅助脚本
 * 
 * 通过 CDP WebSocket 连接浏览器，在 WUJIE Shadow DOM 中上传视频文件。
 * 
 * 用法：
 *   node cdp-upload.js <target-id> <video-path>
 * 
 * 示例：
 *   node cdp-upload.js C5AB87ED8777D91D4D25C60EE169212F C:/Users/.../video.mp4
 */
const WebSocket = require('ws');

const TARGET_ID = process.argv[2];
const VIDEO_PATH = process.argv[3];

if (!TARGET_ID || !VIDEO_PATH) {
  console.error('用法: node cdp-upload.js <target-id> <video-path>');
  console.error('示例: node cdp-upload.js C5AB87ED... C:/path/to/video.mp4');
  process.exit(1);
}

const CDP_PORT = 18800;
const wsUrl = `ws://127.0.0.1:${CDP_PORT}/devtools/page/${TARGET_ID}`;
const ws = new WebSocket(wsUrl);
let msgId = 1;

ws.on('open', () => {
  console.log('✓ 已连接到 CDP');
  console.log(`  Target: ${TARGET_ID}`);
  console.log(`  Video:  ${VIDEO_PATH}`);
  
  // Step 1: 获取文档根节点
  ws.send(JSON.stringify({
    id: msgId++,
    method: 'DOM.getDocument',
    params: { depth: 0, pierce: true }
  }));
});

ws.on('message', (data) => {
  const msg = JSON.parse(data.toString());

  switch (msg.id) {
    case 1: {
      const rootId = msg.result.root.nodeId;
      console.log(`  ✓ 根节点 ID: ${rootId}`);
      ws.send(JSON.stringify({
        id: msgId++,
        method: 'DOM.querySelector',
        params: { nodeId: rootId, selector: 'wujie-app' }
      }));
      break;
    }

    case 2: {
      const wujieId = msg.result.nodeId;
      if (!wujieId) {
        console.error('✗ 未找到 wujie-app 节点');
        process.exit(1);
      }
      console.log(`  ✓ wujie-app ID: ${wujieId}`);
      ws.send(JSON.stringify({
        id: msgId++,
        method: 'DOM.describeNode',
        params: { nodeId: wujieId, depth: 1, pierce: true }
      }));
      break;
    }

    case 3: {
      const node = msg.result.node;
      const shadowRoot = node.shadowRoots?.[0];
      if (!shadowRoot) {
        console.error('✗ 未找到 Shadow Root');
        process.exit(1);
      }
      console.log(`  ✓ Shadow Root ID: ${shadowRoot.nodeId}`);
      ws.send(JSON.stringify({
        id: msgId++,
        method: 'DOM.querySelector',
        params: { nodeId: shadowRoot.nodeId, selector: 'input[type="file"]' }
      }));
      break;
    }

    case 4: {
      const fileInputId = msg.result.nodeId;
      if (!fileInputId) {
        console.error('✗ 未找到 file input 元素');
        process.exit(1);
      }
      console.log(`  ✓ File input ID: ${fileInputId}`);
      ws.send(JSON.stringify({
        id: msgId++,
        method: 'DOM.setFileInputFiles',
        params: {
          nodeId: fileInputId,
          files: [VIDEO_PATH]
        }
      }));
      break;
    }

    case 5: {
      if (msg.error) {
        console.error('✗ 文件上传失败:', msg.error.message);
        process.exit(1);
      }
      console.log('✓ 文件上传成功!');
      ws.close();
      process.exit(0);
    }
  }
});

ws.on('error', (err) => {
  console.error('✗ WebSocket 错误:', err.message);
  process.exit(1);
});

ws.on('close', () => {
  console.log('  连接已关闭');
});

// 超时处理
setTimeout(() => {
  console.error('✗ 操作超时 (15s)');
  process.exit(1);
}, 15000);
