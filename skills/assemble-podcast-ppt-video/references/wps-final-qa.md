# WPS Final PPTX QA

Read this reference on Windows when WPS is the required fidelity target or when
the project contract requires actual WPS rendering before delivery.

Run the reusable audit with the final PPTX and a new validation directory:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File \
  <this-skill>\scripts\wps_render_audit.ps1 \
  -SourcePptx <final.pptx> \
  -OutputDir <project>\validation\wps_final \
  -ExpectedFont "Noto Sans SC" \
  -RequireNotes
```

Omit `-ExpectedFont` or `-RequireNotes` only when that condition is not part of
the deck contract. Use `-Force` for an intentional rerun into the same exact
output directory.

The script stages Chinese paths through an ASCII-only Office directory, opens
the deck in WPS, recursively descends into grouped shapes for font inspection,
exports every slide to 1920×1080 PNG, and writes `wps_audit.json`. Top-level
Shapes alone are not a valid font audit because PPT Master commonly emits one
PowerPoint group per semantic SVG unit.

The automated gate requires:

- exported PNG count equals the slide count;
- every slide reports the expected font when one is supplied;
- every slide has non-empty notes when `-RequireNotes` is supplied.

Then inspect the complete rendered contact sheet and every page at useful
resolution for clipping, overlaps, unexpected wrapping, visual imbalance,
broken SVG/native objects, and missing text. Automation proves coverage and
font/package facts; it does not judge composition or semantic usefulness.

After any PPTX/SVG revision, rerun the audit and reinspect every affected page.
