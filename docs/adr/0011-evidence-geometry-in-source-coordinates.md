# ADR-0011: Evidence geometry in source-image coordinates

**Status:** Accepted for development. Extraction and evidence grading are unchanged.

OCR lines kept only vertical bounds in processed-image pixels, after deskew, resizing,
padding and envelope fitting. That cannot associate a label with a value in another column
or the next aligned row, and it cannot show where evidence sits on the image a person
uploaded. For [ticket #16](https://github.com/FireBird1998/payable-receipt-ocr/issues/16),
private records now carry full geometry and every preparation step's transform, so
diagnostics can trace evidence back to the original image. This is a prefactor for spatial
payable selection (#17). It does not change which amount wins.

## Decision

**Private records.** `OcrWord` carries text, a processed-pixel box and the engine's own
score. `OcrLine` adds left/right bounds and its words. `OcrPassResult` adds engine identity
(`tesseract`), a derived script (`Latin` for `eng`, `Devanagari`), the score scale
(`tesseract-word-confidence-0-100`) and the `CoordinateTransform` of the variant it read.
`Candidate` adds a `source_region` and a `region_basis`.

**Scores are not evidence.** An OCR score is the recognizer's own number. It is reported
beside evidence, never as an evidence grade or a calibrated probability. `None` means the
engine reported no score, which differs from a score of zero. Tesseract always reports one
for accepted word records (ADR-0010 still rejects out-of-range word confidence).

**Coordinate convention.** All coordinates are continuous pixel-corner coordinates: `(0, 0)`
is the top-left corner of the top-left pixel. A box with `left=10, right=12` covers columns 10
and 11. The reported frame is the **source**: the EXIF-oriented image whose dimensions appear
in `source.dimensions`. Each variant records ordered affine steps from source to processed
pixels: `deskew` (OpenCV pixel-centre matrix converted to corners), `resize`, `pad` (24 px),
and `fit-envelope` when applied. Output sizes are rounded, but OpenCV maps corners by exactly
the requested factor, so the step records the factor. EXIF orientation is a separate transform
from stored pixels to the source frame, so stored-pixel locations remain recoverable.

**Clipping.** A source region's polygon lists the processed box corners (top-left, top-right,
bottom-right, bottom-left) mapped to the source and is never clipped. A rotated box stays a
rotated quadrilateral. Axis-aligned `left/top/right/bottom` bounds are clipped to the source
image, and `clipped` records whether clipping changed them, for example when OCR boxed padding.

**Tolerance.** A traced box edge is documented as accurate to 2 source pixels plus one
processed pixel expressed in source pixels (`2 + 1/scale`). Synthetic rectangles traced
through upscaling, downscaling, padding, envelope fitting and ±3–8° deskew measured at most
1.9 px error, against a tolerance of 3.8 px for that case. This covers geometry only. Tesseract
glyph boxes add their own error relative to rendered text.

**Candidate regions.** When the normalized words of a line reproduce its normalized text, a
candidate's region is the union box of the words its money match overlaps (`amount`).
Otherwise it falls back to the whole line (`line`). A union of words is taken in processed
pixels before mapping, so it remains one quadrilateral.

**Privacy and contract.** Geometry appears only in opt-in diagnostics (ADR-0005): word and
line regions, candidate regions and a `coordinates` block describing the frame, tolerance and
per-variant steps. Ordinary Python and CLI payloads are unchanged, and the public schema stays
`payable-receipt-ocr/1`. For all nine synthetic fixtures, default results and every
pre-existing diagnostic field were byte-identical before and after this change.

## Why

Mapping geometry is cheap and deterministic, while recovering it later would mean rerunning
OCR. Keeping transforms beside records, not inside the public result, lets spatial association
and engine comparison (#17, #19) use one convention without committing the public schema early.
Release qualification under ADR-0009 is unaffected, because selection behavior did not change.
