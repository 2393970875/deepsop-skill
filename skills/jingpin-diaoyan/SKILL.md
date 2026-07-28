---
name: jingpin-diaoyan
description: "从CSV关键词数据和品类信息，构建完整的竞品调研Excel框架（Sheet1-3），含颜色标注、淘宝主图获取与嵌入、参数对比"
---

# 竞品调研框架构建（通用版）

从CSV关键词数据和品类信息，构建完整竞品调研Excel（3个Sheet），含颜色标注、淘宝主图获取与嵌入、参数对比。

## 适用场景

- 给定CSV关键词数据（1000条）+ 品类名，需要做竞品调研框架
- 需要从淘宝商品页提取不同产品的商品主图并嵌入Excel
- Sheet2需要9列A-I框架，每行产品不同的淘宝主图
- Sheet3需要28参数×10品牌横向对比，含图含链接

## 前置要求

- CSV关键词数据（包含「关键词」「推荐理由」「竞争指数」「月搜索指数」「市场出价」等字段）
- Python环境（通过`uv`或`D:\anaconda\python.exe`管理）
- Python包：openpyxl, Pillow(PIL)
- 浏览器工具（用于从淘宝获取商品主图，需登录淘宝）

## 3个Sheet结构一览

| # | Sheet名 | 结构 | 维度 |
|:--|:--|:--|:--|
| 1 | 竞争品牌定位 | 3组排列×5列/组 + 颜色标注 + 底部图例 | 前100词→4分类 |
| 2 | 小红书热搜产品 | 9列A-I × 30产品行 + 8色循环 + 品牌合并 | 品牌×30产品 |
| 3 | 竞品产品对比 | 28参数行 × B~K品牌列 + 黄色品牌行 + 嵌入图片 | 10品牌×28参数 |

---

# ⚡ 完整工作流程（按序执行）

```
[输入]                                    [工具]
品类.csv (1000条关键词)                   浏览器 (淘宝已登录)
品类名: 四件套/吸奶器/香薰蜡烛/...         Python + openpyxl + PIL
     |                                         |
     v                                         v
Step 0: 初始化Python环境
Step 1: 解析CSV & 提取品牌 + 分类前100词
     |
Step 2: 构建 Sheet1 → 竞争品牌定位 (3组排列 | 颜色标注 | 底部图例)
     |
Step 3: 设计产品清单 (选30个产品, 每个配好价位和属性)
     |
Step 4: 淘宝搜索 → 逐产品获取真实链接 + 商品主图 (最耗时!)
     |
Step 5: 构建 Sheet2 → 小红书热搜产品 (9列 | 8色 | 品牌合并)
     |
Step 6: 构建 Sheet3 → 竞品产品对比 (28参数 | 10品牌 | 嵌入图)
     |
Step 7: 保存 + 复制到桌面
```

---

# Step 0：初始化Python环境

```powershell
# 确保openpyxl和Pillow
uv pip install openpyxl Pillow
```

# Step 1：解析CSV & 分组（前100词分类）

## 读取CSV
```python
import csv
rows = []
with open('品类.csv', encoding='utf-8-sig') as f:
    for row in csv.DictReader(f):
        rows.append(row)
```

## 排序取前100
```python
def sc(r):
    try: return int(float(r['月搜索指数'].replace(',','')))
    except: return 0
rows.sort(key=sc, reverse=True)
top100 = rows[:100]
```

## 提取品牌列表（从CSV中识别）
从关键词列中提取含品牌名的关键词：
```python
# 示例品牌（需从CSV的品牌关键词提取）
brands = []  # 从CSV中提取的品牌关键词前缀
for r in rows:
    kw = r['关键词']
    # 先人工识别品牌前缀后，建立品牌名录
```

