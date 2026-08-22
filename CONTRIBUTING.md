# Contributing

Thank you for helping improve local, safety-first receipt recognition.

## Ground rules

- Never commit real customer receipts, downloaded checkout screenshots, OCR output containing
  personal information, or proprietary benchmark corpora.
- Reproduce problems with synthetic fixtures whenever possible.
- Preserve `requires_confirmation: true` for every result.
- Do not turn an evidence grade into an automatic-write permission.
- Keep behavior changes covered through the public `recognize(...)` interface.

## Development setup

Install Tesseract and Python 3.10 or newer, then run:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install --editable '.[dev]'
ruff check .
ruff format --check .
pytest
python -m build
twine check dist/*
```

Pull requests should explain the receipt condition being addressed, the observable interface
change, and the synthetic or authorized evidence used to verify it.
