#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Canonical producer of manuscript Figure 4 (symmetry-final, v2).

Author-approved 2026-08 symmetry round. This script is the ACTIVE canonical
producer: it reads the immutable approved-horizontal donor

    scripts/figures/fig04/donor/Figure_04_approved_horizontal.png
    SHA-256 c35d9ed6ccea8d7f6d8ec8ad92d65fb3c5dd2df16d82b015b7a531b2eefc829f

and emits the approved Figure 4 in ONE deterministic pass. It never reads its
own output, and no raster patch is ever applied cumulatively.

The donor itself is the output of the superseded stage
``correct_fig04_type4_horizontal.py`` (archived slide export d595fb36... ->
c35d9ed6...), which established the horizontal Type 4 reading
two -> one -> two, left to right. That stage is retained for provenance; this
script supersedes it as the producer of the shipped asset.

Operations applied to the donor, all lossless:

Type 4 (symmetry)
  * circles translated by integer offsets onto a symmetric lattice:
    UL (0,-9), UR (-1,-9), LL (0,+9), LR (+1,+9), C (+6,+1);
  * all four arrows replaced by ONE donor glyph (the lower-left -> centre
    arrow, axis 45.4195 deg) reused as-is for the two up-right slots and
    vertically MIRRORED - an exact pixel permutation, not a rotation or a
    resample - for the two down-right slots, so the four arrows have equal
    length, equal thickness, equal arrowhead size and mirrored orientation;
  * each arrow placed by integer search so the visible gaps to the two circle
    boundaries are equal and the perpendicular offset from the centre-to-
    centre line is minimal.
  The circle rows move +/-9 px apart because the arrow glyph is a raster
  sprite that cannot be rotated without resampling; squaring the lattice to
  the glyph's own axis is what makes the arrows lie on the centre-to-centre
  lines. Type 4 continues to read horizontally two -> one -> two.

Type 3 (alignment)
  * circles levelled per row by integer dy (the t+2 column sat ~8 px high);
  * arrows re-centred on the connected circle centres with equal gaps;
  * ellipsis dots centred on their columns, spacing equalised, block centred
    between the two lower rows;
  * the six time labels ("t", "t + 1", "t + 2" in both bands) translated
    HORIZONTALLY ONLY, as intact pixel components, to centre them under their
    circle columns: upper -9 / +8 / +7, lower -15 / +1 / +1, dy = 0 for all.
  The ~1 px arrow-length and ellipsis-dot-size variations inherited from the
  slide export are deliberately LEFT UNTOUCHED.

Nothing else changes: Type 1, Type 2, all panel titles, all typology names,
the vertical dividers, every colour, every circle size and the canvas are
preserved pixel-identically, and the output's colour set is a subset of the
donor's (no new colours are introduced).

Ink ownership is a nearest-core Voronoi partition, so every non-pure-white
pixel in a work region is assigned to exactly one drawn element and no
antialiased fringe pixel is orphaned when a component moves.

Usage:
  python make_fig04_symmetry_final.py --out <dir> [--src <donor png>]

Outputs in --out: Figure_04.png, Figure_04.pdf, fig04_symmetry_diff_mask.png,
fig04_symmetry_report.json.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

REPO = Path(__file__).resolve().parents[3]
DEFAULT_DONOR = (REPO / 'scripts' / 'figures' / 'fig04' / 'donor' /
                 'Figure_04_approved_horizontal.png')
DONOR_SHA256 = ('c35d9ed6ccea8d7f6d8ec8ad92d65fb3c5dd2df16d82b015b7a531b2'
                'eefc829f')
EXPECTED_PNG_SHA256 = ('74ea37f0ab54453a7c28895edd381cad3a75c199af88c60de6'
                       '7154721db23484')
CANVAS = (4500, 2531)

PURPLE = (112, 48, 160)
AMBER_D = (255, 188, 1)        # Type 3 saturated row
AMBER_L = (255, 206, 67)       # Type 3 lighter rows