## 分类逻辑（4组）
```python
brand_kw, blue_kw, brand_blue_kw, normal_kw = [], [], [], []
for row in top100:
    kw = row['关键词']
    reason = row.get('推荐理由','')
    
    # 判断是否含品牌名
    has_brand = any(b.lower() in kw.lower() for b in BRANDS)
    # 判断是否蓝海词（注意：黑马词的理由不含"蓝海"字符串！）
    is_blue = '蓝海' in reason
    is_horse = '黑马' in reason
    
    if has_brand and (is_blue or is_horse):
        brand_blue_kw.append(row)    # 品牌+蓝海/黑马
    elif has_brand:
        brand_kw.append(row)         # 纯品牌词
    elif is_blue or is_horse:
        blue_kw.append(row)          # 纯蓝海/黑马词
    else:
        normal_kw.append(row)        # 普通词
```

**优先级**：品牌+蓝海/黑马 > 蓝海/黑马 > 品牌 > 普通

---

# Step 2：构建Sheet1 竞争品牌定位

## 布局
- **R1**: 3组标题（品牌词 / 蓝海词 / 普通词），每组合并5列，每组前也写该组数量
- **R2**: 5列表头：关键词 / 推荐理由 / 竞争指数 / 月搜索指数 / 市场出价
- **R3**: 标签行（写"蓝海词"作为标注）
- **R4+**: 数据行
- **底部**: 图例说明

## 三组排列
| 列范围 | 内容 | 数据来源 |
|:--:|:--|:--:|
| A-E | 品牌词 | brand_kw |
| F-J | 蓝海词（含品牌+蓝海）| blue_kw + brand_blue_kw |
| K-O | 普通词 | normal_kw |

## 颜色标注规则
| 条件 | 底色 | 颜色码 |
|:--|:--|:--:|
| 纯品牌词 | 🟡 黄色 | `FFF3CD` |
| 纯蓝海/黑马词 | 🔵 浅蓝 | `D1E7FF` |
| 品牌+蓝海/黑马 | 🟢 浅青 | `CFF4FC` |
| 普通词 | ⬜ 白底 | `FFFFFF` |

## 底部图例（追加4行）
在数据区之后空一行，写4行图例说明：
1. `"📌 颜色图例说明："`（加粗标题）
2. `"黄色底 = 含品牌名的关键词"`（黄底）
3. `"浅蓝底 = 蓝海词/黑马词（竞争小、有潜力的词）"`（浅蓝底）
4. `"浅青底 = 同时含品牌名 + 蓝海/黑马"`（浅青底）

## 表头样式
- R1: 深蓝 #0F172A，白色粗体字
- R2: 深蓝 #0F172A，白色粗体字
- 列宽：22 / 22 / 10 / 12 / 10
- 冻结窗格：A4

