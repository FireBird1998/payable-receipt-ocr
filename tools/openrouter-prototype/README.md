# Throwaway: direct vision LLM versus local OCR

Question: can a vision LLM extract the final INR payable from every receipt more accurately, and at an acceptable cost, than local OCR?

Each selected engine receives every selected image independently. This is not a fallback pipeline. It changes no production library behavior. Context: [cloud comparator ticket #25](https://github.com/FireBird1998/payable-receipt-ocr/issues/25). Branch: `codex/openrouter-vision-prototype`.

## Run

From the repository root, using the existing development environment:

```sh
.venv/bin/python tools/openrouter-prototype/app.py
```

Open http://127.0.0.1:8765/. Paste an OpenRouter key into the app and click **Connect key**. Do not put credentials in chat or source files. The key stays in server memory and is sent only to OpenRouter; disconnect or stop the server to discard it. No browser storage is used. An existing `OPENROUTER_API_KEY` environment variable is also supported.

Select engines and receipts, then explicitly consent to cloud transmission before **Run comparison**. **Run local OCR only** needs neither key nor cloud consent. A run is limited to 24 calls (images × engines × repetitions). The $1 default threshold covers reported session spend and stops before the next cloud call; an in-flight call can exceed it. Set a dedicated OpenRouter key credit limit for a hard account-side cap. Unknown billing stops the run; inspect OpenRouter Activity before starting another. No automatic retries or provider fallbacks are enabled.

Eight synthetic fixtures are available by default. Uploading an image adds an unlabelled observation; it does not receive an accuracy score. `--include-existing` exposes the previously collected local corpora for explicit selection, but sends nothing at startup. Only use those images after separately authorizing their transmission to OpenRouter and its model provider. The prototype has not established cloud retention/region suitability for private billing data. Provider `data_collection: deny` is a routing filter, not a zero-retention guarantee.

## Measurements and limits

- Gemini 3.1 Flash-Lite and Gemini 2.5 Flash-Lite availability/prices are read from the live OpenRouter catalogue.
- Identical prepared PNG pixels go to each selected engine: EXIF orientation is applied, RGB conversion and metadata removal occur, and resolution is preserved. Inputs are bounded to 10 MiB / 12 megapixels.
- LLM settings: temperature 0, reasoning disabled, 768 output-token limit, strict JSON schema. No local OCR output or ground truth is sent in the LLM prompt.
- Amount and currency exact matches, negative-control abstentions, request failures, all-call p50/p95 wall time, actual `usage.cost`, token counts, generation IDs, prompt hash and image hash appear in the report. Repeats increase call counts, not independent image counts.
- Scores use existing development labels, not qualified field-localization/evidence correctness. An LLM's quoted evidence is unverified. Always confirm the amount before creating an expense.
- No API fee for local OCR does **not** mean free operation. CPU/hosting costs are unmeasured. OpenRouter purchase fees, taxes and hosting are excluded from API usage figures. A running-cost verdict needs a stated deployment cost/utilization assumption and measured LLM usage.
- Errors remain in accuracy denominators; missing cloud billing is unknown, never assumed zero. Summary totals are partial when fewer than all call costs are known.
- Results/uploads live in memory; the OCR worker briefly writes its prepared image to an automatically cleaned temporary directory. Download JSON explicitly to preserve results. Real-bill reports can contain sensitive extracted text: keep them outside Git, e.g. under ignored `output/`.
- Localhost-only development server. Do not deploy it publicly.

## Live follow-up

See [the first live report](RESULTS-2026-09-28.md): eleven successful model responses, one rate-limited attempt, and an incorrect 3.1 abstention. The comparison is incomplete; there is no production replacement verdict.

## Initial smoke check (before connecting the key)

On 2026-09-28, the actual browser-to-server local OCR run matched 6/6 payable fixtures and abstained correctly on 2/2 negative controls, with 0 errors; p50 1.49 s, p95 1.78 s on the local development machine. This verifies the local flow only. No key was supplied and no LLM receipt call was made during this initial check. No comparative accuracy or cost conclusion is established.

## First-party references

- [Image input](https://openrouter.ai/docs/guides/overview/multimodal/image-understanding)
- [Structured output](https://openrouter.ai/docs/guides/features/structured-outputs)
- [Usage accounting](https://github.com/OpenRouterTeam/docs/blob/main/cookbook/administration/usage-accounting.mdx)
- [Provider routing](https://github.com/OpenRouterTeam/docs/blob/main/guides/routing/provider-selection.mdx)
- [Model catalogue](https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties)
