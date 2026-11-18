"""Check the half-section assets as F5 shows them: the whole column in section mode.

Run after the build_section_<id>.py scripts: blender -b --factory-startup --python scripts/verify_sections.py
Parts without a section GLB are shown with their exterior (as the frontend falls back); bino is hidden.
Writes outputs/blender-assembly/section_verification.json and previews/assembly_section_{front,iso}.png.
"""
import bpy
import json
import math
from pathlib import Path
import numpy as np
from mathutils import Euler, Matrix, Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs' / 'blender-assembly'
DATA = json.loads((ROOT / 'data' / 'parts.json').read_text(encoding='utf-8'))
PARTS = {p['id']: p for p in DATA['parts']}
PLANES = {p['id']: p['z'] for p in DATA['opticalPlanes']}
REPO_ASSETS = OUT  # parts.json asset paths are relative to outputs/blender-assembly

report = dict(sectioned=[], fallback=[], hidden=[], swap={}, zExtent={}, axisHits=[], planeOwners={}, failures=[])
def check(ok, message):
    if not ok:
        report['failures'].append(message)


def local_points(path):
    """Vertices of a GLB in datum-local mm, Z up."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(path))
    bpy.context.view_layer.update()
    verts, faces = [], []
    for obj in [o for o in bpy.data.objects if o.type == 'MESH']:
        m = Matrix.Scale(1000, 4) @ obj.matrix_world
        base = len(verts)
        verts += [m @ v.co for v in obj.data.vertices]
        faces += [[base + i for i in p.vertices] for p in obj.data.polygons]
    return verts, faces


def placement(part):
    return (Matrix.Translation(Vector(part['datum']))
            @ Euler([math.radians(a) for a in part.get('rotation', (0, 0, 0))], 'XYZ').to_matrix().to_4x4())


world = {}  # part id -> BVH in world mm, as shown in section mode
for pid, part in PARTS.items():
    if part.get('hideInSection'):
        report['hidden'].append(pid)
        continue
    section = REPO_ASSETS / part['assets'].get('section', '')
    if part['assets'].get('section') and section.is_file():
        report['sectioned'].append(pid)
        verts, faces = local_points(section)
        full, _ = local_points(REPO_ASSETS / part['assets']['full'])
        sec, ext = np.array(verts), np.array(full)
        # Swap consistency on the kept (+Y) half: toggling F5 must not move or resize the part.
        sec_half, ext_half = sec[sec[:, 1] >= 0], ext[ext[:, 1] >= 0]
        delta = np.abs(np.r_[sec_half.min(0) - ext_half.min(0), sec_half.max(0) - ext_half.max(0)])
        report['swap'][pid] = dict(maxDeltaMm=round(float(delta.max()), 2), lo=sec_half.min(0).round(1).tolist(), hi=sec_half.max(0).round(1).tolist(),
                                   fullLo=ext_half.min(0).round(1).tolist(), fullHi=ext_half.max(0).round(1).tolist())
        check(delta.max() <= 1, f'{pid} section bbox differs from full by {delta.max():.2f} mm on the +Y half')
        # The section stands on its datum and stays within the part's height, so stacked sections meet at the
        # same seams (the top is covered by the swap check: vc's full top is the -Y binocular seat).
        z0, z1 = float(sec[:, 2].min()), float(sec[:, 2].max())
        height = part['zRange'][1] - part['zRange'][0]
        report['zExtent'][pid] = [round(z0, 2), round(z1, 2), height]
        check(abs(z0) <= 0.5 and z1 <= height + 0.5, f'{pid} section z {z0:.2f}..{z1:.2f} vs 0..{height}')
    else:
        report['fallback'].append(pid)
        verts, faces = local_points(REPO_ASSETS / part['assets']['full'])
    m = placement(part)
    world[pid] = BVHTree.FromPolygons([m @ Vector(v) for v in verts], faces)

# Optical axis (F6): from the gun's virtual source down to the screens, nothing may block it above the small screen.
top, stop = PLANES['source'], PLANES['large'] - 1
for pid, tree in world.items():
    z = top
    while z > stop:
        hit = tree.ray_cast(Vector((0, 0.5, z)), Vector((0, 0, -1)), z - stop)
        if hit[0] is None:
            break
        report['axisHits'].append(dict(part=pid, z=round(hit[0].z, 1)))
        z = hit[0].z - 0.01
report['axisHits'].sort(key=lambda h: -h['z'])
# The specimen cup (gonio) and the SA working hole sit on the axis by design: the beam passes through
# their holes. Probe a 2 mm disc around the axis to see whether the mesh actually has a through-hole.
report['warnings'], report['throughHole'] = [], {}
for pid in ('gonio', 'sa'):
    probes = [(dx, dy) for dx in np.arange(-2, 2.01, 0.25) for dy in np.arange(-2, 2.01, 0.25) if dx*dx + dy*dy <= 4]
    clear = [(float(dx), float(dy)) for dx, dy in probes if world[pid].ray_cast(Vector((dx, dy, top)), Vector((0, 0, -1)), top - stop)[0] is None]
    report['throughHole'][pid] = dict(clearProbes=len(clear), probes=len(probes), example=clear[0] if clear else None)
    if not clear:
        report['warnings'].append(f'{pid}: no vertical through-hole within 2 mm of the axis in the mesh (beam drawn through it)')
blocked = [h for h in report['axisHits'] if h['z'] > PLANES['small'] + 5 and h['part'] not in report['throughHole']]
check(not blocked, f'optical axis blocked above the small screen: {blocked}')

for plane, z in PLANES.items():
    report['planeOwners'][plane] = [pid for pid, part in PARTS.items() if 'zRange' in part and part['zRange'][0] <= z <= part['zRange'][1]]


def render_column():
    """previews/assembly_section_{front,iso}.png: the whole TEM as section mode shows it, for seams and materials."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    for pid, part in PARTS.items():
        if part.get('hideInSection'):
            continue
        kind = 'section' if pid in report['sectioned'] else 'full'
        existing = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(REPO_ASSETS / part['assets'][kind]))
        for obj in [o for o in bpy.data.objects if o not in existing and o.parent is None]:
            obj.matrix_world = placement(part) @ Matrix.Scale(1000, 4) @ obj.matrix_world
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x, scene.render.resolution_y = 1100, 1600
    world = bpy.data.worlds.new('studio')
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.65, 0.68, 0.72, 1)
    world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.8
    for xyz, power in [((-1500, -2500, 2000), 9000), ((2000, -1500, 0), 5000), ((500, 2000, 1500), 6000)]:
        light = bpy.data.lights.new('soft', 'AREA')
        light.energy, light.size = power * 150, 1500
        obj = bpy.data.objects.new('soft', light)
        scene.collection.objects.link(obj)
        obj.location = xyz
        obj.rotation_euler = (Vector((0, 0, -200)) - obj.location).to_track_quat('-Z', 'Y').to_euler()
    cam = bpy.data.cameras.new('ortho')
    cam.type, cam.ortho_scale, cam.clip_end = 'ORTHO', 3200, 20000
    camera = bpy.data.objects.new('camera', cam)
    scene.collection.objects.link(camera)
    scene.camera = camera
    target = Vector((0, 0, -220))
    for view, offset in [('front', (0, -6000, 0)), ('iso', (-3000, -5000, 2500))]:
        camera.location = target + Vector(offset)
        camera.rotation_euler = (target - camera.location).to_track_quat('-Z', 'Y').to_euler()
        scene.render.filepath = str(OUT / 'previews' / f'assembly_section_{view}.png')
        bpy.ops.render.render(write_still=True)


render_column()
(OUT / 'section_verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print('SECTIONS_REPORT', json.dumps(report, ensure_ascii=False), flush=True)
assert not report['failures'], report['failures']
print('SECTIONS_VERIFIED', len(report['sectioned']), 'sectioned,', len(report['fallback']), 'full,', len(report['hidden']), 'hidden', flush=True)
