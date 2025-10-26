"""AI-Assisted Script Generator with TEE Attestation"""

import os
import json
import secrets
from typing import Dict, Any, Optional, Tuple
from datetime import datetime

import httpx
import asyncio

try:
    from openai import OpenAI
except ImportError as exc:  # pragma: no cover - dependency missing
    OpenAI = None  # type: ignore
    _OPENAI_IMPORT_ERROR = exc
else:
    _OPENAI_IMPORT_ERROR = None


class AIScriptGenerator:
    """Generate code using configurable AI backends (RedPill or local Ollama)."""

    def __init__(self, api_key: str = None, api_url: str = None, provider: Optional[str] = None):
        if OpenAI is None:
            raise RuntimeError(
                "openai package not installed. Install with `pip install openai` to enable AI generation."
            ) from _OPENAI_IMPORT_ERROR

        inferred_provider = (provider or os.getenv("AI_PROVIDER") or "ollama").lower()
        if inferred_provider != "ollama":
            print(
                "⚠️ AI provider '%s' not supported in this build. Falling back to local Ollama." % inferred_provider
            )
            inferred_provider = "ollama"

        self.provider = inferred_provider
        self.model = os.getenv("AI_MODEL") or os.getenv("OLLAMA_MODEL")

        self.temperature = float(os.getenv("AI_TEMPERATURE", "0.3"))
        self.max_tokens = int(os.getenv("AI_MAX_TOKENS", "2000"))

        self.api_base = api_url or os.getenv("AI_API_BASE")
        self.api_key = api_key or os.getenv("AI_API_KEY")

        # Ollama backend
        default_base = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
        self.api_base = self._normalize_base_url(self.api_base or default_base)
        self.api_key = self.api_key or os.getenv("OLLAMA_API_KEY", "ollama")
        self.model = self.model or "gemma3:4b"
        self.supports_attestation = False
        provider_label = "Ollama"

        self._client = OpenAI(api_key=self.api_key, base_url=self.api_base)
        print(f"🤖 AI Generator ({provider_label} via OpenAI SDK): {self.model} @ {self.api_base}")

    async def generate_python_script(
        self,
        task_description: str,
        context: Dict[str, Any] = None,
        include_attestation: bool = True
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Generate Python code from natural language with TEE attestation.

        Returns:
            (code, attestation_data) tuple
        """
        prompt = self._build_prompt("python", task_description, context)
        attestation_flag = include_attestation and self.supports_attestation
        code, attestation = await self._call_ai(prompt, attestation_flag, language="python")
        return code, attestation

    async def generate_javascript_script(
        self,
        task_description: str,
        context: Dict[str, Any] = None,
        include_attestation: bool = True
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Generate JavaScript code from natural language with TEE attestation.

        Returns:
            (code, attestation_data) tuple
        """
        prompt = self._build_prompt("javascript", task_description, context)
        attestation_flag = include_attestation and self.supports_attestation
        code, attestation = await self._call_ai(prompt, attestation_flag, language="javascript")
        return code, attestation

    def _build_prompt(
        self,
        language: str,
        task: str,
        context: Optional[Dict[str, Any]]
    ) -> str:
        """Build optimized prompt for code generation"""

        # Handle retry context with previous errors
        if context and "previous_code" in context:
            base_prompt = f"""The previous code failed. Generate a corrected version.

Previous code:
```{language}
{context['previous_code']}
```

Error:
{context.get('error', 'Unknown error')}

Task: {task}

Generate corrected code that fixes the error. Return only the code, no explanations."""
        else:
            base_prompt = f"""You are an expert {language} programmer. Generate clean, efficient code for the following task.

Task: {task}

Requirements:
- Write production-quality code
- Include error handling
- Add brief comments for complex logic
- Return only the code, no markdown fences or explanations
- Ensure code is self-contained and runnable"""

        if language == "python":
            base_prompt += """

Available libraries: numpy, pandas, matplotlib, requests, web3, eth_account, json, os, sys
Output format: Pure Python code only"""
        elif language == "javascript":
            base_prompt += """

Available libraries: ethers, axios, crypto, fs
Output format: Pure JavaScript code only"""

        if context and "previous_code" not in context:
            base_prompt += f"\n\nContext:\n{json.dumps(context, indent=2)}"

        return base_prompt

    async def _call_ai(
        self,
        prompt: str,
        include_attestation: bool,
        *,
        language: str
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        return await self._call_openai(prompt, include_attestation, language=language)

    def _build_system_prompt(self, language: str) -> str:
        language = language.lower()
        if language == "python":
            return (
                "You are an elite Python developer. Respond with a complete, runnable Python script that strictly "
                "follows the user's instructions. Do not add markdown, explanations, JSON, or commentary—return raw "
                "code only. The script must define a resolve_oracle() function returning a dict with the keys "
                "'decision', 'reason', and 'data'. Finish by executing the guard block described by the user."
            )
        if language == "javascript":
            return (
                "You are an elite JavaScript engineer. Respond with a single runnable JavaScript file that strictly "
                "follows the user's instructions. Do not add markdown, explanations, JSON, or commentary—return raw "
                "code only."
            )
        return (
            "You are an expert software engineer. Respond with code only—no markdown or commentary."
        )

    async def _call_openai(
        self,
        prompt: str,
        include_attestation: bool,
        *,
        language: str,
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Call OpenAI-compatible endpoint (Ollama or RedPill) for code generation."""
        if not self._client:
            raise RuntimeError("AI client not initialized")

        messages = [
            {"role": "system", "content": self._build_system_prompt(language)},
            {"role": "user", "content": prompt},
        ]

        nonce = secrets.token_hex(32) if (include_attestation and self.supports_attestation) else None
        extra_headers = {"X-Attestation-Nonce": nonce} if nonce else None

        extra_body = self._build_extra_body()

        def _run_completion_stream():
            kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
            }
            if self.max_tokens:
                kwargs["max_tokens"] = self.max_tokens
            if extra_headers:
                kwargs["extra_headers"] = extra_headers
            if extra_body:
                kwargs["extra_body"] = extra_body

            stream = self._client.chat.completions.create(stream=True, **kwargs)
            parts: list[str] = []
            created = None
            usage = None

            for chunk in stream:
                if created is None:
                    created = getattr(chunk, "created", None)
                if getattr(chunk, "usage", None):
                    usage = chunk.usage  # type: ignore[attr-defined]
                for choice in getattr(chunk, "choices", []):
                    delta = getattr(choice, "delta", None)
                    if delta and getattr(delta, "content", None):
                        parts.append(delta.content)
                    elif getattr(choice, "message", None) and choice.message.content:
                        parts.append(choice.message.content)
            return "".join(parts), created, usage

        def _run_completion_blocking():
            kwargs: Dict[str, Any] = {
                "model": self.model,
                "messages": messages,
                "temperature": self.temperature,
            }
            if self.max_tokens:
                kwargs["max_tokens"] = self.max_tokens
            if extra_headers:
                kwargs["extra_headers"] = extra_headers
            if extra_body:
                kwargs["extra_body"] = extra_body
            return self._client.chat.completions.create(**kwargs)

        try:
            if self.provider == "ollama":
                content, created, usage = await asyncio.to_thread(_run_completion_stream)
                response_meta = {"created": created, "usage": usage}
            else:
                response = await asyncio.to_thread(_run_completion_blocking)
                choice = response.choices[0]
                content = choice.message.content or ""
                response_meta = {
                    "created": getattr(response, "created", None),
                    "usage": getattr(response, "usage", None),
                }
        except Exception as exc:
            raise Exception(f"AI generation failed: {exc}") from exc

        if not content:
            raise Exception("AI response contained no content")

        code = self._extract_code(content)
        self._validate_generated_code(code, language)

        attestation_data = None
        if nonce:
            try:
                attestation_data = await self._fetch_attestation(
                    nonce=nonce,
                    inference_timestamp=response_meta.get("created") if response_meta else None,
                    model=self.model,
                )
                attestation_data["inference"] = {
                    "model": self.model,
                    "prompt_hash": self._hash_prompt(prompt),
                    "response_hash": self._hash_response(code),
                    "timestamp": response_meta.get("created") if response_meta else None,
                    "usage": response_meta.get("usage") if response_meta else None,
                }
            except Exception as exc:
                print(f"⚠️ Attestation fetch failed (code generation succeeded): {exc}")
                attestation_data = {"error": f"Attestation unavailable: {exc}"}

        return code, attestation_data

    def _validate_generated_code(self, code: str, language: str) -> None:
        trimmed = code.strip()
        if not trimmed:
            raise Exception("Model returned empty code block")
        if language.lower() == "python":
            if "def resolve_oracle" not in trimmed:
                raise Exception("Generated code missing resolve_oracle() definition")
            if "__name__" not in trimmed:
                raise Exception("Generated code missing execution guard")
        elif language.lower() == "javascript":
            if "function resolveOracle" not in trimmed and "const resolveOracle" not in trimmed:
                raise Exception("Generated code missing resolveOracle definition")

    async def _fetch_attestation(
        self,
        nonce: str,
        inference_timestamp: Optional[int],
        model: str
    ) -> Dict[str, Any]:
        """Fetch TEE attestation report for the inference"""
        async with httpx.AsyncClient() as client:
            attestation_endpoint = f"{self.api_base.rstrip('/')}/attestation/report"
            response = await client.get(
                attestation_endpoint,
                params={
                    "model": model,
                    "nonce": nonce
                },
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=30.0
            )

            attestation = response.json()

            # Add verification metadata
            attestation["verification"] = {
                "nonce": nonce,
                "fetched_at": datetime.utcnow().isoformat(),
                "inference_timestamp": inference_timestamp
            }

            return attestation

    def _extract_code(self, ai_response: str) -> str:
        """Extract code from AI response, removing markdown fences"""
        code = ai_response.strip()

        fence_start = code.find("```")
        if fence_start != -1:
            fence_end = code.find("```", fence_start + 3)
            if fence_end != -1:
                fenced = code[fence_start + 3:fence_end]
                if fenced.startswith("python\n"):
                    code = fenced[len("python\n"):]
                else:
                    code = fenced

        # Remove markdown code fences
        if code.startswith("```python"):
            code = code[9:]
        elif code.startswith("```javascript"):
            code = code[13:]
        elif code.startswith("```js"):
            code = code[5:]
        elif code.startswith("```"):
            code = code[3:]

        if code.endswith("```"):
            code = code[:-3]

        return code.strip()

    def _hash_prompt(self, prompt: str) -> str:
        """Hash prompt for verification"""
        import hashlib
        return hashlib.sha256(prompt.encode()).hexdigest()

    def _hash_response(self, response: str) -> str:
        """Hash response for verification"""
        import hashlib
        return hashlib.sha256(response.encode()).hexdigest()

    def _build_extra_body(self) -> Optional[Dict[str, Any]]:
        if self.provider != "ollama":
            return None

        disable_reasoning = os.getenv("AI_DISABLE_REASONING", "true").lower() not in {"false", "0", "no"}
        options: Dict[str, Any] = {
            "temperature": self.temperature,
            "top_p": float(os.getenv("AI_TOP_P", "0.9")),
            "repeat_penalty": float(os.getenv("AI_REPEAT_PENALTY", "1.05")),
        }
        if self.max_tokens:
            options["num_predict"] = self.max_tokens
        if disable_reasoning:
            options["reasoning"] = {"strategy": "disabled"}

        return {"options": options}

    @staticmethod
    def _normalize_base_url(base: str, ensure_suffix: bool = True) -> str:
        """Ensure API base url points at /v1 when required."""
        base = base.rstrip("/")
        if ensure_suffix and not base.endswith("/v1"):
            base = f"{base}/v1"
        return base


async def verify_ai_attestation(attestation_data: Dict[str, Any]) -> bool:
    """
    Verify TEE attestation for AI inference (lightweight check).

    For full verification, use the verification tools in verify_ai_attestation.py
    """
    try:
        # Basic checks
        if not attestation_data.get("verified"):
            return False

        # Check timestamp freshness (within 10 minutes)
        from datetime import datetime, timedelta
        timestamp = attestation_data["attestation"]["timestamp"]
        att_time = datetime.fromisoformat(timestamp.replace('Z', '+00:00'))
        age = datetime.utcnow() - att_time.replace(tzinfo=None)

        if age > timedelta(minutes=10):
            return False

        # Check nonce is present
        if not attestation_data.get("verification", {}).get("nonce"):
            return False

        return True
    except Exception:
        return False
