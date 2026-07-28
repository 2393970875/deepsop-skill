#!/usr/bin/env node
'use strict';

/**
 * GEO诊断报告 PDF 构建脚本
 *
 * 用法: node build-pdf.js <html-path> [output-path]
 *   html-path   — HTML 报告路径（必填）
 *   output-path — 输出 PDF 路径（可选，默认与 HTML 同目录）
 *
 * 流程:
 *   1. 在 HTML 中注入紧凑的 @media print 样式
 *   2. 启动本地 Node.js HTTP 服务
 *   3. 用浏览器打开并导出 PDF
 *   4. 停止 HTTP 服务
 *
 * 退出码:
 *   0 — 成功
 *   1 — HTML 文件不存在
 *   2 — 浏览器 PDF 导出失败
 */

var fs = require('fs');
var path = require('path');
var http = require('http');

var args = process.argv.slice(2);
if (args.length < 1) {
  console.error('用法: node build-pdf.js <html-path> [output-path]');
  process.exit(1);
}

var htmlPath = path.resolve(args[0]);
var outputPath = args[1]
  ? path.resolve(args[1])
  : path.join(path.dirname(htmlPath), path.basename(htmlPath, '.html') + '.pdf');

if (!fs.existsSync(htmlPath)) {
  console.error('❌ HTML 文件不存在: ' + htmlPath);
  process.exit(1);
}

// ── 1. 读取 HTML，注入压缩打印样式 ──
var html = fs.readFileSync(htmlPath, 'utf8');

var compactCSS = [
  '<style id="compact-print" media="print">',
  '@page { size: A4; margin: 0.1in; }',
  'body { font-size: 7px !important; line-height: 1.15 !important; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif !important; }',
  '.dr-hero { padding: 8px 10px 6px !important; margin-bottom: 2px !important; }',
  '.dr-hero__body { gap: 4px !important; }',
  '.dr-hero__badge-row { gap: 2px !important; }',
  '.dr-hero__title { font-size: 14px !important; line-height: 1.1 !important; }',
  '.dr-hero__subtitle { font-size: 7px !important; }',
  '.dr-hero__score-ring { width: 36px !important; height: 36px !important; }',
  '.dr-hero__score-ring svg { width: 36px !important; height: 36px !important; }',
  '.dr-hero__score-ring-bg, .dr-hero__score-ring-fill { stroke-width: 4 !important; }',
  '.dr-hero__score-value { font-size: 14px !important; }',
  '.dr-hero__score-inner { width: 36px !important; height: 36px !important; }',
  '.dr-hero__score-group { gap: 4px !important; }',
  '.dr-hero__grade-badge { padding: 1px 4px !important; }',
  '.dr-hero__grade-value { font-size: 9px !important; }',
  '.dr-hero__grade-label, .dr-hero__grade-desc { font-size: 6px !important; }',
  '.dr-hero__meta { font-size: 7px !important; }',
  '.section-card { margin-bottom: 2px !important; }',
  '.section-card-header { padding: 2px 6px !important; }',
  '.section-card-header h2 { font-size: 9px !important; }',
  '.section-card-body { padding: 2px 6px !important; }',
  '.dr-content { width: min(1080px, calc(100% - 8px)) !important; padding-top: 2px !important; }',
  '.dr-page { padding-bottom: 0 !important; }',
  '* { margin: 0 !important; }',
  'h1, h2, h3, h4, h5, p, div, span, li, td, th { margin: 0 !important; }',
  'p { line-height: 1.15 !important; margin: 0 !important; padding: 0 !important; }',
  '.grid-cols-2, .grid-cols-3, .grid-cols-4 { gap: 1px !important; }',
  '.gap-1, .gap-2, .gap-3, .gap-4, .gap-6, .gap-8 { gap: 1px !important; }',
  '.my-1, .my-2, .my-3, .my-4, .my-6, .my-8, .my-10 { margin-top: 0 !important; margin-bottom: 0 !important; }',
  '.mb-1, .mb-2, .mb-3, .mb-4, .mb-6, .mb-8, .mb-10, .mb-12 { margin-bottom: 0 !important; }',
  '.mt-1, .mt-2, .mt-3, .mt-4, .mt-6, .mt-8 { margin-top: 0 !important; }',
  '.p-1, .p-2, .p-3, .p-4, .p-6, .p-8 { padding: 1px !important; }',
  '.px-1, .px-2, .px-3, .px-4, .px-6 { padding-left: 1px !important; padding-right: 1px !important; }',
  '.py-1, .py-2, .py-3, .py-4 { padding-top: 0 !important; padding-bottom: 0 !important; }',
  '.dimension-slider { padding: 0 !important; margin: 0 !important; }',
  '.aivo-circle-wrapper { margin: 0 auto !important; }',
  '.risk-item, .highlight-item { padding: 0 3px !important; }',
  '.badge, .tag, .dr-hero__badge { font-size: 5px !important; padding: 0 2px !important; }',
  'table { font-size: 6px !important; }',
  'td, th { padding: 0 2px !important; }',
  'img { max-height: 40px !important; }',
  'svg { max-height: 35px !important; width: auto !important; height: auto !important; }',
  'button, .btn, nav, .nav, .dr-nav, [class*=nav] { display: none !important; }',
  '.flex-wrap { flex-wrap: nowrap !important; }',
  '.dr-hero__gradient-anim { display: none !important; }',
  '.min-h-screen { min-height: auto !important; }',
  '.overflow-hidden { overflow: visible !important; }',
  '.space-y-1, .space-y-2, .space-y-3, .space-y-4 { margin-top: 0 !important; }',
  '[class*=space-y] > * + * { margin-top: 0 !important; }',
  '.dr-hero__divider-dot { display: none !important; }',
  '</style>'
].join('\n');

