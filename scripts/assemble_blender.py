"""Assemble the source exterior assets with Blender 5.2.

Run: blender -b --python scripts/assemble_blender.py
The source GLBs are never modified. Dimensions in the .blend are millimetres.
"""
import bpy
import json
import math
import sys
from pathlib import Path
import numpy as np
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tem_geometry import FACE_TO_FACE, flange_circle, frame, mesh_points, port_face, side_flange, side_rod, yaw_degrees

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'models' / 'source'
OUT = ROOT / 'outputs' / 'blender-assembly'
ASSETS = OUT / 'assets'
PREVIEWS = OUT / 'previews'
for directory in (OUT, ASSETS, PREVIEWS):
    directory.mkdir(parents=True, exist_ok=True)
PARTS = json.loads((ROOT / 'data' / 'parts.json').read_text(encoding='utf-8'))['parts']
INTERFACES = json.loads((ROOT / 'data' / 'interfaces.json').read_text(encoding='utf-8'))

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.unit_settings.system = 'METRIC'
scene.unit_settings.scale_length = 0.001
scene.unit_settings.length_unit = 'MILLIMETERS'
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x = 1200
scene.render.resolution_y = 1200
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'

def bounds(objects):
    points = [o.matrix_world @ Vector(c) for o in objects if o.type == 'MESH' for c in o.bound_box]
    return (Vector([min(p[i] for p in points) for i in range(3)]),
            Vector([max(p[i] for p in points) for i in range(3)]))

def dims_mm(part):
    d = part['dims']
    return Vector((d.get('x', d.get('diameter', 1)),
                   d.get('y', d.get('diameter', 1)),
                   d.get('z', d.get('height', 1))))

def mesh_triangles(objects):
    return sum(sum(max(0, len(p.vertices)-2) for p in o.data.polygons) for o in objects if o.type == 'MESH')

# Radial body calibration from the source silhouette and the B dimensions.
# A protruding port makes the full X/Y bounding box larger than the cylinder.
# For box parts, match the specified envelope on all three axes.
CALIBRATION = {
    'gun': (490/340, 490/340, 1.0),
    'accel': (400/279, 400/279, 1.0),
    'cl': (400/278, 400/278, 1.0),
    'ol': (400/290, 400/290, 1.0),
    'il': (400/326, 400/326, 1.0),
    'pl': (400/176, 400/176, 1.0),
    'bino': (220/168, 260/221, 1.0),
    'film': (1.0, 120/213, 60/117),
}
# Box parts whose source mesh is yawed: square them up, then scale X/Y to the envelope.
YAW_PARTS = ('vc', 'base')
# Flange that defines the optical axis, as a slab in datum-local mm after scaling.
FLANGE_SLAB = {pid: ('bottom', 8) for pid in ('gun', 'accel', 'cl', 'ol', 'il', 'pl')}
# vc's generated top flange is fused with the binocular seat; its clean bottom
# flange (r ~198, coaxial with the top one within the source mesh) gives the axis.
FLANGE_SLAB['vc'] = ('bottom', 8)
PASS_THROUGH = ('accel', 'cl', 'ol', 'il', 'pl')  # flanged at both ends
# Generated ol is the mirror image of its four views (large goniometer port on -X).
MIRROR_X = ('ol',)
# Generated il has its SA port at +Y (180 deg); PRD wants it at -X (270 deg).
# Generated cl has its aperture at -Y (0 deg); the four views put it at -X (270 deg).
# Generated accel has its valve actuator at -Y (0 deg); the four views put it at +X (90 deg).
AXIAL_YAW = {'il': 90, 'cl': -90, 'accel': 90}
# Side-entry parts: uniform scale, rod along X. `yaw` turns the source rod onto X
# with its free end toward `tip`; `rigid` is the tongue/aperture-strip length
# (mm) kept undistorted; `work` is the specimen-cup / working-hole centre
# measured inward from the free end; `port` is the column part and its side.
# `match_flange`: scale uniformly so the flange matches the port, flange centre on the port centre.
SIDE_RODS = {
    'gonio': dict(yaw=-90, tip=-1, rigid=16, work=8, port=('ol', 1), match_flange=True),
    'sa': dict(yaw=0, tip=1, rigid=30, work=4, port=('il', -1)),
}

