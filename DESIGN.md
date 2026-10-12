---
name: MyGlico
description: Calm, traceable glycemic follow-up shared between a patient and their doctor.
colors:
  trust-blue: "#167cd9"
  trust-blue-deep: "#0a4c9c"
  action-blue: "#126fc1"
  action-green: "#0d7f55"
  clear-cyan: "#27b7e7"
  steady-green: "#1eab69"
  steady-green-deep: "#0b7a51"
  amber-attention: "#f4a93d"
  amber-attention-text: "#8a5300"
  rose-alert: "#e35d73"
  rose-alert-text: "#b23a50"
  slate: "#52647a"
  morning-mist: "#f4fbfe"
  ink-navy: "#17304a"
  muted-ink: "#56677e"
  surface-glass: "rgba(255, 255, 255, 0.94)"
  hairline-blue: "rgba(22, 124, 217, 0.14)"
typography:
  display:
    fontFamily: "Bahnschrift SemiBold, Trebuchet MS, sans-serif"
    fontSize: "clamp(2.4rem, 5vw, 4.5rem)"
    letterSpacing: "-0.03em"
  headline:
    fontFamily: "Bahnschrift SemiBold, Trebuchet MS, sans-serif"
    fontSize: "clamp(2rem, 3.3vw, 2.9rem)"
    letterSpacing: "-0.03em"
  title:
    fontFamily: "Bahnschrift SemiBold, Trebuchet MS, sans-serif"
    fontSize: "1.5rem"
    letterSpacing: "-0.03em"
  body:
    fontFamily: "Aptos, Segoe UI, sans-serif"
    fontSize: "1rem"
    lineHeight: 1.5
  label:
    fontFamily: "Aptos, Segoe UI, sans-serif"
    fontSize: "0.85rem"
    fontWeight: 700
  eyebrow:
    fontFamily: "Aptos, Segoe UI, sans-serif"
    fontSize: "0.74rem"
    fontWeight: 700
    letterSpacing: "0.18em"
  mono:
    fontFamily: "Consolas, SFMono-Regular, monospace"
    fontSize: "0.85rem"
rounded:
  sm: "14px"
  md: "18px"
  field: "20px"
  card: "24px"
  panel: "30px"
  pill: "999px"
spacing:
  xs: "0.35rem"
  sm: "0.65rem"
  md: "1rem"
  lg: "1.3rem"
  xl: "1.75rem"
components:
  button-primary:
    backgroundColor: "{colors.action-blue}"
    textColor: "#ffffff"
    rounded: "{rounded.pill}"
    padding: "0 1rem"
    height: "2.75rem"
  button-ghost:
    backgroundColor: "{colors.surface-glass}"
    textColor: "{colors.trust-blue-deep}"
    rounded: "{rounded.pill}"
    padding: "0 1rem"
    height: "2.75rem"
  button-danger:
    backgroundColor: "{colors.surface-glass}"
    textColor: "{colors.rose-alert-text}"
    rounded: "{rounded.pill}"
    padding: "0 1rem"
    height: "2.75rem"
  button-compact:
    rounded: "{rounded.pill}"
    padding: "0 0.9rem"
    height: "2.35rem"
  badge:
    rounded: "{rounded.pill}"
    padding: "0.15rem 0.7rem"
    height: "1.75rem"
  input:
    backgroundColor: "#ffffff"
    textColor: "{colors.ink-navy}"
    rounded: "{rounded.field}"
    padding: "0 1rem"
    height: "3rem"
  panel:
    backgroundColor: "{colors.surface-glass}"
    rounded: "{rounded.panel}"
    padding: "1.3rem"
  nav-link:
    textColor: "{colors.muted-ink}"
    rounded: "{rounded.pill}"
    padding: "0.9rem 1.2rem"
---

# Design System: MyGlico

## Overview

**Creative North Star: "The Serene Clinic"**

MyGlico should feel like a trustworthy, welcoming clinic: trust blue for
action and structure, steady green for stability, and nothing that alarms.
The system pairs a soft form language (pills, generous 20–30 px corners,
translucent white panels over a pale morning-mist background) with precise
information: legible numbers, explicit states, and chips that name what is
going on.

