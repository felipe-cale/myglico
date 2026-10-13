---
target: MyGlico frontend
total_score: 27
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 2
target_identity: "file:C:\\Users\\felip\\orca\\workspaces\\myglico\\doliolid\\frontend-react\\src"
timestamp: 2026-10-12T23-19-26Z
slug: frontend-react-src
---
# Critique: frontend-react/src (2026-10-12, after phase 2)
Method: dual-agent (A: design review · B: detector + browser).

## Heuristics 27/40 (was 21)
1 Status 3 · 2 Real world 2 · 3 Control 3 · 4 Consistency 3 · 5 Error prevention 3 · 6 Recognition 3 · 7 Efficiency 3 · 8 Minimalism 2 · 9 Recovery 2 · 10 Help 3

## Detector
CLI 0 findings. Browser: kicker-above-heading x5 + hero-eyebrow-chip (kept eyebrows, by decision), nested-cards x4 (table shells), 1 low-contrast TP (Recharts legend "< 70 mg/dL" #e35d73 3.45:1), 2 FP. 12 font sizes, none < 12px, no overflow. Small targets: info "i" 24px, pagination 42x44.

## Priority issues
- [P1] Patient default window opens empty (only a pending day): fall back to the latest analysed window; pending rows show "–" not 0%; empty state icon.
- [P1] Research vocabulary: "Grupo N", raw "data-07", "Período personalizado de 12958 dias", profile precedence unexplained.
- [P2] Day curve interpolates sparse readings (monotone) — use linear for few readings.
- [P2] Atypical popup overloaded; one gradient per row.
- [P3] Disabled actions without reason; "Encerrar" in header primary zone; no prefers-reduced-motion.