def apply(meshes, matrix):
    for obj in meshes:
        obj.data.transform(matrix)

def local_points(meshes):
    return np.concatenate([np.array([v.co for v in o.data.vertices]) for o in meshes])

def export_part(pid, root, meshes):
    # Export only this local root; remove the assembly placement for each GLB.
    saved_loc, saved_rot, saved_scale = root.location.copy(), root.rotation_euler.copy(), root.scale.copy()
    root.location = (0,0,0)
    root.rotation_euler = (0,0,0)
    root.scale = (0.001,)*3  # glTF coordinates are metres; scene coordinates remain mm
    bpy.ops.object.select_all(action='DESELECT')
    root.select_set(True)
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = root
    exported = ASSETS / f'{pid}_full.glb'
    bpy.ops.export_scene.gltf(filepath=str(exported), export_format='GLB', use_selection=True,
                              export_yup=True, export_apply=False)
    root.location, root.rotation_euler, root.scale = saved_loc, saved_rot, saved_scale
    return exported

assembly = bpy.data.collections.new('TEM · 13 exterior parts')
scene.collection.children.link(assembly)
report = {}
roots = {}
part_meshes = {}

for part in PARTS:
    pid = part['id']
    source = SOURCE / f'{pid}_full.glb'
    if not source.exists():
        raise FileNotFoundError(source)
    existing = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(source))
    imported = list(set(bpy.data.objects) - existing)
    meshes = [o for o in imported if o.type == 'MESH']
    if not meshes:
        raise RuntimeError(f'{pid}: no mesh')
    low, high = bounds(meshes)
    extent = high-low
    target = dims_mm(part)
    # The optical-column meshes already have Z as their long/short axial direction.
    # Side attachments are measured from the body rather than their rods.
    if pid in ('gun','accel','cl','ol','il','pl','vc','base','bino'):
        factor = target.z / extent.z
    elif pid == 'screen':
        large = next(o for o in meshes if o.name.startswith('screen_large') and 'rod' not in o.name)
        lo, hi = bounds([large])
        factor = 160 / max((hi-lo).x, (hi-lo).y, (hi-lo).z)
    elif pid == 'film':
        factor = 360 / max(extent.x, extent.y)  # two 180 mm cassettes
    else:
        factor = target.z / extent.z
    if not math.isfinite(factor) or factor <= 0:
        raise RuntimeError(f'{pid}: invalid scale')

    root = bpy.data.objects.new(pid, None)
    assembly.objects.link(root)
    root.empty_display_size = 40
    root.location = Vector(part['datum'])
    root.rotation_euler = tuple(math.radians(x) for x in part.get('rotation', (0,0,0)))
    roots[pid] = root

    # Put imported vertices into datum-local millimetres. This preserves child
    # meshes but makes the named root the sole assembly placement transform.
    centers = (low+high)/2
    if pid in ('gun','accel','cl','ol','il','pl','vc','base'):
        anchor = Vector((centers.x, centers.y, low.z))
    elif pid == 'gonio':
        anchor = Vector((low.x, centers.y, centers.z))
    elif pid == 'sa':
        anchor = Vector((high.x, centers.y, centers.z))
    elif pid == 'bino':
        anchor = Vector((centers.x, high.y, centers.z))
    elif pid == 'film':
        anchor = Vector((centers.x - 200/factor, centers.y, low.z))
    else:  # screen: large screen center is the L1 datum
        large = next(o for o in meshes if o.name.startswith('screen_large') and 'rod' not in o.name)
        lo, hi = bounds([large])
        anchor = (lo+hi)/2

    for obj in imported:
        if obj.type != 'MESH':
            continue
        world = obj.matrix_world.copy()
        obj.parent = None
        obj.matrix_world = Matrix.Identity(4)
        obj.data = obj.data.copy()
        obj.data.transform(Matrix.Scale(factor, 4) @ Matrix.Translation(-anchor) @ world)
        obj.parent = root
        obj.name = f'{pid}__{obj.name}'
        # Preserve the original materials and child meshes.
    for obj in imported:
        if obj.type != 'MESH':
            bpy.data.objects.remove(obj, do_unlink=True)

    fit = {}
    correction = CALIBRATION.get(pid, (1, 1, 1))
    if pid in YAW_PARTS:
        points = mesh_points(meshes)
        height = np.ptp(points[:, 2])
        # Median over body slices so side flanges in one slice do not bias it.
        fit['yawDeg'] = float(np.median([yaw_degrees(points, k*height, (k+0.08)*height) for k in np.arange(0.15, 0.6, 0.08)]))
        apply(meshes, Matrix.Rotation(math.radians(-fit['yawDeg']), 4, 'Z'))
        extent = np.ptp(mesh_points(meshes)[:, :2], 0)
        correction = (target.x/extent[0], target.y/extent[1], 1)
    apply(meshes, Matrix.Diagonal((*correction, 1)))
    if pid in AXIAL_YAW:
        # Before the flange fit, so the axis is fitted in the final (verified) frame.
        apply(meshes, Matrix.Rotation(math.radians(AXIAL_YAW[pid]), 4, 'Z'))
        fit['axialYawDeg'] = AXIAL_YAW[pid]
    if pid in FLANGE_SLAB:
        # Put the flange axis, not the bounding-box centre, on the optical axis.
        side, slab = FLANGE_SLAB[pid]
        points = mesh_points(meshes)
        z = points[:, 2].min() if side == 'bottom' else points[:, 2].max()
        centre, radius, coverage = flange_circle(points, z, z+slab) if side == 'bottom' else flange_circle(points, z-slab, z)
        apply(meshes, Matrix.Translation((-centre[0], -centre[1], 0)))
        fit.update(flange=side, flangeShift=[float(c) for c in centre], flangeRadius=radius, flangeCoverage=coverage)
        if pid in PASS_THROUGH:
            # A leaning generated body: shear X/Y with height so the top flange
            # is coaxial too, keeping flange faces horizontal (no joint gaps).
            points = mesh_points(meshes)
            top, height = points[:, 2].max(), np.ptp(points[:, 2])
            lean = flange_circle(points, top-slab, top)[0]
            if np.hypot(*lean) > 0.5:
                shear = Matrix.Identity(4)
                shear[0][2], shear[1][2] = -lean[0]/height, -lean[1]/height
                apply(meshes, shear)
                fit['topLeanCorrected'] = [float(c) for c in lean]
    if pid in MIRROR_X:
        # About the optical axis, so coaxiality is kept; restore outward winding.
        apply(meshes, Matrix.Diagonal((-1, 1, 1, 1)))
        for obj in meshes:
            obj.data.flip_normals()
        fit['mirrorX'] = True
    if pid in SIDE_RODS:
        # Rod onto X, flange mating face to x=0, rod axis to y=z=0. The inner
        # rod is lengthened later, once the column port has been measured.
        cfg = SIDE_RODS[pid]
        apply(meshes, Matrix.Rotation(math.radians(cfg['yaw']), 4, 'Z'))
        rod = side_rod(local_points(meshes), cfg['tip'], cfg['rigid'])
        apply(meshes, Matrix.Translation((-rod['face'], -rod['axis'][0], -rod['axis'][1])))
        fit.update(rodYawDeg=cfg['yaw'], rodDiameter=rod['rodDiameter'], sourceRodReach=float(abs(rod['end']-rod['face'])))
    if pid == 'bino':
        # The datum is the centre of the mounting-plate face (PRD §8 bino).
        mount = INTERFACES['bino']['mount']
        apply(meshes, Matrix.Translation(-Vector(mount['point'])))
        root['normalizedMountPoint'] = mount['point']

    # The source large disk is already inclined about X. Remove that inclination
    # so the PRD root rotation supplies the final +30 degrees exactly once.
    # Place the small disk at world (0,0,+100) relative to the large disk.
    if pid == 'screen':
        unrotate = Matrix.Rotation(math.radians(-30),4,'X')
        for obj in meshes:
            obj.data.transform(unrotate)
        def local_center(obj):
            vertices = [v.co for v in obj.data.vertices]
            return Vector([(min(v[i] for v in vertices)+max(v[i] for v in vertices))/2 for i in range(3)])
        large = next(o for o in meshes if 'screen_large' in o.name and 'rod' not in o.name)
        small = next(o for o in meshes if 'screen_small' in o.name and 'support' not in o.name)
        large_center = local_center(large)
        for obj in meshes:
            obj.data.transform(Matrix.Translation(-large_center))
        small_center = local_center(small)
        small_vertices = [v.co for v in small.data.vertices]
        small_diameter = max(max(c[0] for c in small_vertices)-min(c[0] for c in small_vertices),
                             max(c[1] for c in small_vertices)-min(c[1] for c in small_vertices))
        small_scale = 40/small_diameter
        target_local = Matrix.Rotation(math.radians(-30),4,'X') @ Vector((0,0,100))
        translate = target_local-small_center
        small_matrix = Matrix.Translation(translate) @ Matrix.Translation(small_center) @ Matrix.Scale(small_scale,4) @ Matrix.Translation(-small_center)
        for obj in meshes:
            if 'screen_small' in obj.name:
                obj.data.transform(small_matrix)

    report[pid] = dict(source=str(source.relative_to(ROOT)), output=str((ASSETS / f'{pid}_full.glb').relative_to(ROOT)),
        sourceBounds=[list(low),list(high)], sourceTriangles=mesh_triangles(meshes),
        scale=factor, sourceAnchor=list(anchor), datum=part['datum'], xyScale=list(correction), fit=fit,
        meshNames=[o.name for o in meshes])
    part_meshes[pid] = meshes
    if pid not in SIDE_RODS:  # side parts are exported after their rods are fitted
        report[pid]['exportedBytes'] = export_part(pid, root, meshes).stat().st_size
    print('ASSEMBLED', pid, 'triangles', report[pid]['sourceTriangles'], 'fit', fit, flush=True)

