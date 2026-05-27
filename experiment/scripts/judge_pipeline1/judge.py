"""
VLM Judge for CAD geometry verification.

Supports two inference modes:
  - "api":   OpenAI-compatible API (DashScope / vLLM / Ollama / any compatible endpoint)
  - "local": Local Qwen2.5-VL via HuggingFace transformers

Input:  text description + render image
Output: {"match": bool, "error_type": str, "reason": str}
"""

import base64
import io
import json
import re
from pathlib import Path
from typing import Any

import yaml
from PIL import Image

PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "system_prompt.txt"
CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def load_system_prompt(path: str | Path | None = None) -> str:
    p = Path(path) if path else PROMPT_PATH
    return p.read_text(encoding="utf-8").strip()


def load_config(path: str | Path | None = None) -> dict:
    p = Path(path) if path else CONFIG_PATH
    if not p.exists():
        raise FileNotFoundError(f"Config not found: {p}")
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def _image_to_base64(image: Image.Image, fmt: str = "PNG") -> str:
    buf = io.BytesIO()
    image.save(buf, format=fmt)
    return base64.b64encode(buf.getvalue()).decode("utf-8")


# ---------------------------------------------------------------------------
# API backend (OpenAI-compatible)
# ---------------------------------------------------------------------------

class APIJudge:
    """Judge via OpenAI-compatible chat completions API."""

    def __init__(
        self,
        base_url: str = "",
        api_key: str = "",
        model: str = "",
        max_tokens: int = 512,
        temperature: float = 0.0,
        system_prompt: str | None = None,
        max_concurrency: int = 8,
        **kwargs,
    ):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.system_prompt = system_prompt or load_system_prompt()
        self.max_concurrency = max_concurrency

    def judge(self, text: str, image: Image.Image | str | Path) -> dict:
        if isinstance(image, (str, Path)):
            image = Image.open(image).convert("RGB")

        b64 = _image_to_base64(image)
        data_uri = f"data:image/png;base64,{b64}"

        user_content = (
            f"Text description:\n{text}\n\n"
            "Examine the CAD rendering above and determine if it matches the description."
        )

        messages = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_uri}},
                    {"type": "text", "text": user_content},
                ],
            },
        ]

        response_text = self._call_api(messages)
        return _parse_response(response_text)

    def _call_api(self, messages: list[dict]) -> str:
        from openai import OpenAI

        client = OpenAI(
            base_url=self.base_url,
            api_key=self.api_key,
        )
        response = client.chat.completions.create(
            model=self.model,
            messages=messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        return response.choices[0].message.content.strip()

    def judge_batch(self, samples: list[dict]) -> list[dict]:
        """Run judgment on a batch of samples using async concurrent calls."""
        import asyncio

        return asyncio.run(self._judge_batch_async(samples))

    async def _judge_batch_async(self, samples: list[dict]) -> list[dict]:
        import asyncio
        from openai import AsyncOpenAI

        semaphore = asyncio.Semaphore(self.max_concurrency)
        client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)
        results = [None] * len(samples)

        async def _call_one(index: int, sample: dict):
            async with semaphore:
                if isinstance(sample["image"], (str, Path)):
                    image = Image.open(sample["image"]).convert("RGB")
                else:
                    image = sample["image"]

                b64 = _image_to_base64(image)
                data_uri = f"data:image/png;base64,{b64}"

                user_content = (
                    f"Text description:\n{sample['text']}\n\n"
                    "Examine the CAD rendering above and determine if it matches the description."
                )
                messages = [
                    {"role": "system", "content": self.system_prompt},
                    {
                        "role": "user",
                        "content": [
                            {"type": "image_url", "image_url": {"url": data_uri}},
                            {"type": "text", "text": user_content},
                        ],
                    },
                ]

                try:
                    response = await client.chat.completions.create(
                        model=self.model,
                        messages=messages,
                        max_tokens=self.max_tokens,
                        temperature=self.temperature,
                    )
                    text = response.choices[0].message.content.strip()
                    result = _parse_response(text)
                except Exception as e:
                    result = {"match": None, "error_type": "api_error", "reason": str(e)}

                results[index] = result
                done = sum(1 for r in results if r is not None)
                print(f"  [{done}/{len(samples)}] match={result.get('match')}, "
                      f"error_type={result.get('error_type')}")

        tasks = [_call_one(i, s) for i, s in enumerate(samples)]
        await asyncio.gather(*tasks)
        return results


