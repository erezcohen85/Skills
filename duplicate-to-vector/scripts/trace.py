#!/usr/bin/env python3
"""Trace a raster image into color-layer SVG paths (potrace per color).

Usage:
  trace.py IMAGE --colors "#000000,#f272b3" --bg "#ffffff" --out OUT.svg [options]
  trace.py IMAGE --sample            # print dominant colors to pick a palette

Options:
  --colors  comma list of hex colors to trace (one path per color)
  --bg      hex color NOT traced (background). Default: most common color.
  --tol     max RGB distance for a pixel to join a color (default 90)
  --blur    gaussian blur radius before threshold, kills jpeg/glitter noise (default 0.8)
  --close   morphological close size (odd int, 0=off). Fills speckle holes in noisy fills (default 0)
  --turd    potrace turdsize: drop specks smaller than N px (default 4)
  --alpha   potrace alphamax corner smoothness 0..1.34 (default 1.0)
  --split   JSON file: [{"name":"scissors","color":"#000000","rect":[x0,y0,x1,y1]}, ...]
            cuts named elements out of a color layer (rect or "circle":[cx,cy,r], "outside":true to invert)
  --scale   output coordinate scale (default 1.0 = image pixels)
Per-color overrides: --blur, --close, --turd accept "COLOR=VAL" pairs, e.g. --close "#f272b3=7"
"""
import argparse, json, sys
import numpy as np
from PIL import Image, ImageFilter
import potrace


def hex2rgb(h):
    h = h.lstrip('#'); return np.array([int(h[i:i+2], 16) for i in (0, 2, 4)])


def parse_per_color(vals, default, colors):
    out = {c: default for c in colors}
    for v in vals or []:
        if '=' in v:
            c, x = v.split('='); out[c.lower()] = float(x)
        else:
            for c in colors: out[c] = float(v)
    return out


def smooth(mask, blur, close):
    m = Image.fromarray((mask * 255).astype(np.uint8))
    if close and close > 1:
        k = int(close) | 1
        m = m.filter(ImageFilter.MaxFilter(k)).filter(ImageFilter.MinFilter(k))
    if blur and blur > 0:
        m = m.filter(ImageFilter.GaussianBlur(blur))
    return np.asarray(m) > 120


def trace_mask(mask, turd, alpha, scale):
    # potrace's numpy binding treats 0 as foreground -> invert
    path = potrace.Bitmap(~mask).trace(turdsize=int(turd), alphamax=alpha, opttolerance=0.3)
    d = []
    for c in path:
        s = c.start_point; d.append(f"M{s.x*scale:.1f} {s.y*scale:.1f}")
        for seg in c:
            e = seg.end_point
            if seg.is_corner:
                k = seg.c; d.append(f"L{k.x*scale:.1f} {k.y*scale:.1f}L{e.x*scale:.1f} {e.y*scale:.1f}")
            else:
                c1, c2 = seg.c1, seg.c2
                d.append(f"C{c1.x*scale:.1f} {c1.y*scale:.1f} {c2.x*scale:.1f} {c2.y*scale:.1f} {e.x*scale:.1f} {e.y*scale:.1f}")
        d.append("Z")
    return "".join(d)