html = html.replace('</head>', compactCSS + '\n</head>');

// Write temp HTML
var tmpHtml = path.join(path.dirname(htmlPath), '.tmp-pdf-' + path.basename(htmlPath));
fs.writeFileSync(tmpHtml, html, 'utf8');

// ── 2. Start HTTP server ──
var serverDir = path.dirname(htmlPath);
var server;
var serverPort = 0; // will be assigned

function startServer() {
  return new Promise(function(resolve, reject) {
    server = http.createServer(function(req, res) {
      var filePath = path.join(serverDir, decodeURIComponent(req.url).split('?')[0]);
      var ext = path.extname(filePath);
      var ctMap = {
        '.html': 'text/html; charset=utf-8',
        '.json': 'application/json',
        '.js': 'text/javascript',
        '.css': 'text/css',
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.svg': 'image/svg+xml'
      };
      fs.readFile(filePath, function(err, data) {
        if (err) {
          res.writeHead(404);
          res.end('Not found');
          return;
        }
        res.writeHead(200, { 'Content-Type': ctMap[ext] || 'text/plain' });
        res.end(data);
      });
    });

    server.listen(0, '127.0.0.1', function() {
      serverPort = server.address().port;
      console.log('🌐 HTTP server started at http://127.0.0.1:' + serverPort);
      resolve(serverPort);
    });
    server.on('error', reject);
  });
}

function stopServer() {
  return new Promise(function(resolve) {
    if (server) {
      server.close(function() {
        console.log('🛑 HTTP server stopped');
        resolve();
      });
    } else {
      resolve();
    }
  });
}

// ── 3. Main flow ──
var brand = '品牌';
// Extract brand name from file name
var baseName = path.basename(htmlPath, '.html');
var match = baseName.match(/^(.+?)-GEO/);
if (match) brand = match[1];

console.log('📄 开始构建 PDF...');
console.log('   品牌: ' + brand);
console.log('   来源: ' + htmlPath);
console.log('   输出: ' + outputPath);

startServer()
  .then(function(port) {
    var url = 'http://127.0.0.1:' + port + '/' + encodeURIComponent('.tmp-pdf-' + path.basename(htmlPath));
    console.log('   Serving at: ' + url);
    console.log('   ⚠️  请在浏览器中打开此地址，然后使用打印/Ctrl+P 导出为PDF');
    console.log('   ⚠️  或使用 OPClaw 的 browser pdf action 导出');
    console.log('');
    console.log('   ' + url);
    console.log('');
    console.log('   导出后请将 PDF 保存到:');
    console.log('   ' + outputPath);
    return port;
  })
  .catch(function(err) {
    console.error('❌ 启动 HTTP 服务失败: ' + err.message);
    return stopServer().then(function() {
      // Cleanup
      try { fs.unlinkSync(tmpHtml); } catch(e) {}
      process.exit(1);
    });
  });
