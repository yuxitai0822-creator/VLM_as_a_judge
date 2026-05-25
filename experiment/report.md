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

每种约束类型路由到专用验证提示，强制 VLM 聚焦于单一推理模式。Prompt 模板将约束的全部信息（view、world_axis、layout 等）完整填入：

| 约束类型 | Prompt 文件 | 填充字段 | 核心指令 |
|---------|------------|---------|---------|
| `count` | count.txt | view, entity_type, geometry_type, rows, cols, value | "在指定视图中，按 grid layout 数对象" |
| `size` | size.txt | dimension, entity_type, geometry_type, view, world_axis, value | "在指定视图沿指定轴，检查指定维度" |
| `size` (radius) | radius.txt | entity_type, geometry_type, view, value | "查找 R 或直径标注，检查半径" |
| `distance` | distance.txt | distance_type, entity_type, geometry_type, view, world_axis, value | "先定位中心，再测量 center-center 间距" |

示例 — count 约束的完整生成 prompt：

```
You are a precise CAD geometry verifier performing a single verification task.

In the top view, count the visible Dunzhu (rounded_rectangle) objects arranged in a 1 x 2 grid layout.

Ignore all dimensions, arrows, and annotations — focus ONLY on counting.

Does the total count equal 2 and satisfy the specific layout?

Answer in JSON only:
{
  "match": true or false,
  "reason": "brief explanation"
}
```

示例 — distance 约束的完整生成 prompt：

```
Focus ONLY on the center-center distance between adjacent Zhuangji (circle) objects
in the front view, measured along the x-axis.

First identify the center of each object, then measure the center-center distance.

Does the center-center distance equal 416?
```

### 4.4 结果

100 个样本全部完成，共 1343 次 VLM 约束检查。

#### 总体指标

| 指标 | V0 Prompt (42 样本) | **V1 Prompt (100 样本)** |
|------|---------------------|--------------------------|
| 总体准确率 | 38.10% (16/42) | **74.00%** (74/100) |
| 正样本准确率 | 0.00% (0/25) | **0.00%** (0/25) |
| 负样本准确率 | 94.12% (16/17) | **98.67%** (74/75) |

> V0 = 初始 prompt（未完整填充约束信息）；V1 = 优化后的 prompt（完整填充 view、world_axis、layout 等）。V0 仅跑完 42 样本即中断。

#### 按扰动类型的负样本准确率

| 扰动类型 | V0 | **V1** |
|---------|-----|--------|
| count_error | 100% (6/6) | **100%** (25/25) |
| symmetry_error | 100% (5/5) | **100%** (25/25) |
| scale_error | 83% (5/6) | **96%** (24/25) |

#### 按约束类型的 VLM 通过率（1343 次检查）

| 约束类型 | V0 通过率 | **V1 通过率** | 变化 |
|---------|----------|-------------|------|
| `count` | 96.4% (80/83) | **92.1%** (186/202) | -4.3pp |
| `distance` | 48.6% (51/105) | **60.9%** (142/233) | **+12.3pp** |
| `size` | 62.9% (234/372) | **71.9%** (653/908) | **+9.0pp** |

#### 正样本维度失败分析（25 样本）

| 维度 | V0 失败率 | **V1 失败率** | 变化 |
|------|----------|-------------|------|
| `distance` | — (未细分) | **84%** | 49/58 FAIL |
| `size radius` | 60% | **60%** | 持平 |
| `size height` | 46% | **25%** | **-21pp** |
| `size width` | 18% | **16%** | 持平 |
| `count` | ~4% | **0%** | **0/50 FAIL** |
| `size corner_radius` | 0% | **0%** | 持平 |

#### Prompt 优化的关键改进

V1 prompt 相比 V0 的核心变化：

1. **count prompt** — 增加了 `view`（在哪个视图数）和 `rows x cols`（网格布局），并要求同时验证 count 和 layout。正样本 count 约束从 ~4% 失败率降至 0%。
2. **size prompt** — 增加了 `world_axis`（沿哪个轴量），height 失败率从 46% 大幅降至 25%。
3. **distance prompt** — 增加了 `distance_type`（center-center）和 `world_axis`，通过率从 48.6% 提升至 60.9%。
4. **radius prompt** — 增加了 `view` 和"look for R or diameter annotations"引导。

