## Why this works

An isometric overview shows alternate crossings while close views show route segments. Bridge controls, fleet selection and dispatch log sit alongside the map they describe.

## Visual principles

Let a learner remove a connection and observe which destinations fail.

## Interaction principles

Show topology, route changes and outcome counters together.

## Educational principles

The two-bridge scenario exposes a concrete cause/effect relationship between connectivity and deliveries. There is little explicit synthesis of the graph-theory concept or prediction guidance.

## 3D / visualization principles

An isometric overview shows alternate crossings while close views show route segments. Very small route and destination labels need a close camera view.

## Implementation patterns worth studying

Original author reports 12 logic checks, but no repository or test output is available. Do not record those checks as local test success.

## Weaknesses

Strong conceptual transfer; actual algorithm and live behavior are not independently verified.

## Anti-patterns

Do not claim shortest-path correctness without testing the algorithm. Do not overwhelm the learner with a dispatch log before explaining the core connectivity problem.

## What OpenAtlas should learn

- Let a learner remove a connection and observe which destinations fail.
- Show topology, route changes and outcome counters together.
- Make an intervention reversible so recovery can be compared.
- Support both network overview and local route inspection.

## What OpenAtlas should NOT copy

- Do not claim shortest-path correctness without testing the algorithm.
- Do not overwhelm the learner with a dispatch log before explaining the core connectivity problem.