The balance is deliberate. The form welcomes patients who are not technical;
the information stays as precise as a clinical panel. Warmth comes from
shape and space, never from vague data.

**Key Characteristics:**
- Blue→green action gradient (`action-blue` → `action-green`, 135°) reserved
  for the primary action and the active state; its stops are darker than the
  brand blue and green so white labels stay above 4.5:1.
- Translucent white panels with a hairline blue border and a diffuse ambient
  shadow, floating over a pale gradient background.
- Pill-shaped controls everywhere (buttons, chips, badges, nav links,
  pagination).
- A condensed geometric display face for headings over a humanist sans body.
- Uppercase green eyebrows above every panel heading.

## Colors

Cool and clinical at the base, with two calm accents and two semantic
signals used sparingly.

### Primary
- **Action Blue → Action Green** (`action-blue`, `action-green`): the text-bearing
  action gradient (buttons, active nav, active chip, current page, unread dot).
- **Trust Blue** (`trust-blue`): links, focus accents, checkbox accent, chart
  trend line.
- **Deep Trust Blue** (`trust-blue-deep`): text on ghost buttons, chips and
  pagination; select chevrons.
- **Clear Cyan** (`clear-cyan`): focus rings (`0 0 0 4px` at 12–22% alpha)
  and info-state tints.

### Secondary
- **Steady Green** (`steady-green`): "in range" chart segments, stable
  readings and positive badges.
- **Deep Steady Green** (`steady-green-deep`): eyebrow text and green badge
  text.

### Tertiary
- **Amber Attention** (`amber-attention`, text `amber-attention-text`):
  pending analysis, attention, atypical signals.
- **Rose Alert** (`rose-alert`, text `rose-alert-text`): destructive actions
  (revoke, close) and error states.

### Neutral
- **Morning Mist** (`morning-mist`): page background, under radial cyan and
  green washes.
- **Ink Navy** (`ink-navy`): body text and headings.
- **Muted Ink** (`muted-ink`): secondary text, field labels, inactive nav.
- **Slate** (`slate`): soft badges and metadata.
- **Surface Glass** (`surface-glass`): panels, heroes, metric cards.
- **Hairline Blue** (`hairline-blue`): default border of panels, fields and
  chips.

### Named Rules
**The Gradient Means Go Rule.** The action gradient marks only the main
action of a view and the active state (active nav link, active chip, current
page). One gradient-filled button per region.

**The Calm Signal Rule.** Amber and rose appear as tints with dark text
(`amber-attention-text`, `rose-alert-text`), never as large fills, except the
confirm button of a destructive dialog.

## Typography

**Display Font:** Bahnschrift SemiBold (with Trebuchet MS, sans-serif)
**Body Font:** Aptos (with Segoe UI, sans-serif)
**Label/Mono Font:** Consolas (with SFMono-Regular) for patient codes

**Character:** A condensed, engineered display face gives headings a
precise, instrument-like voice; the humanist body keeps reading soft.

### Hierarchy
- **Display** (`clamp(2.4rem, 5vw, 4.5rem)`, tracking -0.03em): landing and
  overview hero headings.
- **Headline** (`clamp(2rem, 3.3vw, 2.9rem)`): page heroes such as the
  patient detail.
- **Title** (1.5rem): panel `h2` headings.
- **Body** (1rem, line-height 1.5): paragraphs and descriptions; 0.88–0.95rem
  for supporting copy.
- **Label** (700, 0.85rem): field labels, buttons, chips.
- **Eyebrow** (700, 0.74rem, 0.18em tracking, uppercase, steady green deep):
  the small kicker above every panel heading.

### Named Rules
**The Eyebrow-Heading Pair Rule.** Every panel opens with an eyebrow, then
an `h2`, then an optional one-line description.

## Layout

Content sits in a centered container (max 1240 px, 1.2 rem padding). Pages
stack panels vertically with a 1 rem grid gap. Heroes split into a 1.15fr
copy column and a 0.85fr visual or summary column. Metric grids use
`auto-fit` with 220 px minimum columns; detail grids use two equal columns.

Breakpoints: 1080 px (heroes and insights collapse), 900 px (two-column
grids stack, navigation wraps), 640 px (phone layout: cards replace tables,
full-width buttons), 360 px (single-column mobile cards). The patient side
must work at 390 px without horizontal scroll.