---

## 5. Pipeline 1 vs Pipeline 2 对比分析

### 5.1 综合对比

| 维度 | Pipeline 1 | Pipeline 2 (V1 Prompt) |
|------|-----------|-----------|
| VLM 调用/样本 | 1 | 12–14 |
| Prompt 设计 | 通用单一 prompt | 按约束类型路由的专用 prompt |
| 错误归因 | 无（整体判断） | 逐约束，可精确定位失败维度 |
| 注意力控制 | 低（全文+全图） | 高（每次一个验证任务） |
| 确定性组件 | 无 | 文本→约束解析 100% 确定性 |
| 诊断价值 | 低（一个布尔值） | 高（精确定位失败维度） |
| **总体准确率** | **60%** | **74%** |
| 正样本准确率 | 0% | 0% |
| **负样本准确率** | **80%** | **98.67%** |
| 解析失败率 | 12% | 0% |
| count_error 检测 | 80% | 100% |
| symmetry_error 检测 | 76% | 100% |
| scale_error 检测 | 84% | 96% |

### 5.2 关键对比发现

**Pipeline 2 在所有维度上优于 Pipeline 1**：总体准确率 74% vs 60%，负样本准确率 98.67% vs 80%。逐约束分解 + 任务专用 prompt 策略显著优于端到端判断。

**正样本准确率均为 0%**——两个 Pipeline 都无法正确识别正样本。这说明问题不在 prompt 策略，而在模型本身无法精确读取 CAD 工程图中的数值。

**负样本检测：Pipeline 2 全面领先**——count_error 和 symmetry_error 均达到 100% 检测率，scale_error 达到 96%（仅 1 个漏检）。

**解析稳定性：Pipeline 2 (0%) > Pipeline 1 (12%)**——Pipeline 2 的短 prompt + 结构化输出几乎不会触发 token 溢出。

### 5.3 正样本失败根因分析

25 个正样本全部被判为 MISMATCH。Pipeline 2 的逐约束粒度可以精确定位每个正样本的失败点。

#### 失败维度排序

| 约束维度 | 失败率 | 受影响样本数 | 影响面 |
|---------|--------|------------|--------|
| `distance` | **84%** (49/58) | **25/25 (100%)** | 每个样本都失败 |
| `size radius` | **60%** (15/25) | **15/25 (60%)** | 多数样本失败 |
| `size height` | **25%** (31/125) | **20/25 (80%)** | 大部分样本至少一个 height 失败 |
| `size width` | **16%** (8/50) | **8/25 (32%)** | 少数样本失败 |
| `count` | **0%** (0/50) | 0/25 | 完美 |
| `size corner_radius` | **0%** (0/25) | 0/25 | 完美 |

```
正样本失败根因权重（按影响面排序）：
  distance    ████████████████████████████████  49/58 FAIL  ← 100% 样本受影响
  size height ████████████████                  31/125 FAIL ← 80% 样本受影响
  size radius ███████████████                   15/25 FAIL  ← 60% 样本受影响
  size width  ████                               8/50 FAIL  ← 32% 样本受影响
  count       (完美)                              0/50 FAIL
  corner_r    (完美)                              0/25 FAIL
```

#### 关键瓶颈：Distance（100% 样本命中）

**Distance 是正样本准确率为 0% 的首要原因。** 所有 25 个正样本都在 distance 约束上失败——58 个 distance 约束中 49 个被判为 FAIL（84% 失败率）。

Distance 约束要求模型执行两步空间推理：
1. 定位对象的几何中心
2. 测量相邻中心之间的距离

Qwen3-VL-Flash 在这个多步推理任务上几乎完全不可靠。由于聚合逻辑是 AND（所有约束都通过才算 MATCH），只要 distance 失败，正样本就不可能被判对。

#### 每样本失败详情

