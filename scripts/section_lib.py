"""Shared builder for the half-section assets (scripts/build_section_<id>.py).

A section asset is the source exterior shell cut on the XZ plane (the -Y operator
half removed) plus schematic interior parts, in datum-local millimetres, Z up.
Input  outputs/blender-assembly/assets/<id>_full.glb
Output outputs/blender-assembly/assets/<id>_section.glb, section_<id>.json, previews/<id>_section_*.png
"""
import bpy
import bmesh
import json
import math
from pathlib import Path
import numpy as np
from mathutils import Euler, Matrix, Vector
from mathutils.bvhtree import BVHTree

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'outputs' / 'blender-assembly'
ASSETS, PREVIEWS = OUT / 'assets', OUT / 'previews'
PARTS = {p['id']: p for p in json.loads((ROOT / 'data' / 'parts.json').read_text(encoding='utf-8'))['parts']}
SEGMENTS = 40  # per 180 degrees


def rect(r0, r1, z0, z1):
    return [(r0, z0), (r1, z0), (r1, z1), (r0, z1)]


def yoke(z0, z1, r_out, gap, t=12, pole=14, r_in=30):
    """Soft-iron C yoke open toward the bore, conical pole tips around a gap at mid height."""
    zc, p = (z0 + z1) / 2, pole
    return [(r_in, z0), (r_out, z0), (r_out, z1), (r_in, z1), (r_in, zc + gap/2), (r_in + p, zc + gap/2 + p),
            (r_in + p, z1 - t), (r_out - t, z1 - t), (r_out - t, z0 + t), (r_in + p, z0 + t),
            (r_in + p, zc - gap/2 - p), (r_in, zc - gap/2)]


def coil_layers(r0, r1, z0, z1, layers):
    """Winding stacked in thin slabs so the section shows turns."""
    step = (z1 - z0) / layers
    return [rect(r0, r1, z0 + k*step + 0.4, z0 + (k+1)*step - 0.4) for k in range(layers)]


def former(r0, r1, z0, z1):
    """Insulating bobbin of a thin ring coil (winding out to r1), open toward the bore."""
    return [(r0, z0), (r1 + 8, z0), (r1 + 8, z1), (r0, z1), (r0, z1 - 2), (r1 + 4, z1 - 2), (r1 + 4, z0 + 2), (r0, z0 + 2)]


def points(obj):
    co = np.empty(len(obj.data.vertices) * 3)
    obj.data.vertices.foreach_get('co', co)
    return co.reshape(-1, 3)


def triangles(obj):
    return sum(len(p.vertices) - 2 for p in obj.data.polygons)


def bvh(obj):
    return BVHTree.FromPolygons([v.co.copy() for v in obj.data.vertices], [tuple(p.vertices) for p in obj.data.polygons])


