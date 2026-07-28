/**
 * auto-search.js — GEO诊断全平台自动搜索脚本
 * 
 * 用法: node auto-search.js <brandName> <productType> [outputDir]
 * 功能: 生成全平台搜索的 WebFetch URL 列表，AI 据此执行搜索
 * 
 * v5.1: 覆盖百度/知乎/小红书/B站/搜狗微信/微博/搜狗网页/搜狗视频/360/贴吧 + Browser:抖音/视频号
 */

function encode(str) {
  return encodeURIComponent(str);
}

const brand = process.argv[2];
const product = process.argv[3];
const outputDir = process.argv[4] || 'diag-output';

if (!brand) {
  console.error('用法: node auto-search.js <品牌名> [产品类型]');
  process.exit(1);
}

const kw = product ? `${brand} ${product}` : brand;
const ekw = encode(kw);
const eb = encode(brand);
const ep = product ? encode(product) : '';

const searches = [
  // === WebFetch 第一波（10-12次并行）===
  { id: 'baidu',        tool: 'WebFetch', url: `https://www.baidu.com/s?wd=${ekw}&ie=utf-8`,                     desc: '百度通用搜索' },
  { id: 'zhihu',        tool: 'WebFetch', url: `https://www.zhihu.com/search?type=content&q=${ekw}`,              desc: '知乎内容搜索' },
  { id: 'xiaohongshu',  tool: 'WebFetch', url: `https://www.xiaohongshu.com/search_result?keyword=${ekw}`,        desc: '小红书搜索' },
  { id: 'bilibili',     tool: 'WebFetch', url: `https://search.bilibili.com/all?keyword=${ekw}`,                  desc: 'B站搜索' },
  { id: 'sogou-weixin', tool: 'WebFetch', url: `https://weixin.sogou.com/weixin?type=2&query=${ekw}`,             desc: '搜狗微信(公众号+视频号)' },
  { id: 'weibo',        tool: 'WebFetch', url: `https://weibo.com/search?q=${ekw}`,                               desc: '微博搜索' },
  { id: 'sogou-web',    tool: 'WebFetch', url: `https://www.sogou.com/web?query=${ekw}`,                          desc: '搜狗网页搜索' },
  { id: 'baidu-news',   tool: 'WebFetch', url: `https://www.baidu.com/s?wd=${ekw}+%E6%96%B0%E9%97%BB&ie=utf-8`,  desc: '百度新闻搜索' },
  { id: 'baidu-tieba',  tool: 'WebFetch', url: `https://tieba.baidu.com/f?kw=${eb}`,                              desc: '百度贴吧' },
  { id: 'so-360',       tool: 'WebFetch', url: `https://www.so.com/s?q=${ekw}`,                                   desc: '360搜索' },
  { id: 'sogou-video',  tool: 'WebFetch', url: `https://v.sogou.com/v?query=${ekw}`,                              desc: '搜狗视频搜索' },
  { id: 'weixin-video', tool: 'WebFetch', url: `https://weixin.sogou.com/web?query=${ekw}+channels.weixin.qq.com`,desc: '搜狗微信视频号搜索' },
];

// === Browser 第二波（3-4次，逐一执行）===
const browserSearches = [
  { id: 'douyin',    tool: 'Browser', url: `https://www.douyin.com/search/${eb}`,            desc: '抖音搜索' },
  { id: 'shipinhao', tool: 'Browser', url: `https://weixin.sogou.com/web?query=${eb}+channels.weixin.qq.com`, desc: '微信视频号搜索(Browser)' },
  { id: 'kuaishou',  tool: 'Browser', url: `https://www.kuaishou.com/search/${eb}`,          desc: '快手搜索（可选）' },
];

// === WebSearch 第三波（如果可用）===
const webSearchQueries = [
  { id: 'ws-intro', query: `${brand} ${product||''} 品牌 介绍 官网`, desc: '通用搜索:品牌介绍' },
  { id: 'ws-review', query: `${brand} ${product||''} 口碑 评价 怎么样`, desc: '通用搜索:口碑评价' },
];

// 输出（后续格式）
const output = {
  brand,
  product: product || null,
  generatedAt: new Date().toISOString(),
  searches,
  browserSearches,
  webSearchQueries,
  instructions: [
    '1. 执行 WebFetch 搜索：同时发起所有 WebFetch 请求',
    '2. 执行 Browser 搜索：逐一打开 Browser 搜索',
    '3. 执行 WebSearch 搜索：如果工具可用',
    '4. 合并所有结果到 ${searchResults} 变量',
  ]
};

const fs = require('fs');
const outPath = `${outputDir}/auto-search-${brand}.json`;
fs.mkdirSync(outputDir, { recursive: true });
fs.writeFileSync(outPath, JSON.stringify(output, null, 2));
console.log(`✅ 全平台搜索计划已生成: ${outPath}`);
console.log(`   WebFetch: ${searches.length}次`);
console.log(`   Browser:  ${browserSearches.length}次`);
console.log(`   WebSearch: ${webSearchQueries.length}次`);
console.log(`   总计: ${searches.length + browserSearches.length + webSearchQueries.length}次`);
