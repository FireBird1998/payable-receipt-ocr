# ADR-0010: Literal TSV ingestion and bounded receipt rows

**Status:** Accepted for development; fresh qualification is required before release.

Tesseract TSV text contains literal quotes: CSV quote handling could swallow later payable
records, while grouping against an expanding row could connect separate lines through a tall
box or overlap chain. For [ticket #15](https://github.com/FireBird1998/payable-receipt-ocr/issues/15),
parse physical tab-separated records, retain valid word records independently, and require
pairwise vertical compatibility for every word assigned to a receipt row.

## Decision

Require the standard twelve-column header; a missing or malformed header fails the pass.
Discard malformed records independently, including invalid numeric fields, nonfinite or
out-of-range word confidence, and nonpositive or out-of-image boxes. Normal hierarchy records
are ignored. Keep later valid words and emit one count-only warning per affected pass.

A pass that discarded malformed records still counts as completed, but the recognition is
degraded and its evidence grade is capped at review, including during baseline early-exit
selection. No raw discarded text appears in warnings. A valid header with no usable words
abstains; failure of every pass remains a controlled engine error.

Sort words by top, left and text before grouping. Two words may share a row only when their
height ratio is at most 2.5, vertical overlap is at least 35% of the smaller height, and center
distance is at most 65% of the smaller height; every existing member must be compatible.
These development thresholds preserve ordinary offset text while bounding tall-box and
transitive expansion. They may split unusually mixed-size text and require corpus evaluation.

The public schema stays at version 1 with an additive `ocr_malformed_records` warning code.
Confirmation remains mandatory and persistence unauthorized. This changes extraction and
evidence grading, so ADR-0009's frozen comparison and fresh holdout requirements still apply;
passing synthetic tests or Docker development runs does not establish release qualification.
