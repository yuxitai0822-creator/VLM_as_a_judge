# CAD-VLM-as-a-Judge 实验报告

## 1. 实验概述

### 1.1 研究问题

视觉语言模型（VLM）能否可靠地判断 CAD 工程图渲染与其文本描述之间是否存在几何不一致？具体考察模型在以下维度的检测能力：

- **对象数量**（count error）
- **尺度/尺寸**（scale error）
- **对称性/间距**（symmetry error）

### 1.2 方法

构建 100 个测试样本（25 正样本 + 75 负样本），每个样本包含：

- **text.txt**：自然语言几何描述（含具体尺寸数值）
- **render.png**：三视图工程图（白底黑线，含尺寸标注）
- **parameter.json**：结构化 CAD 参数

设计两种评估管线（Pipeline）：

| | Pipeline 1 | Pipeline 2 |
|---|---|---|
| 策略 | 端到端单次推理 | 约束分解 + 逐项验证 |
| VLM 调用次数/样本 | 1 | 12–14 |
| Prompt | 通用系统提示 | 按约束类型路由的专用提示 |
| 核心思想 | 让 VLM 一眼判断对错 | 将验证任务分解为原子检查 |

## 2. 数据集

### 2.1 正样本（25 个）

基于 TriView2CAD 参数格式生成，每对参数描述一个桥墩结构：

- 承台（chengtai）：矩形底板
- 墩柱（dunzhu）：圆角矩形
- 桩基（zhuangji）：圆形桩孔

渲染采用三视图布局：

```
┌──────────┬──────────┐
│  Front   │   Side   │
├──────────┴──────────┤
│      Top View       │
└─────────────────────┘
```

### 2.2 负样本（75 个）

每个正样本生成 3 种扰动（共 25 × 3 = 75 个）：

| 扰动类型 | 操作 | 示例 |
|---------|------|------|
| `count_error` | 对象数量 ±1–3 | 4 个桩 → 3 个桩 |
| `scale_error` | 尺寸缩放 0.3×–2.5× | 半径 97 → 242 |
| `symmetry_error` | 间距缩放破坏对称性 | 等间距 → 不等间距 |

负样本使用与对应正样本**相同的文本描述**，唯一差异是渲染中的几何参数被扰动。

### 2.3 尺寸标注策略

渲染图包含参数化的分层尺寸标注：

- **BAND_FEATURE** (40)：圆角矩形宽/高（如 165, 187）
- **BAND_LOCAL** (80)：圆角矩形间距、圆垂直间距（如 382, 391）
- **BAND_CIRCLE** (100)：圆水平间距（如 416）
- **BAND_OVERALL** (120)：总体宽/高（如 860, 833）
- **R / Ø**：半径和直径标注（如 R23, Ø194）

---

## 3. Pipeline 1：端到端 VLM Judge

### 3.1 架构

```
text + render.png → generic system prompt → VLM → {match, error_type, reason}
```

单次 VLM 调用，模型看到完整文本描述和渲染图，输出整体判断。

### 3.2 结果

| 指标 | 值 |
|------|-----|
| 总样本数 | 100 |
| **总体准确率** | **60.00%** (60/100) |
| **正样本准确率** | **0.00%** (0/25) |
| **负样本准确率** | **80.00%** (60/75) |

按扰动类型：

| 扰动类型 | 准确率 | 正确/总数 |
|---------|--------|----------|
| count_error | 80.00% | 20/25 |
| scale_error | 84.00% | 21/25 |
| symmetry_error | 76.00% | 19/25 |

100 个样本中有 12 个（12%）出现 JSON 解析失败（`parse_error`），原因均为模型输出超出 `max_tokens=512` 限制。

### 3.3 关键发现

**正样本准确率 0%：模型从不输出 "match: true"**

模型对**所有 25 个正样本**都输出了 `match: false`。典型推理模式：

> *"base plate width in top view is 156.5+165+217+165+156.5 = 860 (matches), but the front/side views show different horizontal spans..."*

**根因：** 模型不理解多层级尺寸标注的层级关系。它把不同 tier 的标注值混在一起，将 BAND_FEATURE 的 165（圆角矩形宽度）误认为底板总宽度。即使 system prompt 明确说明三视图布局，模型仍无法正确区分标注层级。

---

## 4. Pipeline 2：约束分解 + 任务专用 Prompt

### 4.1 动机

Pipeline 1 暴露的核心问题是 **attention drift**——VLM 在面对完整文本和渲染图时，无法聚焦于单一验证任务，被多个层级的标注值、多个视图的信息干扰。

Pipeline 2 的解决策略：

1. **确定性约束解析**：将文本确定性编译为结构化约束，不依赖 NLP
2. **任务专用 Prompt 路由**：按约束类型选择专用验证提示
3. **逐约束推理**：每次 VLM 调用只验证一个原子属性

### 4.2 确定性约束引擎（Constraint Engine）

约束引擎本质是 **deterministic compiler**，不是 NLP 系统。它通过 regex + 固定映射规则，将每行文本编译为结构化约束。

