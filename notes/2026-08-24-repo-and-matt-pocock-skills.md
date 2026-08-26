# payable-receipt-ocr and Matt Pocock engineering skills

**Date:** 2026-08-24  
**Repo:** `/Users/ankitdas/AnkitPersonalProjech/payable-receipt-ocr`  
**Remote:** `git@github.com:FireBird1998/payable-receipt-ocr.git`  
**HEAD:** `fed7425` — `ci: update official actions to Node 24 releases`  
**Tag:** `v0.1.0a1` → `f538f40` (`feat: publish local receipt OCR alpha`)

## One-paragraph answer

This repository is a local, confirmation-only Python package (`payable-receipt-ocr` `0.1.0a1`) that suggests a payable receipt total from a screenshot. The public seam is `recognize()` plus a frozen `RecognitionResult`; almost all behavior lives in `_engine.py`. **Matt Pocock engineering skills are not implemented in this git tree.** The 1.2.3 skill pack is installed on this machine; the repo contains none of the artifacts those skills read or write (`AGENTS.md` / `CLAUDE.md`, `CONTEXT.md`, `docs/adr/`, `docs/agents/`, `.scratch/`). The code already has a small public interface and opinionated domain terms. That is alignment of *ideas*, not of scaffolding.

**Where this file lives:** `notes/`, not `docs/`. GitHub Pages serves `/docs` from `main` (`https://firebird1998.github.io/payable-receipt-ocr/`). A research note under `docs/` would be published. `MANIFEST.in` only packs `docs` `*.css` `*.html` `*.js`, so this Markdown would not enter the sdist either — Pages does not use `MANIFEST.in`.

This note does not commit, does not edit production source, and does not run `setup-matt-pocock-skills` (`disable-model-invocation: true`; confirm-with-user). Uncommitted INR fail-closed work is described, not committed.

---

## 1. Method

Primary sources only.

**This repository** (working tree unless labelled HEAD):

- `src/payable_receipt_ocr/` (`__init__.py`, `api.py`, `models.py`, `errors.py`, `cli.py`, `__main__.py`, `_engine.py`)
- `tests/test_public_interface.py`, `tests/fixtures/README.md`
- `pyproject.toml`, `MANIFEST.in`, `.github/workflows/ci.yml`, `scripts/setup-models.sh` (untracked)
- `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `THIRD_PARTY_NOTICES.md`, `LICENSE`, `.gitignore`
- `docs/index.html`, `docs/pipeline-report.html`, `docs/stack-map.html`, `docs/learning-lab.html`
- `git status` / `git diff` / `git log` / `git ls-tree HEAD` / `git remote -v` / tag `v0.1.0a1`
- `gh api repos/FireBird1998/payable-receipt-ocr` and `.../pages`; `gh issue list`; `gh pr list`; `gh label list`

**Matt Pocock pack (on disk, not in this repo):** `/Users/ankitdas/.claude/plugins/cache/claude-plugins-official/mattpocock-skills/1.2.3/skills/`

Related copies also exist under `/Users/ankitdas/.agents/skills/`. `/Users/ankitdas/.cursor/skills-cursor/` is a **Cursor product** set, not the Matt Pocock pack.

**HEAD vs working tree.** `models.py` is unmodified. INR fail-closed behavior, `scripts/setup-models.sh`, the CI model-install step, and the test that imports `_engine` are **uncommitted**.

---

## 2. Repository facts

### 2.1 What it is

A MIT-licensed alpha console package: local Tesseract, payment-aware ranking, mandatory confirmation.

```5:11:pyproject.toml
name = "payable-receipt-ocr"
version = "0.1.0a1"
description = "Local, payment-aware receipt OCR with evidence grades and mandatory confirmation"
readme = "README.md"
requires-python = ">=3.10"
license = "MIT"
```

```44:51:pyproject.toml
[project.scripts]
payable-receipt-ocr = "payable_receipt_ocr.cli:main"