# ---------------------------------------------------------------------------
# Local backend (Qwen2.5-VL transformers)
# ---------------------------------------------------------------------------

class QwenVLJudge:
    """Judge using Qwen2.5-VL via HuggingFace transformers."""

    def __init__(
        self,
        model_name: str = "Qwen/Qwen2.5-VL-7B-Instruct",
        device: str = "cuda",
        torch_dtype: str = "float16",
        system_prompt: str | None = None,
        **kwargs,
    ):
        self.model_name = model_name
        self.device = device
        self.torch_dtype = torch_dtype
        self.system_prompt = system_prompt or load_system_prompt()
        self._model = None
        self._processor = None

    def _load(self):
        if self._model is not None:
            return
        import torch
        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration

        dtype_map = {
            "float16": torch.float16,
            "bfloat16": torch.bfloat16,
            "float32": torch.float32,
        }
        dtype = dtype_map.get(self.torch_dtype, torch.float16)

        self._processor = AutoProcessor.from_pretrained(self.model_name)
        self._model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            self.model_name,
            torch_dtype=dtype,
            device_map=self.device,
        )

    def judge(self, text: str, image: Image.Image | str | Path) -> dict:
        self._load()

        if isinstance(image, (str, Path)):
            image = Image.open(image).convert("RGB")

        user_message = (
            f"Text description:\n{text}\n\n"
            "Examine the CAD rendering above and determine if it matches the description."
        )

        messages = [
            {"role": "system", "content": self.system_prompt},
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image},
                    {"type": "text", "text": user_message},
                ],
            },
        ]

        text_input = self._processor.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )

        from qwen_vl_utils import process_vision_info
        image_inputs, video_inputs = process_vision_info(messages)

        inputs = self._processor(
            text=[text_input],
            images=image_inputs,
            videos=video_inputs,
            padding=True,
            return_tensors="pt",
        ).to(self._model.device)

        output_ids = self._model.generate(**inputs, max_new_tokens=512)
        output_ids = output_ids[:, inputs.input_ids.shape[1]:]
        response = self._processor.batch_decode(
            output_ids, skip_special_tokens=True
        )[0].strip()

        return _parse_response(response)

    def judge_batch(self, samples: list[dict]) -> list[dict]:
        results = []
        for i, s in enumerate(samples):
            result = self.judge(s["text"], s["image"])
            results.append(result)
            print(f"  [{i+1}/{len(samples)}] match={result.get('match')}, "
                  f"error_type={result.get('error_type')}")
        return results


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
            "error_type": "parse_error",
            "reason": f"Failed to parse model response: {raw[:200]}",
        }

    return {
        "match": bool(parsed.get("match", False)) if parsed.get("match") is not None else None,
        "error_type": str(parsed.get("error_type", "")),
        "reason": str(parsed.get("reason", "")),
    }


# ---------------------------------------------------------------------------
# Factory — reads config.yaml by default
# ---------------------------------------------------------------------------

def create_judge(config_path: str | Path | None = None) -> APIJudge | QwenVLJudge:
    """
    Create a judge instance from config.yaml.

    Config determines mode ("api" or "local") and all parameters.
    No need to pass anything manually.
    """
    cfg = load_config(config_path)
    mode = cfg.get("mode", "api")
    system_prompt = load_system_prompt(cfg.get("prompt_file"))

    if mode == "api":
        api_cfg = cfg.get("api", {})
        return APIJudge(
            base_url=api_cfg.get("base_url", ""),
            api_key=api_cfg.get("api_key", ""),
            model=api_cfg.get("model", ""),
            max_tokens=api_cfg.get("max_tokens", 512),
            temperature=api_cfg.get("temperature", 0.0),
            system_prompt=system_prompt,
            max_concurrency=api_cfg.get("max_concurrency", 8),
        )
    elif mode == "local":
        local_cfg = cfg.get("local", {})
        return QwenVLJudge(
            model_name=local_cfg.get("model_name", "Qwen/Qwen2.5-VL-7B-Instruct"),
            device=local_cfg.get("device", "cuda"),
            torch_dtype=local_cfg.get("torch_dtype", "float16"),
            system_prompt=system_prompt,
        )
    else:
        raise ValueError(f"Unknown mode: {mode}. Use 'api' or 'local'.")
