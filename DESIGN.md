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
  glyco-low: "#e35d73"
  glyco-in-range: "#1eab69"
  glyco-high: "#f4a93d"
  glyco-very-high: "#8a5300"
  state-pending-bg: "rgba(82, 100, 122, 0.10)"
  state-pending-border: "rgba(82, 100, 122, 0.40)"
  state-atypical-bg: "rgba(244, 169, 61, 0.16)"
  state-selected-bg: "rgba(22, 124, 217, 0.10)"
  state-selected-border: "rgba(22, 124, 217, 0.55)"
  state-disabled-bg: "rgba(82, 100, 122, 0.16)"
typography:
  display:
    fontFamily: "Bahnschrift SemiBold, Trebuchet MS, sans-serif"
    fontSize: "clamp(2.25rem, 4.2vw, 3.5rem)"
    lineHeight: 1
    letterSpacing: "-0.03em"
  headline:
    fontFamily: "Bahnschrift SemiBold, Trebuchet MS, sans-serif"
    fontSize: "clamp(1.75rem, 3vw, 2.5rem)"
    lineHeight: 1.08
    letterSpacing: "-0.025em"
  title:
    fontFamily: "Bahnschrift SemiBold, Trebuchet MS, sans-serif"
    fontSize: "1.375rem"
    lineHeight: 1.2
    letterSpacing: "-0.02em"
  subtitle:
    fontFamily: "Aptos, Segoe UI, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 700
    lineHeight: 1.3
  body:
    fontFamily: "Aptos, Segoe UI, sans-serif"
    fontSize: "1rem"
    lineHeight: 1.55
  body-sm:
    fontFamily: "Aptos, Segoe UI, sans-serif"
    fontSize: "0.875rem"
    lineHeight: 1.45
  label:
    fontFamily: "Aptos, Segoe UI, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 700
    lineHeight: 1.2
  meta:
    fontFamily: "Aptos, Segoe UI, sans-serif"
    fontSize: "0.8125rem"
    fontWeight: 400
    lineHeight: 1.35
  caption:
    fontFamily: "Aptos, Segoe UI, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 700
    lineHeight: 1.2
    letterSpacing: "0.12em"
  data-xl:
    fontFamily: "Bahnschrift SemiBold, Trebuchet MS, sans-serif"
    fontSize: "1.75rem"
    lineHeight: 1.05
    fontFeature: "tnum"
  data-md:
    fontFamily: "Aptos, Segoe UI, sans-serif"
    fontSize: "1.125rem"
    fontWeight: 700
    lineHeight: 1.2
    fontFeature: "tnum"
  data:
    fontFamily: "Aptos, Segoe UI, sans-serif"
    fontSize: "0.9375rem"
    lineHeight: 1.4
    fontFeature: "tnum"
  mono:
    fontFamily: "Consolas, SFMono-Regular, monospace"
    fontSize: "0.9375rem"
    fontWeight: 700
    letterSpacing: "0.06em"
rounded:
  sm: "14px"
  md: "18px"
  field: "20px"
  card: "24px"
  panel: "30px"
  pill: "999px"
spacing:
  "1": "4px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "5": "20px"
  "6": "24px"
  "8": "32px"
  "10": "40px"
  "12": "48px"
