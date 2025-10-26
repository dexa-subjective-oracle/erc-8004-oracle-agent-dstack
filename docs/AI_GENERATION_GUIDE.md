# AI-Assisted Code Generation with TEE Attestation

## Overview

The agent supports **verifiable AI-assisted code generation** with a beautiful web UI. Users can describe tasks in natural language, and the agent will:

1. Generate code using RedPill's TEE-secured AI models (NVIDIA H100)
2. Execute the code in the attested sandbox
3. Provide cryptographic proof (attestation) for independent verification
4. Automatically retry with error feedback if execution fails

## Key Features

- **Natural Language → Code**: Describe what you want, AI generates the implementation
- **TEE Attestation**: Cryptographic proof that AI ran in genuine NVIDIA H100 TEE *(requires RedPill provider; local Ollama mode disables attestation)*
- **Auto-Execution**: Generated code is immediately executed in sandbox
- **Error Recovery**: Automatic retry with error context if code fails
- **Verifiable Results**: End users can independently verify attestations
- **Multi-Language**: Supports both Python and JavaScript

## Quick Start

### Option 1: Use the Web UI (Recommended)

1. Navigate to http://localhost:8000/developer
2. Scroll to the purple "Generate & Execute Code" panel
3. Select language (Python/JavaScript)
4. Describe what you want: "Calculate the factorial of 10"
5. Click "🤖 Generate & Execute"
6. View formatted result with generated code, output, and TEE attestation
7. Click "Copy" to copy code or "Download Attestation" for verification

### Option 2: Use the API Programmatically

### 1. Setup

Add your RedPill API key to `.env`:

```bash
# Local Ollama settings
AI_PROVIDER=ollama
AI_API_BASE=http://127.0.0.1:11434/v1
AI_API_KEY=ollama
OLLAMA_MODEL=gemma3:4b
AI_MODEL=gemma3:4b
AI_TEMPERATURE=0.3
AI_MAX_TOKENS=2000
```

### 2. Basic Usage

```python
import httpx

task = {
    "data": {
        "type": "ai_generate_and_execute",
        "description": "Calculate the factorial of 10 and print the result",
        "language": "python",
        "include_attestation": False
    }
}

async with httpx.AsyncClient() as client:
    resp = await client.post(
        "http://localhost:8000/api/process",
        json=task
    )
    result = resp.json()

    print("Generated Code:")
    print(result["generated_code"])

    print("\nExecution Output:")
    print(result["execution_result"]["stdout"])

    # Save attestation for verification
    with open("attestation.json", "w") as f:
        json.dump(result, f, indent=2)
```

### 3. Verify Attestation

```bash
# Verify the AI inference happened in TEE
python verify_ai_attestation.py attestation.json
```

## API Reference

### Request Format

```json
{
  "data": {
    "type": "ai_generate_and_execute",
    "description": "<natural language task description>",
    "language": "python" | "javascript",
    "context": { /* optional context */ },
    "max_retries": 2,
    "include_attestation": false
  }
}
```

### Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `description` | string | required | Natural language description of what code should do |
| `language` | string | `"python"` | Programming language: `"python"` or `"javascript"` |
| `context` | object | `null` | Additional context (variables, requirements, etc.) |
| `max_retries` | integer | `2` | Number of retries if code fails |
| `include_attestation` | boolean | `false` | Include TEE attestation in response *(RedPill only; ignored in Ollama mode)* |

### Response Format

```json
{
  "success": true,
  "language": "python",
  "generated_code": "# AI-generated code here",
  "execution_result": {
    "success": true,
    "stdout": "output...",
    "stderr": "",
    "result": null
  },
  "attestation": {
    "type": "nvidia_h100_tee",
    "measurements": { /* ... */ },
    "signature": { /* ... */ },
    "timestamp": "2025-01-15T10:30:00Z",
    "nonce": "...",
    "inference": {
      "model": "phala/gemma3-4b-instruct",
      "prompt_hash": "...",
      "response_hash": "...",
      "usage": { /* token usage */ }
    },
    "verification": {
      "nonce": "...",
      "fetched_at": "...",
      "inference_timestamp": 1736938200
    }
  },
  "retries_used": 0,
  "verification_instructions": {
    "message": "This result includes TEE attestation...",
    "verification_script": "python verify_ai_attestation.py",
    "docs_url": "https://docs.redpill.ai/confidential-ai/attestation"
  }
}
```

## Examples

### Example 1: Data Analysis

**Request:**
```json
{
  "data": {
    "type": "ai_generate_and_execute",
    "description": "Load data from /tmp/sales.csv, calculate total revenue, and create a bar chart of top 5 products by sales",
    "language": "python"
  }
}
```

