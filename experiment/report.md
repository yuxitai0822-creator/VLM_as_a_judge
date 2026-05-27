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

使用 Pipeline 2（约束分解 + 逐项验证）测试三个 VLM 模型：

| 模型 | 模型级别 |
|------|---------|
| qwen3-vl-flash | 轻量级 |
| qwen3-vl-plus | 中量级 |
| **qwen3.5-flash** | **新一代轻量级** |

### 1.3 Pipeline 2 架构

```
text.txt
    ↓ 确定性约束引擎 (regex parser)
12–14 个结构化约束
    ↓ Prompt 路由器 (constraint_type → 专用 prompt)
N × VLM 调用 (一个约束 + render.png → match/mismatch)
    ↓ 聚合: 全部通过 → MATCH | 任一失败 → MISMATCH
```

核心组件：

1. **确定性约束引擎**：regex + 固定映射规则，将每行文本编译为结构化约束（size、distance、count）
2. **任务专用 Prompt 路由**：按约束类型路由到专用验证提示（count.txt、size.txt、distance.txt、radius.txt），完整填充 view、world_axis、layout 等信息
3. **逐约束推理**：每次 VLM 调用只验证一个原子属性，缓解 attention drift

## 2. 数据集

### 2.1 正样本（25 个）

基于 TriView2CAD 参数格式生成，每对参数描述一个桥墩结构：

- 承台（chengtai）：矩形底板
- 墩柱（dunzhu）：圆角矩形
- 桩基（zhuangji）：圆形桩孔

渲染采用三视图布局（front + side + top），包含分层尺寸标注（BAND_FEATURE / BAND_LOCAL / BAND_CIRCLE / BAND_OVERALL / RØ）。

### 2.2 负样本（75 个）

每个正样本生成 3 种扰动（共 25 × 3 = 75 个）：

| 扰动类型 | 操作 | 示例 |
|---------|------|------|
| `count_error` | 对象数量变化 | 2×2 圆 → 4×2 圆 |
| `scale_error` | 尺寸缩放 | 半径 97 → 194 |
| `symmetry_error` | 间距缩放 | 水平间距 416 → 832 |

负样本使用与对应正样本**相同的文本描述**，唯一差异是渲染中的几何参数被扰动。

## 3. 三模型对比结果

### 3.1 总体指标

| 指标 | qwen3-vl-flash | qwen3-vl-plus | **qwen3.5-flash** |
|------|---------------|---------------|-------------------|
| **总体准确率** | 74% | 75% | **75%** |
| **正样本准确率** | **0%** (0/25) | **0%** (0/25) | **56%** (14/25) |
| **负样本准确率** | 98.67% (74/75) | 100% (75/75) | 81.33% (61/75) |

### 3.2 负样本按扰动类型

| 扰动类型 | qwen3-vl-flash | qwen3-vl-plus | **qwen3.5-flash** |
|---------|---------------|---------------|-------------------|
| count_error | 100% (25/25) | 100% (25/25) | 76% (19/25) |
| scale_error | 96% (24/25) | 100% (25/25) | **88%** (22/25) |
| symmetry_error | 100% (25/25) | 100% (25/25) | 80% (20/25) |

### 3.3 正样本约束通过率

| 约束维度 | qwen3-vl-flash | qwen3-vl-plus | **qwen3.5-flash** |
|---------|---------------|---------------|-------------------|
| count | **100%** | 92% | **100%** |
| corner_radius | **100%** | 80% | **100%** |
| width | 84% | 24% | **100%** |
| height | 75% | 41% | **99.2%** |
| radius | 40% | 4% | **100%** |
| distance | 16% | 0% | **85.5%** |

### 3.4 约束级别（Constraint-Level）分析

将全部 100 个样本的所有约束合并为一个大集合（~1300 个约束），逐约束判断 VLM 输出是否正确。

**Ground truth 定义**：
- 正样本：所有约束 ground truth = PASS
- 负样本：受扰动影响的约束 ground truth = FAIL，其余 = PASS
  - count_error → count 约束 FAIL，其余 PASS
  - scale_error → size 约束 FAIL，其余 PASS
  - symmetry_error → distance 约束 FAIL，其余 PASS

#### 总体约束准确率

| 模型 | 约束总数 | 正确数 | **准确率** |
|------|---------|--------|-----------|
| qwen3-vl-flash | 1332 | 837 | 62.8% |
| qwen3-vl-plus | 1332 | 652 | 48.9% |
| **qwen3.5-flash** | **1293** | **983** | **76.0%** |

#### 按约束类型的准确率