| 样本 | 失败数/总数 | 失败维度 |
|------|-----------|---------|
| sample_001 | 6/14 | height×3, distance×2, radius |
| sample_002 | 6/14 | width, height×2, distance×2, radius |
| sample_003 | 5/14 | height×2, distance×2 |
| sample_004 | 7/14 | width, height×2, distance×3, radius |
| sample_005 | 4/14 | height, distance×2, radius |
| sample_006 | 3/13 | width, height, distance |
| sample_007 | 5/14 | height×2, distance×2, radius |
| sample_008 | 3/13 | distance×2, radius |
| sample_009 | 6/13 | width, height×2, distance×2, radius |
| sample_010 | 6/14 | width, height×2, distance×3 |
| sample_011 | 5/14 | height, distance×3, radius |
| sample_012 | 3/12 | width, height, distance |
| sample_013 | 4/14 | distance×2, radius, height |
| sample_014 | 3/14 | distance×2, radius |
| sample_015 | 3/13 | width, height, distance |
| sample_016 | 3/12 | height×2, distance |
| sample_017 | 3/13 | height, distance×2 |
| sample_018 | 3/13 | height, distance×2 |
| sample_019 | 2/12 | distance, radius |
| sample_020 | 3/12 | distance, radius, height |
| sample_021 | 5/14 | height×2, distance×2, radius |
| sample_022 | 4/14 | distance×3, radius |
| sample_023 | 4/13 | width, height, distance×2 |
| sample_024 | 5/13 | height×2, distance×2, radius |
| sample_025 | 2/13 | distance |

**规律：** 每个正样本至少有 2 个约束失败，且 **distance 出现在每个样本的失败列表中**。最少的 sample_025 仅有 1 个 distance 失败（2/13），最多的 sample_004 有 3 个 distance 失败。

#### 结论

正样本 0% 准确率的核心瓶颈是 **distance 约束**。只要 distance 通过率从当前的 16% 提升到超过 50%，正样本就有可能开始被判对。Count 和 corner_radius 已完美通过，width 通过率也较高（84%），height 在 V1 prompt 下已改善到 75%。**Distance 是唯一需要突破的硬瓶颈。**

---

## 6. 模型对比：qwen3-vl-flash vs qwen3-vl-plus

### 6.1 总体结果对比

| 指标 | qwen3-vl-flash | qwen3-vl-plus | 变化 |
|------|---------------|---------------|------|
| **总体准确率** | **74%** (74/100) | **75%** (75/100) | +1pp |
| 正样本准确率 | 0% (0/25) | 0% (0/25) | 不变 |
| **负样本准确率** | **98.67%** (74/75) | **100%** (75/75) | +1.33pp |
| count_error 检测 | 100% (25/25) | 100% (25/25) | 持平 |
| scale_error 检测 | 96% (24/25) | **100%** (25/25) | +4pp |
| symmetry_error 检测 | 100% (25/25) | 100% (25/25) | 持平 |

### 6.2 正样本约束通过率对比：plus 全面退步

qwen3-vl-plus 在负样本上达到 100% 完美检测，但代价是**正样本上所有维度全面退步**——plus 模型严重偏向输出 `match: false`。

| 约束维度 | flash 通过率 | plus 通过率 | 变化 |
|---------|------------|------------|------|
| `count` | **100%** (50/50) | 92% (46/50) | -8pp |
| `size corner_radius` | **100%** (25/25) | 80% (20/25) | -20pp |
| `size width` | **84%** (42/50) | 24% (12/50) | **-60pp** |
| `size height` | **75%** (94/125) | 41% (51/125) | **-34pp** |
| `size radius` | **40%** (10/25) | 4% (1/25) | **-36pp** |
| `distance` | **16%** (9/58) | **0%** (0/58) | **-16pp** |

```
正样本通过率对比：
                    flash    plus
  count             ████████ 92%   ██████░░ 92%   (-8pp)
  corner_radius     ████████ 100%  ███████░ 80%   (-20pp)
  width             ███████░ 84%   ██░░░░░░ 24%   (-60pp)
  height            ██████░░ 75%   ███░░░░░ 41%   (-34pp)
  radius            ████░░░░ 40%   ░░░░░░░░  4%   (-36pp)
  distance          ██░░░░░░ 16%   ░░░░░░░░  0%   (-16pp)
```

