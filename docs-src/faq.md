# FAQ

## Does kogo send my PDFs anywhere?

No. All processing happens locally, whether you use the CLI, the library, or
the self-hosted web app. The [hosted demo](https://kogo-demo.tatu-sec.dev/) is
a convenience deployment of the same open-source code — self-host if you'd
rather not use it.

## Can kogo diff scanned PDFs with no text layer?

Not at word precision — scan-only PDFs are compared visually (figures,
layout) since there's no embedded text to extract. Add an OCR text layer
first (e.g. with `ocrmypdf`) if you need word-level text diffs. OCR support
built into kogo itself is tracked on
[ROADMAP.md](https://github.com/ta-061/kogo/blob/main/ROADMAP.md).

## Does kogo handle password-protected PDFs?

No — remove the password first. `compare_pdfs` raises `ComparisonError` for
this (and other user-facing problems: corrupted, empty, or oversized files).

## Why is a moved paragraph reported as delete + add instead of "moved"?

Exact-line matching (see [How it works](architecture.md#text-diff)) already
suppresses this for *unchanged* text that moved. A paragraph that was both
edited and moved doesn't have a byte-identical line to match against, so it's
currently reported as a delete in the old position and an add in the new one.
Dedicated moved-text detection is tracked on
[ROADMAP.md](https://github.com/ta-061/kogo/blob/main/ROADMAP.md).

## How do I use kogo without writing the marked PDFs?

`kogo.compare_pdfs(..., artifacts=False)` — see the
[CI integration recipe](recipes/ci-integration.md).

## Where do I report a bug or request a feature?

[GitHub Issues](https://github.com/ta-061/kogo/issues) using the bug report
or feature request template. For general questions, use
[Discussions](https://github.com/ta-061/kogo/discussions) instead. For
security vulnerabilities, see [SECURITY.md](https://github.com/ta-061/kogo/blob/main/SECURITY.md)
— please don't file a public issue.
