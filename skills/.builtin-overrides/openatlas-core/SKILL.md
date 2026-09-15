---
name: openatlas-core
description: Design accessible interactive learning Notebooks with progressive explanations, worked examples, and meaningful practice.
metadata:
  version: "1.2.0"
---
# OpenAtlas core teaching
Read the learner's prompt carefully and adapt to what they know and want to understand. 


Keep the artifact self-contained with bundled dependencies. Never require storage, parent-frame access, or external APIs. Review both a phone viewport and desktop. Test every important interaction in the final built artifact. Preserve readable editable source and a documented build.

## Reader navigation
OpenAtlas provides the app toolbar, logo, back navigation and table of contents around the Notebook. Do not generate an OpenAtlas wordmark, application menu, branded masthead, "OPENATLAS / FIELD NOTES" banner, edition bar or duplicate reader navigation. Keep topic-specific experiment controls. for each section element add a html class "atlas-section". The reader handles the top inset; do not add spacer elements for its toolbar.
