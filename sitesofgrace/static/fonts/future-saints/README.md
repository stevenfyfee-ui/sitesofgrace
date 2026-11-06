# Future Saints Serif

Self-hosted body and heading face for the Future Saints section (no third-party font host).

- Source: Lora by The Lora Project Authors, static TTFs from
  https://github.com/cyrealtype/Lora-Cyrillic (fonts/ttf: Regular, Italic, Bold, BoldItalic).
- Licence: SIL Open Font License 1.1, see OFL.txt (copied unchanged from upstream).
- Modified Version: subset to U+0000-00FF, U+0100-017F (Latin, Latin-1, Latin Extended-A),
  U+2010-2027, U+2030-203A, U+20AC, U+2122, and converted to WOFF2 with fontTools + brotli.
  Because Lora's licence reserves the font name "Lora", the subset is renamed
  "Future Saints Serif" in its name table, in these file names and in the CSS @font-face family.
- Faces: fs-serif-400, fs-serif-400-italic, fs-serif-700, fs-serif-700-italic.
- Regenerating them is a local, one-off task; fontTools and brotli are not project requirements.
