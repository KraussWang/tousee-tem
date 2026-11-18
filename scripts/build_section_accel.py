"""Half-section asset of the accelerator tube (see section_lib.py).

Run after assemble_blender.py: blender -b --python scripts/build_section_accel.py
Interior z follows the accel hotspots in data/parts.json; dimensions are schematic (C).
The isolation valve is drawn open (gate bored on the optical axis) at the height of the generated actuator.
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from section_lib import Section, rect

s = Section('accel')
HEIGHT = s.height  # 315
VALVE_Z = 47  # measured axis of the +X actuator

def is_attachment(c, n):
    """Valve actuator (+X) is kept whole. The two small -X side flanges are low relief on the skin and
    are sectioned with it: kept whole, their -Y halves would hang as open shells."""
    r = math.hypot(c.x, c.y)
    return abs(c.y) <= 55 and c.x > 0 and 14 < c.z < 82 and r > (201.5 if c.z < 31 else 178)

def is_inner(c, n):
    return math.hypot(c.x, c.y) < 165 and 4 < c.z < HEIGHT - 4

s.split_shell(is_attachment, is_inner)

BORE, WALL_IN, LINER = 30, 150, 36
# Outer wall and end plates; the beam liner hangs from the top plate and ends in the valve's upper seat.
housing = [(BORE, 0.4)] + s.outer_profile(0.4, HEIGHT - 0.4) + [
    (BORE, HEIGHT - 0.4), (BORE, 54), (115, 54), (115, 62), (LINER, 62), (LINER, 299), (WALL_IN, 299), (WALL_IN, 14), (BORE, 14)]
s.carve(s.solid('accel__housing', 'steel', housing, cap='section'), ('x', 120, 215, 9, 0, VALVE_Z))

# Voltage-divider electrodes of the multi-stage accelerator, one per exterior groove pitch.
s.solid('accel__electrodes', 'iron', *[rect(118, 149, z - 2, z + 2) for z in range(75, 290, 22)])
for hid, zc in (('accel.defl1', 230), ('accel.defl2', 150)):
    s.ring_coil(hid, 44, 100, zc - 15, zc + 15, layers=4)

# Isolation valve: lower seat, open gate and push rod from the actuator.
s.solid('accel.valve__body', 'iron', rect(42, 115, 16, 40))
s.carve(s.box('accel.valve', 'brass', (-70, 0, VALVE_Z - 3), (92, 46, VALVE_Z + 3)), ('z', VALVE_Z - 8, VALVE_Z + 8, 16, 0, 0))
s.x_cylinder('accel.valve__rod', 'steel', 93, 205, 6, VALVE_Z)

s.finish(hotspots={'accel.defl1': 'accel.defl1', 'accel.defl2': 'accel.defl2', 'accel.valve': 'accel.valve__body'},
         housing_samples=s.housing_samples, axis=(HEIGHT + 5, -5), view_x=30)
