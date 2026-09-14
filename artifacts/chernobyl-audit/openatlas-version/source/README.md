# Chernobyl Atlas

Editable, offline OpenAtlas notebook. The requested creative brief takes priority as the main subject; the final chapter introduces the requested Tauri framework through packaging this web exhibit. Approximately 20 minutes includes reading and guided interaction.

## Build

From /workspace:

    node source/build.cjs
    node source/make-manifest.cjs

The output is `dist/index.html`, a standalone HTML document with embedded CSS, Three.js 0.180.0, OrbitControls and application JavaScript. No package install, network access or bundler is required. Vendored Three.js source and its MIT license are in `vendor/`. No native app is built.

## Test

Start a local server:

    python3 -m http.server 8000 --directory /workspace

In another terminal:

    node source/test.cjs

The test uses the preinstalled Playwright at `/opt/browser/node_modules/playwright`. It executes all 30 manifest checks, checks the keyboard camera and arrow-key tabs, captures desktop/mobile screenshots, checks horizontal overflow, verifies the reduced-motion default, checks for runtime errors and external requests, and opens the artifact in a sandbox with only allow-scripts. Temporary review images go to `/workspace/.build-tools/`, outside the deliverable directories.

## Interaction

- Drag the 3D view to orbit. Scroll inside Power Block to separate layers; scroll outside the view to continue reading.
- Focus the view and use arrow keys to orbit and + / - to zoom. Pinch zoom is also available.
- Disassembly and layer spacing move independent groups. The camera pulls back as the stack expands, without restricting orbit.
- System checkboxes hide corresponding assemblies. Wireframe, transparency and clipping operate on the 3D material system. The section plane removes the front half of geometry and is not a capped engineering cross-section.
- Steam Circuit uses an animated SVG. On phones the diagram scrolls horizontally so text remains readable.
- Playback and speed affect illustrative motion; reduced-motion readers begin paused and SVG motion remains suppressed by the media query.
- Quiz choices explain both correct and incorrect reasoning. Expandable teaching notes are native keyboard-accessible details elements.

## Scope and references

Geometry is an educational composite, not a plant drawing, safety analysis or thermal-hydraulic simulation. Counts, proportions and flow speeds are deliberately schematic. Reference identification is included in the reading room. Automated public-page requests returned 403 or 404 in the build environment, so no new primary-source validation is claimed. Historical interpretation draws on IAEA INSAG-7 (1992), UNSCEAR 2008 Vol II Annex D, and the EBRD New Safe Confinement project history. The lesson avoids a single speculative total for eventual fatalities and distinguishes historical containment from the site's current condition.

No remote runtime resources, storage, analytics, cookies, fetch calls, services, or navigation outside the notebook are used.
