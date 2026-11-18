"""Half-section asset of the viewing chamber (see section_lib.py).

Run after assemble_blender.py: blender -b --python scripts/build_section_vc.py
The generated shell is a closed skin; the section adds the wall thickness, the Ø60 top
opening and the Ø300 bottom opening. The fluorescent screens are the separate part `screen`.
Cutting away the -Y half removes the viewing window and the binocular seat.
"""
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from section_lib import Section

s = Section('vc', mates=('screen',))
HEIGHT = s.height  # 370
TOP_BORE, BOTTOM_BORE, WALL = 30, 150, 14

# Box walls of the generated skin, measured where the cut plane crosses it.
src = np.array([v.co[:] for v in s.source.data.vertices])
slab = src[(np.abs(src[:, 1]) < 40) & (src[:, 2] > 100) & (src[:, 2] < 220)]
X0, X1 = np.percentile(slab[slab[:, 0] < 0, 0], 50), np.percentile(slab[slab[:, 0] > 0, 0], 50)
Y1 = np.median(src[(np.abs(src[:, 0]) < 100) & (src[:, 1] > 150) & (src[:, 2] > 100) & (src[:, 2] < 220), 1])
flat = src[(np.abs(src[:, 0]) > 200) & (np.abs(src[:, 0]) < 280) & (np.abs(src[:, 1]) < 60)]
Z0, Z1 = np.median(flat[flat[:, 2] < 150, 2]), np.median(flat[flat[:, 2] > 250, 2])
print('VC_BOX', [round(float(v), 1) for v in (X0, X1, Y1, Z0, Z1)], flush=True)

def is_attachment(c, n):
    """Side-wall flanges (-X blind flange, +X gauge port) are kept whole."""
    return (c.x < X0 - 3 or c.x > X1 + 3) and Z0 + 15 < c.z < Z1 - 15 and abs(c.y) < 150

def is_inner(c, n):
    """Skin closing the top and bottom openings, and stray geometry inside the box."""
    r = (c.x**2 + c.y**2) ** 0.5
    inside = X0 + 6 < c.x < X1 - 6 and c.y < Y1 - 6 and Z0 + 6 < c.z < Z1 - 8
    return inside or (r < TOP_BORE + 4 and c.z > Z1 - 30) or (r < BOTTOM_BORE + 4 and c.z < Z0 + 25)

s.split_shell(is_attachment, is_inner)

M = 1.0  # housing sits this far inside the skin
box = s.box('vc__housing', 'steel', (X0 + M, 0, Z0 + M), (X1 - M, Y1 - M, Z1 - M), cap='section')
s.carve(box, ('box', (X0 + WALL, -10, Z0 + WALL), (X1 - WALL, Y1 - WALL, Z1 - WALL)),
        ('z', Z1 - WALL - 5, Z1 + 5, TOP_BORE, 0, 0), ('z', Z0 - 5, Z0 + WALL + 5, BOTTOM_BORE, 0, 0))
# Bottom neck and flange down to the camera chamber; top flange carrying the projector lens.
s.solid('vc__neck', 'steel', [(BOTTOM_BORE, 0.4)] + s.outer_profile(0.4, Z0 + M - 0.4) + [(BOTTOM_BORE, Z0 + M - 0.4)], cap='section')
# The cut edge reaches HEIGHT only through the binocular seat fused to the -Y side; the flange itself is lower.
shell = np.array([v.co[:] for v in s.shell.data.vertices])
FLANGE_TOP = float(shell[(shell[:, 1] > 5) & (np.hypot(shell[:, 0], shell[:, 1]) < 205), 2].max())
s.solid('vc__topflange', 'steel', [(TOP_BORE, Z1 - M + 0.4)] + s.outer_profile(Z1 - M + 0.4, FLANGE_TOP - 0.4, floor=60) + [(TOP_BORE, FLANGE_TOP - 0.4)],
        cap='section')

s.finish(hotspots={}, axis=(HEIGHT + 5, -5), view_x=10, ortho=1100)
