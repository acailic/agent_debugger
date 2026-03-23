# Learning When to Act or Refuse: Guarding Agentic Reasoning Models for Safe Multi-Step Tool Use

Paper: [arXiv:2603.03205v1](https://arxiv.org/abs/2603.03205v1)

## Core Idea

This paper focuses on safety for agentic models that plan, use tools, and act over multiple steps. It introduces a framework where the model explicitly plans, checks safety, then either acts or refuses.

## Why It Matters Here

Refusal is not an error condition. In an agentic system, refusal is often the correct action and should be modeled explicitly.

This is highly relevant to `agent_debugger`.

## Key Takeaways For The Repo

### 1. Safety decisions should be visible in traces

The debugger should not only show successful actions. It should also show:

- why the agent refused
- what safety check triggered the refusal
- what risk category was detected
- what action would have happened otherwise

### 2. Plan-check-act is a useful trace structure

Even without reproducing the paper's full training setup, the repo can benefit from a more explicit structure:

1. plan
2. safety check
3. act or refuse

That structure would make multi-step traces much easier to interpret.

### 3. Guardrails should be first-class events

The event model could grow to include:

- safety_check
- refusal
- policy_violation
- prompt_injection_detected
- sensitive_tool_blocked

Those are more informative than lumping everything into generic errors.

## Concrete Opportunities

- add refusal and safety-check event types
- add a UI filter for guarded vs unguarded actions
- highlight sessions with prompt-injection or privacy-risk signatures
- include blocked actions in replay, not just executed ones

## Caution

The paper is about post-training agent safety, while this repo is a debugger. The correct transfer is observability of safety reasoning and refusal, not assuming the debugger itself is the safety mechanism.

## Best Next Experiment

Add two new event types first:

- `safety_check`
- `refusal`

Then thread them through one end-to-end flow so the UI can distinguish "failed", "blocked", and "refused on purpose."
