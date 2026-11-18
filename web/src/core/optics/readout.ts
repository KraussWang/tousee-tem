import type { OpticsData } from '../../data/optics';
import type { OpticalConfig } from './system';
import { type Affine, conjugatePlanes, evalAffine, type Mat, planeMaps, type Ray, transfer, traceRay } from './trace';

type Point = [number, number];
/** Half-plane n·p ≤ k in the source phase space p = (x₀, θ₀). */
interface HalfPlane { n: Point; k: number }

function clip(poly: Point[], { n, k }: HalfPlane): Point[] {
  const out: Point[] = [];
  const side = (p: Point) => n[0] * p[0] + n[1] * p[1] - k;
  for (let i = 0; i < poly.length; i++) {
    const p = poly[i], q = poly[(i + 1) % poly.length];
    const sp = side(p), sq = side(q);
    if (sp <= 0) out.push(p);
    if (sp * sq < 0) {
      const s = sp / (sp - sq);
      out.push([p[0] + s * (q[0] - p[0]), p[1] + s * (q[1] - p[1])]);
    }
  }
  return out;
}

const area = (poly: Point[]) =>
  Math.abs(poly.reduce((sum, p, i) => { const q = poly[(i + 1) % poly.length]; return sum + p[0] * q[1] - q[0] * p[1]; }, 0)) / 2;

/** |e + a·x₀ + b·θ₀ − center| ≤ r as two half-planes. */
const band = (f: Affine, center: number, r: number): HalfPlane[] => [
  { n: [f[1], f[2]], k: r + center - f[0] },
  { n: [-f[1], -f[2]], k: r - center + f[0] },
];

export interface Illumination {
  /** Source rays (x₀, θ₀) that reach the specimen: vertices of a convex polygon (empty if none). */
  accepted: Point[];
  /** Specimen (x, θ) of a source ray. */
  atSpecimen: (p: Point) => { x: number; t: number };
  /** Where the source's central ray meets the specimen (illumination / probe centre). */
  center: number;
  /** Largest distance of an illuminated point from the centre: illumination radius (TEM) or probe radius (STEM). */
  radius: number;
  /** Convergence semi-angle at the specimen centre: half the angular range of the rays through it. */
  alpha: number;
  /** Beam current relative to the full emission: (accepted phase-space fraction)², ∝ solid angle. */
  current: number;
  /** Lenses whose clear radius cuts the illuminating beam. */
  blocked: string[];
}

export function illumination(config: OpticalConfig, optics: OpticsData): Illumination {
  const { radius: rs, halfAngle: ha } = optics.source;
  const maps = planeMaps(config, config.sourceZ, config.specimenZ);
  const rect: Point[] = [[-rs, -ha], [rs, -ha], [rs, ha], [-rs, ha]];
  const sourceBands: HalfPlane[] = [...band([0, 1, 0], 0, rs), ...band([0, 0, 1], 0, ha)];
  const apertureBands: HalfPlane[] = [], clearBands: HalfPlane[] = [];
  const clears: { id: string; x: Affine; r: number }[] = [];
  for (const { element: e, x } of maps.planes) {
    if (e.aperture) apertureBands.push(...band(x, e.aperture.center, e.aperture.radius));
    if (e.type === 'lens' && e.clearRadius !== undefined) {
      clearBands.push(...band(x, 0, e.clearRadius));
      clears.push({ id: e.id, x, r: e.clearRadius });
    }
  }
  const byApertures = apertureBands.reduce(clip, rect);
  const accepted = clearBands.reduce(clip, byApertures);
  const blocked = clears.filter((c) => byApertures.some(([x0, t0]) => Math.abs(evalAffine(c.x, x0, t0)) > c.r * (1 + 1e-9))).map((c) => c.id);
  const atSpecimen = ([x0, t0]: Point) => ({ x: evalAffine(maps.x, x0, t0), t: evalAffine(maps.t, x0, t0) });
  const center = maps.x[0];
  // Rays through the specimen centre form the line a·x₀ + b·θ₀ = 0, i.e. s·(b, −a); there θ − θ_c = −s (det = 1).
  const dir: Point = [maps.x[2], -maps.x[1]];
  let lo = -Infinity, hi = Infinity;
  for (const { n, k } of [...sourceBands, ...apertureBands, ...clearBands]) {
    const slope = n[0] * dir[0] + n[1] * dir[1];
    if (Math.abs(slope) < 1e-15) { if (k < 0) lo = Infinity; continue; }
    if (slope > 0) hi = Math.min(hi, k / slope); else lo = Math.max(lo, k / slope);
  }
  return {
    accepted, atSpecimen, center, blocked,
    radius: accepted.reduce((r, p) => Math.max(r, Math.abs(atSpecimen(p).x - center)), 0),
    alpha: lo <= hi ? Math.max(Math.abs(lo), Math.abs(hi)) : 0,
    current: accepted.length ? (area(accepted) / area(rect)) ** 2 : 0,
  };
}

