# CAD-VLM-as-a-Judge

Evaluate whether Vision-Language Models can detect fine-grained geometric inconsistencies between text descriptions and CAD renderings.

## Experiment Design

### Research Question

Can VLMs reliably judge whether a CAD rendering matches its text description, specifically catching errors in object count, symmetry, relative position, and scale?

### Method

1. Prepare **positive samples** (text-render pairs that match) and **negative samples** (pairs with deliberate perturbations)
2. Feed each sample to a VLM judge
3. Compare judge outputs against ground-truth labels to compute accuracy

### Perturbation Types

| Type | Description | Example |
|------|-------------|---------|
| `count_error` | Object count changed by ±1–3 | 4 cylinders → 3 cylinders |
| `symmetry_error` | Symmetry constraint broken | rotational → none |
| `scale_error` | Dimension scaled by 0.3×–2.5× | radius 10 → radius 25 |

### Metrics

- **Overall accuracy**: (correct predictions) / (total samples)
- **Positive accuracy**: correct match=True on positive samples
- **Negative accuracy**: correct match=False on negative samples
- **Per error-type accuracy**: accuracy broken down by perturbation type

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                     text.txt + render.png                │
│                          │                               │
│              ┌───────────┴───────────┐                   │
│              │                       │                   │
│         Pipeline 1             Pipeline 2               │
│       (End-to-End VLM)    (Constraint-based)            │
│              │                       │                   │
│     1 generic prompt       Constraint Engine             │
│     + full text            (regex parser)                │
│     + render.png               │                         │
│              │           12-14 constraints                │
│              │               │                           │
│              │         Template Router                    │
│              │         (per constraint)                   │
│              │               │                           │
│              │         N× VLM calls                      │
│              │         (specialized prompt                │
│              │          + render.png)                    │
│              │               │                           │
│              │         Aggregate booleans                │
│              │               │                           │
│              └───────────────┘                           │
│                      │                                   │
│              match / mismatch                            │
└─────────────────────────────────────────────────────────┘
```

---

## Pipeline 1 — End-to-End VLM Judge

Single VLM call with a generic system prompt. The model sees the full text + render and outputs one verdict.

```
text + render.png → generic prompt → VLM → {match, error_type, reason}
```

## Pipeline 2 — Constraint-Based VLM Judge

Decomposes the verification into per-constraint checks with task-specific prompts.

```
text.txt
    ↓
Constraint Engine (deterministic regex parser)
    ↓
12-14 structured constraints
    ↓
Template Router (constraint_type → specialized prompt)
    ↓
N× VLM calls (one constraint + render.png each)
    ↓
Aggregate: all pass → MATCH | any fail → MISMATCH
```

### Why Pipeline 2?

The primary failure mode of VLMs on this task is **attention drift** — the model is distracted by irrelevant dimensions, objects, or annotations. Pipeline 2 mitigates this by:

1. **Decomposing** the verification into atomic checks (one dimension per call)
2. **Specializing** the prompt per constraint type (count, size, distance, radius)
3. **Focusing** the VLM's attention on exactly one reasoning task per inference

---

## Constraint Engine

A deterministic compiler that converts templated text descriptions into structured constraints using regex + fixed mapping rules.

### Architecture

```
constraint_engine/
├── schema.py              # Canonical constraint schemas + factory helpers
├── templates.py           # Regex patterns for each text line
├── parser.py              # parse_text() / parse_file() entry point
├── prompt_router.py       # constraint → classify → template → filled prompt
├── generators/
│   ├── baseplate.py       # Rule 1: Chengtai rectangle (2 size constraints)
│   ├── dunzhu.py          # Rule 2: rounded rectangles (count + distance + 3× size)
│   ├── zhuangji.py        # Rule 3: circles (count + 2× distance + radius)
│   └── height.py          # Rule 4: z-axis heights (3× size)
└── prompt_templates/
    ├── count.txt           # "count the objects, ignore dimensions"
    ├── size.txt            # "check this dimension, ignore others"
    ├── distance.txt        # "measure center-to-center on this axis"
    └── radius.txt          # "check radius of circular objects"
