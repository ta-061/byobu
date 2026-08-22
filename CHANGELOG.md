# Changelog

## 0.1.0 - 2026-08-22 - Initial release

Initial release of kogo. The project was formerly prototyped under the name "byobu"; it was renamed before PyPI publication to avoid collision with the existing `byobu` terminal multiplexer.

- Word-level text diff for Latin text, character-level diff for CJK text (including rare kanji across CJK Extensions B-J), with reading order reconstructed from page layout
- Similarity-based page alignment tolerant of inserted or removed pages
- Visual diff for figures, equations, and layout, with text areas masked out and registration for scanned pages
- Detection of added or removed highlights, comments, and ink annotations
- Style-change detection (bold, italic, font-size changes on otherwise-unchanged text)
- Markers baked into output PDFs so they show up in any viewer
- Web app with a selectable-text PDF.js preview, page-by-page diff view, and downloadable marked-up PDFs
- CLI (`kogo diff`) for scripted comparisons
- Docker image bundling the PDF.js viewer assets
