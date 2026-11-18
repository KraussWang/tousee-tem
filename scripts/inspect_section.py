"""Side-by-side inspection renders of <id>_full.glb and <id>_section.glb for visual acceptance.

Run: blender -b --factory-startup --python scripts/inspect_section.py [-- id ...]   (default: every part with a section GLB)
Set INSPECT_KINDS=section to skip the exterior renders.
Writes outputs/blender-assembly/previews/inspect/<id>_{full,section}_<view>.png; same camera for both assets,
so an artefact seen only in the section image was introduced by the section build.
"""
import bpy
import math
import os
import sys
from pathlib import Path
from mathutils import Matrix, Vector

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'outputs' / 'blender-assembly' / 'assets'
OUT = ROOT / 'outputs' / 'blender-assembly' / 'previews' / 'inspect'
OUT.mkdir(parents=True, exist_ok=True)
ids = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sorted(p.name[:-12] for p in ASSETS.glob('*_section.glb'))

# (name, azimuth deg from -Y counter-clockwise, elevation deg)
VIEWS = [('front', 0, 0), ('iso', -35, 25), ('left', 270, 0), ('right', 90, 0), ('top', 0, 89), ('iso_back', 145, 25),
         ('low', -20, -25)]


def setup():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.resolution_x = scene.render.resolution_y = 1000
    world = bpy.data.worlds.new('studio')
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.32, 0.36, 0.42, 1)
    world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.8
    for xyz, power in [((-900, -1500, 1400), 9000), ((1200, -800, 600), 5000), ((300, 1200, 1500), 6000), ((-600, 300, -900), 3000)]:
        light = bpy.data.lights.new('soft', 'AREA')
        light.energy, light.size = power * 60, 900
        obj = bpy.data.objects.new('soft', light)
        scene.collection.objects.link(obj)
        obj.location = xyz
        obj.rotation_euler = (Vector((0, 0, 200)) - obj.location).to_track_quat('-Z', 'Y').to_euler()
    cam = bpy.data.cameras.new('ortho')
    cam.type, cam.clip_end = 'ORTHO', 20000
    camera = bpy.data.objects.new('camera', cam)
    scene.collection.objects.link(camera)
    scene.camera = camera
    return scene, camera


for pid in ids:
    for kind in os.environ.get('INSPECT_KINDS', 'full,section').split(','):
        scene, camera = setup()
        bpy.ops.import_scene.gltf(filepath=str(ASSETS / f'{pid}_{kind}.glb'))
        bpy.context.view_layer.update()
        meshes = [o for o in bpy.data.objects if o.type == 'MESH']
        # Scene is mm: GLB root carries 0.001 and the importer converts Y-up back to Z-up.
        for obj in [o for o in bpy.data.objects if o.parent is None and o.type != 'CAMERA' and o.type != 'LIGHT']:
            obj.matrix_world = Matrix.Scale(1000, 4) @ obj.matrix_world
        bpy.context.view_layer.update()
        pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
        lo = Vector([min(p[i] for p in pts) for i in range(3)])
        hi = Vector([max(p[i] for p in pts) for i in range(3)])
        target, size = (lo + hi) / 2, max(hi - lo) * 1.15
        camera.data.ortho_scale = size
        for name, az, el in VIEWS:
            a, e = math.radians(az), math.radians(el)
            camera.location = target + 3000 * Vector((math.cos(e) * math.sin(a), -math.cos(e) * math.cos(a), math.sin(e)))
            camera.rotation_euler = (target - camera.location).to_track_quat('-Z', 'Y').to_euler()
            scene.render.filepath = str(OUT / f'{pid}_{kind}_{name}.png')
            bpy.ops.render.render(write_still=True)
        print('INSPECTED', pid, kind, flush=True)