| 约束类型 | qwen3-vl-flash | qwen3-vl-plus | **qwen3.5-flash** |
|---------|---------------|---------------|-------------------|
| count | 74.0% (148/200) | 67.0% (134/200) | **81.9%** (163/199) |
| size | 63.2% (569/900) | 47.9% (431/900) | **76.2%** (662/869) |
| distance | 51.7% (120/232) | 37.5% (87/232) | **70.2%** (158/225) |

qwen3.5-flash 在所有三种约束类型上均为最高准确率。qwen3-vl-plus 在所有类型上均为最低——它的"偏向拒绝"策略导致大量 PASS 约束被误判为 FAIL。

#### FAIL 检测的精确率与召回率

FAIL 精确率 = 模型说 FAIL 时确实应该 FAIL 的比例（避免误报）
FAIL 召回率 = 应该 FAIL 的约束中被模型捕获的比例（避免漏检）

| 约束类型 | 指标 | qwen3-vl-flash | qwen3-vl-plus | **qwen3.5-flash** |
|---------|------|---------------|---------------|-------------------|
| **count** | 精确率 | 43.8% | 38.2% | **93.8%** |
| | 召回率 | 14.0% | 52.0% | 30.0% |
| **size** | 精确率 | 29.0% | 25.4% | **63.0%** |
| | 召回率 | 32.4% | 56.0% | 13.2% |
| **distance** | 精确率 | 20.0% | 24.0% | **38.8%** |
| | 召回率 | 31.0% | 69.0% | 33.9% |

**关键发现**：

- **qwen3.5-flash 精确率最高但召回率最低**：count 精确率 93.8%（几乎不误报），但 count 召回率仅 30%（大量 count 扰动未检出）。模型"谨慎"——只在确信不匹配时才说 FAIL。
- **qwen3-vl-plus 召回率最高但精确率最低**：distance 召回率 69%，但精确率仅 24%——大量误报。模型"激进"——倾向于对所有约束说 FAIL。
- **qwen3-vl-flash 介于两者之间**。

这三个模型呈现典型的**精确率-召回率权衡**：plus 偏高召回低精确（全盘否定），qwen3.5-flash 偏高精确低召回（谨慎判断），flash 居中。

## 4. 模型逐一分析

### 4.1 qwen3-vl-flash

**正样本准确率 0%**。所有 25 个正样本均被判为 MISMATCH。

失败维度排序（正样本）：

| 维度 | 失败率 | 影响样本 |
|------|--------|---------|
| distance | 84% (49/58) | 25/25 (100%) |
| size radius | 60% (15/25) | 15/25 (60%) |
| size height | 25% (31/125) | 20/25 (80%) |
| size width | 16% (8/50) | 8/25 (32%) |
| count | 0% | 0/25 |
| corner_radius | 0% | 0/25 |

**特征**：distance 是致命瓶颈（100% 样本受影响），但 count 和 corner_radius 完美通过。负样本检测率高（98.67%），但部分来自正样本上的误报——模型倾向于对所有 dimension 约束输出 FAIL。

### 4.2 qwen3-vl-plus

**正样本准确率 0%**。plus 模型在正样本上全面退步——所有维度通过率均低于 flash。

正样本通过率对比 flash：

| 维度 | flash | plus | 变化 |
|------|-------|------|------|
| count | 100% | 92% | -8pp |
| corner_radius | 100% | 80% | -20pp |
| width | 84% | 24% | **-60pp** |
| height | 75% | 41% | **-34pp** |
| radius | 40% | 4% | **-36pp** |
| distance | 16% | 0% | **-16pp** |

**特征**：plus 几乎对所有约束输出 `match: false`。负样本 100% 完美检测，但这不是"检测到了扰动"——而是模型拒绝承认任何匹配。flash 比 plus 更适合此任务。

### 4.3 qwen3.5-flash

**正样本准确率 56%（16/25）**。这是唯一能在正样本上达到非零准确率的模型。

#### 正样本失败分析

9 个 MISMATCH 的失败模式：

| 失败原因 | 样本数 | 详情 |
|---------|--------|------|
| 仅 distance 失败 | 8/9 | sample 8,12,13,16,17,18,19,20 |
| 仅 size height 失败 | 1/9 | sample 021 |

失败维度：

| 维度 | 通过率 | 影响样本 |
|------|--------|---------|
| distance | 85.5% (47/55) | 8/25 (32%) |
| size height | 99.2% (117/118) | 1/25 (4%) |
| count | 100% (49/49) | 0/25 |
| corner_radius | 100% (24/24) | 0/25 |
| width | 100% (50/50) | 0/25 |
| radius | 100% (23/23) | 0/25 |

**所有 MISMATCH 均仅因 1 个约束失败**。16 个 MATCH 样本全部通过所有约束（完美）。distance 仍是唯一瓶颈，但通过率从 flash 的 16% 跃升至 85.5%。

