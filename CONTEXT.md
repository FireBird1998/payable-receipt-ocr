# Payable Receipt Recognition

This context turns a receipt image into evidence for a payable-amount suggestion. It never treats recognition confidence as permission to persist an expense.

## Language

**Payable total**:
The final amount the receipt presents as owed or charged after discounts, fees, taxes, and other adjustments.
_Avoid_: Total, subtotal, item total

**Payment label**:
Receipt text that explicitly identifies a nearby amount as the payable total.
_Avoid_: Total label, amount label

**Fallback total**:
A generically labelled total that may support a suggestion when no payment label is available, but may not represent the final amount charged.
_Avoid_: Payable total, confirmed total

**Component amount**:
An amount such as a subtotal, fee, tax, discount, saving, cash, or change that provides context but is not itself the payable-total suggestion.
_Avoid_: Payable amount, line item

**Recognition suggestion**:
A proposed payable total and currency derived from receipt evidence for a person to review.
_Avoid_: Extracted truth, confirmed expense

**Evidence grade**:
The strength of support for a recognition suggestion: `strong`, `review`, or `none`. It is not a probability or permission to persist an expense.
_Avoid_: Confidence score, approval status

**Strong evidence**:
Evidence that meets the strict corroboration policy for a recognition suggestion. Strong evidence still requires confirmation.
_Avoid_: Confirmed, safe to save

**Review evidence**:
Evidence that supports a recognition suggestion but does not meet the strong-evidence policy.
_Avoid_: Failure, rejected

**No evidence**:
The absence of a supported payable-total suggestion.
_Avoid_: Zero total, free receipt

**Confirmation**:
An explicit human decision accepting or correcting a recognition suggestion before an expense is persisted.
_Avoid_: Automatic approval, strong evidence

**False-strong result**:
An incorrect payable total or currency that was assigned strong evidence.
_Avoid_: False positive

**Recognition pass**:
One execution of Tesseract on one image variant with one page-segmentation mode and one language
model, producing a set of OCR lines. Multiple passes run per image to gather independent evidence.
_Avoid_: OCR run, scan

**Corroboration**:
Agreement across independent recognition passes that supports a recognition suggestion. Corroboration
is required for strong evidence but is not itself permission to persist an expense.
_Avoid_: Confidence, confirmation

**Degraded recognition**:
A recognition call in which at least one planned pass failed or the total deadline was reached
before all passes completed. Degraded recognition caps the evidence grade at review.
_Avoid_: Partial failure, error state

**Runtime baseline**:
The recorded combination of operating system, CPU architecture, Tesseract version, and model
checksums that defines the conformance environment. Results produced outside the baseline tuple
set `conformant=false` in the result.
_Avoid_: Reference environment, approved configuration

**Holdout corpus**:
A frozen, consented set of real receipt images with pre-OCR ground-truth labels, used to measure
accuracy before a release. The corpus and its evaluation report are private and not published.
_Avoid_: Test set, benchmark dataset (unless the holdout process is explicitly described)

**Runtime conformance**:
The property of a recognition call whose OS, architecture, and Tesseract version all matched the
baseline tuple. Only conformant calls on the retained reference runtime are eligible for the
accuracy gate.
_Avoid_: Matching environment, compatible runtime

**Payable policy**:
The interpretation rules that determine whether a document presents a unique payable total,
including how to handle zero, credits, missing totals and competing payment windows.
_Avoid_: OCR confidence, payment authorization

**Payable-field evidence**:
The visible document region that supports a recognition suggestion as the final payable,
rather than an unrelated field that happens to contain the same number.
_Avoid_: Numeric match, confirmed expense

**Negative control**:
A document whose payable policy target is no suggestion because a unique payable total is
absent or ambiguous. An execution error is not a successful abstention.
_Avoid_: Zero-payable receipt, failed OCR