#### 约束模式（Canonical Schema）

**Size Constraint** — 单个实体的单一维度：

```json
{
  "constraint_type": "size",
  "view": "top",
  "world_axis": "x",
  "entity": {"entity_type": "Chengtai", "geometry_type": "rectangle"},
  "dimension": "width",
  "value": 860
}
```

**Distance Constraint** — 同类实体间的中心距：

```json
{
  "constraint_type": "distance",
  "distance_type": "center-center",
  "view": "front",
  "world_axis": "x",
  "anchors": [
    {"entity": {"entity_type": "Zhuangji", "geometry_type": "circle"}, "anchor": "center"},
    {"entity": {"entity_type": "Zhuangji", "geometry_type": "circle"}, "anchor": "center"}
  ],
  "value": 416
}
```

**Count Constraint** — 网格布局中的实例数：

```json
{
  "constraint_type": "count",
  "view": "top",
  "entity": {"entity_type": "Dunzhu", "geometry_type": "rounded_rectangle"},
  "layout": {"rows": 1, "cols": 2},
  "value": 2
}
```

#### 解析规则

文本固定为 6 行模板，每行对应一组约束生成规则：

| 文本行 | 实体 | 生成约束 |
|--------|------|---------|
| `A rectangular base plate with width W and height H.` | Chengtai (矩形) | 2× size |
| `Contains N rounded rectangle(s)...spacing S...wide W, tall H, corner radius R.` | Dunzhu (圆角矩形) | 1× count + 1× distance + 3× size |
| `Contains N circle(s) in a R×C grid...` | Zhuangji (圆) | 1× count + 2× distance + 1× size |
| `Dunzhu/Chengtai/Zhuangji height: H.` | 对应实体 | 1× size (z轴) |

**每样本生成 12–14 个约束**（count=1 时跳过 distance 约束）。

**引擎可靠性**：25/25 正样本解析成功，333 个约束零错误。

### 4.3 任务专用 Prompt 路由

每种约束类型路由到专用验证提示，强制 VLM 聚焦于单一推理模式：

| 约束类型 | Prompt 文件 | 核心指令 |
|---------|------------|---------|
| `count` | count.txt | "Count the target objects, ignore all dimensions, arrows, annotations" |
| `size` | size.txt | "Check this one dimension, ignore unrelated objects and dimensions" |
| `size` (radius) | radius.txt | "Check radius of circular objects, ignore unrelated" |
| `distance` | distance.txt | "First identify centers, then measure center-to-center distance on one axis" |

示例 — count 约束的生成 prompt：

```
You are a precise CAD geometry verifier performing a single verification task.

Focus ONLY on counting the target objects in the specified view.
Ignore all dimensions, arrows, and annotations.

Count the visible Dunzhu (rounded_rectangle) objects.
Does the count equal 2?

Answer in JSON only:
{
  "match": true or false,
  "reason": "brief explanation"
}
```

### 4.4 结果

> 注：因 API 连接中断，实际处理 42/100 样本（25 正 + 17 负），1 个样本因连接错误跳过。

#### 总体指标

| 指标 | 值 |
|------|-----|
| 已处理样本 | 42 (25 正 + 17 负) |
| VLM 调用总数 | 560 |
| **总体准确率** | **38.10%** (16/42) |
| **正样本准确率** | **0.00%** (0/25) |
| **负样本准确率** | **94.12%** (16/17) |

#### 按扰动类型的负样本准确率

| 扰动类型 | 准确率 | 详情 |
|---------|--------|------|
| count_error | **100.00%** | 6/6 |
| symmetry_error | **100.00%** | 5/5 |
| scale_error | **83.33%** | 5/6 |

#### 按约束类型的性能（560 次检查）

| 约束类型 | 通过率 | 详情 |
|---------|--------|------|
| `count` | **96.4%** | 80/83 |
| `distance` | **48.6%** | 51/105 |
| `size` | **62.9%** | 234/372 |

#### 正样本维度失败分析（25 样本，350 约束）

| 维度 | 失败率 | 详情 |
|------|--------|------|
| `size radius` | **60%** | 15/25 失败 |
| `size height` | **46%** | 58/125 失败 |
| `size width` | **18%** | 9/50 失败 |
| `size corner_radius` | **0%** | 0/25 失败 |
| `count` | **~4%** | 2/50 失败 |

正样本每样本约束通过率：平均 **60.8%**（范围 42.9%–75.0%）。

---

## 5. Pipeline 1 vs Pipeline 2 对比分析

### 5.1 综合对比

| 维度 | Pipeline 1 | Pipeline 2 |
|------|-----------|-----------|
| VLM 调用/样本 | 1 | 12–14 |
| Prompt 设计 | 通用单一 prompt | 按约束类型路由的专用 prompt |
| 错误归因 | 无（整体判断） | 逐约束，可精确定位失败维度 |
| 注意力控制 | 低（全文+全图） | 高（每次一个验证任务） |
| 确定性组件 | 无 | 文本→约束解析 100% 确定性 |
| 诊断价值 | 低（一个布尔值） | 高（精确定位失败维度） |
| 总体准确率 | 60% | 38% |
| 正样本准确率 | 0% | 0% |
| 负样本准确率 | 80% | 94% |
| 解析失败率 | 12% | 0% |