components:
  button-primary:
    backgroundColor: "{colors.action-blue}"
    textColor: "#ffffff"
    rounded: "{rounded.pill}"
    padding: "0 16px"
    height: "2.75rem"
    typography: "{typography.label}"
  button-ghost:
    backgroundColor: "{colors.surface-glass}"
    textColor: "{colors.trust-blue-deep}"
    rounded: "{rounded.pill}"
    padding: "0 16px"
    height: "2.75rem"
    typography: "{typography.label}"
  button-danger:
    backgroundColor: "{colors.surface-glass}"
    textColor: "{colors.rose-alert-text}"
    rounded: "{rounded.pill}"
    padding: "0 16px"
    height: "2.75rem"
  button-disabled:
    backgroundColor: "{colors.state-disabled-bg}"
    textColor: "{colors.muted-ink}"
    rounded: "{rounded.pill}"
    height: "2.75rem"
  chip-selected:
    backgroundColor: "{colors.state-selected-bg}"
    textColor: "{colors.trust-blue-deep}"
    rounded: "{rounded.pill}"
    height: "2.75rem"
  badge:
    rounded: "{rounded.pill}"
    padding: "4px 12px"
    height: "1.75rem"
    typography: "{typography.label}"
  badge-pending:
    backgroundColor: "{colors.state-pending-bg}"
    textColor: "{colors.slate}"
    rounded: "{rounded.pill}"
  badge-atypical:
    backgroundColor: "{colors.state-atypical-bg}"
    textColor: "{colors.amber-attention-text}"
    rounded: "{rounded.pill}"
  input:
    backgroundColor: "#ffffff"
    textColor: "{colors.ink-navy}"
    rounded: "{rounded.field}"
    padding: "0 16px"
    height: "3rem"
  panel:
    backgroundColor: "{colors.surface-glass}"
    rounded: "{rounded.panel}"
    padding: "24px"
  nav-link:
    textColor: "{colors.muted-ink}"
    rounded: "{rounded.pill}"
    padding: "12px 20px"
    typography: "{typography.label}"
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
  for the primary action, the active nav link and the current pagination
  page; its stops are darker than the brand blue and green so white labels
  stay above 4.5:1.
- Translucent white panels with a hairline blue border and a diffuse ambient
  shadow, floating over a pale background. Surfaces nested inside a panel are
  flat (white or morning mist) with a hairline and no shadow.
- Pill-shaped controls everywhere (buttons, chips, badges, nav links,
  pagination).
- A condensed geometric display face for headings and key figures over a
  humanist sans body; tabular numerals wherever numbers line up.
- Headings carry their own weight; an eyebrow appears only when it adds
  context the heading lacks.

## Colors

Cool and clinical at the base, with two calm accents and two semantic
signals used sparingly. All values live as CSS custom properties on `:root`
in `frontend-react/src/styles.css` (`--react-*`, `--glyco-*`, `--state-*`).

### Primary
- **Action Blue → Action Green** (`action-blue`, `action-green`): the text-bearing
  action gradient (primary button, active nav link, current page, unread dot).
- **Trust Blue** (`trust-blue`): links, focus accents, checkbox accent, chart
  trend line and the selected point on the trend chart.
- **Deep Trust Blue** (`trust-blue-deep`): text on ghost buttons, chips,
  selected toggles and pagination; select chevrons.
- **Clear Cyan** (`clear-cyan`): focus rings (`0 0 0 4px` at 12–22% alpha)
  and info-state tints.

### Secondary
- **Steady Green** (`steady-green`): "in range" chart segments, stable
  readings and positive badges.
- **Deep Steady Green** (`steady-green-deep`): kept eyebrows and green badge
  text.

### Tertiary
- **Amber Attention** (`amber-attention`, text `amber-attention-text`):
  hyperglycemic attention and atypical days.
- **Rose Alert** (`rose-alert`, text `rose-alert-text`): hypoglycemia,
  destructive actions (revoke, close) and error states.

### Glycemic ranges
One mapping everywhere (charts, legends, chips):
`glyco-low` (rose, text `rose-alert-text`) below 70 mg/dL, `glyco-in-range`
(steady green, text `steady-green-deep`) 70–180, `glyco-high` (amber, text
`amber-attention-text`) above 180, `glyco-very-high` (`#8a5300`, fill only)
above 250. Patient signal chips follow it: hyperglycemic profile → amber,
hypoglycemic profile → rose, in range → green.

### States
- **Pending** (`state-pending-bg` + slate text + 1 px dashed
  `state-pending-border`): analysis not yet run, link requests awaiting a
  decision. Pending is neutral, never amber.
- **Atypical** (`state-atypical-bg` + `amber-attention-text`): one chip
  style for an atypical day on every surface (desktop table, mobile card).
- **Selected** (`state-selected-bg` + `state-selected-border`, deep blue
  text): selected day pill, selected table row, selected mobile card,
  active segmented chip (period / selected day).
- **Disabled** (`state-disabled-bg` + `muted-ink` text): disabled buttons and
  pagination edges; never a washed-out gradient.

