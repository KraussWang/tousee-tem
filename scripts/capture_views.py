"""Render the assembled TEM from multiple angles.

Run: blender -b outputs/blender-assembly/TEM_assembly.blend --python scripts/capture_views.py
Reuses the camera, softbox lights and world already saved in the .blend file.
Dimensions in the scene are millimetres.
"""
import bpy
import math
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs' / 'blender-assembly' / 'views'
OUT.mkdir(parents=True, exist_ok=True)

scene = bpy.context.scene
scene.render.resolution_x = 1400
scene.render.resolution_y = 1400
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = 'PNG'

camera = scene.camera
if camera is None:
    camdata = bpy.data.cameras.new('Orthographic')
    camdata.type = 'ORTHO'
    camdata.clip_end = 20000
    camera = bpy.data.objects.new('Camera', camdata)
    scene.collection.objects.link(camera)
    scene.camera = camera
camdata = camera.data
camdata.type = 'ORTHO'
camdata.clip_end = 20000

target = Vector((0, 0, -220))

def track(loc):
    camera.location = loc
    camera.rotation_euler = (target - camera.location).to_track_quat('-Z', 'Y').to_euler()

# (name, azimuth_deg, elevation_deg, distance, ortho_scale)
# azimuth 0 = front (-Y), increases counter-clockwise seen from +Z.
VIEWS = [
    ('front',         0,   0, 5200, 3700),
    ('front_right',  45,   0, 5200, 3700),
    ('right',        90,   0, 5200, 3700),
    ('back_right',  135,   0, 5200, 3700),
    ('back',        180,   0, 5200, 3700),
    ('back_left',   225,   0, 5200, 3700),
    ('left',        270,   0, 5200, 3700),
    ('front_left',  315,   0, 5200, 3700),
    ('iso_fr',       45,  30, 6400, 3700),
    ('iso_br',      135,  30, 6400, 3700),
    ('iso_bl',      225,  30, 6400, 3700),
    ('iso_fl',      315,  30, 6400, 3700),
    ('top',           0,  89, 5200, 3000),
]

for name, az, el, dist, scale in VIEWS:
    azr, elr = math.radians(az), math.radians(el)
    loc = Vector((
        dist * math.cos(elr) * math.sin(azr),
        -dist * math.cos(elr) * math.cos(azr),
        target.z + dist * math.sin(elr),
    ))
    camdata.ortho_scale = scale
    track(loc)
    scene.render.filepath = str(OUT / f'tem_{name}.png')
    bpy.ops.render.render(write_still=True)
    print('RENDERED', name, flush=True)

print('VIEWS_COMPLETE', flush=True)
