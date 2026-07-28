# GEO诊断报告 - 全平台自动搜索规范（v5.1）

> 每次 GEO 诊断启动时，AI **必须先自动执行全平台搜索**，所有平台一次性同时发起，不筛选不省略。
> 这是**强制步骤**，不可跳过。

---

## 一键全平台搜索命令

每次进来先执行这个搜索集，所有平台一次性全发出去：

```
阶段0：全平台搜索（一次性并行发起15-18次搜索）

第一波 WebFetch（10-12次并行，不设间隔）：
  ├── baidu:      https://www.baidu.com/s?wd={encodedKW}&ie=utf-8
  ├── zhihu:      https://www.zhihu.com/search?type=content&q={encodedKW}
  ├── xhs:        https://www.xiaohongshu.com/search_result?keyword={encodedKW}
  ├── bilibili:   https://search.bilibili.com/all?keyword={encodedKW}
  ├── sogou-wx:   https://weixin.sogou.com/weixin?type=2&query={encodedKW}
  ├── weibo:      https://weibo.com/search?q={encodedKW}
  ├── sogou-web:  https://www.sogou.com/web?query={encodedKW}
  ├── baidu-news: https://www.baidu.com/s?wd={encodedKW}+%E6%96%B0%E9%97%BB&ie=utf-8
  ├── baidu-tieba:https://tieba.baidu.com/f?kw={encodedKW}
  ├── 360:        https://www.so.com/s?q={encodedKW}
  └── sogou-video:https://v.sogou.com/v?query={encodedKW}

第二波 Browser（3-4次，逐一执行，每次≤30s）：
  ├── douyin:     open douyin.com/search/{brandName}
  ├── video号:    open weixin.sogou.com/web?query={brandName}+channels.weixin.qq.com
  ├── kuaishou:   open kuaishou.com/search/{brandName}（如可访问）
  └── weibo:      open weibo.com/search?q={brandName}（WebFetch登录拦截时用）

第三波 WebSearch（如果可用）：
  ├── 通用搜索:   "{brandName} {productType}" 品牌 介绍
  └── 通用搜索:   "{brandName}" 评价 口碑
```

---

## 全平台结果合并规则

1. 所有 WebFetch 和 WebSearch 结果 **同时发起**，不等待一个完成再发起下一个
2. 每个平台设置 maxChars=5000
3. 无论命中与否，结果都记录到 `${searchResults}` 变量
4. 命中结果标注 `[平台名:WebFetch]` 或 `[平台名:Browser]`
5. 未命中（反爬/空结果/错误）标注 `[平台名:未采集]`
6. **全部18次搜索完成后**，开始 AI 推理阶段

---

## 微信视频号搜索专项

视频号的内容分散在微信生态中，需要通过以下渠道获取：

### 方法1：搜狗微信搜索（推荐）
```
URL: https://weixin.sogou.com/weixin?type=2&query={encodedKW}
```
搜狗微信涵盖公众号文章，部分视频号内容也会被收录。

### 方法2：搜狗网页搜索+site限定
```
URL: https://weixin.sogou.com/web?query={encodedKW}+channels.weixin.qq.com
```

### 方法3：Browser 打开视频号搜索（备用）
```
Browser: open weixin.sogou.com/web?query={brandName}+channels.weixin.qq.com
```

---

## URL编码速查

| 关键词 | 编码结果 |
|--------|---------|
| 董赣明 | %E8%91%A3%E8%B5%A3%E6%98%8E |
| 爱与光 眼镜 | %E7%88%B1%E4%B8%8E%E5%85%89+%E7%9C%BC%E9%95%9C |

在调用 WebFetch 时直接拼到 URL 里。

---

## 强制规则（不可违反）

1. ✅ **必须全平台搜索** — 不能省略任何一个平台，不能因为怕麻烦跳过
2. ✅ **必须一次性并行发起** — WebFetch 全部同时发起，不设间隔
3. ✅ **必须记录所有结果** — 命中/未命中/反爬/空结果都要记录
4. ✅ **必须标注数据来源** — 真实数据标注平台，虚拟数据标注⚠️虚拟
5. ❌ **不允许AI推理代替搜索** — 只有全部搜索都不可用时才降级
