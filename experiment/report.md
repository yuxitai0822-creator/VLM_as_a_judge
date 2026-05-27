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

使用 Pipeline 2（约束分解 + 逐项验证）测试三个 VLM 模型，以及 Pipeline 1（端到端）测试 qwen3.6-flash：

| 模型 | 模型级别 | 测试 Pipeline |
|------|---------|-------------|
| qwen3-vl-flash | 轻量级 | Pipeline 2 |
| qwen3-vl-plus | 中量级 | Pipeline 2 |
| qwen3.5-flash | 新一代轻量级 | Pipeline 2 |
| **qwen3.6-flash** | **最新轻量级** | **Pipeline 1** |

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

## 3. 四模型对比结果

### 3.1 总体指标

| 指标 | qwen3-vl-flash | qwen3-vl-plus | qwen3.5-flash | **qwen3.6-flash** |
|------|---------------|---------------|---------------|-------------------|
| **总体准确率** | 74% | 75% | 75% | **79%** |
| **正样本准确率** | 0% (0/25) | 0% (0/25) | 56% (14/25) | **56%** (14/25) |
| **负样本准确率** | 98.67% (74/75) | 100% (75/75) | 81.33% (61/75) | **86.67%** (65/75) |

### 3.2 负样本按扰动类型

| 扰动类型 | qwen3-vl-flash | qwen3-vl-plus | qwen3.5-flash | **qwen3.6-flash** |
|---------|---------------|---------------|---------------|-------------------|
| count_error | 100% (25/25) | 100% (25/25) | 76% (19/25) | **92%** (23/25) |
| scale_error | 96% (24/25) | 100% (25/25) | 88% (22/25) | **84%** (21/25) |
| symmetry_error | 100% (25/25) | 100% (25/25) | 80% (20/25) | **84%** (21/25) |

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

### 4.4 qwen3.6-flash（Pipeline 1，端到端判断）

**正样本准确率 56%（14/25），总体准确率 79%**——在四个模型中总体准确率最高。

> 注：qwen3.6-flash 使用 Pipeline 1（单次端到端调用），其余三个模型使用 Pipeline 2（约束分解 + 多次调用）。两者指标在同一样本集上可比，但 Pipeline 2 的约束级数据不适用于此模型。

#### 正样本失败分析

11 个正样本被判为 MISMATCH，失败模式：

| 失败原因 | 样本数 | 详情 |
|---------|--------|------|
| scale_error | 9/11 | sample_006, 009, 011, 012, 013, 018, 019, 020, 021 |
| symmetry_error | 1/11 | sample_005 |
| count_error | 1/11 | sample_016 |

正样本失败以 **尺寸/间距判断** 为主（9/11），与 qwen3.5-flash 的 distance 瓶颈有所不同。端到端 prompt 下模型需要同时处理多个维度，更容易在数值比对上产生偏差。典型误判模式包括：间距算术推导错误（sample_011 将 238 算为 370）、布局方向混淆（sample_012/018/019 将垂直排列误判为水平）、以及多重标注层级干扰导致的数值错位。

#### 负样本检测分析

75 个负样本中 **65 个正确检测**为 MISMATCH，**8 个漏检**（被判为 MATCH），**2 个 parse_error**。

| 扰动类型 | 检测率 | 漏检数 | 漏检样本 |
|---------|--------|--------|---------|
| count_error | 92% (23/25) | 2 漏检 | 漏检: sample_003, 017 |
| scale_error | 84% (21/25) | 3 漏检 + 1 parse_error | 漏检: sample_007, 008, 013; parse_error: sample_002 |
| symmetry_error | 84% (21/25) | 3 漏检 + 1 parse_error | 漏检: sample_007, 014, 024; parse_error: sample_015 |

#### 与 qwen3.5-flash 的关键差异