/** Sample of the illuminating rays at the specimen: polygon vertices, edge midpoints and centroid. */
function illuminationSample(ill: Illumination): { x: number; t: number }[] {
  const poly = ill.accepted;
  if (!poly.length) return [];
  const pts: Point[] = [...poly, ...poly.map((p, i): Point => {
    const q = poly[(i + 1) % poly.length];
    return [(p[0] + q[0]) / 2, (p[1] + q[1]) / 2];
  })];
  pts.push([poly.reduce((s, p) => s + p[0], 0) / poly.length, poly.reduce((s, p) => s + p[1], 0) / poly.length]);
  return pts.map(ill.atSpecimen);
}

/** Largest diffraction order present in the specimen. */
export const maxOrder = (optics: OpticsData) =>
  Math.max(0, ...optics.specimen.regions.flatMap((r) => (r.beams ?? []).map((b) => b.order)));

/** Rays leaving the specimen: TEM — each illuminating ray plus its Bragg beams (θ ± n·θ_B); STEM — the transmitted
 *  cone plus high-angle scattering at absolute angles up to specimen.maxScatterAngle. */
export function specimenRays(config: OpticalConfig, optics: OpticsData, ill: Illumination): Ray[] {
  const z = config.specimenZ;
  const sample = illuminationSample(ill);
  const rays: Ray[] = sample.map(({ x, t }) => ({ z, x, t }));
  if (config.mode.group === 'tem') {
    const bragg = optics.specimen.braggAngle;
    for (let n = 1; n <= maxOrder(optics); n++)
      for (const sign of [1, -1]) rays.push(...sample.map(({ x, t }) => ({ z, x, t: t + sign * n * bragg })));
  } else {
    const max = optics.specimen.maxScatterAngle ?? 0;
    const steps = 8;
    for (const { x } of sample)
      for (let i = -steps; i <= steps; i++) if (i !== 0) rays.push({ z, x, t: (max * i) / steps });
  }
  return rays;
}

/** Lenses that stop rays which would otherwise land in the useful area of the target plane. */
export function blockedAfterSpecimen(config: OpticalConfig, rays: Ray[]): string[] {
  const ids = new Set<string>();
  for (const ray of rays) {
    const result = traceRay(config, ray, config.targetZ, false);
    if (result.blocked?.kind === 'clear' && Math.abs(result.end.x) <= config.targetRadius) ids.add(result.blocked.id);
  }
  return [...ids];
}

export interface Readout {
  /** Focal length per lens id (mm); null = off. */
  lenses: Record<string, number | null>;
  /** Images of the source between the source and the specimen (crossovers), top to bottom. */
  crossovers: number[];
  /** Images of the specimen below it (objective image plane, intermediate images…). */
  imagePlanes: number[];
  /** Images of the specimen's far field below it (back focal plane and its images). */
  diffractionPlanes: number[];
  /** Specimen → target-plane transfer matrix. */
  matrix: Mat;
  /** tem-image: magnification on the target plane (A; negative = inverted relative to the specimen). */
  magnification?: number;
  /** Diffraction and STEM: camera length on the target plane (B, mm). */
  cameraLength?: number;
  alpha: number;
  /** Illumination radius (TEM) or probe radius (STEM), mm. */
  beamRadius: number;
  beamCenter: number;
  relativeCurrent: number;
  /** Element ids where the beam is cut by a clear radius (F16). */
  blocked: string[];
  /** stem-scan: collection semi-angles (rad) of each detector ring at the current camera length. */
  collection?: { id: string; inner: number; outer: number }[];
}

export function readout(config: OpticalConfig, optics: OpticsData): Readout {
  const { sourceZ, specimenZ, targetZ } = config;
  const ill = illumination(config, optics);
  const matrix = transfer(config, specimenZ, targetZ);
  const imaging = config.mode.id === 'tem-image';
  const blocked = [...new Set([...ill.blocked, ...blockedAfterSpecimen(config, specimenRays(config, optics, ill))])];
  const L = matrix[1];
  return {
    lenses: Object.fromEntries(config.elements.filter((e) => e.type === 'lens').map((e) => [e.id, e.f ?? null])),
    crossovers: conjugatePlanes(config, sourceZ, specimenZ, 'image'),
    imagePlanes: conjugatePlanes(config, specimenZ, targetZ, 'image'),
    diffractionPlanes: conjugatePlanes(config, specimenZ, targetZ, 'diffraction'),
    matrix,
    ...(imaging ? { magnification: matrix[0] } : { cameraLength: L }),
    alpha: ill.alpha,
    beamRadius: ill.radius,
    beamCenter: ill.center,
    relativeCurrent: ill.current,
    blocked,
    ...(config.mode.id === 'stem-scan'
      ? { collection: optics.detectors.map((d) => ({ id: d.id, inner: d.rInner / Math.abs(L), outer: d.rOuter / Math.abs(L) })) }
      : {}),
  };
}
