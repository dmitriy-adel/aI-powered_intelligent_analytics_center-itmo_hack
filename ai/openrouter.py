import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable, List, Optional, TypeVar


import requests


from ai.schema import ANNOTATION_SCHEMA


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODELS = [
   "openai/gpt-oss-20b",
   "openai/gpt-oss-120b",
]


__all__ = [
   "DEFAULT_MODELS",
   "OpenRouterError",
   "annotate_article",
   "chat_completion",
   "complete_text",
   "default_concurrency",
   "list_models",
   "map_parallel",
]




class OpenRouterError(RuntimeError):
   pass




def _load_dotenv() -> None:
   env_path = Path(__file__).resolve().parents[1] / ".env"
   if not env_path.exists():
       return
   for line in env_path.read_text(encoding="utf-8").splitlines():
       line = line.strip()
       if not line or line.startswith("#") or "=" not in line:
           continue
       key, _, value = line.partition("=")
       key, value = key.strip(), value.strip().strip('"').strip("'")
       if key:
           os.environ[key] = value




def get_api_key() -> str:
   _load_dotenv()
   key = os.environ.get("OPENROUTER_API_KEY", "").strip()
   if not key or "..." in key or len(key) < 30:
       raise OpenRouterError(
           "OPENROUTER_API_KEY не задан или placeholder. Скопируйте .env.example → .env"
       )
   return key




def default_concurrency() -> int:
   _load_dotenv()
   raw = os.environ.get("LLM_CONCURRENCY", "4")
   try:
       return max(1, int(raw))
   except ValueError:
       return 4




def list_models() -> list[str]:
   _load_dotenv()
   raw = os.environ.get("LLM_MODELS", "").strip()
   if raw:
       return [m.strip() for m in raw.split(",") if m.strip()]
   return list(DEFAULT_MODELS)




def _parse_json_content(content: str) -> dict:
   text = (content or "").strip()
   if text.startswith("```"):
       text = text.split("\n", 1)[-1]
       if text.endswith("```"):
           text = text.rsplit("```", 1)[0]
       text = text.strip()
   try:
       return json.loads(text)
   except json.JSONDecodeError:
       start = text.find("{")
       end = text.rfind("}")
       if start >= 0 and end > start:
           return json.loads(text[start : end + 1])
       raise




def _extract_content(data: dict) -> str:
   choice = (data.get("choices") or [{}])[0]
   message = choice.get("message") or {}
   content = message.get("content")
   if content:
       return content
   reasoning = message.get("reasoning_content") or message.get("reasoning")
   if reasoning:
       return reasoning
   raise KeyError("choices[0].message.content missing")




def chat_completion(
   *,
   model: str,
   system_prompt: str,
   user_prompt: str,
   response_format: Optional[dict] = None,
   timeout: float = 120.0,
   max_retries: int = 4,
   temperature: float = 0.2,
   max_tokens: Optional[int] = None,
) -> tuple[dict, int, str]:
   """OpenRouter chat/completions. Возвращает (response_json, latency_ms, model)."""
   if "120b" in model:
       timeout = max(timeout, 300.0)


   payload: dict[str, Any] = {
       "model": model,
       "messages": [
           {"role": "system", "content": system_prompt},
           {"role": "user", "content": user_prompt},
       ],
       "temperature": temperature,
       "stream": False,
   }
   if max_tokens is not None:
       payload["max_tokens"] = max_tokens
   if response_format is not None:
       payload["response_format"] = response_format


   headers = {
       "Authorization": f"Bearer {get_api_key()}",
       "Content-Type": "application/json",
       "HTTP-Referer": "https://github.com/itmo-hack-gs-labs",
       "X-Title": "GS Labs Analytics Center",
   }


   started = time.monotonic()
   last_body = ""
   for attempt in range(max_retries):
       resp = requests.post(
           OPENROUTER_URL,
           headers=headers,
           json=payload,
           timeout=(15.0, timeout),
       )
       if resp.status_code == 429 and attempt < max_retries - 1:
           time.sleep(5 * (attempt + 1))
           continue
       if resp.status_code >= 400:
           last_body = resp.text[:500]
           raise OpenRouterError(f"{model}: HTTP {resp.status_code}: {last_body}")


       elapsed_ms = int((time.monotonic() - started) * 1000)
       return resp.json(), elapsed_ms, model


   raise OpenRouterError(f"{model}: HTTP 429 after retries: {last_body}")




