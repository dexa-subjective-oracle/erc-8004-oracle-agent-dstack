# Agent API Capabilities

This document describes the available capabilities of the ERC-8004 TEE Agent.

## Overview

The agent supports 5 task types, each corresponding to a specific capability:

1. **Shell Execution** - Execute shell commands
2. **File Operations** - Read/write files
3. **Jupyter Execution** - Execute Python code with Jupyter
4. **Node.js Execution** - Execute JavaScript code
5. *(Browser Control - Coming in Phase 2)*

---

## 1. Shell Execution

Execute shell commands in the sandbox environment.

### Task Format

```json
{
  "data": {
    "type": "shell",
    "command": "ls -la /workspace"
  }
}
```

### Parameters

- `command` (string, required): Shell command to execute

### Example

```python
task = {
    "data": {
        "type": "shell",
        "command": "python --version && pip list"
    }
}
```

---

## 2. File Read

Read file contents from the sandbox filesystem.

### Task Format

```json
{
  "data": {
    "type": "file_read",
    "path": "/workspace/config.json"
  }
}
```

### Parameters

- `path` (string, required): Absolute path to file

### Example

```python
task = {
    "data": {
        "type": "file_read",
        "path": "/home/user/data.txt"
    }
}
```

---

## 3. File Write

Write content to a file in the sandbox filesystem.

### Task Format

```json
{
  "data": {
    "type": "file_write",
    "path": "/workspace/output.txt",
    "content": "Hello, World!"
  }
}
```

### Parameters

- `path` (string, required): Absolute path to file
- `content` (string, required): Content to write

### Example

```python
task = {
    "data": {
        "type": "file_write",
        "path": "/tmp/result.json",
        "content": '{"status": "success"}'
    }
}
```

---

## 4. Jupyter Execution (NEW)

Execute Python code using Jupyter kernel with session persistence.

### Task Format

```json
{
  "data": {
    "type": "jupyter",
    "code": "import numpy as np\nprint(np.array([1,2,3]).mean())",
    "session_id": "optional-session-id",
    "timeout": 30
  }
}
```

### Parameters

- `code` (string, required): Python code to execute
- `session_id` (string, optional): Session ID for persistence across calls
- `timeout` (integer, optional): Execution timeout in seconds (default: 30)

### Features

- **Session Persistence**: Variables persist across executions with same `session_id`
- **Rich Output**: Supports stdout, stderr, return values, and exceptions
- **Package Support**: Access to all installed Python packages

### Examples

**Simple Execution:**
```python
task = {
    "data": {
        "type": "jupyter",
        "code": """
import pandas as pd
df = pd.DataFrame({'a': [1, 2, 3], 'b': [4, 5, 6]})
df.describe()
"""
    }
}
```

**Session Persistence:**
```python
# First call - initialize data
task1 = {
    "data": {
        "type": "jupyter",
        "code": "data = [1, 2, 3, 4, 5]",
        "session_id": "my-analysis"
    }
}

# Second call - process data (same session)
task2 = {
    "data": {
        "type": "jupyter",
        "code": "sum(data) / len(data)",
        "session_id": "my-analysis"
    }
}
```

**Data Analysis:**
```python
task = {
    "data": {
        "type": "jupyter",
        "code": """
import matplotlib.pyplot as plt
import numpy as np

x = np.linspace(0, 10, 100)
y = np.sin(x)

plt.plot(x, y)
plt.title('Sine Wave')
plt.savefig('/tmp/sine_wave.png')
print('Plot saved!')
"""
    }
}
```

---

## 5. Node.js Execution (NEW)

Execute JavaScript code using Node.js runtime.

### Task Format

```json
{
  "data": {
    "type": "nodejs",
    "code": "console.log('Hello from Node.js')",
    "files": {
      "helper.js": "module.exports = { add: (a, b) => a + b };"
    },
    "timeout": 30
  }
}
```

### Parameters

- `code` (string, required): JavaScript code to execute
- `files` (object, optional): Additional files to create in execution directory
- `timeout` (integer, optional): Execution timeout in seconds (default: 30)

### Features

- **Modern JavaScript**: Supports ES6+ syntax
- **NPM Packages**: Access to installed Node.js packages
- **File System**: Can create and use additional files
- **Return Values**: Supports returning JSON-serializable values

### Examples

**Simple Execution:**
```python
task = {
    "data": {
        "type": "nodejs",
        "code": """
const crypto = require('crypto');
const hash = crypto.createHash('sha256').update('hello').digest('hex');
console.log('Hash:', hash);
hash;
"""
    }
}
```

**Web3 Interaction:**
```python
task = {
    "data": {
        "type": "nodejs",
        "code": """
const { ethers } = require('ethers');
const wallet = ethers.Wallet.createRandom();
console.log('Address:', wallet.address);
wallet.address;
"""
    }
}
```

**With Additional Files:**
```python
task = {
    "data": {
        "type": "nodejs",
        "code": """
const utils = require('./utils.js');
const result = utils.calculateTotal([10, 20, 30]);
console.log('Total:', result);
result;
""",
        "files": {
            "utils.js": """
module.exports = {
    calculateTotal: (arr) => arr.reduce((a, b) => a + b, 0)
};
"""
        }
    }
}
```

---

## API Endpoint

All task types are submitted to the same endpoint:

```
POST /api/process
Content-Type: application/json
```

### Request Format

```json
{
  "data": {
    "type": "<task_type>",
    ... task-specific parameters ...
  }
}
```

### Response Format

The response varies by task type but generally includes:

```json
{
  "success": true,
  "result": "...",
  "stdout": "...",
  "stderr": "...",
  "error": null
}
```

---

## Error Handling

All methods return errors in a consistent format:

```json
{
  "error": "Error message",
  "type": "task_type"
}
```

Common error scenarios:
- **Timeout**: Execution exceeded timeout limit
- **Syntax Error**: Invalid code syntax
- **Runtime Error**: Exception during execution
- **Connection Error**: Cannot reach sandbox

---

## Security Considerations

1. **Sandbox Isolation**: All code executes in isolated sandbox environment
2. **TEE Protection**: Agent signing keys protected by TEE (Intel TDX)
3. **No Persistence**: Sandbox state is ephemeral (except Jupyter sessions)
4. **Resource Limits**: Execution timeout and memory limits enforced
5. **Audit Trail**: All executions logged for compliance

---

## Coming Soon (Phase 2)

### Browser Control
- Navigate to URLs
- Click elements
- Fill forms
- Take screenshots
- Extract data

### Advanced File Operations
- File search with regex
- Text replacement
- Directory listing
- Batch operations

### Session Management
- Shell session persistence
- Session listing/cleanup
- Interactive shell input

---

## Testing

A test script is provided to verify all capabilities:

```bash
# Make sure agent server is running on port 3000
# Make sure sandbox is running on port 8080

python test_new_capabilities.py
```

This will test:
- Jupyter execution
- Node.js execution
- Jupyter session persistence
- Direct sandbox API access

---

## Support

For issues or questions:
- GitHub Issues: [Repository Issues](https://github.com/your-repo/issues)
- Documentation: [Full Docs](https://docs.your-domain.com)
- API Reference: [OpenAPI Spec](https://sandbox-url/v1/openapi.json)
