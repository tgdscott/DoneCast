Color Contrast Utilities

Exports from `colorContrast.js` help determine readable text colors per WCAG-like guidelines:

- `hexToRgb(hex)` → `{r,g,b}`
- `relativeLuminanceFromHex(hex)` → `0..1`
- `contrastRatioHex(fgHex, bgHex)` → ratio number
- `isReadable(fgHex, bgHex, threshold=4.5)` → boolean
- `chooseTextColorBW(bgHex, midpoint=128)` → `#000000` or `#FFFFFF`
- `suggestTextColor(fgHex, bgHex)` → returns original if readable, else picks black/white with better ratio
- `chooseReadableBW(bgHex, threshold=4.5)` → picks black/white meeting threshold if possible

Example usage:

```js
import {
  isReadable,
  contrastRatioHex,
  chooseTextColorBW,
  suggestTextColor,
} from './colorContrast';

const bg = '#3A86FF';
const fg = '#FFFFFF';
const ratio = contrastRatioHex(fg, bg); // e.g., 7.1
const readable = isReadable(fg, bg); // true if >= 4.5

// Choose black or white when unsure
const bw = chooseTextColorBW(bg); // '#FFFFFF' for dark backgrounds

// If a chosen color is not readable, suggest a better alternative
const safeText = suggestTextColor(fg, bg); // returns '#000000' or '#FFFFFF' if needed
```

Notes:
- Normal text target ratio: 4.5:1
- Large text or graphics can use 3:1
- 7:1 recommended for extra confidence
