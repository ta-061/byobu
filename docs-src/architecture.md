# How it works

kogo's engine lives in `kogo.engine` (`src/kogo/engine/`), split by concern:
`words` (extraction), `alignment` (page pairing), `text_diff` (text
comparison), `visual_diff` (figures/layout), `annotations`, `render`
(marker baking), and `compare` (orchestration). This page describes the
algorithms, not just the module list.

## Word extraction and reading order

Text is extracted at word precision (character precision for CJK — Chinese,
Japanese, Korean — including rare kanji across CJK Extensions B–J) and
reconstructed into reading order using recursive whitespace cuts, rather than
trusting the PDF's raw internal content-stream order. This is what makes
multi-column pages and slide-style text boxes compare correctly instead of
interleaving unrelated columns into one diff.

## Page alignment

Pages are aligned across the two documents with a similarity-based sequence
alignment (`align_pages` in `alignment.py`) — a dynamic-programming edit
distance over pages, rather than assuming page *N* in the old file
corresponds to page *N* in the new file. This tolerates inserted or removed
pages without desynchronizing the rest of the comparison.

Page similarity combines two signals:

- **Text signature similarity** — a Counter-based overlap of word tokens
  (3-character shingles for CJK runs, whole tokens for Latin text)
- **Visual signature similarity** — a cosine similarity over a small
  grayscale "ink" thumbnail of the page, used when either page has very
  little extractable text (image-heavy or scanned pages), since text
  signatures alone are unreliable there

The alignment also includes a small positional bonus that favors matching
pages at similar relative positions in each document, which helps
disambiguate repeated or near-duplicate pages.

## Text diff

Rather than running `difflib` once over the whole document, text differences
are found in three stages (`text_diff.py`):

1. **Exact-line matching** — text lines that are byte-for-byte identical are
   matched first, independently of page or position. This suppresses
   unchanged columns, slide text boxes, and table cells from turning into
   delete/insert pairs merely because their extraction order shifted between
   revisions.
2. **Reading-order diff within aligned pages** — remaining text is compared
   using `difflib.SequenceMatcher` (`autojunk=False`, which matters for CJK
   text) within each aligned page pair.
3. **Document-wide reflow pass** — any text still unmatched is compared
   across page boundaries, to catch paragraphs that moved to a different
   page during reflow.

For very large, mostly-unrelated documents, `_document_text_differences`
falls back to per-page comparison instead of a single document-wide
`SequenceMatcher` call, since `SequenceMatcher` with `autojunk=False` is
worst-case quadratic; `result["settings"]["large_document_fallback"]`
reports whether this fallback was used.

Style-only changes (bold, italic, font size) on text that is otherwise
unchanged and unmoved are also detected during exact-line matching, and
reported separately from added/deleted text.

## Visual diff

Figures, equations, and other non-text layout are compared by rendering each
aligned page pair to an image, masking out the areas already covered by the
text diff, and taking a pixel difference over what remains
(`visual_diff.py`). Image-only pages (scans, exports) get a translation
registration step first, to correct for scanner or export shifts before the
pixel diff runs, so a page that's merely shifted by a few pixels isn't
reported as changed. Rendering is clamped to a fixed pixel budget regardless
of the PDF's declared page size, to bound memory use on pathological inputs.

## Annotations

Existing PDF annotations (highlights, comments, ink) are fingerprinted — by
type, normalized position, color, opacity, border, and content — and diffed
by fingerprint set difference (`annotations.py`), independently of the text
and visual diffs.

## Output

All detected differences are baked directly into the page content of the
output PDFs (`render.py`), rather than left as PDF annotations, so markers
remain visible in any viewer — including ones that hide annotations by
default, and when printing.
