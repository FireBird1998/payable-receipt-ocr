# ADR-0008: Verification and v1 Release Gate

**Status:** Accepted

## Decision

The first stable release (`1.0`) requires all items in [docs/release/v1-gate.md](../release/v1-gate.md)
to be checked. Until that checklist is complete, the package version remains at `0.x.y` alpha.

### Test tiers

| Tier | Command | CI | What it covers |
|---|---|---|---|
| Portable unit + contract | `pytest -m 'not integration'` | Every push | Schema, error codes, contract invariants, image bounds — no Tesseract required |
| Integration | `pytest -m integration` | After `./scripts/setup-models.sh` | Public `recognize()` on synthetic fixtures with real Tesseract |
| Holdout (private) | `tools/holdout/evaluate.py` | **Not in CI** | Real-world accuracy on frozen private corpus |

The holdout evaluation is never run in public CI. It requires the private corpus, explicit consent,
and the retained reference runtime.

### What CI checks

- Lint (`ruff check`, `ruff format --check`)
- Portable tests (no Tesseract required): `pytest -m 'not integration'`
- Package build and `twine check`
- `tools/check_artifacts.py` artifact privacy scan

Integration tests run in CI only when the Tesseract executable and model files are available.

### What is currently implemented and what remains blocked

The current implementation provides:
- The full recognition pipeline and public API
- The versioned schema and contract tests
- The holdout evaluator framework and manifest schema
- The runtime baseline validation mechanism

v1 remains blocked until:

1. A frozen, authorized holdout corpus of ≥ 300 cases meets the gate (see
   [docs/release/v1-gate.md](../release/v1-gate.md)).
2. An immutable, retained instance of the reference runtime
   (`ubuntu-24.04 / amd64 / tesseract 5.3.4`) is available for the Linux conformance run.
3. The p95 latency is measured on the retained reference runtime and confirmed < 5 000 ms.
4. The memory ceiling (600 MiB candidate) is measured on the reference runtime.
5. A deterministic repeat probe confirms identical output across consecutive runs on the same image.
6. Model and runtime SHA-256 hashes are recorded in the release artifacts.
7. Portable and conformance CI passes green.
8. A privacy and security review is complete.
9. No private data appears in the public repository, artifacts, or documentation.
10. Migration notes from the old alpha schema are published and verified.

### Statistical caveat

Passing the holdout gate (≥ 95% exact on 300 cases, 0 false-strong) does not prove the true
population error rate is below 5%, nor does it guarantee zero false-strong results on unseen data.
The gate is a necessary condition for v1, not a sufficient proof of production-readiness.

## Why

Separating portable and conformance tests allows the CI pipeline to run quickly on every commit
without requiring a Linux reference machine. Keeping holdout evaluation private protects receipt
privacy and prevents the evaluation set from influencing the algorithm. Requiring an immutable
retained runtime ensures that the `conformant` signal in results is meaningful rather than
approximate.
