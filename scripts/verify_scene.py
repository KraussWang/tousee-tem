"""Check saved Blender assembly against parts.json (run after the .blend path)."""
import bpy
import json
import math
import sys
from pathlib import Path
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tem_geometry import flange_circle, mesh_points, port_face, side_flange, yaw_degrees

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'outputs'/'blender-assembly'
parts = json.loads((ROOT/'data'/'parts.json').read_text(encoding='utf-8'))['parts']
for part in parts:
    obj = bpy.data.objects.get(part['id'])
    assert obj, part['id']
    assert (obj.location-Vector(part['datum'])).length < 0.01, (part['id'], tuple(obj.location))
    rotation = Vector([math.degrees(a) for a in obj.rotation_euler])
    assert (rotation-Vector(part.get('rotation', (0, 0, 0)))).length < 0.05, (part['id'], tuple(rotation))
    assert any(child.type == 'MESH' for child in obj.children), part['id']
screen = bpy.data.objects['screen']
assert len([o for o in screen.children if o.type == 'MESH']) == 4
for token, expected_z in [('screen_large',-830),('screen_small',-730)]:
    child = next(o for o in screen.children if token in o.name and 'rod' not in o.name and 'support' not in o.name)
    points = [child.matrix_world @ Vector(c) for c in child.bound_box]
    centre = Vector([(min(p[i] for p in points)+max(p[i] for p in points))/2 for i in range(3)])
    assert abs(centre.z-expected_z) < 2, (token,centre)
    assert abs(centre.x) < 2 and abs(centre.y) < 2, (token,centre)

def meshes(pid):
    return [o for o in bpy.data.objects[pid].children if o.type == 'MESH']

report = dict(flanges={}, joints=[], failures=[])
def check(ok, message):
    if not ok:
        report['failures'].append(message)

# Optical-axis coaxiality: every mating flange centred on (0,0) within 2 mm.
COLUMN = ['vc', 'pl', 'il', 'ol', 'cl', 'accel', 'gun']  # bottom to top
for pid in COLUMN:
    points = mesh_points(meshes(pid))
    low, high = points[:, 2].min(), points[:, 2].max()
    entry = report['flanges'][pid] = dict(zRange=[float(low), float(high)])
    for side, z0, z1 in [('bottom', low, low+8), ('top', high-8, high)]:
        if (pid, side) in (('gun', 'top'), ('vc', 'top')):
            continue  # gun cap is closed; vc's top flange is fused with the bino seat
        centre, radius, coverage = flange_circle(points, z0, z1, min_coverage=0)
        entry[side] = dict(centre=[float(c) for c in centre], radius=radius, coverage=coverage)
        if coverage >= 0.5:
            check(np.hypot(*centre) <= 2, f'{pid} {side} flange centre {centre.round(2)} off axis')
for lower, upper in zip(COLUMN, COLUMN[1:]):
    gap = report['flanges'][upper]['zRange'][0] - report['flanges'][lower]['zRange'][1]
    report['joints'].append(dict(lower=lower, upper=upper, gapMm=float(gap)))
    check(abs(gap) <= 1, f'{lower}/{upper} axial gap {gap:.2f} mm')

# Viewing chamber squared up to the world axes.
points = mesh_points(meshes('vc'))
low, height = points[:, 2].min(), np.ptp(points[:, 2])
report['vcYawDeg'] = float(np.median([yaw_degrees(points, low+k*height, low+(k+0.08)*height) for k in np.arange(0.15, 0.6, 0.08)]))
check(abs(report['vcYawDeg']) <= 0.5, f"vc yaw {report['vcYawDeg']:.2f} deg")

# Binocular plate seated on the vc seat.
seat, mount = bpy.data.objects['vc.bino_seat'].matrix_world, bpy.data.objects['bino.mount'].matrix_world
report['binoMateMm'] = (seat.translation-mount.translation).length
report['binoMateAngleDeg'] = math.degrees(seat.col[2].xyz.angle(-mount.col[2].xyz))
report['binoUpAngleDeg'] = math.degrees(seat.col[1].xyz.angle(mount.col[1].xyz))
check(report['binoMateMm'] <= 2, f"bino mate offset {report['binoMateMm']:.2f} mm")
check(report['binoMateAngleDeg'] <= 2 and report['binoUpAngleDeg'] <= 2, 'bino mate angle')

# Interpenetration of the binocular with its neighbours (triangle pairs).
def bvh(pid):
    trees = []
    for obj in meshes(pid):
        m = obj.matrix_world
        trees.append(BVHTree.FromPolygons([m @ v.co for v in obj.data.vertices], [p.vertices for p in obj.data.polygons]))
    return trees
bino = bvh('bino')
report['binoOverlaps'] = {pid: sum(len(a.overlap(b)) for a in bino for b in bvh(pid)) for pid in ('vc', 'pl', 'il', 'screen')}
check(all(n == 0 for pid, n in report['binoOverlaps'].items() if pid != 'vc'), f"bino intersects {report['binoOverlaps']}")

