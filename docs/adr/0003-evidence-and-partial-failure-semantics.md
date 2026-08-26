# ADR-0003: Evidence and Partial-Failure Semantics

**Status:** Accepted

## Decision

### Evidence grade definitions

| Grade | Meaning |
|---|---|
| `"strong"` | Independent OCR passes agree on a payment-labelled amount with INR evidence, no conflicts, no degradation, and sufficient cross-pass support |
| `"review"` | A payable-total candidate was found but the strict corroboration criteria were not met |
| `"none"` | No supported payable-total candidate was extracted |

`"strong"` is never automatic write permission. All three grades set `requires_confirmation=True`
and `authorizes_persistence=False`.

### Strong-evidence criteria (all required)

1. `label_kind == "payment"` — the winning candidate is associated with a recognized payment label
   (e.g. "to pay", "amount paid", "grand total")
2. No competing candidate with equal or greater cross-pass support (`runner_safe`)
3. At least one explicit INR currency marker in the winning candidate group
4. Not degraded — no OCR pass failed and no deadline pressure during this recognition call
5. No `ranking_warning`, `currency_conflict`, or `competing_total` warning codes on the result
6. Either of:
   - Language-and-pass support: votes from ≥ 2 languages with ≥ 3 total completed passes
   - Arithmetic corroboration: component amounts sum to the winning total within tolerance in ≥ 2
     independent passes

### Conflicts and degradation

If two or more of the following degrade-inducing conditions are present, the grade is capped at
`"review"` regardless of other signals:

- Any OCR pass failed
- The total call deadline was reached before all planned passes completed

A grade of `"none"` is never upgraded by degradation logic. A result with
`evidence_grade="none"` always has `total=null` and `currency=null`.

### Raise-vs-degrade table

| Condition | Outcome |
|---|---|
| All OCR passes failed and no pass completed | Raises `OcrEngineError` |
| No pass completed before deadline | Raises `OcrEngineError` |
| Some passes failed; at least one completed | Continues with degraded flag; grade ≤ `"review"` |
| Deadline reached after some passes completed | Continues with `deadline_exceeded=True`; grade ≤ `"review"` |

### Invariants

- `requires_confirmation` is `True` on every result without exception.
- `authorizes_persistence` is `False` on every result without exception.
- A result with `evidence_grade="none"` has `total=null` and `currency=null`.
- `"strong"` evidence requires an explicit image-level INR indicator; it cannot be inferred from
  the `currency` parameter alone.

## Why

Three grades are enough to communicate to the UI layer what kind of user prompt is appropriate.
Conflating `"none"` with `"review"` would hide the distinction between "we found something
uncertain" and "we found nothing". Making `"strong"` require explicit in-image INR evidence
prevents the currency parameter from silently promoting a weak result to strong.

Capping the grade on degradation rather than raising prevents a single slow or failing Tesseract
pass from blocking a result on a receipt that was otherwise successfully read.