# Side-entry parts: mate the flange face on the measured column port, then
# lengthen only the thin rod so the specimen cup / working hole sits on the
# optical axis. The tongue and the aperture strip move rigidly.
bpy.context.view_layer.update()
for pid, cfg in SIDE_RODS.items():
    column, side = cfg['port']
    face, centre, radius, coverage = port_face(mesh_points(part_meshes[column]), side)
    reach, tip = abs(face), cfg['tip']
    meshes = part_meshes[pid]
    k, axis = 1.0, (0.0, 0.0 if pid == 'gonio' else float(centre[1]))
    if cfg.get('match_flange'):
        # About the flange-face centre, so the mating face stays at x=0.
        flange_centre, flange_radius = side_flange(local_points(meshes), 0.0, -tip)
        k = radius / flange_radius
        apply(meshes, Matrix.Translation((0, *(-k*flange_centre))) @ Matrix.Scale(k, 4))
        axis = tuple(float(c) for c in centre)
        report[pid]['fit'].update(flangeScale=float(k), sourceFlangeDiameter=float(2*flange_radius),
                                  flangeDiameter=float(2*radius))
    end = tip * (local_points(meshes)[:, 0] * tip).max()
    boundary, work = end - tip*k*cfg['rigid'], end - tip*k*cfg['work']
    extra = reach - abs(work)
    stretch = (abs(boundary)+extra) / abs(boundary)
    for obj in meshes:
        co = np.empty(len(obj.data.vertices)*3)
        obj.data.vertices.foreach_get('co', co)
        co = co.reshape(-1, 3)
        s = tip * co[:, 0]
        rodpart = (s > 0) & (s <= abs(boundary))
        co[rodpart, 0] *= stretch
        co[s > abs(boundary), 0] += tip * extra
        obj.data.vertices.foreach_set('co', co.ravel())
        obj.data.update()
    datum = (face, *axis)
    roots[pid].location = datum
    report[pid]['exportedBytes'] = export_part(pid, roots[pid], meshes).stat().st_size
    report[pid]['fit'].update(port=column, portFace=face, portCentreYZ=[float(c) for c in centre],
        portRadius=float(radius), portCoverage=float(coverage), rodStretch=float(stretch), rigidShift=float(extra),
        workPoint=[face + tip*reach, datum[1], datum[2]])
    report[pid]['matedDatum'] = [round(c, 2) for c in datum]
    print('SIDE_MATED', pid, report[pid]['matedDatum'], 'port centre yz', np.round(centre, 2).tolist(),
          'radius', round(radius, 1), 'rod stretch', round(stretch, 3), flush=True)

