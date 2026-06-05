# AI黄财神 Brand Guidelines

## 1. Brand Overview

**Brand name:** AI黄财神  
**Category:** AI-powered trading intelligence and financial technology  
**Brand personality:** Intelligent, trustworthy, premium, disciplined, modern  
**Core idea:** Combining artificial intelligence, market analysis, and financial growth into one recognizable identity.

The visual system should feel professional and advanced, not flashy or speculative.

---

## 2. Logo System

### Source Assets

Use the checked-in brand assets as the source of truth:

| Asset | File | Dimensions | Usage |
|---|---|---:|---|
| Icon | `icon.png` | 1254 × 1254 px | App icon, favicon source, profile image, compact product mark |
| Wordmark | `logo.png` | 2172 × 724 px | Website navigation, report headers, presentation covers, horizontal brand placements |

![AI黄财神 icon](icon.png)

![AI黄财神 wordmark](logo.png)

### Primary Logo

Use the complete brand system with:

- Icon for square or compact placements
- “AI黄财神” wordmark for horizontal placements
- Original proportions and colors preserved

Best used for:

- Website landing pages
- Presentation covers
- Marketing materials
- Social media profile banners
- Product splash screens

### Icon-Only Logo

The icon may be used separately for:

- App icons
- Favicons
- Dashboard avatars
- Browser tabs
- Social media profile images
- Loading screens

### Wordmark-Only Logo

The “AI黄财神” wordmark may be used for:

- Website navigation bars
- Footer branding
- Documents
- Reports
- Narrow horizontal layouts

### Clear Space

Keep empty space around the logo equal to at least:

- **25% of the icon width** around the icon
- **Half the height of the letter “A”** around the wordmark

Do not place text, borders, or interface elements inside this space.

### Minimum Size

- Full logo: minimum width **180 px**
- Wordmark: minimum width **140 px**
- Icon: minimum size **32 × 32 px**
- App icon recommendation: **512 × 512 px** or larger

### Export Notes

The current source PNGs do not include an alpha channel. When a transparent asset is required, export a dedicated transparent-background PNG or SVG from the original artwork rather than manually removing the background from these files.

---

## 3. Brand Colors

The logo uses a premium dark-green and metallic-gold palette.

### Primary Colors

| Color | Hex | Usage |
|---|---|---|
| Deep Fortune Green | `#092E24` | Main background, headings, logo text |
| Jade Green | `#0C3D2F` | Buttons, cards, navigation, secondary surfaces |
| Shadow Green | `#051A10` | Dark backgrounds, shadows, high-contrast areas |
| Prosperity Gold | `#DDAA53` | Primary accent, highlights, active states |
| Heritage Gold | `#C08933` | Darker gold accent, borders, gradients |

### Secondary Colors

| Color | Hex | Usage |
|---|---|---|
| Sage Green | `#3B563F` | Secondary graphics, inactive states |
| Muted Jade | `#7C8E81` | Supporting text, icons, subtle UI elements |
| Soft Silver Green | `#C6CDBF` | Borders, dividers, light interface elements |
| Warm Ivory | `#F7F4EA` | Light backgrounds |
| Pure White | `#FFFFFF` | Clean backgrounds and reversed text |

### Recommended Gold Gradient

```css
background: linear-gradient(
  135deg,
  #F4D98B 0%,
  #DDAA53 45%,
  #C08933 100%
);
```

### Recommended Green Gradient

```css
background: linear-gradient(
  135deg,
  #0C3D2F 0%,
  #092E24 60%,
  #051A10 100%
);
```

---

## 4. Typography

The logo wordmark should be treated as **custom artwork**. Do not recreate it with a standard font.

### English Font

**Primary:** Manrope

Recommended weights:

- Bold 700 for headings
- Semibold 600 for buttons and labels
- Regular 400 for body text

Fallback:

```css
font-family: "Manrope", "Inter", "Helvetica Neue", Arial, sans-serif;
```

### Chinese Font

**Primary:** Noto Sans SC

Recommended weights:

- Bold 700 for headings
- Medium 500 for navigation and labels
- Regular 400 for body text

Fallback:

```css
font-family: "Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif;
```

### Combined Font Stack

```css
font-family:
  "Manrope",
  "Noto Sans SC",
  "PingFang SC",
  "Microsoft YaHei",
  sans-serif;
```

### Type Scale

| Style | Size | Weight |
|---|---:|---:|
| Display heading | 48–64 px | 700 |
| Main heading | 36–48 px | 700 |
| Section heading | 28–32 px | 600 |
| Card heading | 20–24 px | 600 |
| Body text | 16–18 px | 400 |
| Supporting text | 14 px | 400 |
| Caption | 12 px | 400 |

---

## 5. Logo Usage Rules

### Approved Usage

- Dark green logo on ivory or white backgrounds
- Gold and green logo on transparent backgrounds
- White wordmark on dark green backgrounds
- Icon-only version for compact applications

