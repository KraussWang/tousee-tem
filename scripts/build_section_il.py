"""Half-section asset of the intermediate lens (see section_lib.py).

Run after assemble_blender.py: blender -b --python scripts/build_section_il.py
Interior z follows the il hotspots in data/parts.json; dimensions are schematic (C).
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from section_lib import PARTS, Section, coil_layers, yoke

s = Section('il', mates=('sa',))
HEIGHT = s.height  # 260
SA_Z = PARTS['sa']['datum'][2] - s.part['datum'][2]  # 211.8: axis of the SA rod

def is_attachment(c, n):
    """Water fittings / connector (+X) and the SA port flange (-X) are kept whole."""
    r = math.hypot(c.x, c.y)
    if abs(c.y) > 60:
        return False
    if c.x > 0:
        return r > 192.5 and 25 < c.z < 228
    return 174 < c.z < 250 and r > (192.5 if c.z < 229 else 203.5)

def is_inner(c, n):
    return math.hypot(c.x, c.y) < 180 and 4 < c.z < HEIGHT - 4

s.split_shell(is_attachment, is_inner)

BORE, WALL_IN = 30, 166
# Solid top stage (200-260) carrying the SA port channel; thin bottom plate under IL3.
housing = [(BORE, 0.4)] + s.outer_profile(0.4, HEIGHT - 0.4) + [(BORE, HEIGHT - 0.4), (BORE, 200), (WALL_IN, 200), (WALL_IN, 6), (BORE, 6)]
s.carve(s.solid('il__housing', 'steel', housing, cap='section'), ('x', -240, 0, 18, 0, SA_Z))

LENSES = {  # hotspot id: yoke z0, z1
    'il.il3': (8, 62),
    'il.il2': (73, 127),
    'il.il1': (143, 197),
}
for hid, (z0, z1) in LENSES.items():
    s.solid(f'{hid}__yoke', 'iron', yoke(z0, z1, 160, 8, t=8, pole=12))
    s.solid(hid, 'copper', *coil_layers(BORE + 12 + 3, 160 - 8 - 3, z0 + 11, z1 - 11, 4))
s.ring_coil('il.stig', 40, 104, 128.5, 141.5)

s.finish(hotspots={h['id']: h['id'] for h in s.part['hotspots']}, housing_samples=s.housing_samples,
         axis=(HEIGHT + 5, -5), view_x=10)
