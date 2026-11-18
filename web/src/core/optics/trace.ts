import type { ActiveElement, OpticalConfig } from './system';

/** Paraxial ray in the meridional plane: off-axis distance x (mm) and slope θ (rad) going down, at z. */
export interface Ray { z: number; x: number; t: number }
/** Ray transfer matrix [A, B, C, D]: x' = A x + B θ, θ' = C x + D θ. Always has determinant 1. */
export type Mat = [number, number, number, number];

export type BlockKind = 'aperture' | 'clear';
export interface TraceResult {
  /** Start, every element plane passed, and the end (or the plane where the ray stopped). */
  points: { z: number; x: number }[];
  end: Ray;
  blocked?: { id: string; kind: BlockKind };
}

export const IDENTITY: Mat = [1, 0, 0, 1];
export const mul = (m: Mat, n: Mat): Mat =>
  [m[0] * n[0] + m[1] * n[2], m[0] * n[1] + m[1] * n[3], m[2] * n[0] + m[3] * n[2], m[2] * n[1] + m[3] * n[3]];
export const drift = (d: number): Mat => [1, d, 0, 1];
export const thinLens = (f: number | null | undefined): Mat => (f ? [1, 0, -1 / f, 1] : IDENTITY);

/** Elements strictly between z0 (above) and z1 (below), top to bottom. */
export function between(config: OpticalConfig, z0: number, z1: number): ActiveElement[] {
  return config.elements.filter((e) => e.z < z0 && e.z > z1);
}

export function stopKind(e: ActiveElement, x: number): BlockKind | undefined {
  if (e.aperture && Math.abs(x - e.aperture.center) > e.aperture.radius) return 'aperture';
  if (e.clearRadius !== undefined && e.type === 'lens' && Math.abs(x) > e.clearRadius) return 'clear';
  return undefined;
}

function apply(e: ActiveElement, x: number, t: number): number {
  if (e.type === 'lens' && e.f) t -= x / e.f;
  if (e.deflection) t += e.deflection;
  return t;
}

/** Traces a ray down to zEnd. With clip = false it ignores apertures and clear radii (but still reports the first stop). */
export function traceRay(config: OpticalConfig, start: Ray, zEnd: number, clip = true): TraceResult {
  let { x, t, z } = start;
  const points = [{ z, x }];
  let blocked: TraceResult['blocked'];
  for (const e of between(config, start.z, zEnd)) {
    x += t * (z - e.z);
    z = e.z;
    points.push({ z, x });
    const kind = stopKind(e, x);
    if (kind && !blocked) {
      blocked = { id: e.id, kind };
      if (clip) return { points, end: { z, x, t }, blocked };
    }
    t = apply(e, x, t);
  }
  x += t * (z - zEnd);
  points.push({ z: zEnd, x });
  return { points, end: { z: zEnd, x, t }, blocked };
}

/** Transfer matrix from z0 down to z1 (deflectors only add constant slopes and are left out). */
export function transfer(config: OpticalConfig, z0: number, z1: number): Mat {
  let m = IDENTITY, z = z0;
  for (const e of between(config, z0, z1)) {
    m = mul(thinLens(e.type === 'lens' ? e.f : null), mul(drift(z - e.z), m));
    z = e.z;
  }
  return mul(drift(z - z1), m);
}

const PLANE_TOL = 0.5;

/** Planes between z0 and z1 where B = 0 (images of the plane z0) or A = 0 (images of its far field, e.g. back focal planes). */
export function conjugatePlanes(config: OpticalConfig, z0: number, z1: number, kind: 'image' | 'diffraction'): number[] {
  const found: number[] = [];
  let m = IDENTITY, z = z0;
  const segment = (zEnd: number) => {
    const [a, b, c, d] = m;
    const [p, q] = kind === 'image' ? [b, d] : [a, c];
    if (q !== 0) {
      const s = -p / q;
      // A conjugate within PLANE_TOL past the end (rounding of preset focal lengths) still counts as on the end plane.
      const at = z - s;
      if (s > 1e-9 && s <= z - zEnd + PLANE_TOL && !(found.length && Math.abs(found[found.length - 1] - at) < PLANE_TOL)) found.push(at);
    }
  };
  for (const e of between(config, z0, z1)) {
    segment(e.z);
    m = mul(thinLens(e.type === 'lens' ? e.f : null), mul(drift(z - e.z), m));
    z = e.z;
  }
  segment(z1);
  return found;
}

/** Affine function of the start ray (x₀, θ₀): value = [e, a, b] → e + a·x₀ + b·θ₀. */
export type Affine = [number, number, number];
export const evalAffine = (f: Affine, x: number, t: number) => f[0] + f[1] * x + f[2] * t;

/** x at every element plane between z0 and z1, and (x, θ) at z1, as affine functions of the start ray. Includes deflectors. */
export function planeMaps(config: OpticalConfig, z0: number, z1: number) {
  const [o, ex, et] = [{ x: 0, t: 0 }, { x: 1, t: 0 }, { x: 0, t: 1 }].map((r) => traceRay(config, { z: z0, ...r }, z1, false));
  const affine = (p: number, a: number, b: number): Affine => [p, a - p, b - p];
  return {
    planes: between(config, z0, z1).map((element, i) =>
      ({ element, x: affine(o.points[i + 1].x, ex.points[i + 1].x, et.points[i + 1].x) })),
    x: affine(o.end.x, ex.end.x, et.end.x),
    t: affine(o.end.t, ex.end.t, et.end.t),
  };
}
