# Contributing

Thank you for helping improve local, safety-first receipt recognition.

## Ground rules

- Never commit real customer receipts, downloaded checkout screenshots, OCR output containing
  personal information, or proprietary benchmark corpora.
- Reproduce problems with synthetic fixtures whenever possible.
- Preserve `requires_confirmation: true` for every result.
- Do not turn an evidence grade into an automatic-write permission.
- Keep behavior changes covered through the public `recognize(...)` interface.
- Changes that affect the runtime baseline tuple (Tesseract version, model files, OS/arch target)
  require holdout requalification before the new baseline is released.

## Development setup

Install Tesseract and Python 3.10 or newer, then run:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --editable '.[dev]'
./scripts/setup-models.sh
ruff check .
ruff format --check .
```

## Running tests

Portable tests run without Tesseract or model files:

```bash
pytest -m 'not integration'
```

Integration tests require a local Tesseract executable and the model files installed by
`./scripts/setup-models.sh`:

```bash
pytest -m integration
```

CI runs portable tests on every push. Integration tests run in CI when Tesseract and the models
are available.

## Artifact check

Before submitting a pull request, confirm that no real receipt data has been added to the build:

```bash
python -m build
python tools/check_artifacts.py dist/
```

## Baseline-affecting changes

Changes to any of the following require a new holdout evaluation run before the new baseline can
be declared conformant:

- The pinned model SHA-256 hashes in `runtime-baseline.toml`
- The `tesseract_first_line`, `os_name`, or `arch` fields in `runtime-baseline.toml`
- The image preprocessing pipeline in `_image.py`
- The OCR pass schedule in `_ocr.py`
- The evidence grading logic in `_interpretation.py`

Record the change in an ADR under `docs/adr/` if it affects the accuracy gate or reproducibility
contract.

## Pull requests

Pull requests should explain the receipt condition being addressed, the observable interface
change, and the synthetic or authorized evidence used to verify it. Do not include real receipt
data in test fixtures, issue descriptions, or PR comments.