## 完整Python代码（Sheet1核心逻辑）
```python
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

DARK = PatternFill("solid",fgColor="0F172A")
BLUE = PatternFill("solid",fgColor="D1E7FF")
YELLOW = PatternFill("solid",fgColor="FFF3CD")
CYAN = PatternFill("solid",fgColor="CFF4FC")
WHITE = PatternFill("solid",fgColor="FFFFFF")

ws1 = wb.active; ws1.title = "竞争品牌定位"

groups = [
    (f"品牌词（含品牌名）（{len(brand_kw)}个）", brand_kw, 1),
    (f"蓝海词（{len(blue_kw)+len(brand_blue_kw)}个）", blue_kw+brand_blue_kw, 6),
    (f"普通词（{len(normal_kw)}个）", normal_kw, 11),
]

for title, lst, c in groups:
    ws1.merge_cells(start_row=1, start_column=c, end_row=1, end_column=c+4)
    ws1.cell(1,c,title).font = Font(bold=True,color="FFFFFF",size=9)
    ws1.cell(1,c).fill = DARK; ws1.cell(1,c).alignment = CENTER; ws1.cell(1,c).border = BORDER
    
    for j,t in enumerate(["关键词","推荐理由","竞争指数","月搜索指数","市场出价"]):
        cl = ws1.cell(2,c+j,t)
        cl.font = Font(bold=True,color="FFFFFF",size=10); cl.fill = DARK; cl.alignment = CENTER; cl.border = BORDER
    
    ws1.cell(3,c,"蓝海词").fill = BLUE; ws1.cell(3,c).border = BORDER
    
    for i, item in enumerate(lst[:100]):
        r = 4 + i
        kw = item['关键词']; reason = item.get('推荐理由','')
        has_b = any(b.lower() in kw.lower() for b in BRANDS)
        is_blue = '蓝海' in reason; is_horse = '黑马' in reason
        
        if has_b and (is_blue or is_horse): fill = CYAN
        elif is_blue or is_horse: fill = BLUE
        elif has_b: fill = YELLOW
        else: fill = WHITE
        
        for j, v in enumerate([kw, reason, item.get('竞争指数',''), item.get('月搜索指数',''), item.get('市场出价','')]):
            cl = ws1.cell(r, c+j, v)
            cl.font = Font(size=9); cl.border = BORDER; cl.alignment = LCENTER; cl.fill = fill

# 底部图例
legend_start = 4 + max(len(lst) for _, lst, _ in groups) + 2
for label, fg in [("📌 颜色图例说明：", "FFFFFF"),
    ("黄色底 = 含品牌名的关键词（品牌词）","FFF3CD"),
    ("浅蓝底 = 蓝海词/黑马词（竞争小、有潜力的词）","D1E7FF"),
    ("浅青底 = 同时含品牌名 + 蓝海/黑马（品牌+潜力词）","CFF4FC")]:
    ws1.merge_cells(start_row=legend_start, start_column=1, end_row=legend_start, end_column=15)
    ws1.cell(legend_start, 1, label).fill = PatternFill("solid",fgColor=fg)
    ws1.cell(legend_start, 1).font = Font(bold=(fg=="FFFFFF"), size=9 if fg!="FFFFFF" else 10)
    ws1.cell(legend_start, 1).alignment = Alignment(horizontal='left',vertical='center')
    ws1.cell(legend_start, 1).border = BORDER
    legend_start += 1

for c,w in {1:22,2:22,3:10,4:12,5:10,6:22,7:22,8:10,9:12,10:10,11:22,12:22,13:10,14:12,15:10}.items():
    ws1.column_dimensions[get_column_letter(c)].width = w
ws1.row_dimensions[1].height = 22; ws1.row_dimensions[2].height = 20
ws1.freeze_panes = "A4"
```

---

# Step 3：设计产品清单

在构建Sheet2之前，需要先确定30个产品的具体清单：

```python
# 30个产品的key列表，品牌分组，每个品牌2-3款
product_order = ["brand1_prod1","brand1_prod2","brand1_prod3",
    "brand2_prod1","brand2_prod2","brand2_prod3",
    ... # 共30个
]

# 每个产品的价位和属性选项
ATTRS = {
    "brand1_prod1": ("属性选项文本", "价位如¥199-499"),
    ...
}

# 每个产品的显示名称
def get_pname(key):
    names = {"brand1_prod1": "品牌1 产品1名称", ...}
    return names.get(key, key)

# 品牌映射
def get_brand(key):
    m = {"brand1":"品牌1显示名", ...}
    for k,v in m.items():
        if key.startswith(k): return v
    return key.split("_")[0].capitalize()
```

---

# Step 4：淘宝商品主图获取（最关键！）

## 4.1 搜索关键词模板
```
{品牌} + {产品名} + 旗舰店
```
例如：`Momcozy M5 免手扶吸奶器 旗舰店`

## 4.2 用浏览器搜索
```python
# 用browser navigate打开淘宝搜索页
# https://s.taobao.com/search?q={urllib.parse.quote(关键词)}
```