def colour_mask(rgb, colour, tol=60):
    d = np.abs(rgb.astype(int) - np.array(colour, dtype=int)).sum(axis=2)
    return d < tol


def components(mask, min_area=200):
    lab, _n = ndimage.label(mask)
    out = []
    for i, sl in enumerate(ndimage.find_objects(lab), start=1):
        area = int((lab[sl] == i).sum())
        if area < min_area:
            continue
        y0, y1 = sl[0].start, sl[0].stop
        x0, x1 = sl[1].start, sl[1].stop
        out.append({'id': i, 'core_area': area,
                    'bbox': (int(x0), int(y0), int(x1), int(y1))})
    return lab, out


# Type 4: how far the upper and lower circle rows move apart (px, each way).
# The four arrows are one rigid glyph that cannot be rotated without
# resampling, so the circle lattice is squared up to the glyph's own axis
# instead of the other way round. See the report for the derivation.
ROW_SPREAD = 9

T4_REGION = (3400, 940, 4460, 1840)
# Type 3 is split so the t / t+1 / t+2 label bands are excluded: those glyphs
# are text and must stay pixel-identical, so they are never lifted.
T3_SUBREGIONS = [(2280, 840, 3350, 1100), (2280, 1300, 3350, 1900)]
T3_REGION = (2280, 830, 3350, 1900)

# Author-directed candidate-v2 addition: centre the six Type 3 time labels
# under their circle columns by lossless horizontal translation only. Each
# label group ("t", "t + 1", "t + 2") moves as one intact pixel component;
# no glyph is redrawn, resampled, recoloured or retyped, and nothing moves
# vertically.
# x-range starts at 2260 / ends at 3366 so the antialiased fringe columns of
# the two flanking panel dividers (x=2254 and x=3371) are never picked up:
# the dividers must stay pixel-identical.
LABEL_BANDS = [(2260, 1100, 3366, 1200), (2260, 1930, 3366, 2030)]
LABEL_MOVES = {(1100, 0): -9, (1100, 1): +8, (1100, 2): +7,
               (1930, 0): -15, (1930, 1): +1, (1930, 2): +1}
LABEL_GROUP_GAP = 80          # px of white between adjacent label groups


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def owner_map(rgb, cores, region):
    """Assign every non-pure-white pixel in `region` to the nearest core."""
    x0, y0, x1, y1 = region
    sub = cores[y0:y1, x0:x1]
    nonwhite = np.any(rgb[y0:y1, x0:x1] != 255, axis=2)
    _d, idx = ndimage.distance_transform_edt(sub == 0, return_indices=True)
    nearest = sub[idx[0], idx[1]]
    own = np.where(nonwhite, nearest, 0)
    assert (own > 0).sum() == nonwhite.sum(), 'unassigned ink in region'
    full = np.zeros(rgb.shape[:2], dtype=np.int32)
    full[y0:y1, x0:x1] = own
    return full


def sprite_of(rgb, own, key):
    m = (own == key)
    ys, xs = np.nonzero(m)
    y0, y1 = int(ys.min()), int(ys.max()) + 1
    x0, x1 = int(xs.min()), int(xs.max()) + 1
    return {'y0': y0, 'x0': x0, 'mask': m[y0:y1, x0:x1],
            'rgb': rgb[y0:y1, x0:x1].copy()}


def flipv(sp):
    return {'y0': sp['y0'], 'x0': sp['x0'], 'mask': sp['mask'][::-1].copy(),
            'rgb': sp['rgb'][::-1].copy()}


def sprite_stats(sp):
    ys, xs = np.nonzero(sp['mask'])
    v = sp['rgb'][sp['mask']].astype(float)
    # ink coverage on white, normalised so a fully covered pixel weighs 1
    w = 1.0 - v.min(axis=1) / 255.0
    w = w / w.max()
    ys = (ys + sp['y0']).astype(float)
    xs = (xs + sp['x0']).astype(float)
    return (float((xs * w).sum() / w.sum()), float((ys * w).sum() / w.sum()),
            xs, ys, w)