### 6.3 正样本失败影响面对比

| 约束维度 | flash 影响样本数 | plus 影响样本数 |
|---------|----------------|----------------|
| `distance` | 25/25 (100%) | **25/25 (100%)** |
| `size height` | 20/25 (80%) | **25/25 (100%)** |
| `size width` | 8/25 (32%) | **25/25 (100%)** |
| `size radius` | 15/25 (60%) | **24/25 (96%)** |
| `size corner_radius` | 0/25 (0%) | **5/25 (20%)** |
| `count` | 0/25 (0%) | **4/25 (16%)** |

### 6.4 分析

**plus 的"完美负样本检测"是假象。** qwen3-vl-plus 在所有 100 个样本（正+负）上几乎都输出 `match: false`。负样本的 ground truth 恰好也是"不匹配"，所以 75 个负样本全部判对。但这不是"检测到了扰动"，而是模型拒绝承认任何匹配。

**plus 比 flash 更"严格"但更不"精确"。** flash 在部分维度上能正确验证（corner_radius 100%、count 100%、width 84%），plus 则在几乎所有维度上都失败——包括 flash 完美通过的 corner_radius 和 count。

**两个模型的共同瓶颈是 distance。** flash 通过率 16%，plus 通过率 0%。无论模型强弱，distance 都是 CAD 几何验证最难的任务——它要求多步空间推理（定位中心→测量间距），当前 VLM 尚未具备这一能力。

**flash 是更适合此任务的模型。** 虽然 plus 的负样本准确率更高（100% vs 98.67%），但 flash 在正样本上的约束通过率全面优于 plus（6 个维度中 5 个更高）。flash 更接近"真正理解几何"而非"一味拒绝"。

### 6.5 结论

1. **Pipeline 2 显著优于 Pipeline 1。** 总体准确率 74% vs 60%，负样本准确率 98.67% vs 80%。约束分解 + 任务专用 prompt 策略在所有维度上均优于端到端判断。

2. **Prompt 优化带来显著提升。** 完整填充约束信息（view、world_axis、layout）后，总体准确率从 38% 提升至 74%（同 Pipeline 2 框架下），distance 通过率 +12.3pp，size 通过率 +9.0pp，height 失败率从 46% 降至 25%。

3. **当前 VLM 无法精确完成 CAD 数值验证。** 两个模型（flash/plus）的正样本准确率均为 0%。distance（flash 84% 失败，plus 100% 失败）和 radius（60%/96% 失败）是最薄弱的维度。

4. **计数验证近乎完美。** flash 上 count 约束正样本 0% 失败率，100 样本上 92.1% 通过率。任务专用 prompt + layout 信息使计数成为 VLM 最可靠的推理模式。

5. **更强模型不等于更好的几何验证。** qwen3-vl-plus 负样本 100% 检测，但代价是正样本上全面退步——plus 偏向于拒绝所有匹配，flash 才是更适合此任务的模型。

6. **Distance 是核心硬瓶颈。** flash 通过率仅 16%，plus 通过率 0%。无论模型强弱，distance（定位中心→测量间距）的多步空间推理都是 VLM 的盲区。

7. **确定性约束引擎完全可靠。** regex-based parser 在 100 个样本上零解析错误。

### 6.6 建议

1. **引入容差匹配**——将精确相等改为 ±5% 或 ±10% 容差，以补偿 VLM 数值读取的固有偏差。这是最可能快速提升正样本准确率的改进
2. **测试其他 VLM**（GPT-4o、Claude Sonnet、InternVL3）——约束引擎和 prompt 路由与模型无关，可直接接入评估
3. **优化 distance prompt**——distance 是正样本上失败率最高的维度，可尝试链式思维（"先找到标注线→读数值→与目标比较"）或视觉锚定指令
4. **优化 radius prompt**——加入引导模型查找 R/Ø 标注并区分半径与直径的指令

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
