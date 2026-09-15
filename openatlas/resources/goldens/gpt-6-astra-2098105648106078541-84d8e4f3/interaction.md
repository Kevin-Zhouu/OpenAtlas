# Interaction Analysis

## Primary interaction
Initial: The built standalone atlas opens with 708 objects in a head.
Action: Open Brain.
Response: The interface and camera scope narrow to 247 brain parts with six child groups (interaction-1.png).
Action: Set Depth of anatomical exploration to its end using the keyboard.
Response: 24 labeled objects appear, with page 1 / 11 for the 247 parts (interaction-2.png).
Action: Assemble.
Response: The contextual brain returns with all 247 parts shown (interaction-3.png).
Why it matters: A learner can move from the whole to individual named components and back without losing their selected system.

## Secondary interactions
Guided tour changes the interface to four named stages: The head, The cortex, Deep within, Networks (interaction-4.png). Cutaway visibly removes part of the skull and exposes brain tissue (interaction-5.png). Display opens material and section controls with an explicit open-surface warning (interaction-6.png); changing each material/plane was not tested.

## Runtime and responsive check
Local pnpm install, test and build succeeded. Tests reported 708 structures, 12 cranial nerve pairs and 3,312 checked layout cells. A browser resource 404 was recorded, with no observed scene failure; it is not diagnosed beyond available logging. At 390×844 an open display panel covers much of the model. No physical touch device was tested.

## Meaningful versus decorative
Scope changes, explosion and cutaway change what can be inspected. Lighting and camera polish support legibility but do not teach physiology independently. Code capabilities such as undo and isolation remain untested, not observed claims.
