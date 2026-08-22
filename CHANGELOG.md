# Changelog

## 0.1.0 - Initial release

- Word-level text diff for Latin text, character-level diff for CJK text, with reading order reconstructed from page layout
- Similarity-based page alignment tolerant of inserted or removed pages
- Visual diff for figures, equations, and layout, with text areas masked out and registration for scanned pages
- Detection of added or removed highlights, comments, and ink annotations
- Style-change detection (bold, italic, font-size changes on otherwise-unchanged text)
- Markers baked into output PDFs so they show up in any viewer
- Web app with a selectable-text PDF.js preview, page-by-page diff view, and downloadable marked-up PDFs
- CLI (`byobu diff`) for scripted comparisons
- Docker image bundling the PDF.js viewer assets