def erase(out, sp):
    ys, xs = np.nonzero(sp['mask'])
    out[ys + sp['y0'], xs + sp['x0']] = 255


def paste(out, sp, dx, dy):
    ys, xs = np.nonzero(sp['mask'])
    out[ys + sp['y0'] + dy, xs + sp['x0'] + dx] = sp['rgb'][ys, xs]


def footprint(sp, dx=0, dy=0):
    ys, xs = np.nonzero(sp['mask'])
    return set(zip((ys + sp['y0'] + dy).tolist(),
                   (xs + sp['x0'] + dx).tolist()))


def level_rows(vals):
    """Integer shifts bringing `vals` onto one line with the minimum residual
    spread, tie-broken by the smallest total movement."""
    best = None
    for base in np.arange(min(vals) - 1.5, max(vals) + 1.5, 0.01):
        s = [int(round(base - v)) for v in vals]
        f = [v + si for v, si in zip(vals, s)]
        key = (round(max(f) - min(f), 6), sum(abs(si) for si in s))
        if best is None or key < best[0]:
            best = (key, s, f)
    return best[1], best[2], best[0][0]


def axis_angle(sp):
    cx, cy, xs, ys, w = sprite_stats(sp)
    D = np.stack([xs - cx, ys - cy], 1)
    cov = (D * w[:, None]).T @ D / w.sum()
    ev, evec = np.linalg.eigh(cov)
    u = evec[:, int(np.argmax(ev))]
    if u[0] < 0:
        u = -u
    return float(np.degrees(np.arctan2(u[1], u[0])))


def place_on_line(sp, A, B, r_src, r_dst):
    """Integer translation putting the sprite's axial ink midpoint at the
    point that equalises the gaps to the two circle boundaries, with zero
    perpendicular offset from the centre-to-centre line."""
    A, B = np.asarray(A, float), np.asarray(B, float)
    v = B - A
    L = float(np.hypot(*v))
    u = v / L
    n = np.array([-u[1], u[0]])
    cx, cy, xs, ys, w = sprite_stats(sp)
    t = (xs - A[0]) * u[0] + (ys - A[1]) * u[1]
    t_c = (cx - A[0]) * u[0] + (cy - A[1]) * u[1]
    # the sprite's own reference point: its centroid slid along the axis to
    # the midpoint of its ink extent. Translating this point onto Q - which
    # lies on the centre-to-centre line - both equalises the two gaps and
    # zeroes the perpendicular offset.
    R = np.array([cx, cy]) + ((t.min() + t.max()) / 2.0 - t_c) * u
    Q = A + ((r_src + L - r_dst) / 2.0) * u
    d = Q - R
    return int(round(d[0])), int(round(d[1])), d, L


def ray_gaps(sp, dx, dy, A, B, r_src, r_dst, thr=0.25):
    """Visible gaps between a placed sprite and the two circle boundaries,
    measured the same way the verifier measures them: along the ray joining
    the circle centres, using the same coverage threshold."""
    ys, xs = np.nonzero(sp['mask'])
    v = sp['rgb'][sp['mask']].astype(float)
    w = 1.0 - v.min(axis=1) / 255.0
    w = w / w.max()
    keep = w > thr
    Y = ys[keep] + sp['y0'] + dy
    X = xs[keep] + sp['x0'] + dx
    ymin, xmin = int(Y.min()), int(X.min())
    grid = np.zeros((int(Y.max()) - ymin + 1, int(X.max()) - xmin + 1), bool)
    grid[Y - ymin, X - xmin] = True
    A, B = np.asarray(A, float), np.asarray(B, float)
    vec = B - A
    L = float(np.hypot(*vec))
    u = vec / L
    ts = np.arange(0.0, L, 0.25)
    P = A[None, :] + ts[:, None] * u[None, :]
    xi = np.round(P[:, 0]).astype(int) - xmin
    yi = np.round(P[:, 1]).astype(int) - ymin
    ok = ((xi >= 0) & (yi >= 0) & (xi < grid.shape[1])
          & (yi < grid.shape[0]))
    hit = np.zeros(ts.shape, bool)
    hit[ok] = grid[yi[ok], xi[ok]]
    idx = np.nonzero(hit)[0]
    if idx.size == 0:
        return None
    return (float(ts[idx[0]]) - r_src, (L - float(ts[idx[-1]])) - r_dst)


