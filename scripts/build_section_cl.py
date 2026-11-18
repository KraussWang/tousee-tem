"""Half-section asset of the condenser lens: the source exterior shell cut on the
XZ plane (the -Y operator half removed) plus schematic interior parts.

Run after assemble_blender.py: blender -b --python scripts/build_section_cl.py
Interior z follows the cl hotspots in data/parts.json; dimensions are schematic (C).
"""
import math
import sys
from pathlib import Path
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from section_lib import Section, coil_layers, yoke

s = Section('cl')
HEIGHT = s.height  # 415
APERTURE_Z = 130

def is_attachment(c, n):
    """Aperture drive (-X) and water fittings / connector (+X) are kept whole (standard parts are not sectioned)."""
    r = math.hypot(c.x, c.y)
    return abs(c.y) < 80 and r > 183 and (80 < c.z < 178 if c.x < 0 else 22 < c.z < 178)

def is_inner(c, n):
    """Bore and inner surfaces of the generated shell, replaced by the modelled interior."""
    return math.hypot(c.x, c.y) < 160 and 4 < c.z < HEIGHT - 4

s.split_shell(is_attachment, is_inner)

BORE = 30  # Ø60 optical bore
# Housing wall stepped to sit just inside the shell's measured cut profile
# (body r~178-183, ribs ~192-198, bottom flange ~208, top flange ~197).
HOUSING_STEPS = [(0.4, 20, 196), (20, 185, 177.5), (185, 203, 192), (203, 288, 178), (288, 305, 190),
                 (305, 386, 178), (386, HEIGHT - 0.4, 194)]
WALL_IN, PLATE = 162, 16
outer = []
for z0, z1, r in HOUSING_STEPS:
    outer += [(r, z0), (r, z1)]
housing = [(BORE, 0.4)] + outer + [(BORE, HEIGHT - 0.4), (BORE, HEIGHT - PLATE), (WALL_IN, HEIGHT - PLATE),
                                   (WALL_IN, PLATE), (BORE, PLATE)]
s.solid('cl__housing', 'steel', housing, cap='section')

LENSES = {  # hotspot id: yoke z0, z1, outer radius, pole gap, coil layers
    'cl.cl1': (288, 392, 150, 14, 9),
    'cl.cl2': (202, 282, 150, 12, 7),
    'cl.cm': (18, 70, 120, 8, 5),
}
for hid, (z0, z1, r_out, gap, layers) in LENSES.items():
    s.solid(f'{hid}__yoke', 'iron', yoke(z0, z1, r_out, gap))
    s.solid(hid, 'copper', *coil_layers(BORE + 14 + 3, r_out - 12 - 3, z0 + 12 + 3, z1 - 12 - 3, layers))

RINGS = {  # thin stigmator / deflector rings: hotspot id: z0, z1
    'cl.stig': (186, 200),
    'cl.defl1': (167, 184),
    'cl.defl2': (72, 89),
}
for hid, (z0, z1) in RINGS.items():
    s.ring_coil(hid, 40, 104, z0, z1)

# Aperture drive: port tube through the wall, holder rod and brass strip on the X axis (not sectioned).
s.x_cylinder('cl.aperture__port', 'steel', -200, -158, 30, APERTURE_Z, inner=25)
s.x_cylinder('cl.aperture__rod', 'steel', -205, -48, 8, APERTURE_Z)
s.strip('cl.aperture', 'brass', -60, 26, 22, APERTURE_Z, ((0, 4), (-18, 7), (-36, 10)))  # working hole on the optical axis

s.finish(hotspots={h['id']: h['id'] if h['id'] != 'cl.aperture' else 'cl.aperture__rod' for h in s.part['hotspots']},
         housing_samples=[(z, r) for z0, z1, r in HOUSING_STEPS for z in np.arange(z0 + 4, z1 - 4, 2)],
         joined=[('cl.aperture', 'cl.aperture__rod'), ('cl__housing', 'cl.aperture__rod'), ('cl__housing', 'cl.aperture__port')],
         axis=(HEIGHT + 5, -5), view_x=-60)