### Neutral
- **Morning Mist** (`morning-mist`): page background (under faint cyan and
  green washes) and recessed wells inside panels.
- **Ink Navy** (`ink-navy`): body text and headings.
- **Muted Ink** (`muted-ink`): secondary text, field labels, inactive nav.
- **Slate** (`slate`): soft badges, pending state and metadata.
- **Surface Glass** (`surface-glass`): panels and heroes.
- **Hairline Blue** (`hairline-blue`): default border of panels, fields and
  chips.

### Named Rules
**The Gradient Means Go Rule.** The action gradient marks only the main
action of a region, the active nav link and the current pagination page. One
gradient-filled button per region. Toggles and selection (segmented chips,
day pills, selected rows and cards) use the blue selection tint, never the
gradient.

**The Calm Signal Rule.** Amber and rose appear as tints with dark text
(`amber-attention-text`, `rose-alert-text`), never as large fills, except the
confirm button of a destructive dialog.

**The No Decoration Rule.** No gradients or tone tints on cards that do not
carry a state. A flat tint is allowed only for a real state (atypical prompt,
own message, pending, selected).

## Typography

**Display Font:** Bahnschrift SemiBold (with Trebuchet MS, sans-serif)
**Body Font:** Aptos (with Segoe UI, sans-serif)
**Mono Font:** Consolas (with SFMono-Regular) for patient and doctor codes

**Character:** A condensed, engineered display face gives headings and key
figures a precise, instrument-like voice; the humanist body keeps reading
soft.

### Roles
Every font size in the UI comes from one of these roles (`--type-*`):

| Role | Size / line-height | Use |
|---|---|---|
| display | clamp(2.25rem, 4.2vw, 3.5rem) / 1.0, -0.03em | landing `h1` only |
| headline | clamp(1.75rem, 3vw, 2.5rem) / 1.08, -0.025em | page `h1`s |
| title | 1.375rem / 1.2, -0.02em | panel `h2` |
| subtitle | 1.0625rem / 1.3, Aptos 700 | row and card titles, dialog `h3`, state `h3` |
| body | 1rem / 1.55 | paragraphs, inputs |
| body-sm | 0.875rem / 1.45 | supporting copy, card meta |
| label | 0.875rem / 1.2, 700 | field labels, buttons, nav, chips |
| meta | 0.8125rem / 1.35, 400/600 | timestamps, helpers, table headers, tooltips, `small` |
| caption | 0.75rem / 1.2, 700 | the floor: count badge, kept eyebrows |
| data-xl | 1.75rem / 1.05, Bahnschrift, tabular | latest reading, key figures |
| data-md | 1.125rem / 1.2, Aptos 700, tabular | period range on phones, legend %, card figures |
| data | 0.9375rem / 1.4, tabular | table cells |
| mono | 0.9375rem, Consolas 700, 0.06em | patient and doctor codes |

Weights are 400, 600 and 700 only. Nothing renders below 12 px, chart text
included (axis ticks 12 px, legends and tooltips 14 px). Numbers that align
use `tabular-nums`, and numeric table columns are right-aligned (`is-num`).
Uppercase and letter-spacing are reserved for kept eyebrows; labels, table
headers and chips are sentence case. Panel descriptions stop at 60ch.

### Named Rules
**The Eyebrow Earns Its Place Rule.** A panel opens with its `h2` and an
optional one-line description. Add an eyebrow (caption role, uppercase,
0.12em tracking, steady green deep) only when it gives context the heading
lacks: the audience on the landing page, the kind of conversation above a
user-written title, "Vínculos" above pending requests. Never an eyebrow that
restates the heading ("Período" over "Escolher o período").

## Layout

Content sits in a centered container (max 1240 px, 20 px padding, 16 px
below 900 px). Pages stack panels with a 24 px gap (16 px below 640 px).
Heroes split into a 1.15fr copy column and a 0.85fr visual column (landing
only).

**Page header.** App pages open with a page header on the background, outside
any panel: the `h1` in the headline role plus at most one body line (60ch), no
eyebrow (`.react-page-header`). The homes use it instead of a hero.

