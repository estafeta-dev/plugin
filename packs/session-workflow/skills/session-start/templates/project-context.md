# <Project>

## Purpose and rules

<Goal, audience, acceptance, constraints and repository conventions.>

## Documentation map

- Plan: <docs/plans/<workstream>.md, or none for a small task>
- Handover: <HANDOVER.md>
- Architecture and runbooks: <existing links>
- Workflow: estafeta; machine state in .agent-state/session-workflow (not edited by hand)

## Current focus

- Phase and outcome: <phase ID and what it delivers>
- Open decisions: <specific question, or none>
- Next action: <concrete command or task>

## AI providers

Which AI providers may work on this project, and how. The user decides; agents
ask before changing it. Allowed: orchestrate, consult, review, write, or none.
Models: any, or a list. The runtime refuses delegations outside this table.

<!-- estafeta:providers:start -->
| Provider | Allowed | Models | Notes |
| --- | --- | --- | --- |
| <this agent's provider, e.g. claude> | orchestrate, consult, review, write | any | <how it runs here> |
| <other provider, e.g. codex> | <consult, review, write, or none> | <any, or model IDs> | <transport, budget, account> |
<!-- estafeta:providers:end -->

## Run and verify

<Known commands and prerequisites, without secrets. Mark commands not yet run
in this environment.>
