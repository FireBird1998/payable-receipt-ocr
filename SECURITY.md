# Security policy

## Supported version

Only the latest alpha release receives fixes while the project is below `1.0`.

## Reporting a vulnerability

Use GitHub's private vulnerability reporting for this repository. Do not open a public issue with
private receipt content, OCR text, credentials, or exploit details.

## Receipt privacy

The library performs recognition locally and does not make network requests. Callers remain
responsible for upload authentication, temporary-file deletion, resource limits, log redaction,
and retention policies. Diagnostic output can contain the complete recognized receipt text and is
disabled by default in the command-line output.