# Mate the binocular mounting plate onto the viewing-chamber seat. The result
# is the bino datum/rotation; data/parts.json must carry the same values.
def interface_empty(name, parent, matrix):
    empty = bpy.data.objects.new(name, None)
    assembly.objects.link(empty)
    empty.empty_display_type, empty.empty_display_size = 'SINGLE_ARROW', 60
    empty.parent = parent
    empty.matrix_basis = matrix
    return empty

seat, mount = INTERFACES['vc']['bino_seat'], INTERFACES['bino']['mount']
seat_local = frame(seat['point'], seat['normal'], seat['up'])
mount_local = frame((0, 0, 0), mount['normal'], mount['up'])
bpy.context.view_layer.update()
roots['bino'].matrix_world = roots['vc'].matrix_world @ seat_local @ FACE_TO_FACE @ mount_local.inverted()
interface_empty('vc.bino_seat', roots['vc'], seat_local)
interface_empty('bino.mount', roots['bino'], mount_local)
bpy.context.view_layer.update()
report['bino']['matedDatum'] = [round(c, 2) for c in roots['bino'].location]
report['bino']['matedRotationDeg'] = [round(math.degrees(a), 2) for a in roots['bino'].rotation_euler]
print('BINO_MATED', report['bino']['matedDatum'], report['bino']['matedRotationDeg'], flush=True)

