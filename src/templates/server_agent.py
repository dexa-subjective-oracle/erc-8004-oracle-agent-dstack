"""Server Agent - AIO Sandbox Integration"""

import asyncio
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx
from web3 import Web3

from ..agent.base import AgentConfig, BaseAgent, RegistryAddresses


class ServerAgent(BaseAgent):
    """Server agent with AIO Sandbox integration and AI-assisted code generation."""

    def __init__(self, config: AgentConfig, registries: RegistryAddresses, sandbox_url: str = None):
        super().__init__(config, registries)
        self.sandbox_url = sandbox_url or os.getenv("SANDBOX_URL", "http://localhost:8080")
        print(f"📦 Sandbox: {self.sandbox_url}")

        self._oracle_task: Optional[asyncio.Task] = None
        self._oracle_poll_interval = int(os.getenv("ORACLE_POLL_INTERVAL", "30"))
        self._oracle_grace_seconds = int(os.getenv("ORACLE_SETTLEMENT_GRACE_SECONDS", "0"))
        self._evidence_dir = Path(os.getenv("ORACLE_EVIDENCE_DIR", "state/evidence"))
        self._recently_settled: Dict[str, int] = {}

        # Initialize AI generator if available
        self.ai_generator = None
        try:
            from ..agent.ai_generator import AIScriptGenerator

            self.ai_generator = AIScriptGenerator()
        except Exception as e:
            print(f"⚠️ AI Generator disabled: {e}")

    async def process_task(self, task_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute task via AIO Sandbox."""
        data = task_data.get('data', {})
        task_type = data.get('type', 'shell')

        if task_type == 'shell':
            return await self._execute_shell(data.get('command', 'echo "No command"'))
        elif task_type == 'file_read':
            return await self._read_file(data.get('path'))
        elif task_type == 'file_write':
            return await self._write_file(data.get('path'), data.get('content'))
        elif task_type == 'jupyter':
            return await self._execute_jupyter(
                data.get('code', 'print("No code provided")'),
                data.get('session_id'),
                data.get('timeout', 30)
            )
        elif task_type == 'nodejs':
            return await self._execute_nodejs(
                data.get('code', 'console.log("No code provided")'),
                data.get('files'),
                data.get('timeout', 30)
            )
        elif task_type == 'ai_generate_and_execute':
            return await self._ai_generate_and_execute(
                data.get('description', 'No description provided'),
                data.get('language', 'python'),
                data.get('context'),
                data.get('max_retries', 2),
                data.get('include_attestation', True)
            )
        else:
            return {"error": "Unknown task type", "type": task_type}

    async def start_oracle_worker(self) -> None:
        """Launch background watcher that settles oracle requests once deadlines pass."""
        if not self.oracle_client:
            print("ℹ️ Oracle watcher skipped (oracle client not configured)")
            return
        if self._oracle_task and not self._oracle_task.done():
            return
        self._oracle_task = asyncio.create_task(self._oracle_watch_loop(), name="oracle-settlement-loop")
        print(f"🕒 Oracle watcher started (poll interval {self._oracle_poll_interval}s)")

    async def run_oracle_cycle(self, price_override: Optional[int] = None) -> List[Dict[str, Any]]:
        """Process a single oracle polling cycle."""
        return await self._process_pending_requests(price_override=price_override)

    async def _oracle_watch_loop(self) -> None:
        """Continuously poll pending oracle requests and settle when ready."""
        while True:
            try:
                await self._process_pending_requests()
            except Exception as exc:  # pragma: no cover - defensive logging
                print(f"⚠️ Oracle watcher error: {exc}")
            await asyncio.sleep(self._oracle_poll_interval)

    async def _process_pending_requests(self, price_override: Optional[int] = None) -> List[Dict[str, Any]]:
        if not self.oracle_client:
            return []

        pending = await asyncio.to_thread(self.oracle_client.pending_requests)
        if not pending:
            return []

        latest_block = await asyncio.to_thread(self._registry_client.w3.eth.get_block, "latest")
        now_ts = latest_block["timestamp"]
        # Drop entries older than 5 minutes
        expiration = now_ts - 300
        self._recently_settled = {k: v for k, v in self._recently_settled.items() if v >= expiration}
        results: List[Dict[str, Any]] = []

        for request in pending:
            if request.settled:
                continue
            req_hex = request.request_id.hex()
            if req_hex in self._recently_settled:
                continue
            if not self._ready_to_settle(request, now_ts):
                continue
            if price_override is not None:
                price = price_override
                evidence = self._build_manual_evidence(request, price, now_ts)
            else:
                resolution = await self._resolve_request_with_ai(request)
                if not resolution:
                    print(f"⚠️ Skipping request {request.request_id.hex()} due to failed resolution")
                    continue
                price = resolution["price"]
                evidence = resolution["evidence"]
                evidence["settledAt"] = now_ts

            serialized = json.dumps(evidence, sort_keys=True)
            evidence_hash = Web3.keccak(text=serialized)

            print(
                f"⚙️ Settling request {request.request_id.hex()} | "
                f"timestamp={request.timestamp} price={price}"
            )
            tx_hash = await asyncio.to_thread(self.oracle_client.settle_price, request, price, evidence_hash)
            self._recently_settled[req_hex] = now_ts
            self._persist_evidence(request.request_id.hex(), evidence)
            print(f"✅ Settlement submitted: tx={tx_hash}")
            results.append(
                {
                    "requestId": request.request_id.hex(),
                    "timestamp": request.timestamp,
                    "price": price,
                    "txHash": tx_hash,
                }
            )

        return results

    def _ready_to_settle(self, request, now_ts: int) -> bool:
        deadline = request.timestamp + self._oracle_grace_seconds
        if now_ts < deadline:
            remaining = deadline - now_ts
            print(
                f"⏳ Request {request.request_id.hex()} waiting for deadline "
                f"(+{remaining}s)"
            )
            return False
        return True

    def _compute_price(self, request) -> int:
        """
        Derive a deterministic price from ancillary data for demo purposes.

        We hash the ancillary payload to keep results reproducible across runs.
        """
        if request.ancillary_data:
            digest = Web3.keccak(request.ancillary_data)
            value = int.from_bytes(digest[-8:], "big")
            return value % 1_000_000
        return 0

    def _build_manual_evidence(self, request, price: int, settled_at: int) -> Dict[str, Any]:
        ancillary = self._decode_ancillary(request.ancillary_data)
        return {
            "requestId": request.request_id.hex(),
            "identifier": Web3.to_hex(request.identifier),
            "timestamp": request.timestamp,
            "ancillary": ancillary,
            "decision": "OVERRIDE",
            "reason": "Operator-supplied price override",
            "price": price,
            "settledAt": settled_at,
        }

    @staticmethod
    def _decode_ancillary(data: bytes) -> str:
        if not data:
            return ""
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError:
            return data.hex()

    async def _resolve_request_with_ai(self, request) -> Optional[Dict[str, Any]]:
        if not self.ai_generator:
            return None

        ancillary_text = self._decode_ancillary(request.ancillary_data)
        task = self._build_resolution_task(ancillary_text)
        context: Optional[Dict[str, Any]] = {
            "request": {
                "requestId": request.request_id.hex(),
                "identifier": Web3.to_hex(request.identifier),
                "timestamp": request.timestamp,
                "ancillary": ancillary_text,
            }
        }

        attempts = 0
        last_error: Optional[str] = None
        code = ""
        attestation = None

        while attempts < 3:
            try:
                code, attestation = await self.ai_generator.generate_python_script(
                    task_description=task,
                    context=context,
                    include_attestation=False,
                )
            except Exception as exc:
                last_error = str(exc)
                print(f"⚠️ AI generation failed: {exc}")
                break

            execution = self._execute_generated_python(code)
            if execution["success"]:
                decision = execution["decision"]
                price = 1 if decision == "YES" else 0
                evidence: Dict[str, Any] = {
                    "requestId": request.request_id.hex(),
                    "identifier": Web3.to_hex(request.identifier),
                    "timestamp": request.timestamp,
                    "ancillary": ancillary_text,
                    "decision": decision,
                    "reason": execution.get("reason"),
                    "price": price,
                    "data": execution.get("data"),
                    "script": code,
                    "stdout": execution["stdout"],
                    "stderr": execution["stderr"],
                    "executedAt": datetime.utcnow().isoformat(),
                }
                if attestation:
                    evidence["attestation"] = attestation
                return {"price": price, "evidence": evidence}

            last_error = execution["stderr"] or execution["stdout"]
            display_error = " | ".join((last_error or "no output").splitlines()[:3])
            print(
                f"⚠️ AI execution failed for request {request.request_id.hex()}: "
                f"{display_error}"
            )
            context = {
                "previous_code": code,
                "error": last_error or "Unknown error",
            }
            attempts += 1

        display_error = (last_error or "unknown error").strip()
        print(
            f"⚠️ Failed to resolve request {request.request_id.hex()} after retries. "
            f"Last error: {display_error[:240]}"
        )

        # Attempt deterministic template fallback
        fallback = self._fallback_price_script(ancillary_text)
        if fallback:
            execution = self._execute_generated_python(fallback)
            if execution["success"]:
                decision = execution["decision"]
                evidence: Dict[str, Any] = {
                    "requestId": request.request_id.hex(),
                    "identifier": Web3.to_hex(request.identifier),
                    "timestamp": request.timestamp,
                    "ancillary": ancillary_text,
                    "decision": decision,
                    "reason": execution.get("reason"),
                    "price": execution.get("data", {}).get("price"),
                    "data": execution.get("data"),
                    "script": fallback,
                    "stdout": execution["stdout"],
                    "stderr": execution["stderr"],
                    "executedAt": datetime.utcnow().isoformat(),
                    "strategy": "template_price_check",
                }
                return {"price": 1 if decision == "YES" else 0, "evidence": evidence}
            else:
                print(
                    f"⚠️ Fallback template execution failed for request {request.request_id.hex()}: "
                    f"stdout={execution['stdout'][:120]} stderr={execution['stderr'][:120]}"
                )

        return None

    def _build_resolution_task(self, ancillary_text: str) -> str:
        return (
            "You are writing a Python script that resolves an oracle question.\n"
            "Follow these rules carefully:\n"
            "1. Determine whether the answer should be YES or NO.\n"
            "2. Fetch any required data (HTTP requests with the 'requests' library) based on the text below.\n"
            "3. Handle API errors gracefully and document failures via the reason field.\n"
            "4. Define a function `resolve_oracle()` that returns a dict with keys:\n"
            "   - decision: 'YES' or 'NO'\n"
            "   - reason: short human-readable explanation\n"
            "   - data: optional supporting values (e.g. fetched price)\n"
            "5. KEEP EVERY STRING LITERAL (ESPECIALLY URLs) ON A SINGLE LINE AND WRAP IT IN DOUBLE QUOTES.\n"
            "6. NEVER break URLs across lines.\n"
            "7. At the bottom of the script include:\n"
            "   if __name__ == \"__main__\":\n"
            "       import json\n"
            "       result = resolve_oracle()\n"
            "       print(json.dumps(result))\n"
            "8. Use only standard libraries plus 'requests', 'json', and 'datetime'.\n"
            "9. Output raw Python code only (no markdown fences).\n\n"
            "Oracle question:\n"
            f"{ancillary_text}\n"
        )

    def _execute_generated_python(self, code: str) -> Dict[str, Any]:
        result: Dict[str, Any] = {
            "success": False,
            "stdout": "",
            "stderr": "",
            "decision": "UNKNOWN",
            "reason": None,
            "data": None,
        }

        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as tmp_file:
            tmp_file.write(code)
            script_path = tmp_file.name

        try:
            proc = subprocess.run(
                [sys.executable, script_path],
                capture_output=True,
                text=True,
                timeout=120,
            )
            result["stdout"] = proc.stdout.strip()
            result["stderr"] = proc.stderr.strip()

            if proc.returncode != 0:
                return result

            payload = self._extract_json_payload(proc.stdout)
            if not payload:
                return result

            decision = str(payload.get("decision", "")).strip().upper()
            if decision not in {"YES", "NO"}:
                return result

            result["decision"] = decision
            result["reason"] = payload.get("reason")
            result["data"] = payload.get("data")
            result["success"] = True
            return result
        except subprocess.TimeoutExpired:
            result["stderr"] = "Execution timed out"
            return result
        except Exception as exc:
            result["stderr"] = str(exc)
            return result
        finally:
            try:
                os.unlink(script_path)
            except OSError:
                pass

    @staticmethod
    def _extract_json_payload(stdout: str) -> Optional[Dict[str, Any]]:
        lines = [line.strip() for line in stdout.splitlines() if line.strip()]
        for line in reversed(lines):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
        return None

    def _persist_evidence(self, request_id: str, evidence: Dict[str, Any]) -> None:
        try:
            self._evidence_dir.mkdir(parents=True, exist_ok=True)
            path = self._evidence_dir / f"{request_id}.json"
            with path.open("w", encoding="utf-8") as handle:
                json.dump(evidence, handle, indent=2)
        except Exception as exc:
            print(f"⚠️ Failed to persist evidence for {request_id}: {exc}")

    def _fallback_price_script(self, ancillary_text: str) -> Optional[str]:
        url_match = re.search(r"https?://[\w\-./:%?#=&]+", ancillary_text)
        if not url_match:
            print("⚠️ Fallback price script: no URL detected")
            return None

        numbers = re.findall(r"[-+]?[0-9]*\.?[0-9]+", ancillary_text)
        threshold = None
        for value in numbers:
            try:
                threshold = float(value)
                break
            except ValueError:
                continue
        if threshold is None:
            print("⚠️ Fallback price script: no numeric threshold detected")
            return None

        lowered = ancillary_text.lower()
        if "below" in lowered or "less" in lowered:
            operator = "below"
        else:
            operator = "above"

        script = f"""import json
import requests
from datetime import datetime

API_URL = "{url_match.group(0)}"
THRESHOLD = {threshold}
OPERATOR = "{operator}"


def fetch_price():
    response = requests.get(API_URL, timeout=10)
    response.raise_for_status()
    data = response.json()
    price = float(data.get("Price"))
    return price, data


def resolve_oracle():
    try:
        price, raw = fetch_price()
        meets = price >= THRESHOLD if OPERATOR == "above" else price <= THRESHOLD
        decision = "YES" if meets else "NO"
        comparison = ">=" if OPERATOR == "above" else "<="
        reason = f"Price {{price:.2f}} {{comparison}} {{THRESHOLD}}"
        return {{
            "decision": decision,
            "reason": reason,
            "data": {{
                "price": price,
                "threshold": THRESHOLD,
                "operator": OPERATOR,
                "timestamp": raw.get("Time"),
                "source": raw.get("Source"),
            }},
        }}
    except Exception as exc:
        return {{
            "decision": "NO",
            "reason": f"Failed to fetch data: {{exc}}",
            "data": None,
        }}


if __name__ == "__main__":
    result = resolve_oracle()
    print(json.dumps(result))
"""
        print(
            "ℹ️ Using fallback price script:",
            {
                "url": url_match.group(0),
                "threshold": threshold,
                "operator": operator,
            },
        )
        return script

    async def _execute_shell(self, command: str) -> Dict[str, Any]:
        """Execute shell command via sandbox."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    f"{self.sandbox_url}/v1/shell/exec",
                    json={"command": command},
                    timeout=30.0
                )
                return resp.json()
            except Exception as e:
                return {"error": str(e)}

    async def _read_file(self, path: str) -> Dict[str, Any]:
        """Read file via sandbox."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    f"{self.sandbox_url}/v1/file/read",
                    json={"file": path},
                    timeout=10.0
                )
                return resp.json()
            except Exception as e:
                return {"error": str(e)}

    async def _write_file(self, path: str, content: str) -> Dict[str, Any]:
        """Write file via sandbox."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    f"{self.sandbox_url}/v1/file/write",
                    json={"file": path, "content": content},
                    timeout=10.0
                )
                return resp.json()
            except Exception as e:
                return {"error": str(e)}

    def _parse_jupyter_response(self, jupyter_result: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Jupyter response into standardized format."""
        status = jupyter_result.get('status', 'error')
        outputs = jupyter_result.get('outputs', [])

        stdout_parts = []
        stderr_parts = []
        result = None
        error_msg = None

        for output in outputs:
            output_type = output.get('output_type')

            if output_type == 'stream':
                text = output.get('text', '')
                if output.get('name') == 'stdout':
                    stdout_parts.append(text)
                elif output.get('name') == 'stderr':
                    stderr_parts.append(text)

            elif output_type == 'execute_result':
                # This is the return value
                data = output.get('data', {})
                result = data.get('text/plain', str(data))

            elif output_type == 'error':
                error_msg = output.get('evalue', 'Unknown error')
                traceback = output.get('traceback', [])
                stderr_parts.extend(traceback)

        return {
            'success': status == 'ok',
            'stdout': ''.join(stdout_parts),
            'stderr': ''.join(stderr_parts),
            'result': result,
            'error': error_msg
        }

    async def _execute_jupyter(self, code: str, session_id: str = None, timeout: int = 30) -> Dict[str, Any]:
        """Execute Python code via Jupyter kernel."""
        async with httpx.AsyncClient() as client:
            try:
                payload = {"code": code, "timeout": timeout}
                if session_id:
                    payload["session_id"] = session_id

                resp = await client.post(
                    f"{self.sandbox_url}/v1/jupyter/execute",
                    json=payload,
                    timeout=float(timeout + 5)  # Add buffer to HTTP timeout
                )
                sandbox_response = resp.json()

                # Sandbox wraps response in {"success": true, "data": {...}}
                if sandbox_response.get('success') and 'data' in sandbox_response:
                    jupyter_result = sandbox_response['data']
                    return self._parse_jupyter_response(jupyter_result)
                else:
                    error = sandbox_response.get('message', 'Unknown sandbox error')
                    return {"success": False, "error": error, "stdout": "", "stderr": ""}
            except Exception as e:
                return {"success": False, "error": str(e), "stdout": "", "stderr": ""}

    def _parse_nodejs_response(self, nodejs_result: Dict[str, Any]) -> Dict[str, Any]:
        """Parse Node.js response into standardized format."""
        status = nodejs_result.get('status', 'error')
        exit_code = nodejs_result.get('exit_code', 1)

        # Extract result from outputs if present
        result = None
        outputs = nodejs_result.get('outputs', [])
        if outputs:
            # Look for return value in last output
            last_output = outputs[-1]
            if last_output.get('output_type') == 'execute_result':
                data = last_output.get('data', {})
                result = data.get('text/plain', str(data))

        return {
            'success': status == 'ok' and exit_code == 0,
            'stdout': nodejs_result.get('stdout', ''),
            'stderr': nodejs_result.get('stderr', ''),
            'result': result,
            'error': nodejs_result.get('stderr') if status != 'ok' else None
        }

    async def _execute_nodejs(self, code: str, files: Dict[str, str] = None, timeout: int = 30) -> Dict[str, Any]:
        """Execute JavaScript code via Node.js."""
        async with httpx.AsyncClient() as client:
            try:
                payload = {"code": code, "timeout": timeout}
                if files:
                    payload["files"] = files

                resp = await client.post(
                    f"{self.sandbox_url}/v1/nodejs/execute",
                    json=payload,
                    timeout=float(timeout + 5)  # Add buffer to HTTP timeout
                )
                sandbox_response = resp.json()

                # Sandbox wraps response in {"success": true, "data": {...}}
                if sandbox_response.get('success') and 'data' in sandbox_response:
                    nodejs_result = sandbox_response['data']
                    return self._parse_nodejs_response(nodejs_result)
                else:
                    error = sandbox_response.get('message', 'Unknown sandbox error')
                    return {"success": False, "error": error, "stdout": "", "stderr": ""}
            except Exception as e:
                return {"success": False, "error": str(e), "stdout": "", "stderr": ""}

    async def _ai_generate_and_execute(
        self,
        description: str,
        language: str,
        context: Optional[Dict[str, Any]] = None,
        max_retries: int = 2,
        include_attestation: bool = True
    ) -> Dict[str, Any]:
        """
        Generate code with AI and execute it with TEE attestation.

        Returns verifiable result with attestation data for end-user verification.
        Matches existing API response format for UI compatibility.
        """
        if not self.ai_generator:
            return {
                "success": False,
                "error": "AI generator not available. Set REDPILL_API_KEY environment variable.",
                "message": "Please configure RedPill API key in environment"
            }

        if language not in ['python', 'javascript']:
            return {
                "success": False,
                "error": f"Unsupported language: {language}",
                "message": "Supported languages: python, javascript"
            }

        # 1. Generate code with AI (includes TEE attestation)
        try:
            if language == 'python':
                code, attestation = await self.ai_generator.generate_python_script(
                    description, context, include_attestation
                )
            else:  # javascript
                code, attestation = await self.ai_generator.generate_javascript_script(
                    description, context, include_attestation
                )
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "message": "AI code generation failed",
                "language": language
            }

        # 2. Execute the generated code
        if language == 'python':
            exec_result = await self._execute_jupyter(code)
        else:  # javascript
            exec_result = await self._execute_nodejs(code)

        # 3. Check if execution succeeded
        execution_success = exec_result.get('success', False) and not exec_result.get('error')

        if execution_success:
            return {
                "success": True,
                "message": "Code generated and executed successfully",
                "language": language,
                "generated_code": code,
                "output": exec_result.get('stdout', ''),
                "result": exec_result.get('result'),
                "execution_details": {
                    "success": True,
                    "stdout": exec_result.get('stdout', ''),
                    "stderr": exec_result.get('stderr', ''),
                    "result": exec_result.get('result')
                },
                "attestation": attestation if include_attestation else None,
                "retries_used": 0,
                "verification_url": "/verify-attestation" if attestation else None
            }

        # 4. Retry with error feedback if failed
        if max_retries > 0:
            retry_context = {
                **(context or {}),
                "previous_code": code,
                "error": exec_result.get('error', exec_result.get('stderr', 'Unknown error'))
            }

            retry_result = await self._ai_generate_and_execute(
                description,
                language,
                retry_context,
                max_retries - 1,
                include_attestation
            )

            # Update retries_used counter
            if retry_result.get('success'):
                retry_result['retries_used'] = retry_result.get('retries_used', 0) + 1
                retry_result['message'] = f"Code generated and executed successfully (after {retry_result['retries_used']} retries)"

            return retry_result

        # Failed after all retries
        return {
            "success": False,
            "error": exec_result.get('error', exec_result.get('stderr', 'Execution failed')),
            "message": f"Code execution failed after {max_retries + 1} attempts",
            "language": language,
            "generated_code": code,
            "output": exec_result.get('stderr', ''),
            "execution_details": exec_result,
            "attestation": attestation if include_attestation else None,
            "retries_used": max_retries
        }

    def _get_verification_instructions(self) -> Dict[str, str]:
        """Get instructions for end-user verification"""
        return {
            "message": "This result includes TEE attestation. Verify using the verification tools.",
            "verification_script": "python verify_ai_attestation.py",
            "docs_url": "https://docs.redpill.ai/confidential-ai/attestation"
        }

    async def _create_agent_card(self) -> Dict[str, Any]:
        """Create ERC-8004 agent card."""
        from ..agent.agent_card import create_tee_agent_card

        agent_address = await self._get_agent_address()

        capabilities = [
            ("shell-execution", "Execute shell commands via AIO Sandbox"),
            ("file-operations", "Read/write files in sandbox"),
            ("jupyter-execution", "Run Python/Node.js code"),
            ("ai-code-generation", "Generate and execute code from natural language with TEE attestation")
        ]

        # Only add AI capability if generator is available
        if not self.ai_generator:
            capabilities = [c for c in capabilities if c[0] != "ai-code-generation"]

        return create_tee_agent_card(
            name=f"TEE Server Agent - {self.config.domain}",
            description="TEE-secured agent with AIO Sandbox integration for secure code execution",
            domain=self.config.domain,
            agent_address=agent_address,
            agent_id=self.agent_id if self.is_registered else None,
            signature=None,
            capabilities=capabilities,
            chain_id=self.config.chain_id
        )