### Do Not

- Change the logo colors
- Stretch or compress the logo
- Rotate the logo
- Add outlines
- Add unapproved shadows
- Place the logo over visually busy images
- Separate or rearrange elements inside the icon
- Replace the wordmark with a different font
- Use bright neon colors
- Place the logo on low-contrast backgrounds

---

## 6. UI Color Usage

Recommended interface distribution:

- **60%** neutral or dark green backgrounds
- **30%** supporting green and ivory surfaces
- **10%** gold accents

Gold should be used carefully for:

- Important metrics
- Selected navigation
- Premium features
- Primary calls to action
- Positive financial indicators
- Charts and highlights

Avoid using gold for large body text or large background areas.

---

## 7. Button Styles

### Primary Button

- Background: `#DDAA53`
- Text: `#051A10`
- Hover: `#C08933`
- Border radius: 8–12 px
- Font weight: 600

### Secondary Button

- Background: `#0C3D2F`
- Text: `#FFFFFF`
- Hover: `#092E24`

### Outline Button

- Transparent background
- Border: `1px solid #DDAA53`
- Text: `#DDAA53`

---

## 8. Data Visualization

Recommended colors for financial dashboards:

| Purpose | Color |
|---|---|
| Positive movement | `#2E8B57` |
| Strong positive highlight | `#DDAA53` |
| Negative movement | `#C64B4B` |
| Neutral data | `#7C8E81` |
| Primary chart line | `#DDAA53` |
| Secondary chart line | `#3B563F` |
| Grid lines | `#C6CDBF` at low opacity |

Do not use only green and red to communicate meaning. Also use labels, arrows, icons, and patterns for accessibility.

---

## 9. Iconography

Use icons that are:

- Geometric
- Minimal
- Rounded or softly squared
- Consistent in line weight
- Professional rather than playful

Recommended icon style:

- 1.5–2 px strokes
- Rounded line caps
- Dark green by default
- Gold for active or premium states

Avoid highly detailed illustrations inside the product interface.

---

## 10. Photography and Imagery

Use imagery related to:

- Financial analysis
- Institutional trading environments
- Market data
- AI networks
- Professional workspaces
- Global finance

Preferred visual treatment:

- Dark green overlays
- Warm gold highlights
- Clean lighting
- Minimal clutter
- High contrast
- Premium editorial style

Avoid:

- Gambling imagery
- Stacks of cash
- Excessive luxury symbols
- Meme-style trading graphics
- Aggressive “get rich quick” visuals

---

## 11. Brand Voice

The brand should communicate like an experienced financial research team.

### Tone

- Clear
- Analytical
- Calm
- Confident
- Transparent
- Risk-aware

### Preferred Language

- “AI-assisted market intelligence”
- “Research-backed recommendations”
- “Multi-agent financial analysis”
- “Risk-controlled trade execution”
- “Institutional-style research workflow”

### Avoid

- “Guaranteed profits”
- “Risk-free returns”
- “Instant wealth”
- “Never lose a trade”
- “100% accurate predictions”

---

## 12. Suggested Taglines

### Primary Recommendation

> Intelligent research. Disciplined execution.

### Alternatives

> AI-powered insight for smarter trading.

> Multi-agent intelligence for modern markets.

> Research deeply. Trade responsibly.

> From market intelligence to controlled execution.

---

## 13. Brand Applications

### Website

- Dark green navigation
- Ivory or white content background
- Gold primary call-to-action buttons
- Rounded cards with subtle shadows
- Clean financial data displays

### Trading Dashboard

- Dark theme as the primary interface
- Gold for selected agents and major metrics
- Green for healthy portfolio states
- Red only for risk warnings or losses

### Reports

- White or ivory background
- Dark green headings
- Gold section dividers
- Logo in the header
- Page numbers and metadata in muted jade

### Social Media

- Use the icon as the profile image
- Use the full wordmark in banners
- Keep templates consistent with dark green, ivory, and gold

---

## 14. CSS Brand Tokens

```css
:root {
  --brand-green-900: #051A10;
  --brand-green-800: #092E24;
  --brand-green-700: #0C3D2F;
  --brand-green-500: #3B563F;

  --brand-gold-600: #C08933;
  --brand-gold-500: #DDAA53;
  --brand-gold-300: #F4D98B;

  --brand-neutral-500: #7C8E81;
  --brand-neutral-300: #C6CDBF;
  --brand-ivory: #F7F4EA;
  --brand-white: #FFFFFF;

  --success: #2E8B57;
  --danger: #C64B4B;
}
```

---

## 15. Summary

The AI黄财神 visual identity should consistently communicate:

- Artificial intelligence
- Financial intelligence
- Trust
- Discipline
- Premium quality
- Controlled growth

Use the custom logo artwork for branding, and use **Manrope + Noto Sans SC** throughout the product, reports, and marketing materials.