## Elevation & Depth

Soft layers: panels float over the background with one diffuse ambient
shadow, and controls carry small lifts that grow on hover.

### Shadow Vocabulary
- **Ambient panel** (`0 24px 52px rgba(20, 79, 126, 0.14)`): heroes, panels,
  metric cards, dialogs.
- **Soft card** (`0 10px 24px rgba(16, 59, 97, 0.08)`): nested cards and
  list items.
- **Button rest** (`0 3px 8px rgba(20, 99, 155, 0.18)`), rising to
  `0 12px 26px rgba(16, 59, 97, 0.14)` with a 1 px lift on hover.
- **Focus ring** (`0 0 0 4px rgba(39, 183, 231, 0.12–0.22)`): fields and
  buttons on focus.
- **Inner highlight** (`inset 0 1px 0 rgba(255, 255, 255, 0.85)`): fields.

## Shapes

Generous, rounded, never sharp. Large containers use 30 px (panels, heroes),
cards and states 24 px, fields 20 px, nested tiles 14–18 px, and every
interactive control is a full pill (999 px). Borders are 1 px hairlines in
translucent blue. Empty states use a dashed hairline.

## Components

### Buttons
Pills with bold labels, gentle lift on hover.
- **Shape:** full pill (999 px), 2.75 rem tall (compact 2.35 rem).
- **Primary:** blue→green gradient, white label, rest shadow.
- **Hover / Focus:** 1 px upward lift and deeper shadow; focus adds the cyan
  ring.
- **Ghost:** translucent white with deep blue label and blue hairline;
  secondary actions and "back".
- **Danger:** white with rose text and rose hairline; destructive actions,
  always behind a confirmation dialog. **Danger solid** (rose gradient) only
  as that dialog's confirm button.
- **Quiet / Text:** transparent, muted or blue label, for tertiary actions.

### Chips and Badges
- **Chips:** ghost pills used as filters; active chip takes the gradient.
- **Badges:** small pills (1.75 rem) in tinted variants (brand, green, blue,
  soft); counters use a compact round badge.

### Cards / Containers
- **Corner Style:** 30 px panels, 24 px states and cards.
- **Background:** surface glass over morning mist.
- **Shadow Strategy:** ambient panel shadow (see Elevation & Depth).
- **Border:** hairline blue.
- **Internal Padding:** 1.3 rem (heroes 1.75 rem).

### Inputs / Fields
- **Style:** 3 rem tall, 20 px radius, hairline blue border, white fill
  with inner highlight; label above in bold muted 0.85 rem; textareas 6 rem
  minimum.
- **Focus:** border shifts to blue (35%) plus the 4 px cyan ring.
- **Selects:** same shell with a CSS chevron in deep blue.

### Navigation
A rounded topbar (28 px) holding the brand mark and pill nav links in muted
ink; the active link takes the gradient with white text. Counters attach as
compact badges. On narrow screens the links wrap.

### State Blocks
Empty, loading and error states share one block: icon tile plus copy on a
dashed hairline card (24 px). Variants tint the icon (danger rose/amber,
info cyan/blue).

### Dialogs
Centered panel over a dimmed backdrop, with header, body sections and an
actions row; confirmation dialogs pair a ghost cancel with the action.

## Do's and Don'ts

### Do:
- **Do** build every new screen from the panel + eyebrow + `h2` structure.
- **Do** use the shared field, button, badge and state primitives instead of
  inline styles.
- **Do** keep the gradient for one primary action per region and for active
  states.
- **Do** put destructive actions in the danger style behind a confirmation
  dialog.
- **Do** show pending or atypical status as a tinted chip with dark text.

### Don't:
- **Don't** ship browser-default inputs, square corners or flat `#005fcc`
  buttons; those were the off-system patterns removed in the 2026-10 layout
  review.
- **Don't** use emoji as icons.
- **Don't** fill large areas with amber or rose.
- **Don't** hardcode colors outside the `--react-*` tokens; alert text uses
  `--react-rose-text` and `--react-amber-text`.
- **Don't** put white text on the light brand `trust-blue`/`steady-green`
  fills; use the action gradient.
