"""Read-back checks for the normalized GLBs; run in Blender background mode."""
import bpy
import json
from pathlib import Path
from mathutils import Vector

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs' / 'blender-assembly'
parts = json.loads((ROOT / 'data' / 'parts.json').read_text(encoding='utf-8'))['parts']
bpy.ops.wm.read_factory_settings(use_empty=True)
results = {}
for part in parts:
    pid = part['id']
    bpy.ops.object.select_all(action='SELECT')
    bpy.ops.object.delete(use_global=False)
    bpy.ops.import_scene.gltf(filepath=str(OUT / 'assets' / f'{pid}_full.glb'))
    meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
    root = bpy.data.objects.get(pid)
    assert root and len(meshes) >= 1, pid
    points = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
    low = [min(p[i] for p in points) for i in range(3)]
    high = [max(p[i] for p in points) for i in range(3)]
    extent = [high[i]-low[i] for i in range(3)]
    triangles = sum(sum(len(poly.vertices)-2 for poly in o.data.polygons) for o in meshes)
    children = {}
    for obj in meshes:
        q = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
        children[obj.name] = dict(center=[(min(p[i] for p in q)+max(p[i] for p in q))/2 for i in range(3)],
                                  extent=[max(p[i] for p in q)-min(p[i] for p in q) for i in range(3)])
    results[pid] = dict(rootName=root.name, meshCount=len(meshes),
        boundsMetres=[low,high], extentMetres=extent, triangles=triangles,
        children=children,
        bytes=(OUT / 'assets' / f'{pid}_full.glb').stat().st_size,
        imageSizes=[list(i.size) for i in bpy.data.images])
    assert max(abs(x) for x in low+high) < 4, f'{pid}: metres conversion failed'
    if pid in ('gun','accel','cl','ol','il','pl','vc','base'):
        expected = part['dims'].get('height',part['dims'].get('z'))/1000
        assert abs(extent[2]-expected) < 0.005, f'{pid}: height {extent[2]} != {expected}'
    print('VERIFIED',pid,round(max(extent),3),'m',triangles,'tris',flush=True)
(OUT / 'verification.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print('VERIFICATION_COMPLETE',flush=True)