def annotate_article(
   *,
   model: str,
   system_prompt: str,
   user_prompt: str,
   timeout: Optional[float] = None,
) -> dict[str, Any]:
   """Structured JSON annotation через OpenRouter."""
   timeout = timeout or (300.0 if "120b" in model else 120.0)
   schema_prompt = (
       user_prompt
       + "\n\nВерни один JSON-объект строго по этой схеме:\n"
       + json.dumps(ANNOTATION_SCHEMA, ensure_ascii=False, indent=2)
   )
   attempts: list[dict[str, Any]] = [
       {
           "response_format": {
               "type": "json_schema",
               "json_schema": {
                   "name": "news_annotation",
                   "strict": True,
                   "schema": ANNOTATION_SCHEMA,
               },
           },
           "prompt": user_prompt,
       },
       {"response_format": {"type": "json_object"}, "prompt": schema_prompt},
       {"response_format": None, "prompt": schema_prompt + "\n\nТолько JSON, без markdown."},
   ]


   last_error: Optional[Exception] = None
   for attempt in attempts:
       try:
           data, elapsed_ms, resolved = chat_completion(
               model=model,
               system_prompt=system_prompt,
               user_prompt=attempt["prompt"],
               response_format=attempt["response_format"],
               timeout=timeout,
           )
           content = _extract_content(data)
           parsed = _parse_json_content(content)
           usage = data.get("usage") or {}
           return {
               "model": resolved,
               "annotation": parsed,
               "latency_ms": elapsed_ms,
               "usage": usage,
               "cost": usage.get("cost"),
           }
       except (OpenRouterError, json.JSONDecodeError, KeyError, requests.RequestException) as exc:
           last_error = exc
           continue


   raise OpenRouterError(f"{model}: all JSON attempts failed: {last_error}")




def complete_text(
   *,
   model: str,
   system_prompt: str,
   user_prompt: str,
   timeout: Optional[float] = None,
   temperature: float = 0.3,
   max_tokens: int = 4096,
) -> dict[str, Any]:
   """Свободный текст (daily brief)."""
   timeout = timeout or (300.0 if "120b" in model else 120.0)
   data, elapsed_ms, resolved = chat_completion(
       model=model,
       system_prompt=system_prompt,
       user_prompt=user_prompt,
       timeout=timeout,
       temperature=temperature,
       max_tokens=max_tokens,
   )
   content = _extract_content(data)
   usage = data.get("usage") or {}
   return {
       "model": resolved,
       "content": content,
       "latency_ms": elapsed_ms,
       "usage": usage,
       "cost": usage.get("cost"),
   }




T = TypeVar("T")
R = TypeVar("R")




def map_parallel(
   items: List[T],
   fn: Callable[[T], R],
   *,
   concurrency: Optional[int] = None,
   label: str = "",
) -> List[R]:
   if not items:
       return []
   workers = concurrency or default_concurrency()
   if workers <= 1 or len(items) == 1:
       return [fn(x) for x in items]


   results: List[Optional[R]] = [None] * len(items)
   with ThreadPoolExecutor(max_workers=min(workers, len(items))) as pool:
       future_map = {pool.submit(fn, item): i for i, item in enumerate(items)}
       done = 0
       for future in as_completed(future_map):
           idx = future_map[future]
           results[idx] = future.result()
           done += 1
           if label and done % max(1, len(items) // 5) == 0:
               print(f"  {label}: {done}/{len(items)}")


   return [r for r in results if r is not None]