**Generated Code:**
```python
import pandas as pd
import matplotlib.pyplot as plt

# Load data
df = pd.read_csv('/tmp/sales.csv')

# Calculate total revenue
total_revenue = df['revenue'].sum()
print(f'Total Revenue: ${total_revenue:,.2f}')

# Top 5 products
top_products = df.groupby('product')['revenue'].sum().nlargest(5)

# Create bar chart
plt.figure(figsize=(10, 6))
top_products.plot(kind='bar')
plt.title('Top 5 Products by Revenue')
plt.ylabel('Revenue ($)')
plt.savefig('/tmp/top_products.png')
print('Chart saved to /tmp/top_products.png')
```

### Example 2: Web3 Interaction

**Request:**
```json
{
  "data": {
    "type": "ai_generate_and_execute",
    "description": "Check the ETH balance of address 0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb on Base network",
    "language": "javascript",
    "context": {
      "network": "Base",
      "rpc": "https://base.llamarpc.com"
    }
  }
}
```

**Generated Code:**
```javascript
const { ethers } = require('ethers');

const provider = new ethers.JsonRpcProvider('https://base.llamarpc.com');
const address = '0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb';

const balance = await provider.getBalance(address);
const formatted = ethers.formatEther(balance);

console.log(`Address: ${address}`);
console.log(`Balance: ${formatted} ETH`);
formatted;
```

### Example 3: Error Recovery

The agent automatically retries when code fails:

**First Attempt** (fails):
```python
# Tries to read non-existent file
data = open('/tmp/missing.txt').read()
```

**Second Attempt** (succeeds after AI sees error):
```python
# Adds error handling
try:
    data = open('/tmp/missing.txt').read()
except FileNotFoundError:
    print("File not found, using default data")
    data = "default content"
print(f"Data: {data}")
```

## Verification

### Why Verify?

Attestation proves:
1. Code was generated by AI running in genuine NVIDIA H100 TEE
2. The specific model used is attested (not a backdoored version)
3. The inference happened recently (nonce prevents replay attacks)
4. Complete audit trail: prompt hash → AI generation → execution

### Verification Steps

**1. Basic Verification (Lightweight)**

```bash
python verify_ai_attestation.py attestation.json
```

This checks:
- ✓ Attestation structure is valid
- ✓ Nonce is present (replay protection)
- ✓ Timestamp is recent (<10 minutes)
- ✓ TEE type is valid (NVIDIA H100)
- ✓ Inference metadata is complete

**2. Full Verification (Advanced)**

For maximum security, implement full cryptographic verification:

```python
from verify_ai_attestation import AIAttestationVerifier

verifier = AIAttestationVerifier()

# Load attestation
with open('attestation.json') as f:
    att = json.load(f)

# Full verification
success = verifier.verify_attestation(att)

if success:
    # Also verify code hash
    code = att["generated_code"]
    expected_hash = att["attestation"]["inference"]["response_hash"]
    verifier.verify_code_hash(code, expected_hash)
```

**3. Independent Verification (Trustless)**

For zero-trust scenarios, verify against RedPill's API directly:

```python
import requests
import hashlib

# 1. Get fresh attestation from RedPill
nonce = secrets.token_hex(32)
attestation = requests.get(
    "https://api.redpill.ai/v1/attestation/report",
    params={"model": "phala/gemma3-4b-instruct", "nonce": nonce},
    headers={"Authorization": f"Bearer {api_key}"}
).json()

# 2. Verify code hash matches attestation
code_hash = hashlib.sha256(generated_code.encode()).hexdigest()
assert code_hash == attestation["inference"]["response_hash"]

# 3. Verify nonce in attestation
assert attestation["verification"]["nonce"] == nonce
```

## Security Model

### Trust Assumptions

**What you DON'T need to trust:**
- ✗ The agent operator
- ✗ The server infrastructure
- ✗ RedPill's API gateway (for model execution)

**What you DO need to trust:**
- ✓ Intel (for TDX attestation)
- ✓ NVIDIA (for H100 TEE attestation)
- ✓ RedPill's published model hashes
- ✓ The TEE hardware itself

### Attack Resistance

| Attack | Mitigation |
|--------|------------|
| **Replay Attack** | Nonce in attestation (fresh for each request) |
| **Model Substitution** | Model hash in attestation (cryptographically bound to TEE) |
| **Result Tampering** | Response hash in attestation (generated inside TEE) |
| **Prompt Injection** | Input sanitization + prompt engineering best practices |
| **MitM Attack** | HTTPS + attestation signature verification |

### Threat Model

**In Scope:**
- Malicious agent operator
- Compromised server
- Network eavesdropping
- Replay attacks

