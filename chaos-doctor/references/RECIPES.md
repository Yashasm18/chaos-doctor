# Fix recipes

The Doctor never writes free-form code. It picks one recipe, one function and parameters;
the patcher adds one decorator from `chaos_doctor.guards` and checks the file still parses.

| Recipe | Decorator | Fixes | Params (bounds) |
| --- | --- | --- | --- |
| `retry` | `@guards.retry(attempts, backoff_s)` | rate limits, timeouts, tool errors, context errors | attempts 2-6, backoff_s 0-2 |
| `timeout` | `@guards.timeout(seconds)` | hung calls | seconds 0.5-30 |
| `fallback` | `@guards.fallback(value)` | a tool that is down for good | value |
| `validate_output` | `@guards.validate_output(retries)` | garbled replies | retries 1-5 |
| `trim_prompt` | `@guards.trim_prompt(max_chars)` | context-length errors | max_chars 200-20000 |
| `sanitize` | `@guards.sanitize` | prompt injection in tool data | none |

## Where a recipe goes

Put it on the function that **makes** the failing call:

- LLM attacks: the function that calls `client.chat.completions.create`.
- Tool attacks: the function that calls the tool, never the tool itself (the scanner injects
  faults inside the tool, so a guard on the tool would be bypassed).

## Stacking order

When a function has several guards they are kept in this order, outermost first:
`validate_output`, `sanitize`, `fallback`, `retry`, `trim_prompt`, `timeout`.
So `retry` gives every attempt its own `timeout`, and a garbled but successful reply is
re-asked by `validate_output`.

Applying a recipe that is already present updates its parameters instead of adding a second
copy.
