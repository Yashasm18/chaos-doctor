# Agent contract

Chaos Doctor can test any Python agent file that exposes five names at module level.

```python
client = OpenAI(base_url="http://localhost:11434/v1", api_key="ollama")  # OpenAI-style client
TOOLS = ["lookup_order"]                                   # module-level tool functions
TASKS = [{"order_id": "A001", "question": "Where is my order?"}]

def lookup_order(order_id): ...   # a tool

def run(task) -> str: ...         # do the task, return the answer

def check(task, answer) -> bool:  # is the answer right?
    ...
```

Tips that make agents easy to heal:

- Call each tool from a small wrapper function (`get_order` calls `lookup_order`). The Doctor
  guards the wrapper.
- Put the model call in one function (`ask_llm`). The Doctor guards it.
- Look up tools by their module-level name at call time (do not alias them), so the scanner
  can wrap them.

The demo agent `examples/shop_agent/agent.py` follows this contract.