## 4.3 提取图片URL（JS代码）
```javascript
() => {
  const results = [];
  document.querySelectorAll('img').forEach(img => {
    let src = img.getAttribute('src') || img.getAttribute('data-src') || '';
    if (src && src.includes('alicdn') && (src.includes('.jpg') || src.includes('.jpeg')) && !src.includes('gif')) {
      const b = img.getBoundingClientRect();
      if (b.width > 50 && b.height > 50) {
        if (src.startsWith('//')) src = 'https:' + src;
        results.push(src);
      }
    }
  });
  return JSON.stringify([...new Set(results)].slice(0,5));
}
```

## 4.4 下载图片（带Referer！）
```python
import urllib.request, io
from PIL import Image

req = urllib.request.Request(url, headers={
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://www.taobao.com/'  # 必须带！否则403
})
data = urllib.request.urlopen(req, timeout=10).read()
img = Image.open(io.BytesIO(data)).convert('RGB')  # 必须convert RGB
img.save(f"product_imgs/{product_key}.jpg", 'JPEG', quality=92)
```

## 4.5 提取链接
同样在搜索结果页，从商品链接标签提取商品详情页URL。

## 4.6 存储数据
```python
product_data[key] = {
    "product_url": "https://...",
    "img_url": "https://...",
    "local_img": "product_imgs/key.jpg",
    "img_source": "taobao"
}
```

## 4.7 404处理
- 淘宝图片URL有动态签名，404了换新的URL
- CDN域名 `g-search1/2/3` 互相切换试试
- 优先 `_580x580q90.jpg` 后缀
- 批量失败后重新搜索取新URL

## 4.8 子任务并发（优化）
```markdown
你可以用 sessions_spawn 启动一个子任务专门提取图片URL：
task = "你是一个淘宝图片提取助手。逐关键词搜索淘宝，提取商品主图URL保存到 product_data.json..."
```

---

# Step 5：构建Sheet2 小红书热搜产品

## 9列框架
| 列 | 字段名 | 说明 | 宽度 |
|:--|:--|:--|:--:|
| A | 关键词1（品牌名） | 品牌显示名 | 20 |
| B | 搜索指数 | 品牌搜索指数（数字格式） | 12 |
| C | 关键词2（产品名） | 具体产品型号/名称 | 28 |
| D | 搜索指数 | 产品相关搜索指数（可估算） | 12 |
| E | 淘宝链接 | 真实商品详情页URL（可点） | 20 |
| F | 产品图（商品主图） | 130×130嵌入图 | 22 |
| G | 价位 | 价格区间（红色 #C00000） | 16 |
| H | 属性选项 | 规格/类型/香型/容量等 | 36 |
| I | 类型 | 品类分类（进口/国产/质量等） | 16 |

## 关键规则
1. **必须有真实淘宝链接和主图**，否则该行不显示！
2. **每个产品独立搜索**，同一品牌不同产品必须不同链接+不同图片
3. **品牌列合并单元格**（同一品牌的产品合并A、B列）
4. **8色循环底色**
5. **自动筛选**（A1:I末行）

## 品牌行底色（8色循环）
```python
S2_COLORS = ["E0F5FF","FFF3E0","F0FFF0","FFF0F0","F3E5F5","E8F5E9","FFF8E1","F5F5F5"]
for i,b in enumerate(all_brands): brand_color_map[b] = PatternFill("solid",fgColor=S2_COLORS[i%8])
```

## 行高
图片行改为145（130×130图片），普通行默认。

## 照片嵌入
```python
from openpyxl.drawing.image import Image as XlImage
xl = XlImage(fpath)  # 必须文件路径，不能用BytesIO！否则崩溃
xl.width = 130; xl.height = 130
xl.anchor = f'F{row}'  # 第6列
ws2.add_image(xl)
ws2.row_dimensions[row].height = 145
```

## 表头样式
- R1: 深蓝 #0F172A，白色粗体字，居中，自动筛选

## 合并品牌列
```python
ri = 2
while ri < row:
    b = ws2.cell(ri, 1).value
    if b:
        re = ri + 1
        while re < row and ws2.cell(re, 1).value == b: re += 1
        if re - ri > 1:
            ws2.merge_cells(start_row=ri, start_column=1, end_row=re-1, end_column=1)
            ws2.merge_cells(start_row=ri, start_column=2, end_row=re-1, end_column=2)
        ri = re
    else: ri += 1
```

