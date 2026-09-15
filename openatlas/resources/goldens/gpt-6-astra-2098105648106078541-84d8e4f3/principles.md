## Why this works

A dominant anatomical object and persistent control locations make spatial exploration the main activity.

## Visual principles

Keep the anatomy larger than the controls; use system colors consistently and subdued chrome.

## Interaction principles

Make hiding, revealing and reassembling reversible. Pair inventory views with a route back to original anatomical positions.

## Educational principles

Distinguish naming and spatial inspection from explanation of function. Add short organ-specific causal explanations and guided comparisons.

## 3D / visualization principles

Exploded layouts reveal occluded parts but change relative positions; label illustrative layout and preserve assembled reference.

## Implementation patterns worth studying

source/dissection.js separates hierarchy scope, visibility history, pagination and animated layout. source/hierarchy.js organizes anatomical groups. source/main.js coordinates clipping, display modes and camera. source/build.mjs packages an offline standalone artifact.

## Weaknesses

A large number of labeled parts can overwhelm a novice; detailed factual accuracy requires domain review.

## Anti-patterns

Treating a named-mesh inventory as a complete anatomy lesson.

## What OpenAtlas should learn

Use selective reveal and contextual labels to help learners inspect a system; keep source and model limitations visible.

## What OpenAtlas should NOT copy

Do not reproduce branding or imply clinical accuracy from realistic geometry.
