# Influencing LLM Multi-Agent Dialogue via Policy-Parameterized Prompts

Paper: [arXiv:2603.09890v1](https://arxiv.org/abs/2603.09890v1)

## Core Idea

This paper treats prompts as lightweight policy actions that can shape multi-agent dialogue without additional model training. It studies how parameterized prompts can influence dialogue behavior using interpretable indicators.

## Why It Matters Here

Prompt policy is part of agent behavior, so it should be observable.

If prompt structure changes behavior, then a debugger should record the policy context around prompts, not only the raw output.

## Key Takeaways For The Repo

### 1. Prompt policy should be tracked explicitly

For multi-agent systems, traces become much more useful when they capture:

- which prompt template was used
- which policy parameters were active
- what state caused that policy choice
- how the dialogue changed afterward

### 2. Multi-agent evaluation needs behavioral metrics

The paper uses dialogue indicators to assess changes in behavior. This suggests the repo could expose higher-level metrics such as:

- responsiveness
- repetition
- evidence use
- stance shift
- escalation frequency

These metrics would help move the debugger beyond raw event browsing.

### 3. Agent-to-agent interaction needs its own observability model

A multi-agent trace is not just "more messages." It often needs:

- speaker identity
- policy context per turn
- turn-level goals
- cross-agent influence markers

## Concrete Opportunities

- add prompt-policy metadata to LLM request events
- add multi-agent conversation views
- add behavior metrics over a session
- support comparison between two policy settings on similar runs

## Caution

The paper is about influencing dialogue behavior, not debugging infrastructure. The useful lesson is that policy and prompt structure are observable control surfaces and should be represented as such.

## Best Next Experiment

Extend `LLMRequestEvent` metadata with one explicit policy block:

- prompt template ID
- policy parameters
- active role or speaker
- state summary that caused the prompt choice
