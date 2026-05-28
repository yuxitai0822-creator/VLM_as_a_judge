"""
Judge Pipeline 2 — Deterministic constraint parsing + task-specific prompt + per-constraint VLM inference.

Flow (per sample):
    text  →  parse_constraints()  →  [constraint_1, …, constraint_n]
                                              ↓
    for each constraint:
        template_router(constraint)  →  specialized prompt
        VLM(prompt, render_image)    →  {match: bool, reason: str}
                                              ↓
    aggregate all booleans  →  final verdict

Unlike pipeline1 (one generic prompt → one end2end verdict),
pipeline2 makes N VLM calls (one per constraint) with focused,
task-specific prompts that combat attention drift.
"""

from __future__ import annotations

import base64
import io
import json
import re
import sys
from pathlib import Path
from typing import Any

import yaml
from PIL import Image

# Make constraint_engine importable from this location
_SCRIPTS_DIR = Path(__file__).resolve().parent.parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from constraint_engine.parser import parse_text
from constraint_engine.prompt_router import template_router
from constraint_engine.schema import Constraint

CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config.yaml"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

def load_config(path: str | Path | None = None) -> dict:
    p = Path(path) if path else CONFIG_PATH
    if not p.exists():
        raise FileNotFoundError(f"Config not found: {p}")
    return yaml.safe_load(p.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

def _image_to_base64(image: Image.Image, fmt: str = "PNG") -> str:
    buf = io.BytesIO()
    image.save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def _parse_response(raw: str) -> dict:
    """Extract JSON from model response, tolerating markdown fences."""
    json_str = raw

    fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?\s*```", raw, re.DOTALL)
    if fence_match:
        json_str = fence_match.group(1)

    brace_match = re.search(r"\{.*\}", json_str, re.DOTALL)
    if brace_match:
        json_str = brace_match.group(0)

    try:
        parsed = json.loads(json_str)
    except json.JSONDecodeError:
        return {
            "match": None,
            "reason": f"Failed to parse model response: {raw[:200]}",
        }

    match_val = parsed.get("match")
    return {
        "match": bool(match_val) if match_val is not None else None,
        "reason": str(parsed.get("reason", "")),
    }


# ---------------------------------------------------------------------------
# ConstraintJudge — core pipeline2 class
# ---------------------------------------------------------------------------

class ConstraintJudge:
    """
    Pipeline2 VLM Judge.

    For each sample:
      1. Parse text → constraints (deterministic, regex-based)
      2. For each constraint → specialized prompt via template_router
      3. Call VLM per constraint → individual match/mismatch
      4. Aggregate: all match → sample matches; any fail → mismatch
    """

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        model: str = "",
        max_tokens: int = 256,
        temperature: float = 0.0,
        **kwargs,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.max_workers = kwargs.get("max_workers", 1)

    # --- single constraint VLM call ---

    def _call_vlm(self, prompt: str, image: Image.Image) -> dict:
        """Send a specialized verification prompt + image to the VLM."""
        import time
        from openai import APIError, APITimeoutError, RateLimitError, APIConnectionError, OpenAI

        b64 = _image_to_base64(image)
        data_uri = f"data:image/png;base64,{b64}"

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_uri}},
                    {"type": "text", "text": prompt},
                ],
            },
        ]

        max_retries = 3
        for attempt in range(max_retries):
            try:
                client = OpenAI(base_url=self.base_url, api_key=self.api_key)
                response = client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    max_tokens=self.max_tokens,
                    temperature=self.temperature,
                )
                return _parse_response(response.choices[0].message.content.strip())
            except (RateLimitError, APITimeoutError, APIConnectionError) as e:
                print(f"    [RETRY {attempt+1}/{max_retries}] {type(e).__name__}: {e}")
                if attempt < max_retries - 1:
                    time.sleep(5)
                    continue
                return {"match": None, "reason": f"API error after {max_retries} retries: {e}"}
            except APIError as e:
                print(f"    [API ERROR] {type(e).__name__}: {e}")
                raise

    # --- concurrent constraint evaluation ---

    def _evaluate_constraints_batch(
        self, constraints: list[Constraint], image: Image.Image
    ) -> list[dict]:
        """Evaluate all constraints concurrently using ThreadPoolExecutor."""
        from concurrent.futures import ThreadPoolExecutor, as_completed

        results: list[dict | None] = [None] * len(constraints)
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            future_map = {
                pool.submit(self._evaluate_constraint, c, image): i
                for i, c in enumerate(constraints)
            }
            for future in as_completed(future_map):
                idx = future_map[future]
                results[idx] = future.result()

        for i, r in enumerate(results):
            tag = "PASS" if r["match"] else "FAIL"
            ct = r["constraint_type"]
            dim = r.get("dimension") or ""
            val = r.get("value", "")
            print(f"    constraint {i+1}/{len(constraints)}: [{tag}] "
                  f"{ct} {dim}={val}")

        return results

    # --- per-constraint evaluation ---

    def _evaluate_constraint(
        self, constraint: Constraint, image: Image.Image
    ) -> dict:
        """Evaluate a single constraint against the render image."""
        prompt = template_router(constraint)
        vlm_result = self._call_vlm(prompt, image)

        return {
            "constraint_type": constraint["constraint_type"],
            "entity": constraint.get("entity", {}),
            "dimension": constraint.get("dimension"),
            "value": constraint.get("value"),
            "match": vlm_result["match"],
            "reason": vlm_result.get("reason", ""),
        }

    # --- main entry: judge a full sample ---

    def judge(self, text: str, image: Image.Image | str | Path) -> dict:
        """
        Judge whether a CAD render matches its text description.

        Returns:
            {
                "match": bool,                    # final aggregated verdict
                "error_type": str,                # first failing constraint type
                "reason": str,                    # summary
                "constraint_results": [...],       # per-constraint details
                "total_constraints": int,
                "passed": int,
                "failed": int,
            }
        """
        if isinstance(image, (str, Path)):
            image = Image.open(image).convert("RGB")

        # Step 1: deterministic parse
        constraints = parse_text(text)

        # Step 2: per-constraint VLM inference
        if self.max_workers > 1:
            constraint_results = self._evaluate_constraints_batch(constraints, image)
        else:
            constraint_results = []
            for i, c in enumerate(constraints):
                result = self._evaluate_constraint(c, image)
                constraint_results.append(result)
                tag = "PASS" if result["match"] else "FAIL"
                ct = result["constraint_type"]
                dim = result.get("dimension") or ""
                val = result.get("value", "")
                print(f"    constraint {i+1}/{len(constraints)}: [{tag}] "
                      f"{ct} {dim}={val}")

        # Step 3: aggregate
        failed = [r for r in constraint_results if not r["match"]]
        passed_count = len(constraint_results) - len(failed)
        all_match = len(failed) == 0

        error_type = ""
        if failed:
            error_type = failed[0]["constraint_type"]

        reason = (
            f"All {len(constraints)} constraints passed"
            if all_match
            else f"{len(failed)}/{len(constraints)} constraints failed"
        )

        return {
            "match": all_match,
            "error_type": error_type,
            "reason": reason,
            "constraint_results": constraint_results,
            "total_constraints": len(constraint_results),
            "passed": passed_count,
            "failed": len(failed),
        }

    # --- batch ---

    def judge_batch(self, samples: list[dict]) -> list[dict]:
        """Judge a list of samples. Each sample: {text, image_path}."""
        results = []
        for i, s in enumerate(samples):
            text = s["text"]
            image = s.get("image_path") or s.get("image")

            print(f"\n[{i+1}/{len(samples)}] {s.get('sample_id', f'sample_{i+1}')}")
            result = self.judge(text, image)
            results.append(result)

            verdict = "MATCH" if result["match"] else f"MISMATCH ({result['error_type']})"
            print(f"  >> {verdict}  "
                  f"({result['passed']}/{result['total_constraints']} constraints passed)")

        return results


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_judge(config_path: str | Path | None = None) -> ConstraintJudge:
    """Create a ConstraintJudge from config.yaml."""
    cfg = load_config(config_path)
    api_cfg = cfg.get("api", {})
    return ConstraintJudge(
        base_url=api_cfg.get("base_url", ""),
        api_key=api_cfg.get("api_key", ""),
        model=api_cfg.get("model", ""),
        max_tokens=api_cfg.get("max_tokens", 256),
        temperature=api_cfg.get("temperature", 0.0),
        max_workers=api_cfg.get("max_concurrency", 1),
    )