def best_offset(sp, dx0, dy0, A, B, r_src, r_dst, span=2):
    """Integer offset near (dx0, dy0) that best equalises the two visible
    gaps, tie-broken by the smallest perpendicular offset from the line."""
    A, B = np.asarray(A, float), np.asarray(B, float)
    vec = B - A
    L = float(np.hypot(*vec))
    u = vec / L
    n = np.array([-u[1], u[0]])
    cx, cy, _xs, _ys, _w = sprite_stats(sp)
    best = None
    for i in range(-span, span + 1):
        for j in range(-span, span + 1):
            dx, dy = dx0 + i, dy0 + j
            g = ray_gaps(sp, dx, dy, A, B, r_src, r_dst)
            if g is None:
                continue
            perp = abs((cx + dx - A[0]) * n[0] + (cy + dy - A[1]) * n[1])
            # both requirements are hard limits, so minimise the worse of
            # the two rather than letting one be traded away for the other
            imb = abs(g[0] - g[1])
            key = (round(max(imb, perp), 6), round(imb + perp, 6))
            if best is None or key < best[0]:
                best = (key, dx, dy, g, perp)
    return best


def build(donor: Path, outdir: Path) -> dict:
    assert sha256(donor) == DONOR_SHA256, 'src is not the immutable approved-horizontal Figure 4 donor'
    im = Image.open(donor)
    assert im.size == CANVAS and im.mode == 'RGB'
    src = np.array(im)
    rgb = src
    out = src.copy()
    log = {'donor_sha256': DONOR_SHA256, 'row_spread': ROW_SPREAD,
           'type4': {}, 'type3': {}}

    # =================================================== TYPE 4 cores
    m4 = colour_mask(rgb, PURPLE, tol=90)
    m4[:, :3378] = False
    m4[:900, :] = False
    lab4, comps4 = components(m4, min_area=300)
    assert len(comps4) == 9, f'expected 9 Type 4 components, got {len(comps4)}'
    cores4 = np.zeros(rgb.shape[:2], np.int32)
    for k, c in enumerate(comps4, start=1):
        cores4[lab4 == c['id']] = k
    own4 = owner_map(rgb, cores4, T4_REGION)

    recs = []
    for k in range(1, 10):
        sp = sprite_of(rgb, own4, k)
        cx, cy, xs, ys, w = sprite_stats(sp)
        recs.append({'k': k, 'sp': sp, 'cx': cx, 'cy': cy,
                     'ink': float(w.sum())})
    recs.sort(key=lambda d: -d['ink'])
    circles, arrows = recs[:5], recs[5:]

    xmid = sorted(c['cx'] for c in circles)[2]
    UL, LL = sorted([c for c in circles if c['cx'] < xmid - 50],
                    key=lambda c: c['cy'])
    UR, LR = sorted([c for c in circles if c['cx'] > xmid + 50],
                    key=lambda c: c['cy'])
    C = [c for c in circles if abs(c['cx'] - xmid) <= 50][0]
    named = {'UL': UL, 'LL': LL, 'UR': UR, 'LR': LR, 'C': C}
    for t, c in named.items():
        c['r'] = float(np.sqrt(c['ink'] / np.pi))

    # --- target lattice: level the right column, then centre the middle disc
    rx = (UR['cx'] + LR['cx']) / 2.0
    moves4 = {'UL': (0, -ROW_SPREAD),
              'UR': (int(round(rx - UR['cx'])), -ROW_SPREAD),
              'LL': (0, +ROW_SPREAD),
              'LR': (int(round(rx - LR['cx'])), +ROW_SPREAD)}
    newpos = {t: (named[t]['cx'] + moves4[t][0], named[t]['cy'] + moves4[t][1])
              for t in ('UL', 'UR', 'LL', 'LR')}
    tx = float(np.mean([newpos[t][0] for t in newpos]))
    ty = float(np.mean([newpos[t][1] for t in newpos]))
    moves4['C'] = (int(round(tx - C['cx'])), int(round(ty - C['cy'])))
    newpos['C'] = (C['cx'] + moves4['C'][0], C['cy'] + moves4['C'][1])

    halfw = (newpos['UR'][0] - newpos['UL'][0]) / 2.0
    halfh = (newpos['LL'][1] - newpos['UL'][1]) / 2.0
    target_ang = float(np.degrees(np.arctan2(halfh, halfw)))
    cand = [(a, axis_angle(a['sp'])) for a in arrows]
    donor, donor_ang = min(cand, key=lambda t: abs(abs(t[1]) - target_ang))
    down = donor['sp'] if donor_ang > 0 else flipv(donor['sp'])
    up = flipv(down)
    log['type4'].update({
        'arrow_axis_angles_before': [round(a, 4) for _, a in cand],
        'donor_arrow_angle_deg': round(donor_ang, 4),
        'target_lattice_angle_deg': round(target_ang, 4),
        'donor_arrow_origin_bbox': [int(donor['sp']['x0']),
                                    int(donor['sp']['y0'])],
        'circle_moves': {k: list(v) for k, v in moves4.items()},
        'new_centres': {k: [round(v[0], 4), round(v[1], 4)]
                        for k, v in newpos.items()},
        'radii': {t: round(named[t]['r'], 4) for t in named}})

    for rec in recs:
        erase(out, rec['sp'])
    fps = []
    for t in ('UL', 'UR', 'LL', 'LR', 'C'):
        dx, dy = moves4[t]
        paste(out, named[t]['sp'], dx, dy)
        fps.append(footprint(named[t]['sp'], dx, dy))

    arrow_log = {}
    for s, d, sense in (('UL', 'C', 'down'), ('LL', 'C', 'up'),
                        ('C', 'UR', 'up'), ('C', 'LR', 'down')):
        sp = down if sense == 'down' else up
        dxi, dyi, dexact, L = place_on_line(
            sp, newpos[s], newpos[d], named[s]['r'], named[d]['r'])
        key, dxi, dyi, g, perp = best_offset(
            sp, dxi, dyi, newpos[s], newpos[d], named[s]['r'], named[d]['r'])
        paste(out, sp, dxi, dyi)
        fps.append(footprint(sp, dxi, dyi))
        arrow_log[f'{s}->{d}'] = {
            'sense': sense, 'dx': dxi, 'dy': dyi, 'line_len': round(L, 4),
            'gap_src': round(g[0], 4), 'gap_dst': round(g[1], 4),
            'gap_imbalance': round(g[0] - g[1], 4),
            'perp_offset': round(perp, 4),
            'analytic_residual_px': [round(float(dexact[0] - dxi), 4),
                                     round(float(dexact[1] - dyi), 4)]}
    log['type4']['arrows'] = arrow_log
    for i in range(len(fps)):
        for j in range(i + 1, len(fps)):
            assert not (fps[i] & fps[j]), 'Type 4 elements overlap'

    # =================================================== TYPE 3 cores
    cores3 = np.zeros(rgb.shape[:2], np.int32)
    key = 0
    kinds = {}
    for col in (AMBER_D, AMBER_L):
        m = colour_mask(rgb, col, tol=45)
        m[:, :2254] = False
        m[:, 3372:] = False
        m[:800, :] = False
        lab, comps = components(m, min_area=150)
        for c in comps:
            key += 1
            cores3[lab == c['id']] = key
            kinds[key] = 'circle' if c['core_area'] > 20000 else 'arrow'
    blk = (rgb.sum(axis=2) < 200)
    blk[:, :2254] = False
    blk[:, 3372:] = False
    band = np.zeros_like(blk)
    band[1520:1700, :] = True
    labd, compsd = components(blk & band, min_area=60)
    for c in compsd:
        key += 1
        cores3[labd == c['id']] = key
        kinds[key] = 'dot'
    assert sum(v == 'circle' for v in kinds.values()) == 9
    assert sum(v == 'arrow' for v in kinds.values()) == 6
    assert sum(v == 'dot' for v in kinds.values()) == 9

    own3 = np.zeros(rgb.shape[:2], np.int32)
    for reg in T3_SUBREGIONS:
        o = owner_map(rgb, cores3, reg)
        own3 = np.maximum(own3, o)
    present = set(np.unique(own3).tolist()) - {0}
    assert present == set(kinds), 'a Type 3 core fell outside the subregions'

    t3 = {'circle': [], 'arrow': [], 'dot': []}
    for k, kind in kinds.items():
        sp = sprite_of(rgb, own3, k)
        cx, cy, xs, ys, w = sprite_stats(sp)
        t3[kind].append({'k': k, 'sp': sp, 'cx': cx, 'cy': cy,
                         'ink': float(w.sum()),
                         'r': float(np.sqrt(w.sum() / np.pi))})

    rows3 = {}
    for c in t3['circle']:
        rows3.setdefault(round(c['cy'] / 200), []).append(c)
    row_keys = sorted(rows3)
    xs_all = sorted(c['cx'] for c in t3['circle'])
    colx = [float(np.mean(xs_all[0:3])), float(np.mean(xs_all[3:6])),
            float(np.mean(xs_all[6:9]))]

    moves3 = {'circles': [], 'arrows': [], 'dots': []}
    row_y = {}
    for k in row_keys:
        cs = sorted(rows3[k], key=lambda d: d['cx'])
        shifts, finals, spread = level_rows([c['cy'] for c in cs])
        row_y[k] = float(np.mean(finals))
        for c, sdy, fy in zip(cs, shifts, finals):
            c['dy'], c['new_cy'] = sdy, fy
            moves3['circles'].append(
                {'row': int(k), 'cx': round(c['cx'], 3),
                 'cy_before': round(c['cy'], 3), 'dx': 0, 'dy': int(sdy),
                 'cy_after': round(fy, 3)})
        rows3[k] = cs
        log['type3'].setdefault('row_spread_after', {})[str(k)] = round(
            spread, 4)

    for kind in ('circle', 'arrow', 'dot'):
        for rec in t3[kind]:
            erase(out, rec['sp'])
    for k in row_keys:
        for c in rows3[k]:
            paste(out, c['sp'], 0, c['dy'])

    used = set()
    for k in row_keys:
        cs = rows3[k]
        for i in range(2):
            s, d = cs[i], cs[i + 1]
            mid = (s['cx'] + d['cx']) / 2.0
            a = min((z for z in t3['arrow'] if z['k'] not in used),
                    key=lambda z: (z['cx'] - mid) ** 2
                    + (z['cy'] - row_y[k]) ** 2)
            used.add(a['k'])
            cx, cy, xs, ys, w = sprite_stats(a['sp'])
            dx = (((s['cx'] + s['r']) + (d['cx'] - d['r'])) / 2.0
                  - (xs.min() + xs.max()) / 2.0)
            dy = (s['new_cy'] + d['new_cy']) / 2.0 - cy
            dxi, dyi = int(round(dx)), int(round(dy))
            A = (s['cx'], s['new_cy'])
            B = (d['cx'], d['new_cy'])
            _k, dxi, dyi, g, perp = best_offset(
                a['sp'], dxi, dyi, A, B, s['r'], d['r'])
            paste(out, a['sp'], dxi, dyi)
            moves3['arrows'].append(
                {'row': int(k), 'pair': i, 'cx_before': round(a['cx'], 3),
                 'cy_before': round(a['cy'], 3), 'dx': dxi, 'dy': dyi,
                 'gap_src': round(g[0], 4), 'gap_dst': round(g[1], 4),
                 'gap_imbalance': round(g[0] - g[1], 4),
                 'perp_offset': round(perp, 4)})

    e_mid = (row_y[row_keys[1]] + row_y[row_keys[2]]) / 2.0
    cols = {}
    for d in t3['dot']:
        cols.setdefault(min(range(3),
                            key=lambda i: abs(d['cx'] - colx[i])), []).append(d)
    pitch0 = float(np.mean([(max(z['cy'] for z in v) - min(z['cy'] for z in v))
                            / 2.0 for v in cols.values()]))
    for v in cols.values():
        v.sort(key=lambda d: d['cy'])
    # Integer shifts quantise each dot, so the achievable spacing symmetry
    # depends on the pitch chosen. Search the pitch that minimises the worst
    # residual across all nine dots (spacing imbalance within a column, and
    # disagreement of dot heights between columns).
    best_p = None
    for p in np.arange(pitch0 - 1.0, pitch0 + 1.0, 0.01):
        finals = []
        worst_imb = 0.0
        for v in cols.values():
            f = [d['cy'] + round(t - d['cy'])
                 for d, t in zip(v, [e_mid - p, e_mid, e_mid + p])]
            finals.append(f)
            worst_imb = max(worst_imb, abs((f[0] + f[2]) - 2 * f[1]))
        spread = max(max(f[i] for f in finals) - min(f[i] for f in finals)
                     for i in range(3))
        centre_err = max(abs((f[0] + f[2]) / 2.0 - e_mid) for f in finals)
        key = (round(max(worst_imb, spread), 6), round(centre_err, 6))
        if best_p is None or key < best_p[0]:
            best_p = (key, float(p))
    pitch = best_p[1]
    log['type3']['ellipsis_pitch_search'] = {
        'pitch0': round(pitch0, 4), 'pitch_chosen': round(pitch, 4),
        'worst_residual_px': round(best_p[0][0], 4)}
    for ci, v in cols.items():
        for d, ty_ in zip(v, [e_mid - pitch, e_mid, e_mid + pitch]):
            dx, dy = colx[ci] - d['cx'], ty_ - d['cy']
            dxi, dyi = int(round(dx)), int(round(dy))
            paste(out, d['sp'], dxi, dyi)
            moves3['dots'].append(
                {'col': int(ci), 'cx_before': round(d['cx'], 3),
                 'cy_before': round(d['cy'], 3), 'dx': dxi, 'dy': dyi,
                 'residual_px': [round(float(dx - dxi), 4),
                                 round(float(dy - dyi), 4)]})
    # ---- Type 3 time labels: horizontal translation of intact components
    label_log = []
    for x0, y0, x1, y1 in LABEL_BANDS:
        band = np.zeros(rgb.shape[:2], bool)
        band[y0:y1, x0:x1] = np.any(rgb[y0:y1, x0:x1] != 255, axis=2)
        lab, _n = ndimage.label(band, structure=np.ones((3, 3), int))
        objs = ndimage.find_objects(lab)
        comps = [{'id': i, 'x0': s[1].start, 'x1': s[1].stop}
                 for i, s in enumerate(objs, start=1) if s is not None]
        comps.sort(key=lambda c: c['x0'])
        groups, cur = [], [comps[0]]
        for c in comps[1:]:
            if c['x0'] - max(z['x1'] for z in cur) > LABEL_GROUP_GAP:
                groups.append(cur)
                cur = [c]
            else:
                cur.append(c)
        groups.append(cur)
        assert len(groups) == 3, (
            'expected 3 label groups in band %d, got %d' % (y0, len(groups)))
        cores = np.zeros(rgb.shape[:2], np.int32)
        for gi, g in enumerate(groups, start=1):
            cores[np.isin(lab, [c['id'] for c in g])] = gi
        own = owner_map(rgb, cores, (x0, y0, x1, y1))
        for gi, g in enumerate(groups):
            sp = sprite_of(rgb, own, gi + 1)
            dx = LABEL_MOVES[(y0, gi)]
            bx0 = sp['x0']
            bx1 = sp['x0'] + sp['mask'].shape[1]
            erase(out, sp)
            paste(out, sp, dx, 0)
            label_log.append({
                'band': int(y0), 'group': int(gi), 'dx': int(dx), 'dy': 0,
                'bbox_before': [int(bx0), int(sp['y0']), int(bx1),
                                int(sp['y0'] + sp['mask'].shape[0])],
                'cx_bbox_before': round((bx0 + bx1 - 1) / 2.0, 3),
                'cx_bbox_after': round((bx0 + bx1 - 1) / 2.0 + dx, 3),
                'column_x': round(colx[gi], 3),
                'offset_after': round((bx0 + bx1 - 1) / 2.0 + dx - colx[gi],
                                      3)})
    log['type3'].update({'moves': moves3, 'label_moves': label_log,
                         'column_x': [round(x, 4) for x in colx],
                         'ellipsis_centre_y': round(e_mid, 4),
                         'ellipsis_pitch': round(pitch, 4)})

    # =================================================== locality / outputs
    outdir.mkdir(parents=True, exist_ok=True)
    diff = np.any(src != out, axis=-1)
    log['changed_pixels_total'] = int(diff.sum())
    outside = diff.copy()
    for x0, y0, x1, y1 in ([T4_REGION] + T3_SUBREGIONS + LABEL_BANDS):
        outside[y0:y1, x0:x1] = False
    log['changed_pixels_outside_work_regions'] = int(outside.sum())
    assert outside.sum() == 0, 'edit escaped the work regions'
    log['changed_pixels_type1_type2'] = int(diff[:, :2248].sum())
    assert diff[:, :2248].sum() == 0, 'Type 1 / Type 2 changed'

    Image.fromarray(out, mode='RGB').save(
        outdir / 'Figure_04.png')
    Image.fromarray((diff * 255).astype(np.uint8), mode='L').save(
        outdir / 'fig04_symmetry_diff_mask.png')

    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    h, w = out.shape[0], out.shape[1]
    fig = plt.figure(figsize=(15.0, 15.0 * h / w), dpi=300)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(out, interpolation='none')
    ax.axis('off')
    fig.savefig(outdir / 'Figure_04.pdf',
                metadata={'CreationDate': None, 'Producer': None,
                          'Creator': 'SCORCH figure04 symmetry candidate'})
    plt.close(fig)

    log['output_png_sha256'] = sha256(
        outdir / 'Figure_04.png')
    (outdir / 'fig04_symmetry_report.json').write_text(
        json.dumps(log, indent=1))
    return log


def main() -> None:
    ap = argparse.ArgumentParser(
        description='Canonical producer of manuscript Figure 4 (v2).')
    ap.add_argument('--out', required=True,
                    help='output directory for Figure_04.png/.pdf')
    ap.add_argument('--src', default=str(DEFAULT_DONOR),
                    help='immutable approved-horizontal donor PNG')
    args = ap.parse_args()
    donor = Path(args.src).resolve()
    outdir = Path(args.out).resolve()
    if not donor.is_file():
        raise SystemExit(f'donor not found: {donor}')
    log = build(donor, outdir)
    print(json.dumps(log, indent=1))
    if log['output_png_sha256'] != EXPECTED_PNG_SHA256:
        raise SystemExit(
            'output PNG sha256 %s != approved %s'
            % (log['output_png_sha256'], EXPECTED_PNG_SHA256))


if __name__ == '__main__':
    main()
