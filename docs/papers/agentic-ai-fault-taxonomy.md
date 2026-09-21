# Characterizing Faults in Agentic AI: Types, Symptoms, and Root Causes

Paper: [arXiv:2603.06847](https://arxiv.org/abs/2603.06847) (2026)

## Core Idea

An empirical study of faults in real agentic-AI deployments: mining 13,602 issues and pull requests across 40 agentic-system repositories, then analyzing 385 faults via stratified sampling. The result is a taxonomy of 34 fault types organized into four architectural dimensions, with fault types linked to symptoms and root causes by association-rule mining and validated in a developer study of 145 practitioners. Symptom areas include structured-output interpretation, tool calls, runtime execution, and exception handling; root causes include data schema mismatches, dependency drift, state-management complexity, and model interface instability.

## Why It Matters Here

This is the empirical base for recorder robustness. The faults production agent stacks actually exhibit — malformed tool output, exceptions mid-chain, state loss — are precisely the conditions under which instrumentation silently dies. A recorder that drops events when a tool returns a schema the adapter did not expect does not just miss data; it manufactures an incomplete session that looks complete. 385 faults across 40 repos say these are not exotic cases.

The same taxonomy powers completeness self-tests. Each symptom class is a fault to inject into a demo agent: the session completeness diagnostics must flag the session incomplete and name the gap. A diagnostic that only fires on clean traces is decoration; injection makes it provably non-silent.

The root-cause list also seeds active checks. Schema drift between recorded tool calls, dependency changes between session and replay, state loss across a chain — these leave marks in recorded traces, and each detection is a completeness finding with a name the operator recognizes.

## Key Takeaways For The Repo

### 1. The recorder must survive production faults, not just clean runs

The SDK and auto-patch adapters need explicit behavior for malformed tool outputs and exceptions mid-chain: degrade loudly and flag the session incomplete, never drop events silently.

### 2. Fault injection is the test for completeness diagnostics

For each symptom class in the taxonomy, inject it into a demo agent and assert the session is flagged incomplete with the specific gap named. That suite is the proof the diagnostics work.

### 3. Root causes are detectable, not just describable

Data schema mismatch and dependency drift leave traces in recorded sessions — paired calls to the same tool whose schemas disagree. Completeness diagnostics can check for them directly.

## Concrete Opportunities

- build a recorder self-test suite that injects each symptom class (malformed tool output, state loss, exception mid-chain) and asserts an incomplete flag names the gap
- add schema-drift detection between recorded calls to the same tool as a completeness check
- harden auto-patch adapters against structured-output interpretation faults, with a loud fallback when parsing fails
- tag completeness-diagnostic findings with the four-dimension taxonomy so coverage against the 34 fault types is measurable

## Caution

This is GitHub-mined research on harness and framework faults, not model behavior. It says little about reasoning failures or hallucination, and it should not drive claim-verification design — the verification taxonomy answers a different question. Use it for instrumentation coverage and diagnostics self-tests, and expect smaller single-agent stacks to hit only a subset of the 34 types.

## Best Next Experiment

Take three symptom classes — malformed tool output, exception mid-chain, state loss — inject each into the demo agent under the SDK, and assert the session lands flagged incomplete with the right gap named. Three injections, three assertions; commit them as the first recorder self-test.