# Side ports point the PRD way: ol goniometer port +X (90 deg), il SA port -X (270 deg).
def widest_azimuth(pid, z0, z1):
    p = mesh_points(meshes(pid))
    p = p[(p[:, 2] >= z0) & (p[:, 2] <= z1)]
    r = np.hypot(p[:, 0], p[:, 1])
    far = p[r > np.percentile(r, 99.5)]
    return float((math.degrees(math.atan2(far[:, 0].mean(), -far[:, 1].mean())) + 360) % 360)
report['olPortAzimuthDeg'] = widest_azimuth('ol', -100, 100)
report['ilPortAzimuthDeg'] = widest_azimuth('il', -260, -196)
report['clPortAzimuthDeg'] = widest_azimuth('cl', 215, 285)
report['accelActuatorAzimuthDeg'] = widest_azimuth('accel', 550, 615)
check(abs(report['accelActuatorAzimuthDeg'] - 90) <= 15, f"accel valve actuator at {report['accelActuatorAzimuthDeg']:.0f} deg")
check(abs(report['olPortAzimuthDeg'] - 90) <= 15, f"ol goniometer port at {report['olPortAzimuthDeg']:.0f} deg")
check(abs(report['ilPortAzimuthDeg'] - 270) <= 15, f"il SA port at {report['ilPortAzimuthDeg']:.0f} deg")
check(abs(report['clPortAzimuthDeg'] - 270) <= 15, f"cl aperture port at {report['clPortAzimuthDeg']:.0f} deg")

# Side-entry rods: flange face on the column port, free end on the optical axis.
optical = {p['id']: p['z'] for p in json.loads((ROOT/'data'/'parts.json').read_text(encoding='utf-8'))['opticalPlanes']}
report['sideRods'] = {}
fits = {pid: entry['fit'] for pid, entry in json.loads((OUT/'assembly.json').read_text(encoding='utf-8')).items()}
# gonio is centred on its (lower) port flange, so its cup sits a few mm off the specimen plane.
# `window` is twice the cup depth from the free end (8 / 4 mm before any flange-matching scale).
for pid, column, side, target_z, tolerance, window in (('gonio', 'ol', 1, 0.0, 10, 16), ('sa', 'il', -1, optical['sa'], 3, 10)):
    p = mesh_points(meshes(pid))
    face = port_face(mesh_points(meshes(column)), side)[0]
    datum = bpy.data.objects[pid].location
    inward = -side * p[:, 0]
    tip = p[inward >= inward.max() - window*fits[pid].get('flangeScale', 1)]  # specimen cup / aperture working end
    centre = (tip.min(0) + tip.max(0)) / 2
    entry = report['sideRods'][pid] = dict(portFace=face, datumX=float(datum.x), freeEndCentre=centre.round(2).tolist(),
                                           outerX=float(side * (side * p[:, 0]).max()))
    check(abs(face - datum.x) <= 1, f'{pid} flange face {datum.x:.1f} vs {column} port {face:.1f}')
    check(np.hypot(centre[1], centre[2] - target_z) <= tolerance and abs(centre[0]) <= 6, f'{pid} free end {centre.round(1)} off axis')
    check(side * entry['outerX'] > abs(face), f'{pid} outer end not outside the column')
flange_centre, flange_radius = side_flange(mesh_points(meshes('gonio')), report['sideRods']['gonio']['portFace'], 1)
_, port_centre, port_radius, _ = port_face(mesh_points(meshes('ol')), 1)
report['sideRods']['gonio'].update(flangeCentreYZ=flange_centre.round(2).tolist(), flangeDiameter=2*flange_radius,
                                   portCentreYZ=port_centre.round(2).tolist(), portDiameter=2*port_radius)
check(np.hypot(*(flange_centre - port_centre)) <= 2, f'gonio flange centre {flange_centre.round(1)} vs ol port {port_centre.round(1)}')
check(abs(flange_radius / port_radius - 1) <= 0.02, f'gonio flange Ø{2*flange_radius:.1f} vs ol port Ø{2*port_radius:.1f}')
report['sideRods']['gonio']['handleOutside'] = report['sideRods']['gonio']['outerX'] > 400
check(report['sideRods']['gonio']['handleOutside'], 'gonio handle not outside the column')
check(report['sideRods']['sa']['outerX'] >= bpy.data.objects['sa'].location.x - 200, 'sa sticks out more than 200 mm')
# The rods pass through the (generated, possibly plugged) port: report only.
report['sideOverlaps'] = {f'{a}/{b}': sum(len(x.overlap(y)) for x in bvh(a) for y in bvh(b)) for a, b in (('gonio', 'ol'), ('sa', 'il'))}

(OUT/'scene_verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
print('SCENE_REPORT', json.dumps({k: v for k, v in report.items() if k != 'flanges'}), flush=True)
for pid, entry in report['flanges'].items():
    print('FLANGE', pid, {s: (np.round(e['centre'], 2).tolist(), round(e['radius'], 1), round(e['coverage'], 2)) for s, e in entry.items() if s != 'zRange'}, flush=True)
assert not report['failures'], report['failures']
print('SCENE_VERIFIED 13 roots; coaxial flanges; vc square; bino seated', flush=True)