def region_mask(shape, spec):
    H, W = shape
    yy, xx = np.mgrid[0:H, 0:W]
    if 'rect' in spec:
        x0, y0, x1, y1 = spec['rect']; m = (xx >= x0) & (xx < x1) & (yy >= y0) & (yy < y1)
    elif 'circle' in spec:
        cx, cy, r = spec['circle']; m = ((xx - cx) ** 2 + (yy - cy) ** 2) <= r * r
    else:
        raise SystemExit(f"split entry needs rect or circle: {spec}")
    return ~m if spec.get('outside') else m


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('image', help='raster source (jpg/png)')
    ap.add_argument('--sample', action='store_true', help='print dominant colors and exit')
    ap.add_argument('--colors', default='', help='comma list of hex colors to trace, one path each')
    ap.add_argument('--bg', default=None, help='hex color the art is drawn on; emitted as <rect id="bg">, never traced')
    ap.add_argument('--tol', type=float, default=90, help='max RGB distance to join a color (default 90; keep 80-100)')
    ap.add_argument('--out', default=None, help='output .svg (default: IMAGE.svg)')
    ap.add_argument('--blur', action='append', help='gaussian blur before threshold, default 0.8; "#hex=VAL" for one color')
    ap.add_argument('--close', action='append', help='morphological close size (odd), fills speckle holes, default 0; "#hex=7" for one color')
    ap.add_argument('--turd', action='append', help='drop specks smaller than N px, default 4; "#hex=N" for one color')
    ap.add_argument('--alpha', type=float, default=1.0, help='potrace corner smoothness 0..1.34 (default 1.0)')
    ap.add_argument('--split', default=None, help='JSON [{"name","color","rect":[x0,y0,x1,y1]|"circle":[cx,cy,r],"outside":bool}] cuts named elements out of a color layer')
    ap.add_argument('--scale', type=float, default=1.0, help='output coordinate scale (default 1 = image px)')
    a = ap.parse_args()

    im = Image.open(a.image).convert('RGB'); arr = np.asarray(im).astype(int); H, W = arr.shape[:2]

    if a.sample:
        q = (arr // 32) * 32 + 16
        flat = q.reshape(-1, 3); vals, cnt = np.unique(flat, axis=0, return_counts=True)
        order = np.argsort(-cnt)[:12]
        print("dominant colors (quantized, share):")
        for i in order:
            r, g, b = vals[i]; print(f"  #{r:02x}{g:02x}{b:02x}  {cnt[i]/flat.shape[0]*100:5.1f}%")
        return

    colors = [c.strip().lower() for c in a.colors.split(',') if c.strip()]
    if not colors: raise SystemExit("--colors required (or --sample)")
    pal = colors + ([a.bg.lower()] if a.bg else [])
    palrgb = np.array([hex2rgb(c) for c in pal])
    dist = np.linalg.norm(arr[:, :, None, :] - palrgb[None, None, :, :], axis=3)   # H,W,P
    nearest = dist.argmin(axis=2); mind = dist.min(axis=2)
    blur = parse_per_color(a.blur, 0.8, colors); close = parse_per_color(a.close, 0, colors); turd = parse_per_color(a.turd, 4, colors)
    splits = json.load(open(a.split)) if a.split else []

    layers = []  # (name, color, mask)
    for i, c in enumerate(colors):
        mask = (nearest == i) & (mind <= a.tol)
        mask = smooth(mask, blur[c], close[c])
        rest = mask.copy()
        for s in splits:
            if s['color'].lower() != c: continue
            rm = region_mask((H, W), s) & mask
            layers.append((s['name'], c, rm)); rest &= ~rm
        layers.append((c.lstrip('#') if not any(s['color'].lower() == c for s in splits) else f"{c.lstrip('#')}-rest", c, rest))

    ow, oh = W * a.scale, H * a.scale
    parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{ow:g}" height="{oh:g}" viewBox="0 0 {ow:g} {oh:g}">']
    if a.bg: parts.append(f'  <rect id="bg" width="{ow:g}" height="{oh:g}" fill="{a.bg}"/>')
    for name, c, mask in layers:
        n = int(mask.sum())
        if n == 0: print(f"warn: layer {name} empty", file=sys.stderr); continue
        d = trace_mask(mask, turd[c], a.alpha, a.scale)
        parts.append(f'  <path id="{name}" fill="{c}" fill-rule="evenodd" d="{d}"/>')
        print(f"layer {name:<24} color {c}  {n:7d} px  path {len(d):7d} chars")
    parts.append('</svg>')
    out = a.out or a.image.rsplit('.', 1)[0] + '.svg'
    open(out, 'w').write("\n".join(parts)); print("wrote", out)


if __name__ == '__main__':
    main()
