"""Write data/interfaces.json from outputs/blender-assembly/TEM_assembly.blend.

  blender -b outputs/blender-assembly/TEM_assembly.blend --python scripts/capture_interfaces.py
      Read the Empties vc.bino_seat / bino.mount (after adjusting them by hand).
  ... --python scripts/capture_interfaces.py -- --estimate
      Estimate both interfaces from the meshes instead.

Then re-run scripts/assemble_blender.py.
"""
import bpy
import json
import sys
from pathlib import Path
import numpy as np
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / 'data' / 'interfaces.json'
data = json.loads(PATH.read_text(encoding='utf-8'))


def rounded(v):
    return [round(float(c), 2) + 0.0 for c in v]


def as_interface(point, normal, up):
    return dict(point=rounded(point), normal=rounded(Vector(normal).normalized()), up=rounded(Vector(up).normalized()))


def local_faces(root):
    """(centre, normal, area) of every polygon, in root-local coordinates."""
    to_root = root.matrix_world.inverted()
    out = []
    for obj in root.children:
        if obj.type != 'MESH':
            continue
        m = to_root @ obj.matrix_world
        n3 = m.to_3x3().inverted().transposed()
        out += [(m @ p.center, (n3 @ p.normal).normalized(), p.area) for p in obj.data.polygons]
    return out


def local_points(root):
    to_root = root.matrix_world.inverted()
    return np.array([tuple(to_root @ obj.matrix_world @ v.co) for obj in root.children if obj.type == 'MESH'
                     for v in obj.data.vertices])


def estimate_seat(vc):
    """Seat plate on the upper edge of the front slant: area-weighted plate normal,
    contact plane at the outermost rim (the two sockets) along that normal."""
    faces = local_faces(vc)
    top = max(c.z for c, _, _ in faces)
    region = [(c, n, a) for c, n, a in faces if c.y < -150 and c.z > top - 45 and abs(c.x) < 150]
    plate = [(c, n, a) for c, n, a in region if n.z > 0.5 and n.y < -0.2]
    normal = sum((n * a for _, n, a in plate), Vector()).normalized()
    contact = max(c.dot(normal) for c, _, _ in region)
    # Footprint: only the plate and sockets that stand proud of the slant face.
    centres = np.array([tuple(c) for c, _, _ in region if c.dot(normal) > contact - 25])
    centre = Vector((centres.min(0) + centres.max(0)) / 2)
    point = centre + (contact - centre.dot(normal)) * normal
    uphill = Vector((0, 0, 1)) - normal.z * normal
    # Bino top points downhill so its eyepieces face the operator (-Y), clear of pl.
    return as_interface(point, normal, -uphill)


def estimate_mount(bino):
    """Back face of the mounting plate: the bino's +Y extreme in its normalized frame."""
    points = local_points(bino) + np.array(bino.get('normalizedMountPoint', (0, 0, 0)))
    back = points[points[:, 1] > points[:, 1].max() - 3]
    centre = (back.min(0) + back.max(0)) / 2
    return as_interface((centre[0], points[:, 1].max(), centre[2]), (0, 1, 0), (0, 0, 1))


def from_empty(name, offset=(0, 0, 0)):
    m = bpy.data.objects[name].matrix_basis
    return as_interface(m.translation + Vector(offset), m.col[2].xyz, m.col[1].xyz)


vc, bino = bpy.data.objects['vc'], bpy.data.objects['bino']
if '--estimate' in sys.argv:
    seat, mount = estimate_seat(vc), estimate_mount(bino)
else:
    seat = from_empty('vc.bino_seat')
    mount = from_empty('bino.mount', bino.get('normalizedMountPoint', (0, 0, 0)))
data['vc']['bino_seat'], data['bino']['mount'] = seat, mount
PATH.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print('INTERFACES', json.dumps(dict(seat=seat, mount=mount)), flush=True)
