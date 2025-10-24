"""AI-Assisted Script Generator with TEE Attestation"""

import os
import json
import secrets
import httpx
from typing import Dict, Any, Optional, Tuple
from datetime import datetime


class AIScriptGenerator:
    """Generate code using configurable AI backends (RedPill or local Ollama)."""

    def __init__(self, api_key: str = None, api_url: str = None, provider: Optional[str] = None):
        inferred_provider = provider or os.getenv("AI_PROVIDER")
        if not inferred_provider:
            inferred_provider = "redpill" if (api_key or os.getenv("REDPILL_API_KEY")) else "ollama"

        self.provider = inferred_provider.lower()
        self.model = os.getenv("AI_MODEL")
        if self.provider == "ollama":
            self.api_url = api_url or os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
            self.api_key = None
            self.model = self.model or os.getenv("OLLAMA_MODEL", "qwen3:0.6b")
            self.supports_attestation = False
            print(f"🤖 AI Generator (Ollama): {self.model} @ {self.api_url}")
        else:
            self.api_key = api_key or os.getenv("REDPILL_API_KEY")
            self.api_url = api_url or os.getenv("REDPILL_API_URL", "https://api.redpill.ai")
            if not self.api_key:
                raise ValueError("REDPILL_API_KEY not set")
            self.model = self.model or "phala/qwen-2.5-7b-instruct"
            self.supports_attestation = True
            print(f"🤖 AI Generator (RedPill): {self.model}")

        self.temperature = float(os.getenv("AI_TEMPERATURE", "0.3"))
        self.max_tokens = int(os.getenv("AI_MAX_TOKENS", "2000"))

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
        code, attestation = await self._call_ai(prompt, attestation_flag)
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
        code, attestation = await self._call_ai(prompt, attestation_flag)
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
        include_attestation: bool
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        if self.provider == "ollama":
            return await self._call_ollama(prompt)
        return await self._call_redpill(prompt, include_attestation)

    async def _call_redpill(
        self,
        prompt: str,
        include_attestation: bool
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        # Generate fresh nonce for attestation
        nonce = secrets.token_hex(32) if include_attestation else None

        async with httpx.AsyncClient() as client:
            # 1. Make inference request
            headers = {
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json"
            }

            if nonce:
                headers["X-Attestation-Nonce"] = nonce

            try:
                inference_response = await client.post(
                    f"{self.api_url}/v1/chat/completions",
                    headers=headers,
                    json={
                        "model": self.model,
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are an expert programmer. Generate clean, runnable code."
                            },
                            {
                                "role": "user",
                                "content": prompt
                            }
                        ],
                        "temperature": self.temperature,
                        "max_tokens": self.max_tokens
                    },
                    timeout=60.0
                )

                if inference_response.status_code != 200:
                    raise Exception(f"AI API returned status {inference_response.status_code}: {inference_response.text}")

                result = inference_response.json()

                # Extract generated code
                code = result["choices"][0]["message"]["content"]
                code = self._extract_code(code)

                # 2. Fetch attestation if requested
                attestation_data = None
                if include_attestation:
                    try:
                        attestation_data = await self._fetch_attestation(
                            nonce=nonce,
                            inference_timestamp=result.get("created"),
                            model=self.model
                        )

                        # Add inference metadata
                        attestation_data["inference"] = {
                            "model": self.model,
                            "prompt_hash": self._hash_prompt(prompt),
                            "response_hash": self._hash_response(code),
                            "timestamp": result.get("created"),
                            "usage": result.get("usage")
                        }
                    except Exception as e:
                        print(f"⚠️ Attestation fetch failed (code generation succeeded): {e}")
                        attestation_data = {"error": f"Attestation unavailable: {str(e)}"}

                return code, attestation_data

            except Exception as e:
                raise Exception(f"AI generation failed: {str(e)}")

    async def _call_ollama(self, prompt: str) -> Tuple[str, Optional[Dict[str, Any]]]:
        """Call local Ollama server for code generation."""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are an expert programmer. Generate clean, runnable code."},
                {"role": "user", "content": prompt},
            ],
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
            "stream": False,
        }

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(f"{self.api_url}/api/chat", json=payload)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise Exception(f"Ollama call failed: {exc}") from exc

        content_type = response.headers.get("content-type", "").lower()
        content = ""
        if "application/json" in content_type:
            data = response.json()
            content = data.get("message", {}).get("content", "")
        else:
            for line in response.text.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue
                message = chunk.get("message") or {}
                content += message.get("content", "")

        if not content:
            raise Exception(f"Unexpected Ollama response: {response.text[:200]}")

        code = self._extract_code(content)
        return code, None

    async def _fetch_attestation(
        self,
        nonce: str,
        inference_timestamp: Optional[int],
        model: str
    ) -> Dict[str, Any]:
        """Fetch TEE attestation report for the inference"""
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{self.api_url}/v1/attestation/report",
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