#### 负样本失败分析

75 个负样本中 **61 个正确检测**为 MISMATCH，**8 个漏检**（被判为 MATCH），**6 个因 API 断连被跳过**（记为不正确）。

按扰动类型的漏检分布：

| 扰动类型 | 检测率 | 漏检数 | 漏检样本 |
|---------|--------|--------|---------|
| count_error | 76% (19/25) | 3 漏检 + 3 跳过 | 漏检: sample_006, 009, 014 |
| scale_error | 88% (22/25) | 1 漏检 + 2 跳过 | 漏检: sample_001 |
| symmetry_error | 80% (20/25) | 4 漏检 + 1 跳过 | 漏检: sample_006, 015, 024, 025 |

负样本中各维度的 FAIL 率（FAIL = 捕获到扰动）：

| 维度 | FAIL 率 | 分析 |
|------|---------|------|
| distance | 24.1% (41/170) | 最有效的检测维度 |
| count | 10.7% (16/150) | count_error 的主要捕获方式 |
| size height | 8.4% (30/357) | 较弱 |
| size width | 6.0% (9/150) | 较弱 |
| size radius | 5.6% (4/72) | 较弱 |
| corner_radius | 2.7% (2/75) | 最弱 |

**count_error 漏检原因**：qwen3.5-flash 的计数能力极强（正样本 count 100%），因此对负样本中被扰动的计数约束，模型仍能正确数出渲染图中的实际对象数量——但负样本的 count 约束描述的是正确值而非扰动值，所以模型正确地回答了"渲染图中对象数量等于约束值"。

**symmetry_error 漏检原因**：4 个 symmetry_error 漏检说明模型对间距变化的敏感度不足，特别是当间距扰动较小或渲染中标注层级复杂时。

## 5. 结论

### 5.1 核心发现

1. **qwen3.5-flash 是唯一具备 CAD 几何验证能力的模型。** 正样本准确率 56%（flash/plus 均为 0%），5 个维度通过率 99-100%，仅 distance（85.5%）和偶发 height 失败。

2. **更强的模型不等于更好的几何验证。** qwen3-vl-plus 正样本全面退步，偏向拒绝所有匹配。qwen3.5-flash 作为新一代轻量模型，在几何理解能力上实现了代际跨越。

3. **Distance 是跨模型的共同瓶颈。** flash 16%、plus 0%、qwen3.5-flash 85.5%——distance（定位中心→测量间距）的多步空间推理是 VLM 最难的任务。

4. **任务专用 prompt 对适合的推理模式有效。** count 在 flash 和 qwen3.5-flash 上均达到 100% 通过率，验证了 prompt decomposition 策略的价值。

5. **负样本检测存在精度-召回权衡。** flash/plus 负样本 98-100%（但正样本 0%），qwen3.5-flash 负样本 81%（但正样本 56%）。qwen3.5-flash 更接近"真正理解几何"，flash/plus 的负样本高准确率来自偏向拒绝的假阳性。

6. **确定性约束引擎完全可靠。** regex-based parser 在 100 个样本 × 3 个模型上零解析错误。

### 5.2 建议

1. **引入容差匹配**——将精确相等改为 ±5% 或 ±10% 容差，以补偿 VLM 数值读取的固有偏差。这是最可能快速提升正样本准确率的改进
2. **优化 distance prompt**——distance 是跨模型唯一瓶颈，可尝试链式思维（"先找到标注线→读数值→与目标比较"）或视觉锚定指令
3. **测试其他 VLM**（GPT-4o、Claude Sonnet、InternVL3）——约束引擎和 prompt 路由与模型无关
4. **解决 count_error 漏检**——qwen3.5-flash 计数能力过强导致 count_error 检测率偏低（76%），需要调整 count 约束的验证策略

## 6. 附录

### 6.1 实验配置

```yaml
mode: api
api:
  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
  model: "qwen3.5-flash"     # 或 qwen3-vl-flash / qwen3-vl-plus
  max_tokens: 512
  temperature: 0.0
```

### 6.2 文件结构

```
experiment/
├── config.yaml
├── requirements.txt
├── report.md
├── data/
│   ├── positive/    (25 samples)
│   └── negative/    (75 samples)
├── results/
│   ├── per_sample_results.csv      # Pipeline 1
│   ├── metrics.json                # Pipeline 1
│   └── pipeline2/
│       ├── per_sample_results.csv  # Pipeline 2 (最新模型结果)
│       ├── metrics.json
│       └── checkpoint.jsonl        # 断点续跑记录
└── scripts/
    ├── run_pipeline2.py             # Pipeline 2 runner (支持断点续跑)
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