class Section:
    def __init__(self, pid, mates=()):
        """`mates`: ids of neighbouring parts whose exterior must not hit the interior (e.g. a side-entry rod)."""
        bpy.ops.wm.read_factory_settings(use_empty=True)
        self.scene = bpy.context.scene
        self.pid, self.part = pid, PARTS[pid]
        self.height = self.part['dims'].get('height', self.part['dims'].get('z'))
        self.unsectioned = {f'{pid}__attachments'}
        self.report = dict(meshes={}, failures=[])
        self.mates = {}
        for mate in mates:
            other = PARTS[mate]
            place = (Matrix.Translation(Vector(other['datum']) - Vector(self.part['datum']))
                     @ Euler([math.radians(a) for a in other.get('rotation', (0, 0, 0))], 'XYZ').to_matrix().to_4x4())
            objs = self._import(mate)
            for obj in objs:
                obj.data.transform(place)
            self.mates[mate] = [bvh(o) for o in objs]
            for obj in objs:
                bpy.data.objects.remove(obj, do_unlink=True)
        self.source, = self._import(pid)
        self.shell_mat = self.source.data.materials[0]
        # Only after the imports: the glTF importer compensates for the scene unit scale.
        self.scene.unit_settings.scale_length, self.scene.unit_settings.length_unit = 0.001, 'MILLIMETERS'
        # PRD 8.2 colour table; the section face of the housing is the light grey #E6E6E6.
        self.mat = dict(section=self._material('section_grey', 'E6E6E6', 0.0, 0.6),
                        steel=self._material('stainless', 'C8CCD0', 1.0, 0.35),
                        iron=self._material('pole_iron', '6E7378', 0.6, 0.45),
                        copper=self._material('coil_copper', 'B87333', 1.0, 0.35),
                        black=self._material('insulation', '2B2B2B', 0.0, 0.6),
                        brass=self._material('brass', 'C9A227', 1.0, 0.3),
                        paint=self._material('offwhite_paint', 'EDEDE8', 0.0, 0.5))
        self.root = bpy.data.objects.new(pid, None)
        self.scene.collection.objects.link(self.root)

    @staticmethod
    def _material(name, hex_rgb, metallic, roughness):
        mat = bpy.data.materials.new(name)
        mat.use_nodes = True
        bsdf = mat.node_tree.nodes['Principled BSDF']
        srgb = [int(hex_rgb[i:i+2], 16) / 255 for i in (0, 2, 4)]
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in srgb]
        bsdf.inputs['Base Color'].default_value = (*linear, 1)
        bsdf.inputs['Metallic'].default_value = metallic
        bsdf.inputs['Roughness'].default_value = roughness
        return mat

    @staticmethod
    def _import(pid):
        """Meshes of <pid>_full.glb as unparented objects in that part's datum-local mm, Z up."""
        existing = set(bpy.data.objects)
        bpy.ops.import_scene.gltf(filepath=str(ASSETS / f'{pid}_full.glb'))
        bpy.context.view_layer.update()
        new = [o for o in bpy.data.objects if o not in existing]
        meshes = [o for o in new if o.type == 'MESH']
        for obj in meshes:
            obj.data.transform(Matrix.Scale(1000, 4) @ obj.matrix_world)
        for obj in [o for o in new if o.type != 'MESH']:
            bpy.data.objects.remove(obj, do_unlink=True)
        for obj in meshes:
            obj.matrix_world = Matrix.Identity(4)
        return meshes

    # ------------------------------------------------------------ exterior
    def split_shell(self, is_attachment, is_inner):
        """`<id>__attachments` (kept whole: standard parts are not sectioned) and `<id>__shell`
        (cut on y=0, -Y half removed). Both predicates take a face centre and normal;
        `is_inner` marks generated bore/inner surfaces that the modelled interior replaces.
        On the cut-away -Y half an attachment face also needs each vertex, pulled `pull` of the way toward
        the face centre, to pass `is_attachment`: the generated meshes join attachments to the body skin
        with long fan triangles, which would otherwise hang as spikes once the skin behind them is cut
        away; the pull spares ordinary faces whose corners sit just past the predicate's bounds.
        Tiny loose fragments are dropped."""
        pull = 0.35
        def attached(f):
            c, n = f.calc_center_median(), f.normal
            return is_attachment(c, n) and (c.y >= 0 or all(is_attachment(v.co.lerp(c, pull), n) for v in f.verts))
        def part(keep):
            bm = bmesh.new()
            bm.from_mesh(self.source.data)
            bmesh.ops.delete(bm, geom=[f for f in bm.faces if not keep(f)], context='FACES')
            return bm
        attachments = part(attached)
        body = part(lambda f: not attached(f) and not is_inner(f.calc_center_median(), f.normal))
        cut = bmesh.ops.bisect_plane(body, geom=body.verts[:] + body.edges[:] + body.faces[:],
                                     plane_co=(0, 0, 0), plane_no=(0, 1, 0), clear_inner=True)
        self.cut_edge = np.array([v.co[:] for v in cut['geom_cut'] if isinstance(v, bmesh.types.BMVert)])
        dense = [np.array(e.verts[0].co.lerp(e.verts[1].co, t)) for e in cut['geom_cut'] if isinstance(e, bmesh.types.BMEdge)
                 for t in np.linspace(0, 1, max(2, int(e.calc_length()) + 1))]
        self.cut_dense = np.array(dense) if dense else self.cut_edge
        def as_object(name, bm):
            self._drop_fragments(bm)
            mesh = bpy.data.meshes.new(name)
            bm.to_mesh(mesh)
            bm.free()
            obj = bpy.data.objects.new(name, mesh)
            self.scene.collection.objects.link(obj)
            obj.parent = self.root
            mesh.materials.append(self.shell_mat)
            return obj
        self.shell = as_object(f'{self.pid}__shell', body)
        self.attachments = as_object(f'{self.pid}__attachments', attachments)
        bpy.data.objects.remove(self.source, do_unlink=True)

    @staticmethod
    def _drop_fragments(bm, min_area=60.0):
        """Delete face islands smaller than `min_area` mm² (slivers left by the split and the cut). The imported
        meshes split vertices along UV/normal seams, so faces are joined through coincident vertex positions."""
        parent = list(range(len(bm.faces)))
        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i
        bm.faces.index_update()
        owner = {}  # rounded vertex position -> a face index using it
        for f in bm.faces:
            for v in f.verts:
                key = tuple(round(c, 2) for c in v.co)
                if key in owner:
                    parent[find(f.index)] = find(owner[key])
                else:
                    owner[key] = f.index
        area = {}
        for f in bm.faces:
            root = find(f.index)
            area[root] = area.get(root, 0.0) + f.calc_area()
        doomed = [f for f in bm.faces if area[find(f.index)] < min_area]
        bmesh.ops.delete(bm, geom=doomed, context='FACES')
        bmesh.ops.delete(bm, geom=[v for v in bm.verts if not v.link_faces], context='VERTS')

    def shell_radius(self, z, half=1.5):
        """Inscribed radius of the shell at height z, None where absent: the smaller of the cut edge's
        +X / -X sides and of the outer surface met by rays cast inward across the kept +Y half (side
        ports and flanges on the cut plane must not make the revolved housing poke through the shell
        further round). Rays come from outside so leftover inner skins are never hit first."""
        sel = self.cut_dense[np.abs(self.cut_dense[:, 2] - z) < half]
        sides = [np.abs(s[:, 0]).max() for s in (sel[sel[:, 0] > 0], sel[sel[:, 0] < 0]) if len(s)]
        if not sides:
            return None
        if not hasattr(self, 'shell_tree'):
            self.shell_tree = bvh(self.shell)
        far = 1000
        rays = [self.shell_tree.ray_cast(Vector((far * math.cos(a), far * math.sin(a), z)), Vector((-math.cos(a), -math.sin(a), 0)), far)
                for a in np.radians(np.arange(15, 166, 15))]
        return min(sides + [far - hit[3] for hit in rays if hit[0] is not None])

    def outer_profile(self, z0, z1, margin=1.0, step=2.0, floor=0.0):
        """(r, z) polyline from z0 up to z1 that sits `margin` inside the shell's cut edge."""
        zs = np.arange(z0, z1 + step / 2, step)
        zs[-1] = z1
        raw = [self.shell_radius(z) for z in zs]
        ok = np.array([r is not None and r > floor for r in raw])
        r = np.interp(zs, zs[ok], np.array([x for x, good in zip(raw, ok) if good]))
        r = np.minimum.reduce([r, np.r_[r[1:], r[-1]], np.r_[r[0], r[:-1]]]) - margin
        self.housing_samples = [(float(z), float(x)) for z, x in zip(zs[2:-2], r[2:-2])]
        profile = [(float(r[0]), float(zs[0]))]
        for i in range(1, len(zs)):  # hold each radius until it changes, so steps stay square
            if abs(r[i] - profile[-1][0]) > 0.4:
                profile += [(profile[-1][0], float(zs[i-1])), (float(r[i]), float(zs[i]))]
        profile.append((profile[-1][0], float(zs[-1])))
        return [p for i, p in enumerate(profile) if i == 0 or p != profile[i-1]]

    # ------------------------------------------------------------ interior
    def new_object(self, name, bm, mat, cap=None):
        """`cap`: material for the section faces on y=0 (the rest keeps `mat`)."""
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        mesh = bpy.data.meshes.new(name)
        bm.to_mesh(mesh)
        bm.free()
        mesh.materials.append(mat)
        if cap:
            mesh.materials.append(cap)
        obj = bpy.data.objects.new(name, mesh)
        self.scene.collection.objects.link(obj)
        obj.parent = self.root
        self._paint_cap(obj)
        return obj

    @staticmethod
    def _paint_cap(obj):
        if len(obj.data.materials) > 1:
            for poly in obj.data.polygons:
                poly.material_index = int(abs(poly.center.y) < 1e-3 and abs(poly.normal.y) > 0.99)

    @staticmethod
    def revolve(bm, profile):
        """Closed (r, z) polygon swept 180 degrees about Z from +X through +Y to -X.
        The two end caps lie on y=0 and are the section faces."""
        rings = []
        for k in range(SEGMENTS + 1):
            a = math.pi * k / SEGMENTS
            rings.append([bm.verts.new((r * math.cos(a), r * math.sin(a), z)) for r, z in profile])
        n = len(profile)
        for k in range(SEGMENTS):
            for i in range(n):
                j = (i + 1) % n
                bm.faces.new((rings[k][i], rings[k][j], rings[k+1][j], rings[k+1][i]))
        bm.faces.new(rings[0][::-1])
        bm.faces.new(rings[-1])

    def solid(self, name, mat, *profiles, cap=None):
        bm = bmesh.new()
        for profile in profiles:
            self.revolve(bm, profile)
        return self.new_object(name, bm, self.mat[mat], self.mat[cap] if cap else None)

    def ring_coil(self, hid, r0, r1, z0, z1, layers=2):
        """Thin stigmator / deflector ring: black bobbin `<hid>__former` and copper winding `<hid>`."""
        self.solid(f'{hid}__former', 'black', former(r0, r1, z0, z1))
        self.solid(hid, 'copper', *coil_layers(r0 + 6, r1, z0 + 2, z1 - 2, layers))

    @staticmethod
    def _x_cylinder(x0, x1, radius, y, z, inner=0.0, segments=32):
        bm = bmesh.new()
        def ring(rr, x):
            return [bm.verts.new((x, y + rr * math.cos(2*math.pi*k/segments), z + rr * math.sin(2*math.pi*k/segments)))
                    for k in range(segments)]
        o0, o1 = ring(radius, x0), ring(radius, x1)
        for k in range(segments):
            bm.faces.new((o0[k], o0[(k+1) % segments], o1[(k+1) % segments], o1[k]))
        if inner:  # tube: inner wall and annular ends
            i0, i1 = ring(inner, x0), ring(inner, x1)
            for k in range(segments):
                j = (k + 1) % segments
                bm.faces.new((i0[j], i0[k], i1[k], i1[j]))
                bm.faces.new((o0[j], o0[k], i0[k], i0[j]))
                bm.faces.new((o1[k], o1[j], i1[j], i1[k]))
        else:
            bm.faces.new(o0)
            bm.faces.new(o1)
        return bm

    def x_cylinder(self, name, mat, x0, x1, radius, z, y=0.0, inner=0.0):
        """Whole (unsectioned) rod or tube along X."""
        self.unsectioned.add(name)
        return self.new_object(name, self._x_cylinder(x0, x1, radius, y, z, inner), self.mat[mat])

    def box(self, name, mat, lo, hi, cap=None, sectioned=True):
        bm = bmesh.new()
        bmesh.ops.create_cube(bm, size=1)
        bmesh.ops.scale(bm, vec=[h - l for l, h in zip(lo, hi)], verts=bm.verts[:])
        bmesh.ops.translate(bm, vec=[(l + h) / 2 for l, h in zip(lo, hi)], verts=bm.verts[:])
        if not sectioned:
            self.unsectioned.add(name)
        return self.new_object(name, bm, self.mat[mat], self.mat[cap] if cap else None)

    def cutter(self, kind, *args):
        """Temporary boolean tool: ('x', x0, x1, radius, y, z[, segments]) | ('z', z0, z1, radius, x, y[, segments]) | ('box', lo, hi)."""
        if kind == 'box':
            bm = bmesh.new()
            lo, hi = args
            bmesh.ops.create_cube(bm, size=1)
            bmesh.ops.scale(bm, vec=[h - l for l, h in zip(lo, hi)], verts=bm.verts[:])
            bmesh.ops.translate(bm, vec=[(l + h) / 2 for l, h in zip(lo, hi)], verts=bm.verts[:])
        else:
            a0, a1, radius, u, v, *segments = args
            bm = self._x_cylinder(a0, a1, radius, u if kind == 'x' else v, v if kind == 'x' else -u, segments=(segments or [48])[0])
            if kind == 'z':  # x -> z, y -> y, z -> -x
                bmesh.ops.transform(bm, matrix=Matrix(((0, 0, -1), (0, 1, 0), (1, 0, 0))).to_4x4(), verts=bm.verts[:])
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
        mesh = bpy.data.meshes.new('cutter')
        bm.to_mesh(mesh)
        bm.free()
        obj = bpy.data.objects.new('cutter', mesh)
        self.scene.collection.objects.link(obj)
        return obj

    def carve(self, obj, *cutters, operation='DIFFERENCE'):
        """Exact boolean of `obj` with each cutter (removed afterwards)."""
        for tool in cutters:
            tool = self.cutter(*tool) if isinstance(tool, tuple) else tool
            mod = obj.modifiers.new('carve', 'BOOLEAN')
            mod.operation, mod.object, mod.solver = operation, tool, 'EXACT'
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.modifier_apply(modifier=mod.name)
            bpy.data.objects.remove(tool, do_unlink=True)
        self._paint_cap(obj)
        return obj

    def strip(self, name, mat, x0, x1, width, z, holes, y=0.0, thickness=2.0):
        """Whole flat strip along X with vertical through-holes [(x, diameter), ...]."""
        obj = self.box(name, mat, (x0, y - width/2, z - thickness/2), (x1, y + width/2, z + thickness/2), sectioned=False)
        return self.carve(obj, *[('z', z - 5, z + 5, d / 2, x, y, 24) for x, d in holes])

    # ------------------------------------------------------------ checks, export, previews
    def check(self, ok, message):
        if not ok:
            self.report['failures'].append(message)

    def finish(self, hotspots, housing_samples=None, joined=(), axis=None, view_x=0.0, ortho=820, grow=5):
        """`hotspots`: {hotspot id: mesh name or (mesh name, bbox growth mm)} that must sit on their mesh.
        `housing_samples`: [(z, r)] of the housing wall, checked against the shell's cut edge.
        `joined`: mesh-name pairs that are allowed to interpenetrate.
        `axis`: (z_top, z_bottom) of the optical axis that must be unobstructed."""
        pid, report, check = self.pid, self.report, self.check
        meshes = [o for o in self.root.children if o.type == 'MESH']
        report['meshes'] = {o.name: triangles(o) for o in meshes}
        for obj in meshes:
            check(len(obj.data.vertices) > 0, f'{obj.name} is empty')
        meshes = [o for o in meshes if len(o.data.vertices)]
        report['triangles'] = sum(report['meshes'].values())
        check(report['triangles'] <= 50000, f"{report['triangles']} triangles > 50k")
        for obj in meshes:
            p = points(obj)
            if obj.name not in self.unsectioned:
                check(p[:, 1].min() >= -0.01, f'{obj.name} reaches y={p[:, 1].min():.2f}')
            check(p[:, 2].min() >= -0.01 and p[:, 2].max() <= self.height + 0.01, f'{obj.name} outside z 0..{self.height}')
        if housing_samples:
            # Housing cap stays inside the shell's cut edge.
            inside = []
            for z, r in housing_samples:
                for side in (1, -1):
                    sel = self.cut_dense[(side * self.cut_dense[:, 0] > 150) & (np.abs(self.cut_dense[:, 2] - z) < 2)]
                    if len(sel):
                        inside.append(bool(np.abs(sel[:, 0]).max() >= r - 0.5))
            report['housingInsideShell'] = dict(samples=len(inside), inside=int(sum(inside)))
            check(sum(inside) >= 0.9 * len(inside), f'housing pokes through the shell at {len(inside) - sum(inside)} of {len(inside)} samples')
        # Each hotspot sits on its mesh (grown bounding box).
        report['hotspots'] = {}
        local = {s['id']: np.array(s['local']) for s in self.part['hotspots']}
        for hid, target in hotspots.items():
            name, pad = target if isinstance(target, tuple) else (target, grow)
            p = points(bpy.data.objects[name])
            inside = bool(np.all(local[hid] >= p.min(0) - pad) and np.all(local[hid] <= p.max(0) + pad))
            report['hotspots'][hid] = inside
            check(inside, f'hotspot {hid} {local[hid].tolist()} not on {name}')
        # Interior parts do not interpenetrate each other or the neighbouring parts' exteriors.
        interior = [o for o in meshes if o not in (self.shell, self.attachments)]
        trees = {o.name: bvh(o) for o in meshes}
        allowed = {frozenset(pair) for pair in joined}
        report['overlaps'] = {}
        for i, a in enumerate(interior):
            for b in interior[i+1:]:
                n = len(trees[a.name].overlap(trees[b.name]))
                if n:
                    report['overlaps'][f'{a.name}/{b.name}'] = n
                    check(frozenset((a.name, b.name)) in allowed, f'{a.name} intersects {b.name} ({n} triangle pairs)')
        report['mateOverlaps'] = {}
        for mate, mate_trees in self.mates.items():
            hits = {o.name: n for o in interior if (n := sum(len(trees[o.name].overlap(t)) for t in mate_trees))}
            report['mateOverlaps'][mate] = hits
            check(not hits, f'{mate} exterior intersects {hits}')
        if axis:
            top, bottom = axis
            blocked = {}
            for name, tree in trees.items():
                hit = tree.ray_cast(Vector((0, 0.5, top)), Vector((0, 0, -1)), top - bottom)
                if hit[0] is not None:
                    blocked[name] = round(hit[0].z, 1)
            report['axisBlockedAtZ'] = blocked
            check(not blocked, f'optical axis blocked: {blocked}')

        bpy.ops.object.select_all(action='DESELECT')
        self.root.scale = (0.001,) * 3  # glTF metres; vertices stay datum-local millimetres
        self.root.select_set(True)
        for obj in meshes:
            obj.select_set(True)
        exported = ASSETS / f'{pid}_section.glb'
        bpy.ops.export_scene.gltf(filepath=str(exported), export_format='GLB', use_selection=True, export_yup=True, export_apply=False)
        report['exportedBytes'] = exported.stat().st_size
        check(report['exportedBytes'] <= 15 * 2**20, f"{report['exportedBytes']} bytes > 15 MB")
        self.root.scale = (1,) * 3

        scene = self.scene
        scene.render.engine = 'BLENDER_EEVEE'
        scene.render.resolution_x = scene.render.resolution_y = 1200
        world = bpy.data.worlds.new('studio')
        scene.world = world
        world.use_nodes = True
        world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.65, 0.68, 0.72, 1)
        world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.8
        for xyz, power in [((-900, -1500, 1400), 9000), ((1200, -800, 600), 5000), ((300, 1200, 1500), 6000)]:
            light = bpy.data.lights.new('soft', 'AREA')
            light.energy, light.size = power * 60, 900
            obj = bpy.data.objects.new('soft', light)
            scene.collection.objects.link(obj)
            obj.location = xyz
            obj.rotation_euler = (Vector((0, 0, 200)) - obj.location).to_track_quat('-Z', 'Y').to_euler()
        cam = bpy.data.cameras.new('ortho')
        cam.type, cam.ortho_scale, cam.clip_end = 'ORTHO', ortho, 10000
        camera = bpy.data.objects.new('camera', cam)
        scene.collection.objects.link(camera)
        scene.camera = camera
        target = Vector((view_x, 0, self.height / 2))
        for view, offset in [('front', (0, -2500, 0)), ('iso', (-1440, -2100, 1090))]:
            camera.location = target + Vector(offset)
            camera.rotation_euler = (target - camera.location).to_track_quat('-Z', 'Y').to_euler()
            scene.render.filepath = str(PREVIEWS / f'{pid}_section_{view}.png')
            bpy.ops.render.render(write_still=True)

        (OUT / f'section_{pid}.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print('SECTION_REPORT', json.dumps(report, ensure_ascii=False), flush=True)
        assert not report['failures'], report['failures']
        print('SECTION_COMPLETE', pid, report['triangles'], 'triangles', report['exportedBytes'], 'bytes', flush=True)
