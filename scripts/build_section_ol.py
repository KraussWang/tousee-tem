"""Half-section asset of the objective lens (see section_lib.py).

Run after assemble_blender.py: blender -b --python scripts/build_section_ol.py
Interior z follows the ol hotspots in data/parts.json; dimensions are schematic (C).
The pole-piece gap (156-186) takes the goniometer rod from +X and the aperture strip from -X,
so the main winding is split into an upper and a lower half.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from section_lib import PARTS, Section, coil_layers, yoke

s = Section('ol', mates=('gonio',))
HEIGHT = s.height  # 300
GONIO_Y, GONIO_Z = (PARTS['gonio']['datum'][i] - s.part['datum'][i] for i in (1, 2))  # 0.75, 172.9: holder axis
APERTURE_Z = 160

def is_attachment(c, n):
    """Goniometer port flange (+X) and aperture port flange (-X) are kept whole."""
    r = math.hypot(c.x, c.y)
    if c.x > 0:
        # Everything of the Ø240 port flange outside x=200, except the body skin (radial normal) it sits on.
        # The top flange (z > 262, r < 240) also reaches into that circle: drop its rim and underside.
        skin = (n.x * c.x + n.y * c.y) / r > 0.95 and r < (213 if c.z < 262 else 240)
        underside = n.z < -0.9 and c.z > 255
        rad = math.hypot(c.y - GONIO_Y, c.z - GONIO_Z)
        # Close to the body (x < 214) only the flange rim itself (normal radial about the port axis) belongs to it.
        rim = rad > 105 and (n.y * (c.y - GONIO_Y) + n.z * (c.z - GONIO_Z)) / rad > 0.9
        return c.x > 200 and rad < 123 and not skin and not underside and (c.x >= 214 or rim)
    return abs(c.y) < 50 and 125 < c.z < 215 and r > (199 if c.z < 205 else 212)

def is_inner(c, n):
    """Inner skin (r~180) of the generated body; the necks between the double flanges stay."""
    r = math.hypot(c.x, c.y)
    return (r < 183.5 and 22 < c.z < 268) or (r < 150 and 4 < c.z < HEIGHT - 4)

s.split_shell(is_attachment, is_inner)

BORE, WALL_IN = 30, 166
GONIO_PORT, APERTURE_PORT = ('x', 140, 262, 30, GONIO_Y, GONIO_Z), ('x', -240, -140, 14, 0, APERTURE_Z)
housing = [(BORE, 0.4)] + s.outer_profile(0.4, HEIGHT - 0.4) + [(BORE, HEIGHT - 0.4), (BORE, 268), (WALL_IN, 268), (WALL_IN, 26), (BORE, 26)]
s.carve(s.solid('ol__housing', 'steel', housing, cap='section'), GONIO_PORT, APERTURE_PORT)

# Main lens: yoke shell, the two pole pieces closing it toward the axis, split winding.
s.carve(s.solid('ol.coil__yoke', 'iron', [(78, 114), (162, 114), (162, 246), (78, 246), (78, 234), (150, 234), (150, 126), (78, 126)]),
        GONIO_PORT, APERTURE_PORT)
s.solid('ol.upperpole', 'iron', [(34, 246), (77.6, 246), (77.6, 212), (18, 186), (6, 186), (6, 196), (34, 214)])
s.solid('ol.lowerpole', 'iron', [(34, 114), (77.6, 114), (77.6, 138), (18, 156), (6, 156), (6, 150), (34, 136)])
s.solid('ol.coil', 'copper', *coil_layers(82, 147, 128.5, 155.5, 3), *coil_layers(82, 147, 189, 231.5, 5))

# Below the gap: stigmator inside the lower pole bore, objective mini-lens, image-shift rings.
s.ring_coil('ol.stig', 12, 24, 120.5, 133.5)
s.solid('ol.om__yoke', 'iron', yoke(76, 112, 130, 6, t=7, pole=10))
s.solid('ol.om', 'copper', *coil_layers(BORE + 10 + 3, 130 - 7 - 3, 85.5, 102.5, 2))
s.ring_coil('ol.shift1', 40, 104, 53.5, 66.5)
s.ring_coil('ol.shift2', 40, 104, 33.5, 46.5)

# Objective aperture: port tube, holder rod and brass strip just above the lower pole tip (not sectioned).
s.x_cylinder('ol.aperture__port', 'steel', -222, -168, 12, APERTURE_Z, inner=8)  # ends inside the port flange (x -223.5)
s.x_cylinder('ol.aperture__rod', 'steel', -221, -38, 3, APERTURE_Z)
s.strip('ol.aperture', 'brass', -40, 12, 14, APERTURE_Z, ((0, 3), (-12, 5), (-24, 7)), thickness=1.6)  # working hole on the optical axis

spots = {h['id']: h['id'] for h in s.part['hotspots'] if not h['id'].startswith('ol.scan')}  # scan coils: drawn by the web app (V2)
spots.update({'ol.aperture': 'ol.aperture__rod', 'ol.upperpole': ('ol.upperpole', 10), 'ol.lowerpole': ('ol.lowerpole', 10)})
s.finish(hotspots=spots, housing_samples=s.housing_samples, joined=[('ol.aperture', 'ol.aperture__rod')],
         axis=(HEIGHT + 5, -5), view_x=10)