---

# Step 6：构建Sheet3 竞品产品对比

## 布局结构
```
┌─────┬──────────────┬────────────┬────────────┬──────┬────────────┐
│     │   A          │   B        │   C        │ ...  │   K        │
├─────┼──────────────┼────────────┼────────────┼──────┼────────────┤
│ R1  │ 对比维度     │ [URL链接]  │ [URL链接]   │      │ [URL链接]  │ ←蓝灰表头
│ R2  │ 品牌         │ 品牌A      │ 品牌B      │      │ 品牌J     │ ←黄色底#FFFF00
│ R3  │ 产品名       │ 产品名A    │ 产品名B    │      │ 产品名J   │
│ R4  │ 图片         │ [100×100] │ [100×100]  │      │ [100×100] │ ←行高120
│ R5  │ 价位         │ 价格区间  │ 价格区间   │      │ 价格区间  │ ←红色
│ R6+ │ ...28参数... │           │            │      │           │
│ R29 │ 推荐理由     │ 理由文本  │ 理由文本   │      │ 理由文本  │ ←行高80
└─────┴──────────────┴────────────┴────────────┴──────┴────────────┘
```

## 颜色规范
| 区域 | 样式 |
|:--|:--|
| R1 表头行（A1 + B1~K1） | 蓝灰 `#6699CC` 白字 |
| R2 品牌行（B2~K2） | 黄色 `#FFFF00` 粗体 |
| A列（参数名列） | 蓝灰 `#6699CC` 白字 |

## 关键：B~K列对齐
```python
brands = ["品牌A","品牌B",...]  # 10个品牌
for i, brand in enumerate(brands):
    col = 2 + i  # B=2, C=3, ..., K=11
    ws3.cell(1, col).value = link  # R1: 搜索链接
    ws3.cell(2, col).value = brand # R2: 品牌名
    ws3.cell(3, col).value = prod  # R3: 产品名
    # ... 后续行全部用这个col写入
```

**常见bug**：数据从D列写入而不是B列 → 整列偏移2列！
**检查方法**：R7（面料支数）B列的值应该是最前面品牌的数据。

## 行业参数适配
不同品类的Sheet3参数不同，需要预配bp字典：
```python
bp = {
    "品牌A": {"产品名": "...", "价位": "...", "材质": "...",
              "图案": "...",  # 四件套品类用"图案"
              "适用场景": "...",
              ...},
}
```
**注意**：吸奶器品类"面料支数"改为"最大吸力"，"纱织密度"改为"吸力档位"等。

## 图片嵌入
```python
# B~K列各嵌入一张品牌主图
for i, brand in enumerate(brands):
    col = 2 + i
    key = brand_to_key[brand]
    local_img = real_data.get(key, {}).get("local_img", "")
    if local_img and os.path.exists(local_img):
        xl = XlImage(local_img)
        xl.width = 100; xl.height = 100
        xl.anchor = f'{get_column_letter(col)}4'
        ws3.add_image(xl)
ws3.row_dimensions[4].height = 120  # 图片行高
ws3.row_dimensions[29].height = 80  # 推荐理由行高
```

---

# Step 7：保存与复制

```python
# 先保存到workspace
wb.save(os.path.join(WORKSPACE, f"竞品调研框架-{品类名}.xlsx"))

# 再复制到桌面
import shutil
desktop = os.path.join(os.path.expanduser("~"), "Desktop")
try:
    shutil.copy2(src_path, os.path.join(desktop, f"竞品调研框架-{品类名}.xlsx"))
except PermissionError:
    # Excel可能打开被锁定，换个文件名
    shutil.copy2(src_path, os.path.join(desktop, f"竞品调研框架-{品类名}-v2.xlsx"))
```

---

# ⚠️ 核心规则：每一行产品必须独立获取图片和链接

