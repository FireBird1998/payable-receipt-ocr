"""Public recognition regressions using synthetic Tesseract output and images."""

from decimal import Decimal
from pathlib import Path
from subprocess import CompletedProcess

import pytest
from PIL import Image

from payable_receipt_ocr import OcrEngineError, recognize
from payable_receipt_ocr._contracts import RuntimeValidation

HEADER = (
    "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext"
)


def word(text, *, left=20, top=100, width=80, height=20, conf="95"):
    return f"5\t1\t1\t1\t1\t1\t{left}\t{top}\t{width}\t{height}\t{conf}\t{text}"


def payable(*, top=160):
    return [word("TO PAY", top=top), word("INR 120.00", left=150, top=top)]


@pytest.fixture
def read_tsv(tmp_path, monkeypatch):
    source = tmp_path / "synthetic.png"
    Image.new("RGB", (600, 400), "white").save(source)
    runtime = RuntimeValidation("synthetic", False, "synthetic", {}, tmp_path, "1")
    monkeypatch.setattr("payable_receipt_ocr._engine.validate_runtime", lambda **_: runtime)
    temporary_inputs = []

    def read(records, *, header=HEADER):
        def run(command, **kwargs):
            assert command[0] == "tesseract"
            image = Path(command[1])
            assert image.is_file()
            temporary_inputs.append(image)
            return CompletedProcess(command, 0, header + "\n" + "\n".join(records) + "\n", "")

        monkeypatch.setattr("payable_receipt_ocr._ocr.subprocess.run", run)
        result = recognize(source, diagnostics=True)
        assert result.requires_confirmation is True
        assert result.authorizes_persistence is False
        return result

    yield read
    assert temporary_inputs
    assert all(not image.exists() for image in temporary_inputs)


def lines(result):
    return result.to_dict(include_diagnostics=True)["diagnostics"]["ocr"]["passes"][0]["lines"]


@pytest.mark.parametrize("product", ['"Sale', '"Sale"', 'Pack "Large"'])
def test_literal_quotes_preserve_product_and_later_payable(read_tsv, product):
    result = read_tsv([word(product, top=20), *payable()])
    assert result.total == Decimal("120.00")
    assert product in [line["text"] for line in lines(result)]
    assert result.evidence_grade == "strong"


@pytest.mark.parametrize(
    "damaged",
    [
        "5\tPRIVATE_SENTINEL",
        word("PRIVATE_SENTINEL") + "\textra",
        word("PRIVATE_SENTINEL", conf="invalid"),
        word("PRIVATE_SENTINEL", conf="nan"),
        word("PRIVATE_SENTINEL", conf="inf"),
        word("PRIVATE_SENTINEL", conf="101"),
        word("PRIVATE_SENTINEL", top="invalid"),
        word("PRIVATE_SENTINEL", left=-1),
        word("PRIVATE_SENTINEL", height=0),
        word("PRIVATE_SENTINEL", width=-1),
        word("PRIVATE_SENTINEL", top=100000),
    ],
)
def test_damaged_records_keep_later_payable_but_require_review(read_tsv, damaged):
    result = read_tsv([damaged, *payable()])
    assert result.total == Decimal("120.00")
    assert result.evidence_grade == "review"
    payload = result.to_dict()
    assert payload["processing"]["degraded"] is True
    assert payload["processing"]["passes_failed"] == 0
    assert payload["processing"]["passes_completed"] == 12
    warnings = [w for w in payload["warnings"] if w["code"] == "ocr_malformed_records"]
    assert len(warnings) == 12
    assert all(len(w["message"]) < 200 for w in warnings)
    assert "PRIVATE_SENTINEL" not in str(payload)
    assert "PRIVATE_SENTINEL" not in str(lines(result))


def test_unusable_header_raises_controlled_error(read_tsv):
    with pytest.raises(OcrEngineError, match="All OCR passes failed"):
        read_tsv(payable(), header="PRIVATE_SENTINEL")


def test_only_damaged_records_abstain(read_tsv):
    result = read_tsv(["5\tPRIVATE_SENTINEL"])
    assert result.total is None
    assert result.evidence_grade == "none"
    assert result.to_dict()["processing"]["degraded"] is True


def test_empty_page_is_not_malformed(read_tsv):
    result = read_tsv(["1\t1\t0\t0\t0\t0\t0\t0\t600\t400\t-1\t", ""])
    assert result.total is None
    assert result.to_dict()["processing"]["degraded"] is False
    assert not any(w.code == "ocr_malformed_records" for w in result.warnings)


@pytest.mark.parametrize("reverse", [False, True])
def test_tall_box_cannot_join_quantity_and_payable(read_tsv, reverse):
    records = [word("TOTAL ITEMS 2", top=20), word("ART", left=300, top=10, height=200), *payable()]
    result = read_tsv(list(reversed(records)) if reverse else records)
    assert result.total == Decimal("120.00")
    assert all(
        not ("TOTAL ITEMS" in line["text"] and "TO PAY" in line["text"]) for line in lines(result)
    )


def test_overlapping_chain_cannot_merge_distant_rows(read_tsv):
    records = [word("TOTAL ITEMS 2", top=20)]
    records += [word("ART", left=300, top=top) for top in range(30, 100, 10)]
    result = read_tsv([*records, *payable(top=100)])
    assert result.total == Decimal("120.00")
    assert all(line["bottom"] - line["top"] <= 40 for line in lines(result))


def test_slightly_offset_words_still_form_payable_row(read_tsv):
    result = read_tsv(
        [
            word("TO", left=20, top=100),
            word("PAY", left=70, top=103),
            word("INR 120.00", left=150, top=106),
        ]
    )
    assert result.total == Decimal("120.00")
    assert result.evidence_grade == "strong"
    assert [line["text"] for line in lines(result)] == ["TO PAY INR 120.00"]
