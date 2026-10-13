---
target: MyGlico frontend
total_score: 27
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 6
target_identity: "file:C:\\Users\\felip\\orca\\workspaces\\myglico\\doliolid\\frontend-react\\src"
timestamp: 2026-10-13T03-16-22Z
slug: frontend-react-src
---
# Critique: frontend-react/src (2026-10-13, round 3, after dialog + global loading)
Method: dual-agent (A: design review · B: detector + browser) + technical audit 13/20 (was 12/20).

## Heuristics 27/40
1 Status 3 · 2 Real world 2 · 3 Control 3 · 4 Consistency 3 · 5 Error prevention 3 · 6 Recognition 3 · 7 Efficiency 2 · 8 Minimalism 3 · 9 Recovery 3 · 10 Help 2

## Detector
CLI 0. Browser: eyebrow kickers (kept by decision), nested table shells, 2 FP. 0 contrast failures, no overflow, no text < 12px. Dialog bodies are the only scrollers. Global loading appears/disappears correctly; never during 70 s idle.

## Priority issues
- [P1] Global loading can trap the keyboard on a hung request (no timeout, blocks F5/Esc) and swallows typing in search-as-you-type.
- [P1] Focus ring ~1.2:1 (DESIGN.md alpha 12-22%).
- [P1] Conversation opens at the oldest message; notifications don't name the conversation/sender.
- [P1] Doctor profile chip contradicts the numbers (hypo precedence).
- [P1] Full-history trend joins 1991 and 2026 without years/gaps.
- [P1] 2.3 MB hero PNG lazy above the fold; 846 KB single bundle.
- [P2] Atypical popup overloaded + dev jargon; dialog says "Vínculo" to both roles; polling with hidden tab; bell lacks unread count; no per-route title; extremes chart lacks text alternative; ProactivePrompt silent errors.
