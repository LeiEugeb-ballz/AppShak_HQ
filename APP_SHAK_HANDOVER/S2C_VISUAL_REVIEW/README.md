# S2C visual-review package

This package checks whether six synthetic ATS states remain truthfully and legibly represented by the read-only office. It certifies the verification process, not the office's final visual polish. The [S2C handover report](../S2C_VISUAL_PERCEPTUAL_VERIFICATION.md) explains the scope and limitations.

Read [manifest.json](manifest.json) for the ATS-to-visual contract, [review.json](review.json) for per-state semantic and structural results and measured browser/canvas bounds, then [findings.json](findings.json) for bounded perceptual findings. The `baseline_image` paths point to preserved S2B images; `baseline_sha256` locks their bytes. The images below are current S2C review captures.

| ATS fixture | S2C screenshot | Original S2B baseline |
| --- | --- | --- |
| Active execution | [active.png](images/active.png) | [active.png](../S2B_VISUAL_BASELINES/active.png) |
| Validation failed | [validation_failed.png](images/validation_failed.png) | [validation_failed.png](../S2B_VISUAL_BASELINES/validation_failed.png) |
| Needs reconciliation | [needs_reconciliation.png](images/needs_reconciliation.png) | [needs_reconciliation.png](../S2B_VISUAL_BASELINES/needs_reconciliation.png) |
| Complete | [complete.png](images/complete.png) | [complete.png](../S2B_VISUAL_BASELINES/complete.png) |
| Waiting for capability | [waiting_for_capability.png](images/waiting_for_capability.png) | [waiting_for_capability.png](../S2B_VISUAL_BASELINES/waiting_for_capability.png) |
| Backend unavailable | [stale_unavailable.png](images/stale_unavailable.png) | [stale_unavailable.png](../S2B_VISUAL_BASELINES/stale_unavailable.png) |

`review.json` records requested Chrome window sizes and measured inner viewport sizes separately. Headless Chrome uses a minimum 500-pixel inner viewport for the compact capture; deterministic canvas tests also check a 390-pixel render. Structural checks cover bounds and labels, not aesthetic quality or accessibility certification.

The six findings were supplied by the Owner/independent visual review. `PERCEPTUAL_REVIEWED` means those findings are captured; `HUMAN_ACCEPTED` remains **false**. An independent reviewer should compare each screenshot with its ATS fixture and recorded checks, then report any additional misleading representation as a bounded finding. Review must not alter ATS state, dispatch, validation, or the roadmap.

To regenerate browser evidence, start the existing Vite development server on `127.0.0.1:4173` from `appshak-ui`, then run `node tests/s2cBrowserAudit.mjs` from that directory. The script requires a locally installed Chrome or Edge and changes only this review package's screenshots and `review.json`.
