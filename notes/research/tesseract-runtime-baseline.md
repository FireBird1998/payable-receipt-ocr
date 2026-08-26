# Research: reproducible Tesseract runtime baseline

**Issue:** [#6 — Research the reproducible Tesseract runtime baseline][R1]  
**Parent:** [#1 — Wayfinder: production-grade payable receipt recognition pipeline][R2]  
**Researched:** 2026-08-26  
**Scope:** Public package specification only. Linux CPU is the production reference; macOS is a
development environment. OCR remains local and every result still requires human confirmation.

## Answer

The supported runtime cannot be expressed as “Tesseract is installed” or even as a Tesseract
major-version range. It must be an explicitly validated **runtime tuple**:

1. Linux distribution/image and CPU architecture;
2. exact Tesseract executable build/package;
3. the executable's Leptonica and image-library environment;
4. exact `eng.traineddata` and `Devanagari.traineddata` bytes;
5. exact OCR parameters and relevant environment settings; and
6. the Python/pytesseract and preprocessing dependency lock.

Model-format compatibility is broader than behavioral compatibility. Official `tessdata_fast`
models work with the LSTM engine in Tesseract 4 and 5 and require OEM 1, but official documentation
and release notes demonstrate that OCR output can change with language order, thresholding defaults,
colormap handling, and other engine fixes. There is no upstream guarantee of identical OCR text,
boxes, or confidences across Tesseract releases, OS packages, architectures, or dependency builds.
[S1][S2][S12][S13][S14]

The proposed Devanagari download is an authentic, byte-reproducible artifact and its stated SHA-256
is correct. It is **not a 2024 model version**: commit
`87416418657359cb625c412a48b6e1d6d41c29bd` changed only the README. The model payload is the older
Google-trained `4.00.00alpha:Devanagari:synth20170629` model, with a configuration update in
February 2018 and a path-only move in March 2018. The same model blob is present at the
`tessdata_fast` `4.1.0` tag, at the evaluated 2024 commit, on current `main`, and inside Ubuntu
24.04's `tesseract-ocr-script-deva` `1:4.1.0-2` package.
[S3][S4][S5][S6][S7][S19][S32]

That makes the proposal technically suitable as a **candidate**, not a quality decision. Official
sources cannot establish whether this script model is the best model for the three supported receipt
populations. The private holdout must decide that. Because the pipeline also performs English
passes, pinning only Devanagari is insufficient: the English model must also be identified and
verified.

## Verified facts

### 1. Engine and traineddata are independently versioned

- Upstream's current stable release on the research date is Tesseract **5.5.3**, published
  2026-07-24. Its release includes fixes for memory-safety issues in `.traineddata` deserialization
  and integer overflow in LSTM deserialization. [S15]
- Ubuntu 22.04 LTS supplies `tesseract-ocr` **4.1.1-2.1build1**; Ubuntu 24.04 LTS supplies
  **5.3.4-1build5**. An unqualified `apt install tesseract-ocr` therefore does not select the same
  engine across Linux releases. [S16][S17]
- Ubuntu 24.04 independently supplies both `tesseract-ocr-eng` and
  `tesseract-ocr-script-deva` as **1:4.1.0-2**. Both install under
  `/usr/share/tesseract-ocr/5/tessdata/`; the Devanagari package is not a dependency of the engine
  package and must be installed or supplied separately. [S17][S18][S19][S20]
- Tesseract's installation documentation describes the engine and traineddata as two installation
  parts and documents the Debian/Ubuntu script package naming convention
  `tesseract-ocr-script-deva`. [S8]
- Therefore “Tesseract 5.3.4” alone does not identify the recognition runtime. Engine package,
  English model, script model, and their bytes are separate baseline fields.

### 2. What the proposed model actually is

Evaluated artifact:

```text
repository: tesseract-ocr/tessdata_fast
path:       script/Devanagari.traineddata
commit:     87416418657359cb625c412a48b6e1d6d41c29bd
Git blob:   3c33bd676b0ae7a480ec1c1f5ebdd13513aa5433
size:       17,943,870 bytes
SHA-256:    3bbb87c1de2a6a2ef0a97dc041e6eea2723a1c22d638f5e38157a5cd441c12b7
embedded:   4.00.00alpha:Devanagari:synth20170629
```

The SHA-256 was independently recomputed from the upstream raw artifact. `combine_tessdata -d`
shows an LSTM network, punctuation/word/number DAWGs, unicharset, recoder, configuration, and the
embedded version above.

Official repository facts:

- `tessdata_fast` is an integerized speed/accuracy compromise. It supports only the LSTM engine in
  Tesseract 4 and 5; OEM 0 and 2 are unsupported. [S1][S2]
- The Devanagari script model covers `hin+san+mar+nep+eng`; script models are distinct from
  single-language models such as `hin`. [S1]
- Official command examples invoke the repository-layout model as `-l script/Devanagari` and state
  that it supports the Devanagari-script languages and English. A flat custom tessdata directory
  can expose the same file as `Devanagari.traineddata`. [S12]
- Commit `874164...` changed one README line to mention Tesseract 5; it did not change the model.
  [S3]
- The model was updated in `4e7c9ce...` to add configuration addressing auto-PSM issue 1273, then
  moved unchanged into `script/` by `9f875fb...`. [S4][S5]
- The upstream blob is identical at tag `4.1.0`, the proposed commit, and current `main`. Artifact
  inspection also found the same SHA-256 inside Ubuntu 24.04 package
  `tesseract-ocr-script-deva_4.1.0-2_all.deb`; the package download itself has Canonical-published
  SHA-256 `553ec9dec86c2a899a948a1593db0cd3928d1ca2b23b2f751058d2b0e1adc2ea`.
  [S6][S19][S21][S32]
- The matching upstream `tessdata_fast` English model has SHA-256
  `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`. That is also the checksum
  pinned by the current Homebrew formula and was independently found inside Ubuntu 24.04 package
  `tesseract-ocr-eng_4.1.0-2_all.deb`. [S11][S20][S22][S33]

The commit pin plus SHA-256 is useful defense in depth, but the SHA-256 is the direct identity of
the downloaded bytes. Documentation must not describe the commit date as the model's training or
release date.

### 3. pytesseract does not install or pin Tesseract

`pytesseract` 0.3.13 is a wrapper around a separately installed executable. Its default command is
the string `tesseract`; callers may set an absolute `tesseract_cmd`, pass arbitrary configuration
including `--tessdata-dir`, query the executable version, and terminate a subprocess on timeout.
Each OCR call starts a Tesseract subprocess. [S9][S10]

Consequences:

- Pinning `pytesseract` does not pin the engine or models.
- `PATH` is part of executable selection unless the package resolves and validates an absolute
  command.
- `pytesseract.get_tesseract_version()` is useful validation but does not identify traineddata.
- The upstream FAQ's adaptive-classifier warning concerns reuse of the same `TessBaseAPI` object
  across images. A fresh subprocess per pytesseract call does not preserve that API object between
  passes. [S10][S23]

### 4. OCR output is versioned behavior, not a stable serialization

Verified examples of output-affecting inputs and changes:

- Tesseract's official command documentation says both runtime and output can differ when the order
  of multiple languages changes. [S12]
- Tesseract 5.2.0 added `invert_threshold` and changed its default from `0.5` to `0.7`. [S13]
- Tesseract 5.3.0 changed thresholding behavior by removing colormaps before thresholding. [S14]
- Tesseract 5.5.1 fixed colormap handling and a Sauvola binarization error. [S24]
- Tesseract uses Leptonica for internal image processing; its quality guide states that
  binarization, rescaling, deskewing, transparency handling, dictionaries, and PSM selection affect
  accuracy. [S25]
- The FAQ documents adaptive-classifier state as a cause of inconsistent results when one API object
  is reused for multiple images, and documents `OMP_THREAD_LIMIT` as the control for Tesseract's CPU
  thread count. [S23]

No primary source found promises bit-for-bit or OCR-equivalent output across engine patch releases,
Linux distributions, macOS and Linux, CPU architectures, compiler optimizations, or Leptonica
versions. That absence must be treated as an unknown, not converted into a claim that every repeated
run is nondeterministic.

What is realistically reproducible:

- source/model/package bytes when identified by digest;
- apt package availability at an Ubuntu archive snapshot, while that snapshot is retained;
- the declared CLI flags, environment, Python lock, and preprocessing code;
- results observed repeatedly on an immutable reference environment.

What cannot be promised from version metadata alone:

- equivalent text, boxes, confidences, candidate ranking, or latency on a different tuple;
- Linux/macOS output parity;
- future availability of an upstream URL or Ubuntu snapshot forever;
- holdout accuracy or resource behavior without measurement.

### 5. Linux packaging and CI

The uncommitted CI proposal uses `ubuntu-latest`, runs an unqualified
`apt-get install tesseract-ocr`, and checksum-pins only Devanagari. That is useful ordinary CI, but
it is not a reproducible OCR baseline:

- GitHub currently maps `ubuntu-latest` to Ubuntu 24.04, but `-latest` migrates to newer GA images,
  GA images update weekly, and even explicit OS-version runner images receive weekly software
  updates. [S26][S27]
- APT supports exact `package=version` selection. Ubuntu's snapshot service can select the archive
  as of a UTC timestamp and explicitly lists reproducible deployments as a use case. Snapshot
  retention is promised for at least two years, not indefinitely. [S28][S29]
- Ubuntu 24.04's engine, English model, and Devanagari model are separate package versions and
  therefore all need selection/provenance. [S17][S19][S20]

An explicit `ubuntu-24.04` label improves OS-family stability but does not freeze the VM image or apt
archive. Exact apt versions improve package selection but still require those versions and
dependencies to remain available. An Ubuntu snapshot fixes the archive view for its retention
window. A digest-addressed runtime image or internally retained signed package set can preserve
artifacts longer. The downstream provisioning ticket must choose among these mechanisms.

At startup or in a release-gate job, the eventual implementation should fail closed on a baseline
mismatch and record at least:

- OS release and architecture;
- full `tesseract --version` output, not only `5.x`;
- engine and model package versions when packages are used;
- SHA-256 for both `eng.traineddata` and `Devanagari.traineddata`;
- model discovery from the actual configured tessdata directory;
- exact OCR flags (`--oem`, PSMs, config values) and relevant environment such as the selected
  OpenMP thread limit;
- Python lock/environment and package version.

### 6. macOS development compatibility

Official Tesseract and pytesseract documentation supports installation with
`brew install tesseract`. [S8][S9] As of the research date, Homebrew's formula:

- installs Tesseract 5.5.3;
- has separate, moving dependencies including Leptonica;
- supplies only `eng`, `osd`, and `snum`;
- pins its `eng.traineddata` to `tessdata_fast` tag `4.1.0` with SHA-256
  `7d4322bd...`; and
- directs users who need other models to install `tesseract-lang`. [S11]

Therefore macOS can be a supported development environment for installation, smoke tests, and local
iteration, but native Homebrew output must not define production golden results or satisfy the Linux
quality/latency gate. A Homebrew upgrade may change the engine and dependencies even when this Python
package is unchanged. Developers should be shown their active executable version and model hashes;
Linux-parity evaluation must run the selected Linux reference environment.

### 7. Licensing and distribution

- Tesseract is Apache-2.0 licensed. [S8][S30]
- `tessdata_fast` states that all repository data is Apache-2.0 licensed. [S1][S31]
- pytesseract 0.3.13 is Apache-2.0 licensed. [S9]
- Apache-2.0 section 4 requires recipients of redistributed copies or derivatives to receive the
  license, modified files to be marked, relevant notices to be retained, and any upstream NOTICE
  attribution to be carried when a NOTICE exists. It does not relicense this package's own MIT code.
  [S31]

The current download-at-setup proposal distributes a locator and checksum, not model bytes inside
the Python distribution. If a later wheel, container, cache, appliance, or mirror redistributes the
traineddata, that artifact must carry the applicable Apache-2.0 materials. The exact delivery mode
and third-party-notice packaging belong to the provisioning/distribution ticket; this is not legal
advice.

## Recommendations for the public specification

These are recommendations derived from the facts, not upstream guarantees.

1. **Support Tesseract 5 only for the production baseline.** Tesseract 4 can read the candidate
   model, but including Ubuntu 22.04's 4.1.1 engine would create a second behavior family requiring
   its own corpus and latency validation.
2. **Name one exact validated Linux tuple per package release.** Do not claim support for all
   Tesseract 5.x versions from format compatibility.
3. **Treat every engine, model, preprocessing-library, OCR-flag, or architecture change as an OCR
   behavior change.** Re-run synthetic integration tests and the authorized frozen holdout before
   promoting the new tuple.
4. **Keep the proposed Devanagari artifact as a candidate with its current SHA-256, but describe it
   accurately as the long-lived 2017/2018 `tessdata_fast` script model.** Corpus evidence, not its
   2024 README commit, must approve it.
5. **Pin and verify English too.** If the matching official `tessdata_fast` 4.1.0 English artifact is
   selected, its candidate SHA-256 is
   `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`.
6. **Require OEM 1** with these `tessdata_fast` models and keep PSM/config values in the baseline.
7. **Separate native macOS compatibility from Linux conformance.** Native Homebrew is allowed for
   development; only the reference Linux tuple can produce release-gate evidence.
8. **Make baseline drift visible and fail closed in conformance jobs.** Emit provenance and reject
   missing/wrong executable versions or model hashes rather than silently using system defaults.
9. **Do not call `ubuntu-latest` plus unversioned apt reproducible.** A conformance job needs an
   explicit OS/architecture and either an apt snapshot with exact versions or an immutable,
   digest-addressed equivalent chosen by provisioning.
10. **Version the baseline as data.** Store the selected tuple in one machine-readable manifest that
    CI, diagnostics, and deployment validation consume; do not duplicate versions across prose and
    scripts.

## Unknowns and downstream decisions

This research does **not** decide:

- whether production should use Ubuntu 24.04's maintained `5.3.4-1build5`, build/package upstream
  5.5.3, or use another immutable Tesseract 5 artifact;
- whether the 5.5.3 deserialization fixes have been backported to the chosen distribution package;
- x86-64 versus ARM64, compiler/SIMD policy, OpenMP thread limit, process concurrency, memory budget,
  and timeout values—the resource-envelope ticket must decide and measure these;
- whether `Devanagari`, `hin`, or another authorized model/pass strategy performs best on Blinkit,
  Swiggy, and Zepto INR receipts—the frozen holdout must decide;
- whether model bytes are downloaded, installed from OS packages, mirrored, or embedded, and how
  long artifacts must remain recoverable—the provisioning/distribution ticket must decide;
- whether repeated runs on the eventual fixed tuple are empirically identical. Add a repeat-run
  probe to baseline qualification rather than assuming either determinism or nondeterminism.

## Acceptance constraints for downstream tickets

A downstream provisioning proposal is incomplete unless it supplies:

- one exact Linux OS/image/architecture identity;
- exact Tesseract and traineddata identities for both English and Devanagari;
- a retained and checksum-verified installation path;
- a startup/CI verification procedure;
- an upgrade and holdout requalification procedure;
- macOS instructions explicitly labeled development-compatible rather than production-equivalent;
- Apache-2.0 handling for every redistributed Tesseract/model artifact; and
- a handoff to the resource-envelope ticket for threading, timeout, latency, and concurrency.

## Proposed resolution comment for issue #6

> Resolved by `notes/research/tesseract-runtime-baseline.md`.
>
> The key constraint is that Tesseract compatibility is not OCR-output equivalence. Production must
> validate and pin a complete Linux runtime tuple: OS/image and architecture, exact engine build,
> Leptonica/runtime environment, both English and Devanagari model bytes, OCR flags, and the Python
> lock. `ubuntu-latest` plus unversioned apt is not reproducible; native Homebrew is development
> compatible but not production-conformant.
>
> The proposed Devanagari SHA-256
> `3bbb87c1de2a6a2ef0a97dc041e6eea2723a1c22d638f5e38157a5cd441c12b7` is verified and matches
> upstream `tessdata_fast` 4.1.0/current main and Ubuntu 24.04's script package. However,
> `874164...` is a 2024 README-only commit, not a new model release; the payload is the 2017/2018
> LSTM model. Keep it as a candidate until holdout evidence approves it, and pin the English model
> too.
>
> Provisioning must next choose the exact Tesseract 5 artifact and retention mechanism, while the
> resource-envelope ticket chooses architecture/threading/timeouts. Any engine, model, library,
> flag, or architecture change requires Linux holdout requalification. OCR remains fully local and
> every result remains confirmation-required.

## Primary sources

### Tesseract and tessdata

- [S1 — `tessdata_fast` README at the evaluated commit](https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/87416418657359cb625c412a48b6e1d6d41c29bd/README.md)
- [S2 — Tesseract data-file compatibility documentation](https://tesseract-ocr.github.io/tessdoc/Data-Files.html)
- [S3 — evaluated commit `874164...`](https://github.com/tesseract-ocr/tessdata_fast/commit/87416418657359cb625c412a48b6e1d6d41c29bd)
- [S4 — Devanagari configuration update `4e7c9ce...`](https://github.com/tesseract-ocr/tessdata_fast/commit/4e7c9ce934584e30654178261986ca1a03ffcfe8)
- [S5 — script-directory move `9f875fb...`](https://github.com/tesseract-ocr/tessdata_fast/commit/9f875fb8194767ea22a0018072ba8d3ebf3939cc)
- [S6 — Devanagari artifact at `tessdata_fast` 4.1.0](https://github.com/tesseract-ocr/tessdata_fast/blob/4.1.0/script/Devanagari.traineddata)
- [S7 — proposed raw Devanagari artifact](https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/87416418657359cb625c412a48b6e1d6d41c29bd/script/Devanagari.traineddata)
- [S8 — official Tesseract installation documentation](https://tesseract-ocr.github.io/tessdoc/Installation.html)
- [S12 — official command-line usage](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html)
- [S13 — Tesseract 5.2.0 release](https://github.com/tesseract-ocr/tesseract/releases/tag/5.2.0)
- [S14 — Tesseract 5.3.0 release](https://github.com/tesseract-ocr/tesseract/releases/tag/5.3.0)
- [S15 — Tesseract 5.5.3 release](https://github.com/tesseract-ocr/tesseract/releases/tag/5.5.3)
- [S23 — official Tesseract FAQ](https://tesseract-ocr.github.io/tessdoc/FAQ.html)
- [S24 — Tesseract 5.5.1 release](https://github.com/tesseract-ocr/tesseract/releases/tag/5.5.1)
- [S25 — official quality guide](https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html)
- [S30 — Tesseract 5.5.3 license](https://raw.githubusercontent.com/tesseract-ocr/tesseract/5.5.3/LICENSE)
- [S31 — `tessdata_fast` license at the evaluated commit](https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/87416418657359cb625c412a48b6e1d6d41c29bd/LICENSE)
- [S32 — current-main Devanagari artifact](https://github.com/tesseract-ocr/tessdata_fast/blob/main/script/Devanagari.traineddata)
- [S33 — matching English artifact at the evaluated commit](https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/87416418657359cb625c412a48b6e1d6d41c29bd/eng.traineddata)

### pytesseract

- [S9 — pytesseract 0.3.13 README](https://raw.githubusercontent.com/madmaze/pytesseract/v0.3.13/README.rst)
- [S10 — pytesseract 0.3.13 executable wrapper source](https://raw.githubusercontent.com/madmaze/pytesseract/v0.3.13/pytesseract/pytesseract.py)

### First-party packaging and CI records

- [S11 — Homebrew Tesseract formula at inspected revision](https://raw.githubusercontent.com/Homebrew/homebrew-core/f1f97135a8594081ff489c1abf2898e640193ad2/Formula/t/tesseract.rb)
- [S16 — Ubuntu 22.04 `tesseract-ocr`](https://packages.ubuntu.com/jammy/tesseract-ocr)
- [S17 — Ubuntu 24.04 `tesseract-ocr`](https://packages.ubuntu.com/noble/tesseract-ocr)
- [S18 — Ubuntu 24.04 `libtesseract5`](https://packages.ubuntu.com/noble/amd64/libtesseract5)
- [S19 — Ubuntu 24.04 Devanagari package](https://packages.ubuntu.com/noble/all/tesseract-ocr-script-deva)
- [S20 — Ubuntu 24.04 English package](https://packages.ubuntu.com/noble/all/tesseract-ocr-eng)
- [S21 — Canonical download record and checksum for the Devanagari package](https://packages.ubuntu.com/noble/all/tesseract-ocr-script-deva/download)
- [S22 — Canonical download record and checksum for the English package](https://packages.ubuntu.com/noble/all/tesseract-ocr-eng/download)
- [S26 — GitHub-hosted runner reference](https://docs.github.com/en/actions/reference/runners/github-hosted-runners)
- [S27 — GitHub runner-image release/update policy](https://raw.githubusercontent.com/actions/runner-images/main/README.md)
- [S28 — Ubuntu Noble `apt-get` manual](https://manpages.ubuntu.com/manpages/noble/en/man8/apt-get.8.html)
- [S29 — Ubuntu Snapshot Service](https://snapshot.ubuntu.com/)

### Repository tickets

- [R1 — research issue #6](https://github.com/FireBird1998/payable-receipt-ocr/issues/6)
- [R2 — parent Wayfinder issue #1](https://github.com/FireBird1998/payable-receipt-ocr/issues/1)

[S1]: https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/87416418657359cb625c412a48b6e1d6d41c29bd/README.md
[S2]: https://tesseract-ocr.github.io/tessdoc/Data-Files.html
[S3]: https://github.com/tesseract-ocr/tessdata_fast/commit/87416418657359cb625c412a48b6e1d6d41c29bd
[S4]: https://github.com/tesseract-ocr/tessdata_fast/commit/4e7c9ce934584e30654178261986ca1a03ffcfe8
[S5]: https://github.com/tesseract-ocr/tessdata_fast/commit/9f875fb8194767ea22a0018072ba8d3ebf3939cc
[S6]: https://github.com/tesseract-ocr/tessdata_fast/blob/4.1.0/script/Devanagari.traineddata
[S7]: https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/87416418657359cb625c412a48b6e1d6d41c29bd/script/Devanagari.traineddata
[S8]: https://tesseract-ocr.github.io/tessdoc/Installation.html
[S9]: https://raw.githubusercontent.com/madmaze/pytesseract/v0.3.13/README.rst
[S10]: https://raw.githubusercontent.com/madmaze/pytesseract/v0.3.13/pytesseract/pytesseract.py
[S11]: https://raw.githubusercontent.com/Homebrew/homebrew-core/f1f97135a8594081ff489c1abf2898e640193ad2/Formula/t/tesseract.rb
[S12]: https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html
[S13]: https://github.com/tesseract-ocr/tesseract/releases/tag/5.2.0
[S14]: https://github.com/tesseract-ocr/tesseract/releases/tag/5.3.0
[S15]: https://github.com/tesseract-ocr/tesseract/releases/tag/5.5.3
[S16]: https://packages.ubuntu.com/jammy/tesseract-ocr
[S17]: https://packages.ubuntu.com/noble/tesseract-ocr
[S18]: https://packages.ubuntu.com/noble/amd64/libtesseract5
[S19]: https://packages.ubuntu.com/noble/all/tesseract-ocr-script-deva
[S20]: https://packages.ubuntu.com/noble/all/tesseract-ocr-eng
[S21]: https://packages.ubuntu.com/noble/all/tesseract-ocr-script-deva/download
[S22]: https://packages.ubuntu.com/noble/all/tesseract-ocr-eng/download
[S23]: https://tesseract-ocr.github.io/tessdoc/FAQ.html
[S24]: https://github.com/tesseract-ocr/tesseract/releases/tag/5.5.1
[S25]: https://tesseract-ocr.github.io/tessdoc/ImproveQuality.html
[S26]: https://docs.github.com/en/actions/reference/runners/github-hosted-runners
[S27]: https://raw.githubusercontent.com/actions/runner-images/main/README.md
[S28]: https://manpages.ubuntu.com/manpages/noble/en/man8/apt-get.8.html
[S29]: https://snapshot.ubuntu.com/
[S30]: https://raw.githubusercontent.com/tesseract-ocr/tesseract/5.5.3/LICENSE
[S31]: https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/87416418657359cb625c412a48b6e1d6d41c29bd/LICENSE
[S32]: https://github.com/tesseract-ocr/tessdata_fast/blob/main/script/Devanagari.traineddata
[S33]: https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/87416418657359cb625c412a48b6e1d6d41c29bd/eng.traineddata
[R1]: https://github.com/FireBird1998/payable-receipt-ocr/issues/6
[R2]: https://github.com/FireBird1998/payable-receipt-ocr/issues/1
