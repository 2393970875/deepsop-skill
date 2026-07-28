# GEO诊断报告 - 全平台搜索查询模板（v5.1）

> ⚠️ **强制规则**：每次诊断启动后，**必须先执行全平台搜索**，再开始 AI 推理。
> 所有 WebFetch 搜索必须同时发起，不设间隔，不省略任何一个平台。
> 搜索执行规范详见 `references/search-strategy.md`。
> 全平台搜索策略详见 `references/multi-platform-search.md`。

---

## 阶段0：全平台搜索（强制先执行）

### 第1波：WebFetch 全平台（12次并行，一次性全部发起）

```
搜索F1: baidu       → https://www.baidu.com/s?wd={encodedKW}&ie=utf-8
搜索F2: zhihu       → https://www.zhihu.com/search?type=content&q={encodedKW}
搜索F3: xiaohongshu → https://www.xiaohongshu.com/search_result?keyword={encodedKW}
搜索F4: bilibili    → https://search.bilibili.com/all?keyword={encodedKW}
搜索F5: sogou-wx    → https://weixin.sogou.com/weixin?type=2&query={encodedKW}
搜索F6: weibo       → https://weibo.com/search?q={encodedKW}
搜索F7: sogou-web   → https://www.sogou.com/web?query={encodedKW}
搜索F8: baidu-news  → https://www.baidu.com/s?wd={encodedKW}+%E6%96%B0%E9%97%BB&ie=utf-8
搜索F9: baidu-tieba → https://tieba.baidu.com/f?kw={brandName}
搜索F10: so-360      → https://www.so.com/s?q={encodedKW}
搜索F11: sogou-video → https://v.sogou.com/v?query={encodedKW}
搜索F12: weixin-video→ https://weixin.sogou.com/web?query={encodedKW}+channels.weixin.qq.com
```

**执行策略**：12次 WebFetch 同时发起，不设任何间隔。
**结果记录**：
- 有内容 → 提取 title/url/snippet，标注 `[来源:平台名]`
- 反爬/403/空结果 → 记录 `[平台名:未采集]`
- 所有结果合并到 `${searchResults}`

### 第2波：Browser 辅助（3-4次，逐一执行，每次≤30s）

```
搜索B1: douyin     → open https://www.douyin.com/search/{brandName} → snapshot → close
搜索B2: shipinhao  → open https://weixin.sogou.com/web?query={brandName}+channels.weixin.qq.com → snapshot → close
搜索B3: kuaishou   → open https://www.kuaishou.com/search/{brandName} → snapshot → close（可选）
搜索B4: weibo-alt  → open https://weibo.com/search?q={brandName} → snapshot → close（WebFetch被拦截时）
```

**执行策略**：逐一执行 Browser，完成后立即关闭页签。
**结果记录**：标注 `[Browser:平台名]`

### 第3波：WebSearch（如果可用）

```
搜索W1: "{brandName} {productType}" 品牌 介绍 官网
搜索W2: "{brandName} {productType}" 评价 口碑
```

**执行策略**：和 Browser 不冲突时可与第2波并行。

---

## 阶段1 搜索组（基于阶段0结果，AI自行判断是否补充搜索）

不再需要单独的搜索组，阶段0的全平台搜索已覆盖所有信息维度。
如果阶段0数据不足，可针对性补充1-2次搜索。

---

## 阶段2 搜索组（基于阶段0结果）

同上，依赖阶段0的全平台搜索结果。

---

## 阶段3 搜索组（基于阶段0结果）

同上，依赖阶段0的全平台搜索结果。

---

## 搜索次数汇总

| 波次 | 工具 | 搜索次数 | 方式 |
|------|------|---------|------|
| 第1波 | WebFetch | 12次 | 一次全部发起 |
| 第2波 | Browser | 3-4次 | 逐一执行 |
| 第3波 | WebSearch | 2次 | 可用时并行 |
| **总计** | **三引擎** | **17-18次** | **全平台覆盖** |

---

## 全平台 vs 旧版对比

| 版本 | 搜索次数 | 平台数 | 微信视频号 | 贴吧 | 360 | 搜狗视频 |
|------|---------|--------|-----------|------|-----|---------|
| v5.0 | 14-22次 | 6个 | ❌ | ❌ | ❌ | ❌ |
| **v5.1** | **17-18次** | **12个** | **✅** | **✅** | **✅** | **✅** |

---

## URL编码速查

| 原始 | 编码后 |
|------|--------|
| 空格 | `+` 或 `%20` |
| 中文 | `%XX%YY%ZZ`（UTF-8） |

全平台搜索时，先用 `encodeURIComponent()` 编码关键词再拼入 URL。
