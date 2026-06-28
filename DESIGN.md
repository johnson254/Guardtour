---
name: GuardTour SecOps
description: Security guard tour operations dashboard and mission control
colors:
  bg: "#0a0a0f"
  panel: "#14141c"
  card: "#1e1e28"
  surface-input: "#1a1a24"
  border: "#2c2c3a"
  text: "#f0f0f0"
  text-muted: "#a0a0b0"
  primary: "#d32f2f"
  primary-light: "#ff6659"
  primary-bg: "rgba(211, 47, 47, 0.12)"
  accent-green: "#4caf50"
  accent-amber: "#ffc107"
  accent-blue: "#0d6efd"
typography:
  display:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif"
    fontSize: "clamp(1.5rem, 4vw, 2rem)"
    fontWeight: 800
    lineHeight: 1.1
  heading:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif"
    fontSize: "clamp(1.1rem, 2.5vw, 1.5rem)"
    fontWeight: 700
    lineHeight: 1.2
  title:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif"
    fontSize: "1rem"
    fontWeight: 700
    lineHeight: 1.3
  body:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif"
    fontSize: "0.85rem"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif"
    fontSize: "0.7rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0.05em"
    textTransform: "uppercase"
  caption:
    fontFamily: "ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif"
    fontSize: "0.65rem"
    fontWeight: 400
    lineHeight: 1.3
    letterSpacing: "0.03em"
  mono:
    fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace"
    fontSize: "0.75rem"
rounded:
  xs: "10px"
  sm: "14px"
  md: "18px"
  lg: "24px"
  pill: "40px"
  full: "60px"
spacing:
  xs: "8px"
  sm: "12px"
  md: "16px"
  lg: "20px"
  xl: "24px"
  xxl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    backgroundImage: "linear-gradient(135deg, {colors.primary}, #9a0007)"
    textColor: "#ffffff"
    rounded: "{rounded.pill}"
    padding: "12px 24px"
    fontWeight: 600
  button-secondary:
    backgroundColor: "#2a2a35"
    textColor: "#ffffff"
    rounded: "{rounded.pill}"
    padding: "12px 24px"
    fontWeight: 600
  card-default:
    backgroundColor: "{colors.panel}"
    rounded: "{rounded.lg}"
    borderWidth: "1px"
    borderColor: "rgba(255,255,255,0.03)"
  card-elevated:
    backgroundColor: "{colors.card}"
    rounded: "{rounded.md}"
    borderWidth: "1px"
    borderColor: "{colors.border}"
  input-default:
    backgroundColor: "{colors.surface-input}"
    textColor: "{colors.text}"
    rounded: "28px"
    borderWidth: "1.5px"
    borderColor: "{colors.border}"
    padding: "14px 20px"
  nav-tab:
    backgroundColor: "transparent"
    textColor: "{colors.text-muted}"
    rounded: "{rounded.full}"
    padding: "10px 22px"
    fontWeight: 600
  nav-tab-active:
    backgroundColor: "{colors.primary}"
    textColor: "#ffffff"
    rounded: "{rounded.full}"
    padding: "10px 22px"
    fontWeight: 600
---

# Design System: GuardTour SecOps — The Watch Floor

## 1. Overview

**Creative North Star: "The Watch Floor"**

The Watch Floor is a security operations console designed for dispatchers who monitor live field operations under pressure. It takes its visual language from industrial control rooms and network operations centers — dark environments where screens glow with critical real-time data. Every design decision prioritizes clarity, reliability, and calm authority over decorative flourish.

