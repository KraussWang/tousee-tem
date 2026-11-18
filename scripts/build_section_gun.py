"""Half-section asset of the field-emission gun (see section_lib.py).

Run after assemble_blender.py: blender -b --python scripts/build_section_gun.py
Interior z follows the gun hotspots in data/parts.json; dimensions are schematic (C).
The ion pump (+Y side) and the HT cables are kept whole.
"""
import math
import sys
import bmesh
import numpy as np
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from section_lib import Section, rect

s = Section('gun')
DOME_TOP = 296  # the insulator stands on the dome above this

def is_attachment(c, n):
    """HT cable above the insulator and the ion pump with its neck. The cable heading to -Y plugs into
    the cut-away half of the insulator, so it is sectioned with the shell rather than left floating."""
    r = math.hypot(c.x, c.y)
    return c.y > 0 and (c.z > 358 or (c.z > 312 and r > 57) or (r > 166 and 55 < c.z < 220))

def is_inner(c, n):
    """The generated shell is double-walled (outer r 162.7, inner 159.5): drop the inner skin."""
    r = math.hypot(c.x, c.y)
    if not 12 < c.z < 300:
        return False
    if c.z < 236:
        return r < 161
    return (n.x * c.x + n.y * c.y) / max(r, 1e-6) + n.z < 0

s.split_shell(is_attachment, is_inner)

BORE, WALL = 30, 10
outer = s.outer_profile(0.4, DOME_TOP)
dome = [(r - WALL, z) for r, z in reversed(outer) if 244 <= z <= 286]
# Chamber wall, dome and a bottom plate with the Ø60 exit bore.
housing = [(BORE, 0.4)] + outer + [(52, DOME_TOP), (52, 286)] + dome + [(150, 244), (150, 16), (BORE, 16)]
s.solid('gun__housing', 'steel', housing, cap='section')

# Ceramic HT insulator with the emitter module in its conical recess.
s.solid('gun__insulator', 'black', [(0, 302), (20, 302), (40, 276), (50, 276), (50, 356), (0, 356)], cap='section')
s.solid('gun.emitter', 'steel', rect(0, 12, 288, 301.5), [(0, 272), (3, 287.6), (0, 287.6)])  # suppressor cap, ZrO/W tip
# Extractor and the two anodes: dished electrodes with a centre hole, 40 mm apart, each held off the
# chamber wall by short ceramic posts at 0, 90 and 180 degrees (the 0/180 posts are cut on y=0).
R_EL, R_WALL = 120, 150
ELECTRODES = {'gun.extractor': (257, 20), 'gun__anode1': (217, 22), 'gun__anode2': (177, 24)}  # bottom z, hole radius
dome_z, dome_r = zip(*sorted((z, r) for r, z in dome))
posts = bmesh.new()
for name, (z, hole) in ELECTRODES.items():
    s.solid(name, 'steel', [(hole, z), (R_EL, z), (R_EL, z + 6), (hole + 22, z + 6), (hole + 14, z + 11), (hole, z + 11)])
    wall = min(R_WALL, float(np.interp(z + 6, dome_z, dome_r, left=R_WALL))) * math.cos(math.pi / 80) - 1  # inside the faceted wall
    for lo, hi in [((R_EL + 0.5, 0, z), (wall, 6, z + 6)), ((-wall, 0, z), (-R_EL - 0.5, 6, z + 6)),
                   ((-3, R_EL + 0.5, z), (3, wall, z + 6))]:
        cube = bmesh.ops.create_cube(posts, size=1)['verts']
        bmesh.ops.scale(posts, vec=[h - l for l, h in zip(lo, hi)], verts=cube)
        bmesh.ops.translate(posts, vec=[(l + h) / 2 for l, h in zip(lo, hi)], verts=cube)
s.new_object('gun__standoffs', posts, s.mat['black'], s.mat['section'])
# Conical exit down to the bottom flange.
s.solid('gun__exit', 'iron', [(64, 168), (70, 168), (36, 60), (36, 16.4), (BORE, 16.4), (BORE, 60)])

s.finish(hotspots={'gun.emitter': 'gun.emitter', 'gun.extractor': 'gun.extractor'}, housing_samples=s.housing_samples,
         axis=(271, -5), view_x=0, ortho=900)
