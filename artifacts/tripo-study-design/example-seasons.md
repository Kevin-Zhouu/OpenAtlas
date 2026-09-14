# Example generated brief: why Earth has seasons

This example illustrates the proposed generator's output. It has not been built or experimentally evaluated.

## Design rationale

Audience: secondary-school learners; 10-minute lesson. Use a controllable Sun–Earth model because axis orientation, illumination, and orbital position are spatial relationships. Focus on the misconception that proximity to the Sun explains opposite seasons in the two hemispheres. Link the 3D scene to a simple sunlight-angle diagram and computed daylight comparison. Keep climate and weather prediction outside scope.

## Codex build prompt

Build **Tilt Lab**, an interactive learning website explaining Earth's seasons. Deliver a working browser experience, source code, and startup instructions. Make reasonable implementation decisions, run it, inspect it, and fix observed problems.

### Learning outcomes and content

The learner should be able to predict which hemisphere receives more direct sunlight at a given orbital position, explain why the hemispheres have opposite seasons, and predict what changes in a circular-orbit model when axial tilt becomes zero.

Use [NASA's explanation of seasons](https://spaceplace.nasa.gov/seasons/en/) for the relationship between tilt, orbital position, and sunlight. Earth's axis maintains approximately the same direction over a year; the distance explanation does not account for Earth's seasonal pattern. Distinguish rotation from revolution. Verify the equations and constants used for numerical readouts against an authoritative reference before implementation; add that reference to the lesson's source notes.

### Scene and art direction

Make an approachable tabletop science exhibit: deep navy background, warm ivory interface, gold sunlight, blue Earth, and restrained coral highlights for the selected location. Keep semantic colors consistent with labels and line styles.

Use a Sun, an enlarged Earth with visible north/south axis and equator, a circular orbit guide, and parallel incoming rays in the Earth close-up. Label sizes and distances as schematic. Keep the axis direction fixed in world space while Earth moves around the Sun; animate daily rotation separately.

Start with the Earth close-up and a compact orbit overview, both driven by shared state. Show a clear “Move through the year” control. The orbit overview shows one Earth at its current position and four labeled landmark positions. Use smooth camera transitions and a fixed-camera reduced-motion option. Keep bloom and background detail minimal so the day/night boundary remains legible.

On desktop, place the scene beside the explanation and controls. On a narrow screen stack the scene, controls, and short explanation. Keep the subject unobscured in every camera and selected state. Support orbit, zoom, reset, keyboard access, and touch; avoid obligatory camera motion.

### Learning interactions

1. **Move through the year.** Start at the March equinox landmark with approximately 23.5° tilt. A labeled orbital-position slider moves through a simplified 360° year, with equinox/solstice stops. Before moving to June, ask which hemisphere will receive more direct sunlight. Update the axis/sunlight relationship, terminator, selected-location readout, and explanation from the same model. A June-to-December comparison should reverse the north/south pattern. Label dates as approximate landmarks rather than an ephemeris. Reset restores the initial position, camera, and parameters.

2. **Remove the tilt.** Let the learner change axial tilt from 0° to 30°, default approximately 23.5°, while keeping the circular orbit fixed. Ask what will happen to the yearly daylight variation at 40° N before setting tilt to zero. Show the resulting daylight curve and a ray-angle inset. Explain the result as an idealized model, without claiming to simulate all seasonal climate effects. At zero tilt the selected nonpolar location's idealized daylight should remain approximately 12 hours throughout the orbit.

3. **Compare hemispheres.** Provide linked location choices at 40° N and 40° S. Show their locations, daylight durations, and local-noon sunlight angles side by side at the same orbital position. Ask the learner to predict the southern result after observing the northern one. At the June and December landmarks the patterns should reverse; at the equinoxes idealized daylight is approximately equal. Selecting a hemisphere must never silently change the orbital position.

For each activity, collect a prediction before displaying the explanation. Give feedback about tilt and illumination rather than only a correct/incorrect badge. Finish with a new orbital position and a southern-hemisphere prediction, then a short explanation task contrasting tilt with the distance hypothesis. Provide an exemplar explanation for self-checking; do not pretend a keyword match proves conceptual understanding.

### Model and implementation

Use the existing project's conventions; otherwise use TypeScript, Vite, and Three.js with accessible HTML controls. Use procedural geometry for this schematic model. Keep orbital phase, axial tilt, rotation, selected latitude, and camera state separate. Scene illumination, charts, numerical values, and feedback must derive from the shared scientific state.

Use a documented idealized geometric model for daylight, excluding atmospheric refraction and the finite angular size of the Sun. Verify its math and handle singularities explicitly if extending the latitude controls toward the poles. Do not add simulated temperature readings. Explain the use of a circular orbit and altered display scale in an expandable model-notes panel.

Include pause, restart, visible focus, non-color labels, reduced motion, readable numeric outputs, and a 2D/text lesson fallback if 3D rendering is unavailable. Cap render resolution and avoid unnecessary particles. Target smooth interaction on a typical laptop and a usable narrow-screen layout; report measurements from the actual test environment.

### Acceptance and delivery

Verify the build and the learning flows. Test that the axis direction remains fixed through a complete orbit; a June-to-December change reverses the hemispheric pattern; zero tilt removes yearly daylight variation in the circular-orbit model; and equinox daylight at ±40° is approximately 12 hours under the stated assumptions. Test numeric readouts against independently calculated fixtures, not merely the same implementation functions.

Inspect screenshots of the opening view, each activity, the zero-tilt state, and the final challenge on desktop and mobile. Check all controls, reset, keyboard access, labels, chart agreement, resize behavior, and browser errors. Correct failures before delivering. State any checks you could not perform. Deliver the source, lesson sources, model assumptions, startup instructions, and an honest verification report.
