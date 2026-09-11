# Font Licenses

The fonts listed below are bundled with the release build and may be used in
commercial YouTube clips. Each font is distributed under the SIL Open Font
License (OFL) 1.1. The original license text is included next to each font.

## Bundled fonts

| Font | File | License | Original source |
|------|------|---------|----------------|
| Anton | `Anton.ttf` | `Anton-OFL.txt` | [google/fonts — Anton](https://github.com/google/fonts/tree/main/ofl/anton) |
| Bebas Neue | `Bebas Neue.ttf` | `BebasNeue-OFL.txt` | [google/fonts — Bebas Neue](https://github.com/google/fonts/tree/main/ofl/bebasneue) |
| Archivo Black | `Archivo Black.ttf` | `ArchivoBlack-OFL.txt` | [google/fonts — Archivo Black](https://github.com/google/fonts/tree/main/ofl/archivoblack) |
| Barlow Condensed SemiBold | `Barlow Condensed SemiBold.ttf` | `BarlowCondensed-OFL.txt` | [google/fonts — Barlow Condensed](https://github.com/google/fonts/tree/main/ofl/barlowcondensed) |
| Lilita One | `Lilita One.ttf` | `LilitaOne-OFL.txt` | [google/fonts — Lilita One](https://github.com/google/fonts/tree/main/ofl/lilitaone) |

These display fonts are intended for short, high-contrast hook text:

- Anton and Bebas Neue: tall, bold headlines
- Archivo Black: heavy, high-impact emphasis
- Barlow Condensed SemiBold: compact text where width is limited
- Lilita One: playful creator or entertainment content

## Local-only fonts

The following older files remain in this directory for local compatibility, but
their redistribution license has not been verified. They are intentionally not
included in the Tauri bundle or portable zip:

- `Capo_Sfogliato.ttf`
- `Gatchina *.ttf`
- `Super Hockey.ttf`
- `Super Kidpop.ttf`
- `Super Starfish.ttf`

When adding another font to a release, add its original license file and update
both `src-tauri/tauri.conf.json` and `scripts/package-portable.ps1` allowlists.