**Patient home** is one reading column (max 760 px, centered): page header,
latest reading (data-xl value, meta time and counts, the primary "Registrar
leitura" plus a ghost link to the full panel), atypical-day prompt,
conversations, doctors.

**Doctor home** is triage-first. At ≥1080 px it is a grid
`minmax(0, 2fr) minmax(320px, 1fr)`: the patient list in the main column and a
rail with pending requests, then conversations. The DOM (and phone/focus
order) is pending → conversations → patients. In the rail, the conversation
origin line is hidden below 1280 px. The patient list is a `react-table`
(name, code with an icon copy button, profile chip, numeric columns
right-aligned with `is-num`, an "Abrir painel" row link) and becomes divider
rows below 900 px.

**Patient detail** follows one reading path, patient at 390 px first and
doctor at 1440 px:
1. Page header: "Back" text link above the name `h1`, a meta line
   ("data-07 · 97 medições"; the source file is doctor-only) and the actions.
   Patient: "Registrar leitura" (primary, opens and focuses the entry form) +
   "Baixar relatório" (ghost); doctor: "Baixar relatório" (primary).
2. Period bar (`.react-period-bar`): one panel with the range in data-md
   ("Período: 01/04/1989 – 30/04/1989"), meta lines for the window kind and
   the available history, and ghost actions "Alterar período" (disclosure with
   the date form, open by default when the window is custom or days are
   selected) and "Ver todo o histórico". The adjusted-period notice, the
   selected-day chips and the single pending-analysis note live inside it.
3. Period summary (`.react-period-summary`): key figures (average, days
   observed or day measurements, and the atypical-days action tile that opens
   the multi-select) next to the time-in-range block (donut + legend rows; the
   only place the three percentages appear; in day mode the legend adds the
   reading counts as meta). Two columns at ≥900 px, three figures in a row at
   ≥1080 px. In day mode the `h2` carries the date.
4. Trend, full width, with the period / day segmented control in its header
   and the day strip below; then the extremes-by-hour chart (200 px tall).
5. Data panels (daily indicators, recent records): tables on desktop; below
   640 px each collapses into a closed disclosure ("Evolução diária (30
   dias)") with divider rows.
6. Patient: the manual entry panel, collapsed to its header row. Doctor: the
   "Acesso a este paciente" section with the danger text "Revogar associação".
When the window has no analysed day (only pending days or none), one state
block ("Ainda não há dias analisados neste período", primary "Ver todo o
histórico", plus the atypical-days button) replaces the summary and charts;
the period bar and data panels stay.

Detail grids use two equal columns.

### Spacing scale
4 px base: 4, 8, 12, 16, 20, 24, 32, 40, 48 (`--space-1` … `--space-12`).
- Panel padding 24 px (20 px below 640 px); heroes 32 px, or 24 × 32.
- Panel header to content 16 px; heading to description 4 px.
- Sub-section `h3`: 24 px above, 8 px below.
- Fields: label to control 8 px, field to field 16 px, form to actions 24 px.
- Chip and button clusters: 8 px.
- Interactive targets stay at least 44 px tall.

Breakpoints: 1080 px (heroes collapse, rails stack), 900 px (two-column
grids stack, navigation moves to the drawer), 640 px (phone layout: divider
rows and closed disclosures replace tables, full-width header buttons).
The patient side must work at 390 px without horizontal scroll.

## Elevation & Depth

Soft layers: top-level panels float over the background with one diffuse
ambient shadow; everything nested inside them is flat.

### Shadow Vocabulary
- **Ambient panel** (`0 24px 52px rgba(20, 79, 126, 0.14)`): heroes, panels,
  the notifications popover. Dialogs and menus use their own popover shadow.
- **Button rest** (`0 3px 8px rgba(20, 99, 155, 0.18)`), rising to
  `0 12px 26px rgba(16, 59, 97, 0.14)` with a 1 px lift on hover.
- **Focus ring** (`0 0 0 4px rgba(39, 183, 231, 0.12–0.22)`): fields,
  buttons and icon buttons on focus or hover.
- **Inner highlight** (`inset 0 1px 0 rgba(255, 255, 255, 0.85)`): fields.

Nested surfaces (stat cards, mobile cards) have no shadow and no hover lift;
lists inside panels are divider rows with no surface at all.

## Shapes

Generous, rounded, never sharp. Large containers use 30 px (panels, heroes),
cards and states 24 px, fields 20 px, nested tiles 14–18 px, and every
interactive control is a full pill (999 px). Borders are 1 px hairlines in
translucent blue. Empty and pending states use a dashed hairline.

## Components

### Buttons
Pills with bold 14 px labels, gentle lift on hover.
- **Shape:** full pill (999 px), 2.75 rem tall (compact keeps 44 px height
  with tighter padding).
- **Primary:** blue→green gradient, white label, rest shadow.
- **Hover / Focus:** 1 px upward lift and deeper shadow; focus adds the cyan
  ring.
- **Disabled:** flat `state-disabled-bg` with muted ink text, no shadow.
- **Ghost:** translucent white with deep blue label and blue hairline;
  secondary actions and "back".
- **Danger:** white with rose text and rose hairline; destructive actions,
  always behind a confirmation dialog. **Danger solid** (rose gradient) only
  as that dialog's confirm button.
- **Quiet / Text:** transparent, muted or blue label, for tertiary actions.
- **Danger text:** a text button in rose text for destructive row actions
  (revoke a link); still behind the confirmation dialog, 44 px hit area, never
  the loudest element in the row.
- **Icon-only:** a 20 px drawn icon in a 44 px transparent hit area with an
  `aria-label` (copy code). Icons are inline SVG with a 2 px stroke.

### Chips and Badges
- **Chips:** ghost pills used as filters and removable selections; the active
  chip takes the blue selection tint (`state-selected-bg`, blue border, deep
  blue text).
- **Segmented control** (`.react-segmented`): an exclusive view toggle
  (period / selected day). `role="group"` with `aria-pressed` buttons inside
  one white hairline pill (4 px inset); the pressed button takes the selection
  tint. Right-aligned in the panel header on desktop, full width under the
  heading below 900 px. Never the gradient.
- **Badges:** small pills (1.75 rem) in tinted variants (brand, green, blue,
  soft, pending, atypical); counters use a compact round badge (caption).

### Cards / Containers
- **Corner Style:** 30 px panels, 24 px states and cards.
- **Background:** surface glass over morning mist; nested cards flat white or
  morning mist.
- **Shadow Strategy:** ambient shadow on top-level panels only.
- **Border:** hairline blue.
- **Internal Padding:** 24 px (20 px on phones).

### Inputs / Fields
- **Style:** 3 rem tall, 20 px radius, hairline blue border, white fill
  with inner highlight; label above in bold muted 14 px, 8 px gap; textareas
  6 rem minimum.
- **Focus:** border shifts to blue (35%) plus the 4 px cyan ring.
- **Selects:** same shell with a CSS chevron in deep blue.

### Navigation
A rounded topbar (28 px) holding the brand mark and pill nav links in muted
ink (label role); the active link takes the gradient with white text.
Counters attach as compact badges. Below 900 px the links move into a
drawer and the brand tagline is hidden; in the drawer, logout is a quiet
text button below the language switcher. The footer is a single meta-role
line stating that MyGlico does not diagnose.

### Lists, Popovers and Conversation
- **Lists are divider rows, not cards.** Conversations, doctor links,
  pending requests, atypical-day prompts and the phone patient list are rows
  separated by a top hairline with 16 px vertical padding (12 px in prompts);
  no per-row border, fill, radius or shadow. A row whose whole surface opens
  something stretches its visible text link over the row (`::after`), keeps
  the visible label right-aligned on desktop and rings the whole row on
  keyboard focus. Ended items (revoked, rejected, cancelled links) collapse
  behind a `<details>` disclosure ("Vínculos anteriores (n)").
- **Disclosures** (`.react-disclosure`, `.react-disclosure-toggle`): secondary
  content opens on demand behind a `<details>` summary or an
  `aria-expanded` button with a chevron that turns 180°. Uses: the period date
  form, the manual entry form (opened by `#new-reading` or the header CTA),
  its optional fields ("Mais detalhes (opcional)"), and phone data panels,
  whose summary carries the `h2` with a count.
- **Key figures** (`.react-figure`): label (label role), value (data-xl,
  unit in meta), helper (meta); no card. An interactive figure (atypical
  days) is a white hairline tile (18 px) that rings on focus, with its action
  in deep blue; its accessible name is "{label}: {value}. {action}".
- **Inline forms are flat:** a sub-panel opened inside a panel (new
  conversation, doctor search) is bracketed by hairlines with 16 px padding;
  only true overlays (the atypical-day multi-select) keep a surface.
- **Header CTAs follow the content:** a panel's "add / new" action is primary
  only while its list is empty and ghost once there are items.
- **Overlays are opaque:** the drawer and the notifications popover use a
  solid white (or white → morning mist) fill; translucent glass is for
  panels over the page background only.
- **Notification rows are flat:** no per-row card; a hairline between rows,
  12 px vertical padding, `[dot] [label / time] [mark read]` with the text
  button keeping a 44 px hit area. Consecutive notifications about the same
  conversation collapse into one row with a count.
- **Conversation:** the title is the page `h1` (headline role) under a
  "Back" text link; the danger "Close" sits in the header, never beside
  "Send". The message list is a bare scroll area (no well); pagination sits
  above it because older pages come first. Own messages take a flat blue
  tint. Below 640 px the composer sticks to the bottom of the viewport with a
  top hairline.

### Charts
Recharts with 12 px axis ticks, 14 px legends and tooltips. Trend charts start
the Y axis at 0 and end on a round top of at least 300 mg/dL (next multiple
of 50 above the data); the ticks are exactly 0, 70, 180, 250 and that top, so
the reference values read as labels and 250 never collides with the top.
The time-in-range legend uses divider rows, with dot colors from the
`--glyco-*` tokens. Reference lines use the glycemic range colors; the selected
point is a solid trust-blue dot.
A day curve with fewer than 6 readings is drawn as straight segments
(`type="linear"`), never smoothed, so the chart does not suggest values nobody
measured. Legend text is always `--react-text`; color lives in the swatch only.
Series animate only when the user has not asked for reduced motion.

### State Blocks
Empty, loading and error states share one block: icon tile plus copy on a
dashed hairline card (24 px). The tile always carries a drawn SVG glyph that
matches its tone (info, danger, neutral), never an empty square. The patient
detail never opens on an empty window when analysed days exist: the default
period falls back to the latest analysed 30 days and the period bar says how
many newer days still wait for analysis. Pending rows show "–", not 0%.

### Motion
Motion is short (150–220 ms) and functional: hover lift, drawer slide, chart
entry, smooth scroll to an anchor. Under `prefers-reduced-motion: reduce` all
of it becomes instant (no translate, no slide, no chart animation, `auto`
scrolling) while every state change still happens.

### Dialogs
Centered panel over a dimmed backdrop, with header (subtitle `h3`), body
sections and an actions row; confirmation dialogs pair a ghost cancel with
the action.

## Do's and Don'ts

### Do:
- **Do** build every new screen from the panel + `h2` + description
  structure, using the type roles and the spacing scale.
- **Do** use the shared field, button, badge and state primitives instead of
  inline styles.
- **Do** keep the gradient for one primary action per region, the active nav
  link and the current page.
- **Do** put destructive actions in the danger style behind a confirmation
  dialog.
- **Do** show pending status as the neutral dashed chip and atypical status
  as the amber chip, both with dark text.

### Don't:
- **Don't** ship browser-default inputs, square corners or flat `#005fcc`
  buttons; those were the off-system patterns removed in the 2026-10 layout
  review.
- **Don't** add an eyebrow that restates its heading.
- **Don't** set text below 12 px or invent font sizes outside the roles.
- **Don't** use the gradient for toggles or selection.
- **Don't** use emoji as icons.
- **Don't** smooth a curve across sparse readings or ship an animation that
  ignores reduced motion.
- **Don't** leave a disabled primary action without saying what is missing.
- **Don't** fill large areas with amber or rose.
- **Don't** hardcode colors outside the `:root` tokens; alert text uses
  `--react-rose-text` and `--react-amber-text`.
- **Don't** put white text on the light brand `trust-blue`/`steady-green`
  fills; use the action gradient.