**Out of Scope:**
- TEE hardware vulnerabilities (trust Intel/NVIDIA)
- Side-channel attacks on TEE
- Compromised root certificates

## Best Practices

### 1. Prompt Engineering

**Good Prompts:**
```json
{
  "description": "Load CSV from /tmp/data.csv, calculate average of 'price' column, create bar chart, save to /tmp/chart.png",
  "language": "python"
}
```

**Bad Prompts:**
```json
{
  "description": "do something with data",  // Too vague
  "language": "python"
}
```

### 2. Context Usage

Provide context for better code generation:

```json
{
  "description": "Calculate compound interest",
  "language": "python",
  "context": {
    "principal": 1000,
    "rate": 0.05,
    "years": 10,
    "formula": "A = P(1 + r)^t"
  }
}
```

### 3. Error Handling

Let the agent retry automatically:

```json
{
  "description": "Read file and process data",
  "max_retries": 2  // Allow 2 retries for resilience
}
```

### 4. Verification

Always verify attestations for production use:

```python
# After generating code
if result.get("attestation"):
    with open("attestation.json", "w") as f:
        json.dump(result, f)

    # Verify before using result
    verified = verify_attestation("attestation.json")
    if not verified:
        raise SecurityError("Attestation verification failed")
```

### 5. Model Selection

Choose model based on task:

| Task | Recommended Model | Reason |
|------|-------------------|--------|
| Simple code | `gemma3:4b` (Ollama) | Fast, good for straightforward tasks |
| Complex logic | `phala/deepseek-chat-v3-0324` | Strong reasoning capabilities |
| Large codebase | `phala/gpt-oss-120b` | Most capable, handles complexity |
| Balanced | `phala/llama-3.3-70b` | Good trade-off |

## Testing

```bash
# 1. Set API key
export REDPILL_API_KEY=your_api_key

# 2. Ensure agent and sandbox are running
python deployment/local_agent_server.py  # Port 8000
# Sandbox should be on port 8080

# 3. Run tests
python test_ai_generation.py

# 4. Verify attestations
python verify_ai_attestation.py attestation_test1.json
python verify_ai_attestation.py attestation_test2.json
python verify_ai_attestation.py attestation_test3.json
```

## Troubleshooting

### Issue: "AI generator not available"

**Cause:** `REDPILL_API_KEY` not set

**Solution:**
```bash
export REDPILL_API_KEY=your_api_key
# Restart agent server
```

### Issue: "Attestation verification failed"

**Cause:** Attestation too old or invalid

**Solution:**
- Check timestamp (must be <10 minutes old)
- Ensure nonce is present
- Verify network connectivity to RedPill API

### Issue: Code generation fails repeatedly

**Cause:** Unclear prompt or impossible task

**Solution:**
- Make prompt more specific
- Add context with examples
- Check if task is actually doable in sandbox

### Issue: Execution times out

**Cause:** Generated code is too complex or has infinite loop

**Solution:**
- Simplify the task description
- Add timeout constraints in prompt
- Review generated code before execution

## Monitoring

Track these metrics:

```python
result = await process_ai_task(task)

# Log metrics
log_metric("ai_generation.success", result["success"])
log_metric("ai_generation.retries", result["retries_used"])
log_metric("ai_generation.language", result["language"])

if result.get("attestation"):
    log_metric("ai_generation.model", result["attestation"]["inference"]["model"])
    log_metric("ai_generation.tokens", result["attestation"]["inference"]["usage"])
```

## Costs

Local Ollama inference runs on your own hardware, so there are no per-token API fees. Resource consumption largely depends on your host machine (GPU/CPU RAM, VRAM, etc.).

## FAQ

**Q: Can I use non-Phala models?**
A: Yes, but only Phala models provide TEE attestation. Other models run without cryptographic proof.

**Q: How do I verify attestations programmatically?**
A: Use the `AIAttestationVerifier` class in `verify_ai_attestation.py`.

**Q: What if the AI generates malicious code?**
A: Sandbox isolation prevents host access. All code runs in isolated container.

**Q: Can I use this for production?**
A: Yes, with proper attestation verification and monitoring.

**Q: How fresh must attestations be?**
A: Default: 10 minutes. Configurable in verification script.

## Next Steps

1. ✓ Set `REDPILL_API_KEY` in `.env`
2. ✓ Run test script: `python test_ai_generation.py`
3. ✓ Verify attestations: `python verify_ai_attestation.py attestation_test1.json`
4. ✓ Integrate into your application
5. ✓ Monitor metrics and costs

## Support

- RedPill Docs: https://docs.redpill.ai
- Attestation Guide: https://docs.redpill.ai/confidential-ai/attestation
- GitHub Issues: https://github.com/your-repo/issues
