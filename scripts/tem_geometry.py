"""Mesh measurements shared by the assembly and verification scripts.

All functions take world-space points in millimetres (Z up).
"""
import math
import numpy as np
from mathutils import Matrix, Vector


def mesh_points(objects):
    points = []
    for obj in objects:
        if obj.type != 'MESH':
            continue
        count = len(obj.data.vertices)
        local = np.empty(count * 3)
        obj.data.vertices.foreach_get('co', local)
        local = local.reshape(-1, 3)
        m = np.array(obj.matrix_world)
        points.append(local @ m[:3, :3].T + m[:3, 3])
    return np.concatenate(points)


def _kasa(xy):
    a = np.column_stack((xy, np.ones(len(xy))))
    d, e, f = np.linalg.lstsq(a, -(xy ** 2).sum(1), rcond=None)[0]
    centre = np.array((-d / 2, -e / 2))
    return centre, math.sqrt(max(centre @ centre - f, 0))


def flange_circle(points, z0, z1, bins=90, iterations=5, min_coverage=0.5):
    """Centre/radius of the outer rim of a flange lying in the slab z0..z1.

    The outermost vertex is taken per angular bin; bins whose radius departs
    from the median (side ports, actuators, seats) are rejected before a
    least-squares circle fit.
    """
    xy = points[(points[:, 2] >= z0) & (points[:, 2] <= z1)][:, :2]
    if len(xy) < 12:
        raise RuntimeError(f'flange slab {z0:.1f}..{z1:.1f}: too few vertices')
    centre = (xy.min(0) + xy.max(0)) / 2
    for _ in range(iterations):
        d = xy - centre
        r = np.hypot(d[:, 0], d[:, 1])
        idx = ((np.arctan2(d[:, 1], d[:, 0]) + math.pi) / (2 * math.pi) * bins).astype(int) % bins
        outer = np.array([xy[idx == b][r[idx == b].argmax()] for b in range(bins) if (idx == b).any()])
        ro = np.hypot(*(outer - centre).T)
        keep = outer[np.abs(ro - np.median(ro)) < 0.04 * np.median(ro)]
        centre, radius = _kasa(keep)
    if len(keep) / bins < min_coverage:
        raise RuntimeError(f'flange slab {z0:.1f}..{z1:.1f}: rim coverage {len(keep)/bins:.2f} < {min_coverage}')
    return centre, radius, len(keep) / bins


def yaw_degrees(points, z0, z1, limit=45, step=0.1):
    """Angle that the minimum-area XY rectangle of the slab makes with the X axis."""
    xy = points[(points[:, 2] >= z0) & (points[:, 2] <= z1)][:, :2]
    best = None
    for deg in np.arange(-limit, limit + step / 2, step):
        a = math.radians(deg)
        rx = xy @ np.array((math.cos(a), math.sin(a)))
        ry = xy @ np.array((-math.sin(a), math.cos(a)))
        area = np.ptp(rx) * np.ptp(ry)
        if best is None or area < best[0]:
            best = (area, deg)
    return float(best[1])


def side_rod(points, tip, rigid, step=2.0):
    """Locate a side-entry rod lying along X with its free end toward `tip` (+1/-1).

    Walks inward from the free end: the first `rigid` mm are the tongue/strip,
    then the thin rod, until a slice is >3x the rod size (the mounting flange).
    Returns the flange mating-face x, the rod axis (y, z) and the free-end x.
    """
    s = tip * points[:, 0]
    end = s.max()
    spans, centres = [], []
    depth = rigid
    while True:
        sl = points[(s <= end - depth) & (s > end - depth - step)]
        if len(sl) == 0:
            depth += step
            continue
        span = max(np.ptp(sl[:, 1]), np.ptp(sl[:, 2]))
        if spans and span > 3 * np.median(spans):
            break
        spans.append(span)
        centres.append(((sl[:, 1].min() + sl[:, 1].max()) / 2, (sl[:, 2].min() + sl[:, 2].max()) / 2))
        depth += step
        if depth > end - s.min():
            raise RuntimeError('side rod: no flange found')
    axis = np.median(np.array(centres), 0)
    return dict(face=tip * (end - depth), axis=axis, end=tip * end, rodDiameter=float(np.median(spans)))


def port_face(points, sign, min_radius=205, half_width=150):
    """Mating face x and (y, z) centre of the side-port flange of a column part on the `sign` X side."""
    sel = points[(sign * points[:, 0] > min_radius) & (np.abs(points[:, 1]) < half_width)]
    face = np.percentile(sign * sel[:, 0], 99.5)
    slab = sel[sign * sel[:, 0] >= face - 6]
    centre, radius, coverage = flange_circle(slab[:, [1, 2, 0]], -1e9, 1e9, min_coverage=0)
    return float(sign * face), centre, radius, coverage


def side_flange(points, face, outward, depth=6):
    """(y, z) centre and radius of a side part's mounting flange whose mating face is at x=`face`,
    the flange extending toward `outward` (+1/-1) along X."""
    s = outward * (points[:, 0] - face)
    slab = points[(s >= 0) & (s <= depth)]
    centre, radius, _ = flange_circle(slab[:, [1, 2, 0]], -1e9, 1e9)
    return centre, radius


def frame(point, normal, up):
    """4x4 frame: origin at point, +Z along normal, +Y along up (orthogonalised)."""
    z = Vector(normal).normalized()
    y = (Vector(up) - Vector(up).dot(z) * z).normalized()
    x = y.cross(z)
    m = Matrix((x, y, z)).transposed().to_4x4()
    m.translation = Vector(point)
    return m


# Rotate 180 degrees about local Y: faces the two frames at each other, ups shared.
FACE_TO_FACE = Matrix.Rotation(math.pi, 4, 'Y')
