# Holdout corpus process (private)

This directory defines the **contract only** for a private, consented holdout corpus used by
`tools/holdout/evaluate.py`.

## Privacy and storage requirements

- Keep all real receipt images and manifests in private storage only.
- Never commit private manifests, holdout images, OCR text dumps, or derived personal data to this
  repository.
- Do not upload private holdout assets into CI artifacts, docs, or issue threads.

## Data sourcing and labelling expectations

- Collect receipts only with explicit consent and legal permission.
- Create ground-truth labels **before OCR runs** to prevent model-feedback bias.
- Store expected totals as exact decimal strings and expected currency as `INR`.
- Double-label at least 10% of cases and adjudicate disagreements.

## Quality controls before freezing

- Run exact deduplication using image SHA-256.
- Run perceptual deduplication checks and manually review near-duplicates.
- Stratify by app (`blinkit`, `swiggy`, `zepto`) and capture type before freeze.
- Freeze each corpus version with immutable metadata: `corpus_version`, `frozen_at`,
  `runtime_baseline_id`, and canonicalized `manifest_sha256`.

## Manifest and evaluator

- Manifest shape is documented in `manifest.schema.json`.
- Evaluator validates path safety, manifest hash, image byte hashes, app coverage, and corpus size.
- Reports stay privacy-safe: no filenames, no image paths, no OCR text.