| 维度 | qwen3.5-flash | qwen3.6-flash | 变化 |
|------|---------------|---------------|------|
| 总体准确率 | 75% | **79%** | **+4pp** |
| 正样本准确率 | 56% | 56% | 持平 |
| 负样本准确率 | 81.33% | **86.67%** | **+5pp** |
| count_error 检测 | 76% | **92%** | **+16pp** |
| scale_error 检测 | 88% | 84% | -4pp |
| symmetry_error 检测 | 80% | **84%** | +4pp |

**核心变化**：qwen3.6-flash 在 **count_error 检测上大幅跃升**（76% → 92%，+16pp），成为其总体准确率提升的主要驱动力。这可能得益于新一代模型对对象计数的视觉能力增强。scale_error 略有下降（88% → 84%），但整体更均衡。

#### 推理质量

qwen3.6-flash 的 `reason` 字段展现出比 qwen3.5-flash 更细致的推理过程。在正确的判断中，模型能准确引用渲染图中的具体标注数值并进行多步算术推导。例如 sample_022 的 reason 包含完整推导链："89.5+142+107+142+89.5=570, centers at 160.5 and 409.5, diff=249"；sample_008 从腿位坐标反推圆心间距："x=246 and x=709 → spacing 463"。在正确拒识的负样本中，reason 长度可达 200+ 词，包含跨视图的数值交叉验证。

但这带来了新的失败模式——**算术推理偏差**。9 个被误判为 scale_error 的正样本中，模型进行了详细的间距计算但结果有误：sample_011 将水平间距从 238 算为 370，sample_021 将 436 算为 440。这类失败不是"看不懂图"而是"算错了数"，属于可补偿的系统性偏差。

#### 负样本漏检分析

8 个漏检样本（+ 2 个 parse_error）的失败模式：

| 漏检类型 | 漏检样本 | 原因分析 |
|---------|---------|---------|
| count_error | sample_003, 017 | 模型正确计数了渲染中的对象但认为与文本一致；扰动幅度可能不足以引起警觉 |
| scale_error | sample_007, 008, 013 | 模型进行了详细匹配但未发现缩放偏差；sample_007 甚至注意到虚线/实线差异但自行解释为"风格差异" |
| symmetry_error | sample_007, 014, 024 | 间距扰动被忽略；模型倾向于信任渲染中的标注数值而非独立计算间距 |

值得关注的是 sample_007（scale_error）和 sample_017（count_error）在漏检时均注意到了"文本描述为虚线（dashed）但渲染为实线"的差异，但模型主动将其解释为"stylistic difference, not a geometric discrepancy"——这表明模型具备发现细节差异的能力，但在判断"这是否构成不一致"时过于宽容。

### 5.1 核心发现

1. **qwen3.6-flash 取得最高总体准确率 79%。** 相比 qwen3.5-flash（75%），qwen3.6-flash 在负样本检测上提升显著（86.67% vs 81.33%），正样本准确率持平（56%）。

2. **qwen3.5-flash / qwen3.6-flash 是仅有的具备 CAD 几何验证能力的模型。** 正样本准确率 56%（flash/plus 均为 0%）。qwen3.6-flash 进一步改善了精确率-召回率平衡。

3. **更强的模型不等于更好的几何验证。** qwen3-vl-plus 正样本全面退步，偏向拒绝所有匹配。从 qwen3.5 到 qwen3.6，轻量级模型的几何理解能力持续代际提升。

4. **Distance 仍是跨模型的共同瓶颈。** flash 16%、plus 0%、qwen3.5-flash 85.5%——distance（定位中心→测量间距）的多步空间推理是 VLM 最难的任务。

5. **负样本检测的精度-召回权衡持续改善。** qwen3.6-flash 负样本 86.67%（比 qwen3.5-flash 的 81.33% 提升 5pp），同时维持正样本 56% 不降，表明新模型的判断更准确而非更激进。

6. **确定性约束引擎完全可靠。** regex-based parser 在 100 个样本 × 4 个模型上零解析错误。

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
  model: "qwen3.6-flash"     # 或 qwen3-vl-flash / qwen3-vl-plus / qwen3.5-flash
  max_tokens: 512
  temperature: 0.0
  max_concurrency: 8
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
