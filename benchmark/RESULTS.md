# Doctor benchmark results

20 planted weaknesses across 3 agents (shop, helpdesk, travel). Each case: the attack breaks the agent, the Doctor diagnoses it once, the patch is applied, the attack is re-run. Reproduce with `python benchmark/run.py --model <ollama model>`.

| Doctor | Fixed | Right function (model's own pick) | Right recipe | Placement corrected | Fell back to rules | Avg time per diagnosis |
| --- | --- | --- | --- | --- | --- | --- |
| qwen3:4b | **18/20** | 15/20 | 20/20 | 5 | 0 | 47.0 s |
| rules | **20/20** | n/a | n/a | n/a | n/a | 0.0 s |

Recorded on: qwen3:4b (Apple M1, 8 GB, Ollama), rules (rules, no model).

The rule-based Doctor was written for this recipe menu, so 20/20 is its ceiling, not a fair rival; the model rows are the real test. Both qwen3:4b misses are `rate_limit_storm` on the shop agent: the model chose the right recipe (`retry`) on the right function, but the patch did not survive the 429 burst. This run predates parameter logging, so the cause (most likely too few attempts) is not recorded. A partial second run (stopped at case 14 when Ollama exited) reproduced the first miss and matched every other result.

## Per case

### qwen3:4b

| Case | Fix | Params | On | Fixed |
| --- | --- | --- | --- | --- |
| `shop/token_timeout` | `retry` | not recorded | `ask_llm()` | yes |
| `shop/rate_limit_storm` | `retry` | not recorded | `ask_llm()` | no |
| `shop/silent_degradation` | `validate_output` | not recorded | `ask_llm()` | yes |
| `shop/context_length` | `trim_prompt` | not recorded | `ask_llm()` | yes |
| `shop/tool_failure` | `retry` | not recorded | `get_order()` | yes |
| `shop/prompt_injection` | `sanitize` | not recorded | `get_order()*` | yes |
| `helpdesk/token_timeout` | `retry` | not recorded | `complete()` | yes |
| `helpdesk/rate_limit_storm` | `retry` | not recorded | `complete()` | yes |
| `helpdesk/silent_degradation` | `validate_output` | not recorded | `complete()` | yes |
| `helpdesk/context_length` | `trim_prompt` | not recorded | `complete()` | yes |
| `helpdesk/tool_failure` | `retry` | not recorded | `load_ticket()*` | yes |
| `helpdesk/prompt_injection` | `sanitize` | not recorded | `load_ticket()*` | yes |
| `travel/token_timeout` | `retry` | not recorded | `generate_reply()` | yes |
| `travel/rate_limit_storm` | `retry` | not recorded | `generate_reply()` | yes |
| `travel/silent_degradation` | `validate_output` | not recorded | `generate_reply()` | yes |
| `travel/context_length` | `trim_prompt` | not recorded | `generate_reply()` | yes |
| `travel/tool_failure` | `retry` | not recorded | `lookup_flight()*` | yes |
| `travel/prompt_injection` | `sanitize` | not recorded | `lookup_flight()*` | yes |
| `shop/rate_limit_storm+weak_retry` | `retry` | not recorded | `ask_llm()` | no |
| `travel/silent_degradation+weak_validate` | `validate_output` | not recorded | `generate_reply()` | yes |

### rules

| Case | Fix | Params | On | Fixed |
| --- | --- | --- | --- | --- |
| `shop/token_timeout` | `retry` | attempts=4, backoff_s=0.05 | `ask_llm()` | yes |
| `shop/rate_limit_storm` | `retry` | attempts=4, backoff_s=0.05 | `ask_llm()` | yes |
| `shop/silent_degradation` | `validate_output` | retries=3 | `ask_llm()` | yes |
| `shop/context_length` | `retry` | attempts=4, backoff_s=0.05 | `ask_llm()` | yes |
| `shop/tool_failure` | `retry` | attempts=4, backoff_s=0.05 | `get_order()` | yes |
| `shop/prompt_injection` | `sanitize` | defaults | `get_order()` | yes |
| `helpdesk/token_timeout` | `retry` | attempts=4, backoff_s=0.05 | `complete()` | yes |
| `helpdesk/rate_limit_storm` | `retry` | attempts=4, backoff_s=0.05 | `complete()` | yes |
| `helpdesk/silent_degradation` | `validate_output` | retries=3 | `complete()` | yes |
| `helpdesk/context_length` | `retry` | attempts=4, backoff_s=0.05 | `complete()` | yes |
| `helpdesk/tool_failure` | `retry` | attempts=4, backoff_s=0.05 | `load_ticket()` | yes |
| `helpdesk/prompt_injection` | `sanitize` | defaults | `load_ticket()` | yes |
| `travel/token_timeout` | `retry` | attempts=4, backoff_s=0.05 | `generate_reply()` | yes |
| `travel/rate_limit_storm` | `retry` | attempts=4, backoff_s=0.05 | `generate_reply()` | yes |
| `travel/silent_degradation` | `validate_output` | retries=3 | `generate_reply()` | yes |
| `travel/context_length` | `retry` | attempts=4, backoff_s=0.05 | `generate_reply()` | yes |
| `travel/tool_failure` | `retry` | attempts=4, backoff_s=0.05 | `lookup_flight()` | yes |
| `travel/prompt_injection` | `sanitize` | defaults | `lookup_flight()` | yes |
| `shop/rate_limit_storm+weak_retry` | `retry` | attempts=6, backoff_s=0.05 | `ask_llm()` | yes |
| `travel/silent_degradation+weak_validate` | `validate_output` | retries=5 | `generate_reply()` | yes |

\* placement corrected by the call-site check (the model picked another function).
