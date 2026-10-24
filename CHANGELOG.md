# Changelog

## 1.0.0 — 2026-10-25

First finalized release of the Calibration Trending System desktop application.

- Preserve omitted calibration metadata and save event/point edits atomically.
- Edit point values, uncertainties and exclusions through the desktop bridge.
- Evaluate zero-width prediction intervals and require usable current-epoch history.
- Keep resistor extraction on page 3 and 33622A extraction on the final page for all 15 dB points.
- Reject ambiguous AC-divider and DC-reference result rows.
- Archive linked certificates by SHA-256 and create separate database/document backup generations.
- Protect local web forms with CSRF tokens, host checks and shared import validation.
- Render stored text safely and bundle offline charts.
- Use the selected voltage point's nominal for drift and uncertainty display.
- Patch the optional Next.js frontend to 16.4.3 and include its full source in this repository.
- Build versioned Windows releases with a packaged self-test and portable launcher.
- Keep production databases, linked PDFs and generated binaries out of Git tracking.

Operational note: the source certificate for historical calibration ID 41 is still unavailable. Its measurements and record were preserved. The database maintenance command reports missing documents rather than inventing replacements.