```

### Constraint Schema

Three canonical types:

**Size Constraint** — a single dimension of one entity:

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

**Distance Constraint** — center-to-center spacing between two entities:

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

**Count Constraint** — number of instances in a grid layout:

```json
{
  "constraint_type": "count",
  "view": "top",
  "entity": {"entity_type": "Dunzhu", "geometry_type": "rounded_rectangle"},
  "layout": {"rows": 1, "cols": 2},
  "value": 2
}
```

### Parsing Rules

The text follows exactly 6 templated lines:

| Line | Template | Generator | Constraints |
|------|----------|-----------|-------------|
| 1 | `A rectangular base plate with width W and height H.` | baseplate | 2× size (width, height) |
| 2 | `Contains N rounded rectangle(s) arranged horizontally with spacing S, each W wide, H tall, corner radius R.` | dunzhu | 1× count + 1× distance + 3× size |
| 3 | `Contains N circle(s) in a R×C grid layout, horizontal spacing HS, vertical spacing VS, radius R, solid/dashed line style.` | zhuangji | 1× count + 2× distance + 1× size |
| 4 | `Dunzhu (pier column) height: H.` | height | 1× size (z-axis) |
| 5 | `Chengtai (bearing platform) height: H.` | height | 1× size (z-axis) |
| 6 | `Zhuangji (pile foundation) height: H.` | height | 1× size (z-axis) |

**Total: 12–14 constraints per sample** (fewer when count=1 skips distance constraints).

### Prompt Template Router

Each constraint type is routed to a specialized verification prompt:

| Constraint Type | Template | Focus |
|----------------|----------|-------|
| `count` | count.txt | Count objects only, ignore all dimensions |
| `size` | size.txt | Check one dimension, ignore unrelated objects |
| `size` (dimension=radius) | radius.txt | Check radius of circular objects |
| `distance` | distance.txt | Measure center-to-center distance on one axis |

---

## Project Structure

```
experiment/
├── config.yaml
├── requirements.txt
├── README.md
│
├── data/
│   ├── positive/            # 25 positive samples (text == render)
│   └── negative/            # 75 negative samples (3 perturbations × 25)
│
├── results/                 # Pipeline 1 output
│
└── scripts/
    ├── run.py               # Pipeline 1 runner
    ├── run_pipeline2.py     # Pipeline 2 runner
    │
    ├── constraint_engine/   # Deterministic text → constraint compiler
    │   ├── schema.py
    │   ├── templates.py
    │   ├── parser.py
    │   ├── prompt_router.py
    │   ├── generators/
    │   └── prompt_templates/
    │
    ├── judge_pipeline1/     # End-to-end VLM judge
    │   └── judge.py
    │
    ├── judge_pipeline2/     # Constraint-based VLM judge
    │   └── judge.py
    │
    ├── evaluate_pipeline/   # Metrics + CSV export
    │   └── evaluate.py
    │
    └── data_pipeline/       # Render utilities
        ├── render.py
        └── sample_schema.py
```

## Data Format

Each sample is a directory under `data/positive/` or `data/negative/`:

```
data/positive/sample_001/
├── text.txt           # Natural language description
├── parameter.json     # CAD parameters
└── render.png         # Concatenated front + side + iso views
```

### parameter.json schema

```json
{
  "rect_width": 860,
  "rect_height": 833,
  "rounded_rect_horizontal_count": 2,
  "rounded_rect_horizontal_distance": 382,
  "rounded_rect_width": 165,
  "rounded_rect_height": 187,
  "rounded_rect_radius": 23,
  "circle_horizontal_count": 2,
  "circle_vertical_count": 2,
  "circle_horizontal_distance": 416,
  "circle_vertical_distance": 391,
  "circle_radius": 97,
  "circle_solid_or_dashed": true,
  "dunzhu_height": 325,
  "chengtai_height": 341,
  "zhuangji_height": 356
}
```

Negative samples include an extra field:

```json
{
  "...": "...(same but perturbed)...",
  "_perturbation": "count_error"
}
```

The `_perturbation` field is one of: `count_error`, `symmetry_error`, `scale_error`.

## Configuration

All settings live in `config.yaml`:

```yaml
mode: api

api:
  base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1"
  api_key: "sk-xxxxxxxx"
  model: "qwen3-vl-flash"
  max_tokens: 512
  temperature: 0.0

data_dir: "data"
output_dir: "results"
```

## Quick Start

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure

Edit `config.yaml` — fill in `api_key`, `base_url`, `model`.

### 3. Run Pipeline 1 (end-to-end)

```bash
cd experiment
python scripts/run.py
```

### 4. Run Pipeline 2 (constraint-based)

```bash
cd experiment
python scripts/run_pipeline2.py
```

Output goes to `results/pipeline2/`:
- `per_sample_results.csv` — per-sample predictions and correctness
- `metrics.json` — aggregate accuracy metrics

## Supported Models

| Model | Mode | Notes |
|-------|------|-------|
| Qwen2.5-VL / Qwen3-VL | `api` | Via DashScope or any OpenAI-compatible endpoint |
| Qwen2.5-VL | `local` | Via HuggingFace transformers (pipeline1 only) |
