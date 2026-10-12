---
target: MyGlico frontend
total_score: 21
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 5
target_identity: "file:C:\\Users\\felip\\orca\\workspaces\\myglico\\doliolid\\frontend-react\\src"
timestamp: 2026-10-12T18-36-41Z
slug: frontend-react-src
---
# Critique: frontend-react/src (2026-10-12)
Method: dual-agent (A: design review · B: detector + browser) + technical audit (12/20).

## Heuristics 21/40
1 Status 2 · 2 Real world 1 · 3 Control 3 · 4 Consistency 2 · 5 Error prevention 2 · 6 Recognition 2 · 7 Efficiency 2 · 8 Minimalism 2 · 9 Recovery 3 · 10 Help 2

## Priority issues
- [P1] White text on blue→green gradient fails AA (2.96–4.27:1); rose count badge 3.45:1. colorize
- [P1] Mobile notifications panel clipped off left edge; items lack context; shared aria-label. adapt + harden
- [P1] Research/clinical jargon on patient screens (recorte analítico, ocorrências críticas, risco > 250, grupos, SHORTID, Aguardando: Paciente). clarify (decision: keep hipo/hiper with plain explanation)
- [P1] Patient journey inverted: no glucose on home, Registrar leitura buried, default window lands on empty pending day. layout + distill
- [P1] Focus/AT: closed drawer focusable under aria-hidden; FilterHelpDialog no focus mgmt; distribution % aria-hidden. harden

## P2 (next round)
Small chart text 9–11px; no prefers-reduced-motion; missing h1 (login/register/investigation); aria-current; live region for polled messages; ProactivePrompt swallowed errors; 823KB bundle; 2.3MB hero PNG; polling in hidden tabs; ~240 raw colors; duplicate CSS blocks; pagination for single page; chart palette drift.

## Persona red flags
Dona Lúcia (68, low vision): 9px labels, "Risco" alarming, revoke button loudest in card. Casey: reading entry 2 screens away. Sam: focus lost in hidden drawer; identical notification names.