[project.urls]
Homepage = "https://github.com/FireBird1998/payable-receipt-ocr"
Documentation = "https://firebird1998.github.io/payable-receipt-ocr/"
Issues = "https://github.com/FireBird1998/payable-receipt-ocr/issues"
Source = "https://github.com/FireBird1998/payable-receipt-ocr"
```

HEAD `README.md` (lines 7–12): local payment-aware receipt OCR that suggests the amount actually paid and always requires human confirmation; tuned for Blinkit, Swiggy, and Zepto; alpha, not an accounting system.

Runtime dependencies (`pyproject.toml` 29–34): `numpy`, `opencv-python-headless`, `Pillow`, `pytesseract`. Dev extra: `build`, `pytest`, `ruff`, `twine`. Author: `FireBird1998`.

### 2.2 Public interface vs implementation

The **interface** is one function, one frozen result type, and a small error hierarchy.

HEAD `src/payable_receipt_ocr/api.py`:

```python
def recognize(
    image: PathLike,
    *,
    currency: str = "UNKNOWN",
    tessdata_dir: Optional[PathLike] = None,
    pass_timeout_seconds: float = 15.0,
) -> RecognitionResult:
```

It resolves the path (`InputFileError` on missing/unreadable), calls `_engine.process_receipt`, maps `UnidentifiedImageError` to `UnsupportedImageError`, and returns `RecognitionResult.from_payload`. Docstring: no network, no file writes, confirmation always required.

HEAD `src/payable_receipt_ocr/models.py`:

```python
EvidenceGrade = Literal["strong", "review", "none"]

@dataclass(frozen=True)
class RecognitionResult:
    total: Optional[Decimal]
    currency: str
    evidence_grade: EvidenceGrade
    requires_confirmation: Literal[True]
    needs_review: bool
    matched_label: Optional[str]
    matched_line: Optional[str]
    warnings: Tuple[str, ...]
    source_filename: str
    source_dimensions: Tuple[int, int]
    pass_count: int
