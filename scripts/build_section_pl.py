"""Half-section asset of the projector lens (see section_lib.py).

Run after assemble_blender.py: blender -b --python scripts/build_section_pl.py
Interior z follows the pl hotspots in data/parts.json; dimensions are schematic (C).
The isolation valve is drawn open (gate bored on the optical axis) at the height of the generated actuator.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from section_lib import Section, coil_layers

s = Section('pl')
HEIGHT = s.height  # 170
VALVE_Z = 52  # measured axis of the +X actuator

def is_attachment(c, n):
    """Valve actuator (+X) and the -X side fitting are kept whole."""
    r = math.hypot(c.x, c.y)
    return abs(c.y) < 70 and 8 < c.z < 92 and r > (199 if c.z < 12 else 179)

def is_inner(c, n):
    return math.hypot(c.x, c.y) < 168 and 4 < c.z < HEIGHT - 4

s.split_shell(is_attachment, is_inner)

BORE, WALL_IN = 30, 160
# Bottom plate, partition between valve stage and lens (60-64), top plate.
housing = [(BORE, 0.4)] + s.outer_profile(0.4, HEIGHT - 0.4) + [
    (BORE, HEIGHT - 0.4), (BORE, 154), (WALL_IN, 154), (WALL_IN, 64), (BORE, 64), (BORE, 60), (WALL_IN, 60), (WALL_IN, 12), (BORE, 12)]
s.carve(s.solid('pl__housing', 'steel', housing, cap='section'), ('x', 120, 215, 9, 0, VALVE_Z))

# Projector lens: yoke with long conical pole pieces, as in the section view.
Z0, Z1, R_OUT, T = 66, 126, 156, 9
s.solid('pl.coil__yoke', 'iron', [(BORE, Z0), (R_OUT, Z0), (R_OUT, Z1), (BORE, Z1), (BORE, 100), (60, Z1 - T), (R_OUT - T, Z1 - T),
                                  (R_OUT - T, Z0 + T), (60, Z0 + T), (BORE, 92)])
s.solid('pl.coil', 'copper', *coil_layers(64, R_OUT - T - 3, Z0 + T + 3, Z1 - T - 3, 5))
s.ring_coil('pl.defl', 40, 104, 129, 143)

# Isolation valve: seat ring, open gate and push rod from the actuator.
s.solid('pl.valve__body', 'iron', [(42, 16), (118, 16), (118, 44), (100, 44), (100, 40), (42, 40)])
s.carve(s.box('pl.valve', 'brass', (-70, 0, VALVE_Z - 3), (92, 46, VALVE_Z + 3)), ('z', VALVE_Z - 8, VALVE_Z + 8, 16, 0, 0))
s.x_cylinder('pl.valve__rod', 'steel', 93, 205, 6, VALVE_Z)

s.finish(hotspots={'pl.defl': 'pl.defl', 'pl.coil': 'pl.coil', 'pl.valve': 'pl.valve__body'}, housing_samples=s.housing_samples,
         axis=(HEIGHT + 5, -5))
