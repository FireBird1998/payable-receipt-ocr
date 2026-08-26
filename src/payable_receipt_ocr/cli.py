"""Command-line adapter for payable-receipt-ocr."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from ._engine import SUPPORTED_CURRENCIES
from .api import recognize
from .errors import ReceiptOcrError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="payable-receipt-ocr",
        description="Suggest a confirmation-only payable total from a local receipt image.",
    )
    parser.add_argument("image", type=Path, help="JPG, JPEG, PNG, or WebP receipt image")
    parser.add_argument(
        "--currency",
        default="INR",
        choices=sorted(SUPPORTED_CURRENCIES),
        help="ISO currency supplied as supporting context",
    )
    parser.add_argument(
        "--tessdata-dir",
        type=Path,
        help="Directory containing eng.traineddata and Devanagari.traineddata",
    )
    parser.add_argument(
        "--pass-timeout",
        type=float,
        default=2.0,
        help="Maximum seconds for each Tesseract pass",
    )
    parser.add_argument(
        "--deadline",
        type=float,
        default=5.0,
        help="Maximum total wall time in seconds",
    )
    parser.add_argument(
        "--runtime-policy",
        choices=("development", "conformant"),
        default="development",
        help="Runtime validation mode: development reports drift, conformant fails closed",
    )
    parser.add_argument(
        "--diagnostics",
        action="store_true",
        help="Include sensitive OCR text and candidate evidence in the output",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = recognize(
            args.image,
            currency=args.currency,
            tessdata_dir=args.tessdata_dir,
            diagnostics=args.diagnostics,
            deadline_seconds=args.deadline,
            pass_timeout_seconds=args.pass_timeout,
            runtime_policy=args.runtime_policy,
        )
    except ReceiptOcrError as error:
        print(
            "payable-receipt-ocr [{}]: {}".format(error.code, error),
            file=sys.stderr,
        )
        return error.exit_code
    except Exception as error:  # pragma: no cover - defensive CLI contract.
        print("payable-receipt-ocr [unexpected]: {}".format(error), file=sys.stderr)
        return 1
    print(
        json.dumps(
            result.to_dict(include_diagnostics=args.diagnostics),
            ensure_ascii=False,
            separators=(",", ":"),
        )
    )
    return 0