```

`to_dict(..., include_diagnostics=False)` omits OCR text by default. Schema key: `schema_version: payable-receipt-ocr/v1`.

Package exports (`src/payable_receipt_ocr/__init__.py`): `ConfigurationError`, `EvidenceGrade`, `InputFileError`, `OcrEngineError`, `ReceiptOcrError`, `RecognitionResult`, `UnsupportedImageError`, `recognize`. Version `__version__ = "0.1.0a1"`.

The **implementation** is `_engine.py` (1032 lines). Module docstring: callers should use `payable_receipt_ocr.recognize` instead of importing this module.

Line counts 2026-08-24 (`wc -l`): `_engine.py` 1032; `models.py` 87; `cli.py` 62; `api.py` 50; `__init__.py` 24; `errors.py` 21; `__main__.py` 5; `tests/test_public_interface.py` 95.

### 2.3 Domain terms (no `CONTEXT.md`)

Public identifiers are consistent across Python, README, CONTRIBUTING, and the HTML site:

| Term | Where it appears |
| --- | --- |
| `recognize` | `api.py`; `README.md` Python interface; `CONTRIBUTING.md` |
| `RecognitionResult` | `models.py`; `README.md` |
| `evidence_grade` `strong` / `review` / `none` | `models.py`; `README.md` pipeline step 6 |
| `requires_confirmation` always true | `models.py` docstring and field; `README.md`; `CONTRIBUTING.md` |
| `PAYABLE_RECEIPT_OCR_TESSDATA_DIR` | HEAD README; working-tree README; `scripts/setup-models.sh`; `_engine.py` |

There is still no `CONTEXT.md`. Domain-modeling would record those terms with avoid-lists (`CONTEXT-FORMAT.md` in the skill pack). Live naming problems in the tree: dual entry points (`cli.py` vs `_engine.main`) and prototype copy inside production `_engine.py`.

### 2.4 Pipeline (working-tree `_engine.py`)

Working-tree `process_receipt` (lines 748–773):

1. Require Tesseract; validate currency and timeout.
2. Resolve model directory; **INR fail-closed** if Devanagari is missing.
3. Load image, preprocess two variants.
4. English always; Devanagari only for `INR` or `UNKNOWN` when a model exists.
5. OCR × variants × languages × PSM modes `(4, 6, 11)`.
6. Classify / score / arithmetic / aggregate / grade.

HEAD `_evidence_grade` (verified via `git show`): `strong` only if the winner’s `label_kind == "payment"`, no `ranking_warnings`, currency supported, runner gap safe (`>= 18` if runner is payment else `>= 20`), and either (two languages and `support_count >= 3`) or (`arithmetic_pass_ids >= 2`). Otherwise `review`. Empty groups → `none`.

HEAD `_warnings` appended “The Devanagari OCR model was unavailable; INR evidence is weaker” when `has_devanagari` was false. Working tree removes that path and raises instead for INR.

README combinatorics: `2 image variants × 2 languages × 3 page layouts = 12 OCR passes`. Explicit USD/EUR/GBP stay on six English passes (working-tree README).

### 2.5 Safety contract

| Rule | Source |
| --- | --- |
| `requires_confirmation` is `Literal[True]` and assigned `True` | `models.py` |
| Grades `strong` / `review` / `none`; `strong` is not write permission | `models.py`; `_evidence_grade`; `CONTRIBUTING.md` |
| Diagnostics default off | `models.py` `to_dict`; CLI `--diagnostics`; `SECURITY.md` |
| No network in `recognize` | `api.py` docstring; `SECURITY.md` |
| Never commit real receipts | `CONTRIBUTING.md`; `tests/fixtures/README.md` |
| Private vuln reports; no public issue with receipt text | `SECURITY.md` |
| INR fail-closed if Devanagari model missing | **working tree only** `_engine.py` 761–767 |

Working-tree fail-closed check:

```761:767:src/payable_receipt_ocr/_engine.py
    model_directory = _model_directory(tessdata_dir)
    if currency_context == "INR" and model_directory is None:
        raise ConfigurationError(
            "INR recognition requires Devanagari.traineddata to guard against rupee-symbol "
            "leading-digit errors. Run scripts/setup-models.sh, pass tessdata_dir=..., or set "
            "PAYABLE_RECEIPT_OCR_TESSDATA_DIR."
        )
```

HEAD did **not** fail-close: it loaded the image first, appended Devanagari whenever a model directory existed, and warned via `_warnings(..., has_devanagari=...)`.

### 2.6 Dual CLI

**Packaged adapter.** Entry point `payable_receipt_ocr.cli:main`. `__main__.py` delegates to `cli.main`. Flags: `--currency`, `--tessdata-dir`, `--pass-timeout`, `--diagnostics`. Output: `RecognitionResult.to_dict`. Errors: stderr + exit 1.

**Engine leftover.** `_engine.py` still defines `write_html_report` (line 865) and `main` with `--tessdata-dir`. HTML copy (HEAD, around the lede paragraph): “This throwaway prototype tests Blinkit, Swiggy, and Zepto-style screenshots. It keeps English and Devanagari evidence separate, exposes every pass, and always requires user confirmation.”

Two entry points, two failure surfaces, two payloads (compact `to_dict` vs full engine dict including OCR text).

### 2.7 Tests

One module: `tests/test_public_interface.py`. Pytest marker `integration: requires a local Tesseract executable` (`pyproject.toml`).

**HEAD:** public imports only (`InputFileError`, `RecognitionResult`, `recognize`). Missing-file unit test; three integration synthetic-image tests; compact JSON test; `python -m payable_receipt_ocr` test. No `_engine` import.

**Working tree** adds an INR-model unit test that **patches internals**:

```python
from payable_receipt_ocr import (
    ConfigurationError,
    InputFileError,
    RecognitionResult,
    _engine,
    recognize,
)

