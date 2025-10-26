# Ollama Chat Completion Truncation Repro

Run the command below against the local Ollama OpenAI-compatible endpoint to reproduce the truncated response that stops at the Diadata URL. The returned JSON ends with `"finish_reason": null` and omits the remainder of the script.

```bash
curl -s http://127.0.0.1:11434/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "gemma3:4b",
    "messages": [
      {"role": "system", "content": "You are an elite Python developer. Respond with raw Python code only."},
      {"role": "user", "content": "Resolve whether Bitcoin price exceeds 110570 using https://api.diadata.org/v1/assetQuotation/Bitcoin/0x0000000000000000000000000000000000000000000000000000000000000000. Define resolve_oracle() returning decision, reason, data and end with __main__ printing json.dumps(resolve_oracle())."}
    ],
    "temperature": 0.2,
    "max_tokens": 800
  }'
```
