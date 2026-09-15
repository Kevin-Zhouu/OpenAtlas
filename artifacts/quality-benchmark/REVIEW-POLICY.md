# Review policy correction

Implemented after the user identified long, repetitive review cycles. The atlas benchmark passed under its existing rules. These changes were then deployed to the local application, worker and generation image; they did not retroactively approve the artifact.

## Changes

- The first independent audit returns one consolidated checklist and all reasonably discoverable blockers.
- Reports distinguish evidenced publication blockers from optional suggestions. Suggestions alone can pass; an unexplained request to revise cannot trigger application repair.
- Server-owned findings persist across repairs and Continue. A fresh Re-run clears them. Follow-up review keeps criterion names, focuses on prior blockers and affected behavior, and includes a short fresh regression sweep. New blockers, regressions of passed criteria, and severity changes need explanations grounded in the original request.
- First reviews target four minutes, with an eight-minute ceiling. Follow-ups target two minutes, with a four-minute ceiling. Generation's longer time budget does not apply to reviews.
- Quota, browser/tool, timeout and insufficient-evidence failures preserve the build and stop review. They do not consume application repair attempts by asking the builder to fix infrastructure.
- Independent image/motion evidence, artifact fingerprints, full mechanical publication checks and the two-repair limit remain.

## Verification

153 backend tests passed; 13 opt-in tests skipped. Targeted policy checks also passed after the final rule for regressions of previously passed criteria was added. Tests cover suggestions-only approval, real blockers, unsupported severity/new-blocker changes, omitted criteria, consolidated feedback, state persistence through Continue, and retained checkpoints without spurious repair after quota/tool failures.

A separate real Docker test passed for deletion-preserving snapshot collection and the 512 process/thread limit.

The timing targets are policy settings, not an observed end-to-end speedup. A future run is needed to measure the new review latency distribution. No guarantee is made that one audit discovers every defect.