def test_inr_requires_devanagari_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_engine, "_require_tesseract", lambda: None)
    monkeypatch.setattr(_engine, "_model_directory", lambda _explicit=None: None)

    with pytest.raises(ConfigurationError, match="INR recognition requires"):
        recognize(FIXTURES / "clean-screenshot.png", currency="INR")
```

Working tree also asserts `pass_count == (12 if currency == "INR" else 6)`.

On-disk fixtures (`git ls-tree HEAD` / `ls tests/fixtures`): `clean-screenshot.png`, `multiple-totals.png`, `angled-photo.jpg`. Expected totals (`tests/fixtures/README.md`): INR 1280.50, INR 604.50, USD 85.47. Synthetic only. Integration tests skip if `tesseract` is not on `PATH`.

Not covered: `_deskew` / `_preprocess` in isolation; `write_html_report`; engine `main`; Pages JS.

### 2.8 Packaging, CI, models

Working-tree `MANIFEST.in`:

```
include CONTRIBUTING.md
include LICENSE
include README.md
include SECURITY.md
include THIRD_PARTY_NOTICES.md
recursive-include docs *.css *.html *.js
recursive-include scripts *.sh
recursive-include tests *.jpg *.md *.png *.py
```

HEAD lacked `recursive-include scripts *.sh`.

**Untracked** `scripts/setup-models.sh`:

- File: `Devanagari.traineddata`
- URL pin: `tesseract-ocr/tessdata_fast` commit `87416418657359cb625c412a48b6e1d6d41c29bd`
- SHA-256: `3bbb87c1de2a6a2ef0a97dc041e6eea2723a1c22d638f5e38157a5cd441c12b7`
- Install dir: `$XDG_DATA_HOME/payable-receipt-ocr/tessdata` or `~/.local/share/payable-receipt-ocr/tessdata`
- Env: `PAYABLE_RECEIPT_OCR_TESSDATA_DIR`
- Exit 1 on checksum mismatch

**Not committed in this research task.**

Working-tree CI adds `./scripts/setup-models.sh` after installing `tesseract-ocr`. Matrix: Python 3.10 / 3.12 / 3.13; ruff; pytest; build; twine. HEAD CI had no model-install step.

`.gitignore` ignores `private-inputs/`, `output/`, and `*.traineddata`. Local directories `private-inputs/`, `private-models/`, and `output/` exist on disk. `private-models/` is not a directory ignore; only `*.traineddata` files are ignored.

### 2.9 Documented scope and production bar

In scope (HEAD `README.md`): JPG/JPEG/PNG/WebP; English digital receipts and Indian grocery/delivery screenshots; INR/USD/EUR/GBP; payable-total suggestion only.

Out of scope: PDFs, HEIC, handwriting, multipage, reliable line items, merchant/date, storage, auth, HTTP server.

Holdout gate (HEAD `README.md` Project status): exploratory 35/35 is not an independent benchmark. Production stays unproven until a frozen authorized holdout of ≥30 unseen screenshots (10 per supported app) hits:

```text
exact total + currency ≥ 90%
AND false-strong results = 0
AND confirmation required = 100%
```

First release is `0.1.0a1`, not `1.0`. `docs/pipeline-report.html` repeats the exploratory 35/35 / zero false-strong / confirmation 35/35 / blocked formal gate story.

Visual site files (`git ls-tree HEAD`): `docs/index.html`, `docs/learning-lab.html`, `docs/pipeline-report.html`, `docs/stack-map.html`, `docs/assets/styles.css`, `docs/assets/learning-lab.js`. README links match those names.

HEAD README treated Devanagari as **optional** (six English passes without it). Working-tree README makes it **required for INR** and documents `ConfigurationError` fail-closed.

### 2.10 Uncommitted work (not committed)

`git status` 2026-08-24:

- Modified: `.github/workflows/ci.yml`, `CONTRIBUTING.md`, `MANIFEST.in`, `README.md`, `THIRD_PARTY_NOTICES.md`, `src/payable_receipt_ocr/_engine.py`, `tests/test_public_interface.py`
- Untracked: `scripts/setup-models.sh` (and this `notes/` file)

Substance: INR requires Devanagari or `ConfigurationError`; XDG data-dir discovery; Devanagari pass only for `INR`/`UNKNOWN` when a model exists; weaker-INR warning removed; docs/CI/MANIFEST treat the checksummed model as required for INR; test imports `_engine`. `models.py` is not in the diff.

### 2.11 Git and GitHub

| Fact | Source |
| --- | --- |
| Remote | `git remote -v`: `git@github.com:FireBird1998/payable-receipt-ocr.git` |
| `main` | `fed7425` tracking `origin/main` |
| Commits | `f538f40` feat: publish local receipt OCR alpha; `fed7425` ci: update official actions to Node 24 releases |
| Tag | `v0.1.0a1` → `f538f40` |
| Pages | `gh api .../pages`: `html_url` `https://firebird1998.github.io/payable-receipt-ocr/`, `source.branch` `main`, `source.path` `/docs` |
| Issues | `has_issues` true; `gh issue list --state all` empty |
| PRs | `gh pr list --state all` empty |
| Labels | GitHub defaults: `bug`, `documentation`, `duplicate`, `enhancement`, `good first issue`, `help wanted`, `invalid`, `question`, `wontfix` |