The atmosphere is **professional and restrained** — a dark tactical theme where the near-black background (#0a0a0f) recedes into the environment, letting data and alerts command attention. The Alarm Red accent (#d32f2f) is used sparingly and intentionally: it signals active missions, warnings, and interactive elements. Green indicates healthy status (systems online, guards on duty). Color is never decorative — every hue carries operational meaning.

This system explicitly rejects gamified UI, playful animations, ornamental gradients, and any visual element that would trivialize the seriousness of security operations. The interface earns trust through consistent spacing, crisp typography, and predictable behavior.

**Key Characteristics:**
- Dark-native background reduces eye strain in low-light control rooms
- Tonal surface hierarchy (bg → panel → card → input) creates depth without shadows
- Alarm Red as a functional accent — scarcity is the point
- Generous rounded corners (24px on containers) soften the tactical density
- Typography relies on a single system-ui stack for reliability and performance
- Status is communicated through color + icon + label, never color alone

## 2. Colors

Alarm Red (#d32f2f) is the operational anchor — a high-visibility red that signals alerts, active state, and interactive elements without overwhelming the dark canvas.

### Primary

- **Alarm Red** (#d32f2f / `oklch(0.48 0.18 25)`): Primary accent for active nav tabs, primary buttons, progress bar fills, critical status indicators, and interactive hover states.
- **Alarm Red Light** (#ff6659 / `oklch(0.62 0.15 25)`): Used for icon accents, table header text, and hover highlights within the Alarm Red family.
- **Alarm Red Glow** (rgba(211, 47, 47, 0.12)): Tinted transparent background for pill badges, alert backgrounds, and subtle emphasis without full saturation.

### Secondary

- **Status Green** (#4caf50 / `oklch(0.62 0.13 145)`): Online status, healthy systems, completed checkpoints, field compliance metrics.
- **Status Amber** (#ffc107 / `oklch(0.72 0.13 85)`): Day shift badges, warning states, transitional status.
- **Status Blue** (#0d6efd / `oklch(0.5 0.16 265)`): Night shift badges, informational indicators.

### Neutral

- **Pitch** (#0a0a0f / `oklch(0.07 0.01 265)`): Page background. The room recedes; data advances.
- **Slate Dark** (#14141c / `oklch(0.12 0.01 265)`): Panel/card container background. Primary surface for content blocks.
- **Slate Mid** (#1e1e28 / `oklch(0.16 0.01 265)`): Elevated card background, hover states. One step above panel.
- **Slate Input** (#1a1a24 / `oklch(0.14 0.01 265)`): Input field background, table row background.
- **Border** (#2c2c3a / `oklch(0.22 0.02 265)`): Subtle container borders. Enough definition to separate surfaces without adding visual noise.
- **Text** (#f0f0f0 / `oklch(0.92 0.005 265)`): Primary body and heading text. High contrast against dark backgrounds.
- **Text Muted** (#a0a0b0 / `oklch(0.65 0.02 265)`): Secondary text, labels, metadata. Comfortably above 4.5:1 against dark surfaces.

### Named Rules

**The Functional Color Rule.** Every color carries operational meaning. Red is never decorative — it signals alerts, active missions, and interactive targets. Green always means "okay." This is a control panel, not a data viz dashboard. The user should never wonder whether a color means something.

## 3. Typography

**Display/Body Font:** System UI stack (ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif)
**Mono Font:** System monospace stack (ui-monospace, SFMono-Regular, Consolas, monospace)

**Character:** A single sans-serif system stack used across all roles. No external font loads, no FOUC, no variable font complexity — reliability matters more than typographic distinction in a real-time ops tool. Weight and size do the hierarchy work.

### Hierarchy

- **Display** (800 weight, clamp(1.5rem, 4vw, 2rem), 1.1 line-height): Hero stat values, org name, section-defining numbers. Maximum gravity.
- **Heading** (700 weight, clamp(1.1rem, 2.5vw, 1.5rem), 1.2 line-height): Card titles, section headers. Strong but not shouting.
- **Title** (700 weight, 1rem, 1.3 line-height): Guard names, mission titles, list item headings within cards.
- **Body** (400 weight, 0.85rem, 1.5 line-height): General content text, descriptions, route names. Comfortably readable at small sizes.
- **Label** (700 weight, 0.7rem, 1.2, 0.05em letter-spacing, uppercase): Stat labels, card headers, table headers. Consistent uppercase convention for metadata.
- **Caption** (400 weight, 0.65rem, 1.3, 0.03em letter-spacing): Timestamps, secondary metadata, helper text. Smallest legible size.
- **Mono** (0.75rem): Operator IDs, callsigns, device identifiers. Technical data in monospace for scannability.

### Named Rules

**The No-Font-Load Rule.** No Google Fonts, no @font-face, no external type foundry. The system stack loads instantly, renders predictably on every device, and never flashes. Typographic personality comes from weight contrast and spacing, not from font choice.

## 4. Elevation

The Watch Floor uses a **hybrid approach**: depth is created through tonal surface layering (bg → panel → card → input), while soft shadows (0 12px 36px rgba(0,0,0,0.5)) are reserved for glass-card containers that need to float above the surface. Interactive elements (buttons, hover states) lift slightly with translateY(-2px) but cast no additional shadow — the motion itself signals affordance.

This preserves the flat, control-room aesthetic during rest while giving primary containers a sense of physical presence.

### Shadow Vocabulary

- **Container Shadow** (`box-shadow: 0 12px 36px rgba(0,0,0,0.5)`): Applied to glass-card and card containers. Creates depth beneath content blocks without casting sharp, defined shadows.

### Named Rules

**The Tonal-By-Default Rule.** Surface color alone establishes the depth hierarchy. The shadow is a secondary signal, not the primary depth mechanism. A page should read correctly even with all shadows removed — the layered backgrounds do the work.

## 5. Components

### Buttons
- **Shape:** Pill-shaped (40px border-radius). Full, tactile click areas.
- **Primary:** Alarm Red gradient (135deg, #d32f2f → #9a0007). White text. 12px 24px padding. 0.85rem font, 600 weight.
- **Hover:** translateY(-2px) lift, brightness(1.05) filter. No shadow added — the lift is the signal.
- **Secondary:** Dark gray background (#2a2a35). White text. Same shape and interaction as primary.
- **Ghost/Inline:** Text-only buttons use Alarm Red text on transparent background. No border, no padding — used for destructive actions or tertiary links.

### Cards / Containers
- **Corner Style:** Generous rounded corners — 24px for .glass-card and .card, 18px for .mission-card and .guard-card, 14px for compact list items.
- **Background:** Panel (#14141c) for large cards; Card (#1e1e28) for nested or elevated cards.
- **Border:** 1px solid rgba(255,255,255,0.03) on glass-card / 1px solid #2c2c3a on dashboard cards.
- **Shadow:** Container shadow on glass-card only. Dashboard cards are shadowless — tonal hierarchy does the work.
- **Internal Padding:** 24px (card-body), 20px 24px (card-header). Cards breathe.
- **Hover State:** Border shifts to Alarm Red on interactive cards (guard-card, mission-card, daily-pin-item). Subtle, unmistakable.

### Inputs / Fields
- **Style:** Dark surface input (#1a1a24), 1.5px border (#2c2c3a), 28px border-radius, 14px 20px padding. 0.9rem text.
- **Focus:** Border shifts to Alarm Red (#d32f2f), 3px outer glow (rgba(211,47,47,0.2)). No outline.
- **Error / Disabled:** Standard red border treatment for errors. Disabled fields at 0.5 opacity.

### Navigation Tabs
- **Style:** Horizontal pill-group container (60px border-radius, 4px padding, dark semi-transparent background, backdrop-filter blur).
- **Tabs:** Individual pill buttons (60px border-radius, 10px 22px padding, 0.85rem 600 weight). Muted text by default, Alarm Red gradient + white text when active.
- **Active State:** Box-shadow glow (0 2px 10px rgba(211,47,47,0.4)) reinforces the active tab.

### Status Indicators
- **LED Dots:** 8px circles. Green (#4caf50) with matching glow for online/active. Muted gray for offline. Red (at reduced opacity) for inactive/warning.
- **Pulse Ring:** Animated ::after pseudo-element for live status indicators. Green ring expands outward on a 2s loop.
- **Badges:** Small pills (3px 10px padding, 20px radius, 0.65rem 600 weight uppercase) with tinted backgrounds matching their meaning — red-tinted for "active/scheduled", green-tinted for "completed", amber/blue-tinted for shift types.

### Custom Toggles
- **Style:** 42px × 20px switch track (#2a2a35, 34px radius, 1px border). 12px white circular thumb.
- **Active:** Track fills Alarm Red (#d32f2f), thumb slides 20px right. 0.4s transition.

### Progress Bars
- **Style:** 6px height track. Panel background. 3px radius. Fill is Alarm Red → Alarm Red Light gradient. 0.5s width transition.

### Modal / Dialog
- **Style:** Fixed overlay (rgba(0,0,0,0.8)), centered glass-card container (500px max-width, 90% mobile). Card-title header, body content, dual-button footer (primary + secondary).

### Toasts
- **Style:** Fixed bottom-right stack. Card-styled container, 4px Alarm Red left border. Slide-in from right (0.4s spring curve). Success variant uses green left border.

### Form Inputs (Blueprint Identity standard)
- **Base class:** `.rs-fi` — `width:100%; padding:7px 11px; border-radius:8px; border:1px solid rgba(255,255,255,0.07); background:rgba(13,13,20,0.95); color:#f0f0f0; font-size:0.78rem; line-height:1.3; transition:border-color .15s, box-shadow .15s, background .15s`
- **Placeholder:** `color:rgba(255,255,255,0.22)`
- **Hover:** `border-color:rgba(255,255,255,0.16)`
- **Focus:** `outline:none; border-color:#d32f2f; box-shadow:0 0 0 2px rgba(211,47,47,0.14); background:rgba(13,13,20,0.98)`
- **Small variant:** `.rs-fi-sm` — `padding:6px 10px; font-size:0.74rem`
- **Textarea:** `resize:vertical; min-height:56px; line-height:1.45`
- **Select:** `height:32px; cursor:pointer`
- **Label:** `.rs-lbl` — `font-size:0.58rem; font-weight:900; text-transform:uppercase; letter-spacing:0.7px; color:rgba(255,255,255,0.42); display:block; margin-bottom:4px`
- **Field note:** `.rs-field-note` — `font-size:0.6rem; color:rgba(255,255,255,0.32); margin-top:4px`
- **Required indicator:** `.rs-field-required` — `color:#ff5252`
- **Usage:** All input forms across manage/dispatch/routes MUST use these classes. Never use inline-styled inputs smaller than `font-size:0.74rem` or `padding:6px 10px`.

## 6. Do's and Don'ts

### Do:
- **Do** use color functionally — red for alerts/active, green for healthy/complete, amber for warnings. Every color should answer "what does this mean operationally?"
- **Do** prefer tonal layering over shadows for depth. The surface hierarchy (bg → panel → card) should be legible with all shadows removed.
- **Do** use the system font stack. No external font loads means no FOUC, no layout shift, no performance tax.
- **Do** use generous rounded corners (24px on primary containers) — they soften the dark tactical density without sacrificing professionalism.
- **Do** communicate status redundantly: color + icon + text label. A color-blind operator should still understand every state.
- **Do** use `text-wrap: balance` on card titles and section headers for clean line breaks.

### Don't:
- **Don't** gamify the UI. No badges for achievements, no celebratory animations, no progress "rewards." This is security operations, not a fitness app.
- **Don't** use gradient text (`background-clip: text` with gradient background) for anything other than the logo. Solid colors are more legible and more professional.
- **Don't** use glassmorphism (backdrop-filter blur with transparency) as a default container style. Reserve blur for the nav-tabs container only.
- **Don't** introduce a second font family. The system stack covers all roles. A second font would need to justify itself operationally.
- **Don't** use border-left colored stripes as accents. Use full borders, background tints, or nothing.
- **Don't** use side-stripe borders on cards or alerts. A 3px left border on alert items is acceptable for critical alerts only — this is an established operational convention, not decoration.
- **Don't** allow text overflow on stat values or mission names at any breakpoint. Test heading copy at 375px.
- **Don't** use muted gray (#a0a0b0) for body text — it's reserved for labels and metadata. Body text is always #f0f0f0.
