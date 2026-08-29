#!/usr/bin/env python3
"""Self-test: rasterize an SVG with headless Chrome, compare to the original raster.

Usage:
  selftest.py ORIGINAL.jpg TRACED.svg --colors "#000000,#f272b3,#ffffff" [--target 1.0] [--tolpx 1] [--grid 8]

Prints:
  mismatch %  (pixels whose palette class differs, after --tolpx dilation tolerance)
  per-color IoU
  worst grid cells (row,col, mismatch %) -> where to look
Writes:
  TRACED.render.png   (what the SVG actually looks like)
  TRACED.diff.png     (red = original has it, blue = trace has it, grey = match)
Exit 0 if mismatch <= --target else 1.
"""
import argparse, subprocess, sys, os, shutil
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

CHROME = ["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", "google-chrome", "chromium", "chrome"]


def hex2rgb(h):
    h = h.lstrip('#'); return np.array([int(h[i:i+2], 16) for i in (0, 2, 4)])


def render(svg, w, h, out):
    exe = next((c for c in CHROME if os.path.exists(c) or shutil.which(c)), None)
    if not exe: raise SystemExit("no Chrome found for rasterizing; install Chrome or rasterize another way")
    html = os.path.abspath(svg) + ".html"
    open(html, 'w').write(f'<body style="margin:0;background:#fff"><img src="file://{os.path.abspath(svg)}" style="width:{w}px;height:{h}px;display:block"></body>')
    subprocess.run([exe, "--headless=new", "--hide-scrollbars", "--force-device-scale-factor=1",
                    f"--window-size={w},{h}", f"--screenshot={os.path.abspath(out)}", f"file://{html}"],
                   check=True, capture_output=True, timeout=60)
    os.remove(html)


def classify(arr, pal):
    d = np.linalg.norm(arr[:, :, None, :] - pal[None, None, :, :], axis=3)
    return d.argmin(axis=2)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('original'); ap.add_argument('svg'); ap.add_argument('--colors', required=True)
    ap.add_argument('--target', type=float, default=1.0); ap.add_argument('--tolpx', type=int, default=1)
    ap.add_argument('--grid', type=int, default=8); ap.add_argument('--median', type=int, default=3)
    a = ap.parse_args()

    orig = Image.open(a.original).convert('RGB'); W, H = orig.size
    base = a.svg.rsplit('.', 1)[0]
    render_png = base + '.render.png'; render(a.svg, W, H, render_png)
    rend = Image.open(render_png).convert('RGB').resize((W, H))

    colors = [c.strip().lower() for c in a.colors.split(',')]
    pal = np.array([hex2rgb(c) for c in colors])
    if a.median > 1:  # tame jpeg / glitter noise in the reference the same way for both
        orig = orig.filter(ImageFilter.MedianFilter(a.median)); rend = rend.filter(ImageFilter.MedianFilter(a.median))
    co = classify(np.asarray(orig).astype(int), pal); cr = classify(np.asarray(rend).astype(int), pal)

    # tolerance: a pixel matches if the same class exists within tolpx in the other image
    mis = np.zeros((H, W), bool); diff = np.full((H, W, 3), 235, np.uint8)
    st = ndimage.generate_binary_structure(2, 1)
    for i, c in enumerate(colors):
        o = co == i; r = cr == i
        od = ndimage.binary_dilation(o, st, iterations=a.tolpx) if a.tolpx else o
        rd = ndimage.binary_dilation(r, st, iterations=a.tolpx) if a.tolpx else r
        only_o = o & ~rd; only_r = r & ~od
        mis |= only_o | only_r
        diff[only_o] = (220, 40, 40); diff[only_r] = (40, 80, 220)
        inter = (o & r).sum(); union = (o | r).sum()
        print(f"  {c}: IoU {inter/max(union,1):.3f}   orig {o.sum():7d}px  trace {r.sum():7d}px")
    pct = mis.mean() * 100
    Image.fromarray(diff).save(base + '.diff.png')
    print(f"mismatch: {pct:.2f}%  (target {a.target}%)   render: {render_png}   diff: {base}.diff.png")

    g = a.grid; cells = []
    for gy in range(g):
        for gx in range(g):
            sl = mis[gy*H//g:(gy+1)*H//g, gx*W//g:(gx+1)*W//g]
            cells.append((sl.mean()*100, gy, gx, gx*W//g, gy*H//g, (gx+1)*W//g, (gy+1)*H//g))
    cells.sort(reverse=True)
    print("worst cells (mismatch%, row, col, x0,y0,x1,y1):")
    for m, gy, gx, x0, y0, x1, y1 in cells[:6]:
        if m > 0: print(f"  {m:5.1f}%  r{gy} c{gx}  [{x0},{y0},{x1},{y1}]")
    sys.exit(0 if pct <= a.target else 1)


if __name__ == '__main__':
    main()