Matt Pocock triage strings from `setup-matt-pocock-skills/triage-labels.md` (`needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`) are **absent**. GitHub default `wontfix` **is** present. That is not Matt Pocock setup: there is no `docs/agents/triage-labels.md`.

No monorepo signals: no `pnpm-workspace.yaml`, no `package.json` workspaces, no `packages/*`.

**Confirmed absent** (`ls` 2026-08-24): `AGENTS.md`, `CLAUDE.md`, `CONTEXT.md`, `CONTEXT-MAP.md`, `docs/adr`, `docs/agents`, `.scratch`, `TECH-DEBT.md`, `TEST-STRATEGY.md`, `ARCHITECTURE.md`.

---

## 3. Matt Pocock implementation audit

“Implemented” means **this git tree contains the files those skills expect**. A plugin on a laptop does not count.

Explore list from `setup-matt-pocock-skills/SKILL.md`: remotes; `AGENTS.md` / `CLAUDE.md` and `## Agent skills`; `CONTEXT.md` / `CONTEXT-MAP.md`; `docs/adr/`; `docs/agents/`; `.scratch/`; whether `triage` is installed; monorepo signals.

`triage` **is** present in the 1.2.3 pack (`engineering/triage/SKILL.md`). If setup were run, Section B (labels) would apply. It has not been run.

`setup-matt-pocock-skills` is `disable-model-invocation: true`. It must be user-invoked and confirm-with-user. This research session did not run it.

### Artifact table

| Artifact | Expected by | In this repo? |
| --- | --- | --- |
| `AGENTS.md` or `CLAUDE.md` with `## Agent skills` | setup-matt-pocock-skills; writing-for-agents | **Absent** |
| `CONTEXT.md` | setup `domain.md`; domain-modeling `CONTEXT-FORMAT.md` | **Absent** |
| `CONTEXT-MAP.md` | setup / domain-modeling (multi-context) | **Absent** (appropriate for one package) |
| `docs/adr/` | domain-modeling ADR format; setup `domain.md` | **Absent** |
| `docs/agents/issue-tracker.md` | setup; to-tickets; to-spec; triage | **Absent** |
| `docs/agents/domain.md` | setup `domain.md` | **Absent** |
| `docs/agents/triage-labels.md` | setup if triage installed | **Absent** |
| `.scratch/` | setup explore; to-tickets local-markdown mode | **Absent** |
| Labels `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human` | `triage-labels.md` | **Absent** |
| `TECH-DEBT.md` / `TEST-STRATEGY.md` / `ARCHITECTURE.md` | not named in the 1.2.3 Matt Pocock pack | **Absent** |