# Simple, material-independent studio view; camera and lights are excluded from exports.
world = bpy.data.worlds.new('White studio')
scene.world = world
world.use_nodes = True
world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.65,0.68,0.72,1)
world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.7
for xyz, power, size in [((2800,-3200,4200),350000,2200),((-2400,-500,1800),180000,1800),((600,2500,3000),250000,2000)]:
    light = bpy.data.lights.new('Softbox','AREA')
    light.energy, light.shape, light.size = power,'DISK',size
    obj = bpy.data.objects.new('Softbox',light)
    scene.collection.objects.link(obj)
    obj.location = xyz
    obj.rotation_euler = (-obj.location).to_track_quat('-Z','Y').to_euler()
camdata = bpy.data.cameras.new('Orthographic')
camdata.type, camdata.ortho_scale = 'ORTHO', 3700
camdata.clip_end = 20000
camera = bpy.data.objects.new('Camera',camdata)
scene.collection.objects.link(camera)
scene.camera = camera
target = Vector((0,0,-220))
for view, loc in [('front',(0,-5200,-150)),('left',(-5200,0,-150)),
                  ('right',(5200,0,-150)),('top',(0,0,5200)),('iso',(3700,-5200,2700))]:
    camera.location = loc
    camera.rotation_euler = (target-camera.location).to_track_quat('-Z','Y').to_euler()
    scene.render.filepath = str(PREVIEWS / f'assembly_{view}.png')
    bpy.ops.render.render(write_still=True)

bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(OUT / 'TEM_assembly.blend'))
(OUT / 'assembly.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
print('ASSEMBLY_COMPLETE', flush=True)