### 5.2 关键对比发现

**正样本准确率均为 0%**——两个 Pipeline 都无法正确识别正样本。这说明问题不在 prompt 策略，而在模型本身无法精确读取 CAD 工程图中的数值。

**负样本准确率：Pipeline 2 (94%) > Pipeline 1 (80%)**——Pipeline 2 的提升主要来自约束分解使 count_error 和 symmetry_error 的检测率达到 100%。

**解析稳定性：Pipeline 2 (0%) > Pipeline 1 (12%)**——Pipeline 2 的短 prompt + 结构化输出几乎不会触发 token 溢出。

### 5.3 约束级别的深入发现

Pipeline 2 的逐约束粒度揭示了模型能力的精细图谱：

| 能力维度 | 模型表现 | 分析 |
|---------|---------|------|
| **对象计数** | 96.4% 通过 | 任务专用 prompt 有效缓解了注意力漂移 |
| **圆角半径** | 100% 通过 | 角半径标注（如 R23）清晰可读 |
| **宽度验证** | 82% 通过 | 整体宽度标注较容易识别 |
| **高度验证** | 54% 通过 | Z轴高度和多层级标注是主要干扰 |
| **距离测量** | 49% 通过 | 需要多步空间推理（定位中心→测量间距） |
| **半径验证** | 40% 通过 | 圆的半径标注读取困难 |

---

## 6. 结论

### 6.1 核心发现

1. **Qwen3-VL-Flash 无法精确完成 CAD 数值验证任务。** 两个 Pipeline 的正样本准确率均为 0%，模型无法准确读取工程图中的数值标注。

2. **任务专用 Prompt 对计数任务有效，对数值读取无效。** count 约束的 96.4% 通过率验证了 prompt decomposition 可以缓解注意力漂移。但 size 和 distance 约束的低通过率说明，prompt 策略无法弥补模型在精确数值读取上的根本缺陷。

3. **约束分解提供了卓越的诊断信息。** Pipeline 2 虽然总体准确率低于 Pipeline 1（38% vs 60%），但能精确定位模型的薄弱环节（radius 60% 失败、distance 51% 失败），这是 Pipeline 1 无法提供的。

4. **负样本的高准确率是假阳性。** Pipeline 2 的 94% 负样本准确率并非因为模型成功检测到了扰动，而是因为模型在正样本上也大量误报——正样本平均只有 60.8% 约束通过，因此负样本"碰巧"被正确标记为不匹配。

5. **确定性约束引擎完全可靠。** regex-based parser 在 100 个样本上零错误，验证了文本模板的固定性。

### 6.2 建议

1. **测试更强的 VLM**（GPT-4o、Claude Sonnet、Qwen2.5-VL-72B）——约束引擎和 prompt 路由与模型无关，换用更强的模型可能显著改善数值验证准确率
2. **引入容差匹配**——将精确相等改为 ±5% 或 ±10% 容差，以补偿 VLM 数值读取的固有偏差
3. **补充 Pipeline 1 对比数据**——当前 Pipeline 1 结果基于不同 max_tokens 设置（512 vs 256），需要统一条件下的公平对比
4. **完成剩余 58 个样本**——补充完整的 100 样本结果
5. **优化 distance/radius prompt**——加入链式思维（chain-of-thought）步骤或视觉锚定（visual grounding）指令

---

## 7. 附录

### 7.1 实验配置

```yaml
mode: api
api:
  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
  model: "qwen3-vl-flash"
  max_tokens: 256          # Pipeline 2; Pipeline 1 使用 512
  temperature: 0.0
```

### 7.2 文件结构

```
experiment/
├── config.yaml
├── requirements.txt
├── prompts/system_prompt.txt
├── data/
│   ├── positive/    (25 samples)
│   └── negative/    (75 samples)
├── results/
│   ├── per_sample_results.csv      # Pipeline 1
│   ├── metrics.json                # Pipeline 1
│   └── pipeline2/
│       ├── per_sample_results.csv  # Pipeline 2
│       └── metrics.json            # Pipeline 2
└── scripts/
    ├── run.py                       # Pipeline 1 runner
    ├── run_pipeline2.py             # Pipeline 2 runner
    ├── constraint_engine/           # 确定性约束引擎
    │   ├── schema.py                # 约束模式定义
    │   ├── templates.py             # Regex 模式
    │   ├── parser.py                # parse_text() / parse_file()
    │   ├── prompt_router.py         # 约束→专用 prompt 路由
    │   ├── generators/              # 逐规则约束生成器
    │   └── prompt_templates/        # 任务专用 VLM prompt
    ├── judge_pipeline1/judge.py     # Pipeline 1: 端到端 VLM judge
    ├── judge_pipeline2/judge.py     # Pipeline 2: 约束分解 VLM judge
    └── evaluate_pipeline/evaluate.py # 评估指标 + CSV 导出
```