**Verdict: no.** Not a partial install missing one file. Zero setup artifacts. GitHub’s default `wontfix` is not a substitute for `docs/agents/triage-labels.md`.

---

## 4. Implicit alignment (ideas without scaffolding)

Codebase-design glossary (`engineering/codebase-design/SKILL.md`): **module**, **interface**, **implementation**, **depth**, **seam**, **adapter**.

**`recognize()` is deep at the package seam.** Callers learn one function, a frozen result, and a handful of errors. Behind that: deskew, two variants, up to 12 Tesseract passes, row reconstruction, label ranking, arithmetic checks, evidence grading. Deletion test: remove `recognize` / `process_receipt` and that complexity returns to every caller.

**`_engine.py` is not deep internally.** Depth is leverage at an interface, not line count. One file mixes OpenCV/Tesseract, ranking policy, evidence policy, HTML reporting, JSON file output, and a second CLI. Prototype skill: throwaway code must be marked and not mistaken for production. `write_html_report` still says “throwaway prototype” in the same module `api.py` calls for production recognition.

**Tests vs TDD seams.** TDD: tests live at seams, never against internals. HEAD tests mostly use `recognize` / `RecognitionResult` / `python -m`. The uncommitted INR test monkeypatches `_engine._require_tesseract` and `_engine._model_directory`. TDD would refuse that unless the maintainer pre-agreed an internal seam. `pass_count == 12 if INR else 6` couples tests to pass combinatorics.

**Domain language without a glossary.** Load-bearing terms already in README/code/HTML: payable total vs fallback; payment label vs fallback label; evidence grade `strong`/`review`/`none`; confirmation vs write permission; diagnostics default-off; INR Devanagari requirement (WIP). `CONTEXT-FORMAT.md` wants those terms, opinionated, with avoid-lists — and forbids implementation details. There is no `CONTEXT.md`.

**Single-context.** No `CONTEXT-MAP.md`, no workspace files. Setup default: single-context. Matches the tree.

---

## 5. Gaps that will bite on the next large slice of work

1. **No agent-facing map.** Without `AGENTS.md`/`CLAUDE.md` and `CONTEXT.md`, every session re-derives confirmation-is-not-authorization.
2. **`_engine.py` locality.** Ranking, INR model policy, HTML, and prototype CLI share one file. Splitting without an agreed seam will scatter tests that already reach `_engine` in the WIP.
3. **Dual CLI.** `payable-receipt-ocr` → compact JSON, controlled errors. `_engine.main` → full OCR dump and prototype HTML.
4. **Test seam not agreed.** HEAD is close to public-interface TDD. The WIP INR test trains the next change to patch private helpers.
5. **Holdout is a gate with no artifact.** README and `docs/pipeline-report.html` block production on a private ≥30-image holdout. The repo has three synthetic fixtures. No ADR records why 35/35 exploratory cannot be the gate.
6. **INR fail-closed is half-landed.** Working tree + untracked script + CI step; not on `origin/main`. Published alpha still follows HEAD’s warn-and-continue Devanagari behavior.
7. **Tracker is empty.** `to-tickets` / `to-spec` / `triage` have nowhere to publish. Issues are enabled but unused.
8. **`docs/` is a public site.** Default ADR path `docs/adr/` would be served by Pages. Raise that during setup. Do not invent a substitute path in this note.

---

## 6. Recommended next skill sequence

Recommendations only. Not approval. **Do not run setup until the maintainer confirms tracker and `AGENTS.md` vs `CLAUDE.md`.**

### Already useful with no setup

| Skill | Why |
| --- | --- |
| **research** | This file. No `docs/agents/` required |
| **tdd** | Tests at agreed seams; reads `CONTEXT.md` if present |
| **codebase-design** | Vocabulary reference, not a write session |
| **diagnosing-bugs** | Same optional `CONTEXT.md` habit |
| **prototype** | Throwaway HTML to answer a question; leftover already in `_engine` |
| **code-review** (Standards axis) | `CONTRIBUTING.md` + Fowler baseline; Spec axis wants an issue/spec |