这是整个工作中最重要的规则，也是最容易被忽略的坑：

- **Sheet2里每一个产品行的图片和链接都必须独立获取**
- 即使是同一品牌的不同产品，也必须搜索不同的关键词，获取不同的淘宝商品页链接和不同的商品主图
- 绝对不能用品牌通用图塞给同一品牌的不同产品行
- 绝对不能复制同一个链接给同一品牌的多个产品

**检查方法**：
- 确认图片文件数量 = 产品总数
- 同品牌多个产品图文件大小应明显不同
- Excel中E列链接应每个都不同

---

# 关键陷阱记录（避坑指南）

## 数据类
1. **Sheet3 B~K列数据必须对齐** — 最常见的bug：品牌名在第2行B~K列，但参数数据从D列写入，导致整列偏移2列。检查办法：R7"面料支数"对应B列的值应该是**第一个品牌**的数据。
2. **参数行号必须一一对应** — 第8行的数据不能错填到第7行，写入时显式指定row参数。
3. **品牌名和产品名对位** — Row2品牌名在B~K，Row3产品名也必须在同列的B~K。
4. **Sheet1 R3标签行** — 必须保留，参考文件中有这一行（写"蓝海词"）。

## 图片类
5. **浏览器evaluate必须用原始targetId** — tabId会导致"tab not found"。获取targetId：`browser open`返回的`suggestedTargetId`，或`browser tabs`查看。
6. **淘宝CDN图片下载必须带Referer头** — 不加会返回403或404。
7. **URL失效处理** — 淘宝图片URL有动态签名，404了就重新搜索取新URL。CDN域名`g-search1/2/3`可互换试试。
8. **openpyxl XlImage必须用文件路径** — 传BytesIO会报"I/O operation on closed file"。
9. **PIL必须convert('RGB')** — 避免CMYK/RGBA图片导致openpyxl错误。
10. **load_workbook + add_image 导致旧句柄关闭** — 不要修复已有工作簿插入图片，应完整重新生成Excel。

