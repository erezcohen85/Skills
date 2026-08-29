---
name: duplicate-to-vector
description: Use when asked to duplicate, recreate, trace, vectorize or "make an exact/perfect copy" of a logo, image, drawing or lettering as SVG / vector / editable paths / 3D-print outline — especially when the source is a raster (jpg/png), the text uses a font you cannot identify, or the user says the copy must be pixel-accurate. Invoked as "Duplicate to Vector N" where N = allowed self-test iterations.
---

# Duplicate to Vector

## Overview

A "perfect copy" of a picture is a **measured** copy: trace the real pixels, render the
result, diff it against the original, fix the worst regions, repeat. Never redraw from
memory, never substitute a look-alike font, never declare done without a diff score.

**Violating the letter of these rules is violating the spirit.** A hand-drawn "close"
paw or a Google-Fonts stand-in for a brush script is not a copy — it is a guess.

## Invocation

`Duplicate to Vector N` (also "duplicate to vector", "perfect copy", "trace this logo").
`N` = max self-test+fix iterations the user allows. No N given → N = 3. `N = 0` → one
trace, one self-test, report score, no fixing. Splitting elements with `--split` is a
structural step, not an accuracy iteration — it does NOT count against N; do it last.

## Tools (in this skill's `scripts/`; needs python3 + Pillow, numpy, scipy, pypotrace, Chrome)

| Script | Does |
|---|---|
| `trace.py IMG --sample` | prints dominant colors → pick the palette |
| `trace.py IMG --colors "#hex,#hex" --bg "#hex" --out X.svg [--blur --close --turd --tol --split]` | one potrace path per color; `--split` JSON cuts named elements (scissors, comb, title…) out of a color layer |
| `selftest.py IMG X.svg --colors "#hex,#hex,#hex" [--target 1.0 --tolpx 1]` | renders X.svg with headless Chrome, prints mismatch %, per-color IoU, worst grid cells; writes `X.render.png` + `X.diff.png` (red = missing, blue = extra) |

`python3 scripts/trace.py --help` for every flag. Per-color overrides: `--close "#f272b3=7"`.

## Procedure

1. **Read the source image** (Read tool) and note every distinct element and color.
2. **Palette**: `trace.py IMG --sample`. Choose 2–5 flat colors that cover the picture
   (glitter/gradient → its one mean color). `--bg` = the color the art is drawn ON (the
   disc/paper), even if it is not the most common color; if the true outside color equals
   an art color (black corners + black line art) that is fine — it becomes part of that
   layer. Include bg in `selftest --colors`.
3. **Trace, iteration 0**: `trace.py … --out work/v0.svg`. Defaults: blur 0.8, turd 4.
   Noisy fills (glitter, jpeg) → `--close 7` for that color only.
4. **Self-test**: `selftest.py IMG work/v0.svg --colors …`. Then **Read `v0.diff.png` and
   `v0.render.png`** — the number says how bad, the diff says where and what kind:
   - red thin strokes / teeth / serifs missing → lower `--blur` (0.4), lower `--turd` (2)
   - blue blobs / merged letters → raise `--blur`, or `--close` too high
   - a whole element the wrong color → palette / `--tol` (keep 80–100; extremes lose edges)
   - holes inside a fill (glitter) → `--close 7…9` on that color. **Intent beats score
     here**: the original's specks are real pixels, so the score may RISE when you close
     them. Keep the closed version when the fill is clearly meant to be flat (glitter,
     halftone, jpeg noise) and report both scores; a 3D print wants the flat fill.
   - two elements traced as one path but user wants them separate → `--split` regions
     (find coordinates from the worst-cell boxes and the original)
5. **Iterate ≤ N times**: change **one parameter per iteration**, keep the best-scoring
   SVG (except the glitter/intent case above), log `iteration, change, mismatch%` in a table. Stop early when
   `mismatch ≤ target` (default 1.0 % at `--tolpx 1`; jpeg sources bottom out ≈1.3 %, so
   for jpeg use `--tolpx 2` where ≤1 % is reachable). `selftest.py` exits 1 while above
   target — that is the loop signal, not an error.
6. **Split** (free, after the loop) when the user wants separately editable elements:
   write a `--split` JSON with a rect/circle per element (scissors, comb, title…), choosing
   cut lines in the gaps you see in the original; re-run trace with the winning flags and
   re-run selftest once to confirm the score held.
7. **Deliver**: best SVG (path ids = color hex, or element names when split), the score table, and the
   final `diff.png` so the user sees the residual. If the user wants an editable canvas,
   feed the paths into `/design` artboards (one absolutely-positioned `<svg>` per element).
   If they want 3D: paths are ready for OpenSCAD `import("x.svg")` + `linear_extrude`.

## Quick reference — what "good" looks like

| Source | Realistic floor (tolpx 1) | Typical fix count |
|---|---|---|
| clean PNG, flat colors | < 0.3 % | 0–1 |
| jpeg logo, flat colors | 1.0–1.5 % | 1–2 |
| jpeg with glitter/gradient fills | 1.3–2 % | 2–3 (`--close`) |

## Red flags — STOP, you are guessing

- "I'll approximate this with a similar Google Font" → trace the letters.
- "I'll draw the paw / scroll / icon with ellipses and bezier guesses" → trace it.
- "Looks right, publishing" without a `selftest` score and without Reading the diff.
- Score went UP after a change and you kept the change → revert (sole exception: the
  glitter/intent case, reported with both scores); one change per iteration.
- Changing 3 flags at once "to save an iteration" → you cannot tell which one helped.
- Tracing came out inverted (fill covers the whole board, art shows as holes) → the mask
  polarity flipped; `trace.py` handles potrace's inverted numpy convention — do not
  hand-fix by adding `fill-rule` tricks.

| Excuse | Reality |
|---|---|
| "Font is fine, close enough" | User asked for perfect. Letterforms are pixels; trace them. |
| "N iterations is too few" | Do the N, report residual honestly, ask for more. |
| "Diff is only edges" | Read the diff image; edge halo is fine, missing comb teeth are not. |
| "Chrome render is slow" | 3 s. Skipping it is how inverted paths ship. |

## Common mistakes

- Forgetting bg color in `selftest --colors` → everything outside art counts as mismatch.
- Cutting a `--split` rect through an element that touches another (scissors tip on the
  scroll) → look at the original crop first, choose the cut line in the gap.
- Comparing at the wrong size: the SVG viewBox must equal the image pixel size (default).