### Needs setup first

`to-tickets`, `to-spec`, `triage`, `implement` (tickets), `wayfinder`, and code-review’s spec axis all say: run `/setup-matt-pocock-skills` if tracker config is missing.

`domain-modeling` creates `CONTEXT.md` / ADRs lazily. `improve-codebase-architecture` is runnable without them and blinder.

### Suggested order (not executed)

1. **`setup-matt-pocock-skills`** — confirm-with-user. Present findings, ask, then write.
2. **`domain-modeling`** — lock confirmation field name, `recognize` spelling, evidence grades, payment vs fallback, INR fail-closed. Write `CONTEXT.md`. Offer ADRs only when hard-to-reverse + surprising + real trade-off (checksum pin; dual CLI; holdout gate; Pages vs ADR path).
3. **`codebase-design` / `improve-codebase-architecture`** — `_engine.py` mixed concerns as the deepening candidate; agree the test seam before extracting modules.
4. **`tdd` at the agreed seam** — default: public `recognize` / CLI JSON. Internal `_engine` patches only if the maintainer explicitly agrees a second seam.

### Tracker / layout recommendation (not a decision)

Setup default: if `git remote` is GitHub, propose GitHub Issues. This remote is GitHub; `pyproject.toml` already lists an Issues URL; `has_issues` is true.

**Recommendation:** **single-context** (one package) **and GitHub Issues**, *if* the maintainer wants `gh issue create`. **Also consistent with the evidence:** local markdown under `.scratch/` — solo tree, **zero** issues and PRs, two commits. Setup should ask.

**Triage labels:** if setup runs, keep the five defaults. Do not treat GitHub’s existing `wontfix` as already-configured Matt Pocock vocabulary without writing `docs/agents/triage-labels.md`.

**Pages:** default `docs/adr/` is public on this repo. Raise that during setup.

---

## 7. Sources

### Repository

- `src/payable_receipt_ocr/__init__.py`, `api.py`, `models.py`, `errors.py`, `cli.py`, `__main__.py`, `_engine.py`
- `tests/test_public_interface.py`, `tests/fixtures/README.md`
- `pyproject.toml`, `MANIFEST.in`, `.github/workflows/ci.yml`, `scripts/setup-models.sh` (untracked)
- `README.md`, `CONTRIBUTING.md`, `SECURITY.md`, `THIRD_PARTY_NOTICES.md`, `LICENSE`, `.gitignore`
- `docs/index.html`, `docs/pipeline-report.html`, `docs/stack-map.html`, `docs/learning-lab.html`
- `git log`, `git status`, `git diff`, `git ls-tree HEAD`, `git show HEAD:...`, `git remote -v`, tag `v0.1.0a1`
- `gh api repos/FireBird1998/payable-receipt-ocr` and `.../pages`
- `gh issue list --state all`, `gh pr list --state all`, `gh label list`

### Matt Pocock skills (1.2.3)

Directory: `/Users/ankitdas/.claude/plugins/cache/claude-plugins-official/mattpocock-skills/1.2.3/skills/`

- `engineering/setup-matt-pocock-skills/SKILL.md`, `domain.md`, `triage-labels.md`, `issue-tracker-github.md`
- `engineering/README.md`, `engineering/research/SKILL.md`
- `engineering/domain-modeling/SKILL.md`, `CONTEXT-FORMAT.md`, `ADR-FORMAT.md`
- `engineering/codebase-design/SKILL.md`
- `engineering/tdd/SKILL.md`
- `engineering/improve-codebase-architecture/SKILL.md`
- `engineering/to-tickets/SKILL.md`, `to-spec/SKILL.md`, `triage/SKILL.md`
- `engineering/prototype/SKILL.md`, `diagnosing-bugs/SKILL.md`, `code-review/SKILL.md`, `implement/SKILL.md`
- `productivity/writing-for-agents/SKILL.md`