## Excel类
11. **保存前关Excel** — 否则PermissionError。被锁定时换文件名保存。
12. **Sheet1清空前必须unmerge_cells** — 否则赋值报"'MergedCell' object attribute 'value' is read-only"。
13. **Sheet3 R4图片行高=120** — 100×100图片需要足够行高。
14. **Sheet3推荐理由行高=80** — 避免多行文字截断。
15. **Sheet3 R2品牌行必须黄色底色 (#FFFF00)** — 重要视觉区分。
16. **Sheet2图片行行高=145** — 130×130图片的适配高度。

## 流程类
17. **CSV编码用utf-8-sig** — 避免BOM问题。
18. **browser navigate会更新当前tab** — 保持同一targetId，避免新建tab。
19. **子任务和主任务不要同时操作同一个targetId** — 不线程安全。
20. **黑马词也要单独判断** — 黑马词推荐理由不含"蓝海"字符串，代码中需加 `is_horse = '黑马' in reason`。

---

# 完整参考案例1：四件套品类（已验证，已落地）

## 品类
四件套（床上用品）

## 输入
- `四件套.csv`：1000条关键词
- 来源：桌面 `C:\Users\26606\Desktop\四件套.csv`

## 品牌清单
Sheet2全部品牌（17个）：MUJI无印良品、铭都、山姆、宜家、胖东来、白白叶叶、罗莱、teenieweenie、野兽派、富安娜、亚朵、舒飘儿、安敏诺、水星家纺、水漾家纺、康尔馨、造卧
Sheet3对标品牌（10个）：无印良品、铭都、山姆、宜家、胖东来、白白叶叶、罗莱、teenieweenie、野兽派、富安娜

## Sheet3参数（四件套行业版）
R1:链接 | R2:品牌(黄底) | R3:产品名 | R4:图片(120行高)
R5:价位 | R6:材质 | R7:面料支数 | R8:纱织密度 | R9:工艺 | R10:适用床尺寸
R11:是否含床笠 | R12:被套设计 | R13:枕套尺寸 | R14:颜色/花型 | R15:风格定位
R16:是否礼盒装 | R17:适用季节 | R18:手感 | R19:缩水率 | R20:色牢度
R21:是否抗菌 | R22:是否防螨 | R23:产地 | R24:发货周期 | R25:售后政策
R26:颜值评分 | R27:综合推荐指数 | R28:推荐理由(80行高)

---

# 完整参考案例2：吸奶器品类（已验证，已落地）

## 品类
吸奶器（母婴用品）

## 输入
- `吸奶器.csv`：1000条关键词
- 来源：`C:\Users\26606\.openclaw\media\outbound\006b897c-2380-42e2-97e8-064f870f8af6.csv`

## Sheet1 分类结果
品牌词58条 / 品牌+蓝海3条 / 蓝海0条 / 普通词39条
**关键发现**：吸奶器品类蓝海词极少，仅有的3条都含品牌名，说明该品类品牌词高度垄断，不易找蓝海机会。

## 品牌排名（按搜索指数）
Momcozy(121k) > 熊猫布布(100k) > 新贝(99k) > 美德乐(90k) > 卡乐怡(81k) > 小白熊(70k) > 十月结晶(59k) > 大贝贝(51k) > 波洛洛(45k) > 小雅象(39k) > 贝能(26k) > 波咯咯(22k) > 贝亲(19k)

## Sheet2 产品清单（30个）
Momcozy 3款 / 美德乐3款 / 熊猫布布3款 / 卡乐怡3款 / 小白熊3款 / 新贝3款 / 十月结晶3款 / 波洛洛3款 / 小雅象3款 / 波咯咯2款 / 贝能1款

## Sheet3 参数差异（与四件套对比）
- R7改为"最大吸力"（代替"面料支数"）
- R8改为"吸力档位"（代替"纱织密度"）
- 新增"单边/双边""是否免手扶""穿戴式""电池容量""续航时间""噪音""喇叭罩尺寸"等
- 去掉"被套设计""枕套尺寸""颜色""风格""是否礼盒装"等

---

# 通用适配指南：如何为新品类快速构建竞品调研Excel

## 新品类需要调整的配置项

| 配置项 | 说明 |
|:--|:--|
| BRANDS列表 | 从CSV的品牌关键词提取，注意大小写匹配 |
| product_order | 30个产品的key列表 |
| ATTRS字典 | 每个产品的价位和属性选项 |
| bp字典 | 10个主品牌的28参数详情 |
| get_pname() | key→产品名映射 |
| get_brand() | key→品牌名映射 |
| Sheet3参数列表 | 根据品类替换行业参数 |
| 搜索关键词模板 | `{品牌} + {产品名} + 旗舰店` |
| 图片命名规则 | `product_imgs/{product_key}.jpg` |

## 跨品类通用验证清单

执行前逐条检查：
- [ ] CSV编码是utf-8-sig
- [ ] BRANDS列表已完整覆盖品类品牌
- [ ] 100词分类逻辑包含`is_horse`判断
- [ ] Sheet3 B~K列写入正确（`col = 2 + i`）
- [ ] 所有Excel打开已关闭
- [ ] 所有产品独立搜索过，有不同链接和图片
- [ ] 淘宝搜索用 `browser navigate`（非JS跳转）
- [ ] 图片下载带 Referer 头
- [ ] XlImage用文件路径（非BytesIO）
- [ ] PIL convert('RGB')
- [ ] Sheet1底部追加了图例

## CSS选择器参考（淘宝搜索结果页）

淘宝搜索结果页的商品图片在 `<img>` 标签中，`src` 或 `data-src` 属性包含 alicdn 图片URL。页面加载完成后所有大图（580x580）的 `width > 50`。没有固定的class名可依赖，所以用 `document.querySelectorAll('img')` 全量扫描 + 尺寸过滤。
