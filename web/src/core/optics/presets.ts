import type { ModeGroup, ModeId, OpticsData } from '../../data/optics';
import type { PartsData } from '../../data/parts';
import { illumination, specimenRays } from './readout';
import { buildSystem, configure, type OpticalConfig, type OpticalSystem, scanForOffset } from './system';
import { between, type Mat, mul, type Ray, thinLens, transfer, traceRay } from './trace';

/** Solver inputs that are not in optics.json: TEM illumination crossovers (PRD-v2 搂4.4). */
export const TARGETS = { cl1Crossover: 400, temCl2Crossover: 230 };
/** Projector-lens focal lengths the solver may use (mm). */
export const F_RANGE: [number, number] = [5, 3000];
const PROJECTOR = ['il1', 'il2', 'il3', 'pl'] as const;

export const round6 = (v: number) => Math.round(v * 1e6) / 1e6;
const lensFor = (u: number, v: number) => 1 / (1 / u + 1 / v);
const zOf = (system: OpticalSystem, id: string) => system.byId.get(id)!.z;

/** Objective split into two thin lenses at specimen 卤 h with focal length f: back focal plane on the objective
 *  aperture (h + f = z_spec 鈭?z_ola) and the specimen imaged onto the selected-area aperture. */
export function solveObjective(system: OpticalSystem): { h: number; f: number } {
  const z0 = zOf(system, 'specimen');
  const toBfp = z0 - zOf(system, 'ola'), toImage = z0 - zOf(system, 'saa');
  // g(f) = 1/f 鈭?1/h 鈭?1/(toImage 鈭?h) with h = toBfp 鈭?f: g 鈫?+鈭?at f 鈫?0 and is negative at f = toBfp / 2.
  const g = (f: number) => { const h = toBfp - f; return 1 / f - 1 / h - 1 / (toImage - h); };
  let lo = 1e-6, hi = toBfp / 2;
  for (let i = 0; i < 200; i++) { const mid = (lo + hi) / 2; if (g(mid) > 0) lo = mid; else hi = mid; }
  const f = (lo + hi) / 2;
  return { h: toBfp - f, f };
}

/** CL1 / CL2 / CM focal lengths. TEM: CL1 鈫?crossover +400, CL2 鈫?+230, CM images it onto the pre-field's front focal
 *  plane (parallel beam). STEM: CM off, CL2 crossover on the plane the pre-field images onto the specimen (probe). */
export function solveIllumination(system: OpticalSystem, group: ModeGroup): Record<'cl1' | 'cl2' | 'cm', number | null> {
  const zs = zOf(system, 'source'), z1 = zOf(system, 'cl1'), z2 = zOf(system, 'cl2'), zm = zOf(system, 'cm');
  const pre = system.byId.get('ol-pre')!, zSpec = zOf(system, 'specimen');
  const x1 = TARGETS.cl1Crossover;
  const cl1 = lensFor(zs - z1, z1 - x1);
  if (group === 'tem') {
    const x2 = TARGETS.temCl2Crossover;
    return { cl1, cl2: lensFor(x1 - z2, z2 - x2), cm: lensFor(x2 - zm, zm - (pre.z + pre.f!)) };
  }
  const v = pre.z - zSpec;
  const probeObject = pre.z + (pre.f! * v) / (v - pre.f!);
  return { cl1, cl2: lensFor(x1 - z2, z2 - probeObject), cm: null };
}

function withFocals(config: OpticalConfig, f: Record<string, number>): OpticalConfig {
  return { ...config, elements: config.elements.map((e) => (e.id in f ? { ...e, f: f[e.id] } : e)) };
}

/** Relative clearance (r 鈭?|x|) / r of each given lens over the rays that would land in the useful target area, sorted
 *  ascending; a negative first entry means some useful ray is cut. */
export function clearanceMargins(config: OpticalConfig, rays: Ray[], lenses: readonly string[] = PROJECTOR): number[] {
  const margins = new Map<string, number>();
  for (const ray of rays) {
    const result = traceRay(config, ray, config.targetZ, false);
    if (Math.abs(result.end.x) > config.targetRadius) continue;
    between(config, ray.z, config.targetZ).forEach((e, i) => {
      if (!lenses.includes(e.id) || e.clearRadius === undefined) return;
      const m = (e.clearRadius - Math.abs(result.points[i + 1].x)) / e.clearRadius;
      margins.set(e.id, Math.min(margins.get(e.id) ?? Infinity, m));
    });
  }
  return [...margins.values()].sort((a, b) => a - b);
}

/** Clearance beyond this fraction of the clear radius counts as "enough"; among such solutions the weakest lenses win. */
export const MARGIN_CAP = 0.2;

/** Lexicographic score, larger is better: [capped smallest margin, weakest projector lens' focal length]. */
type Score = [number, number];
const better = (a: Score, b: Score) => a[0] > b[0] + 1e-9 || (a[0] > b[0] - 1e-9 && a[1] > b[1] + 1e-9);
const worst = (scores: Score[]): Score => [Math.min(...scores.map((s) => s[0])), Math.min(...scores.map((s) => s[1]))];

const logspace = (a: number, b: number, n: number) =>
  Array.from({ length: n }, (_, i) => a * (b / a) ** (i / (n - 1)));

export interface ProjectionSolution { f: Record<string, number>; margin: number; value: number; score: Score }

/** Searches x 鈭?[lo, hi] on a log grid, then refines around the best point. */
function logSearch<T extends { score: Score }>(lo: number, hi: number, n: number, solve: (x: number) => T | null): T | null {
  let best = null as T | null, bestX = 0;
  const visit = (x: number) => {
    if (x < lo || x > hi) return;
    const s = solve(x);
    if (s && (!best || better(s.score, best.score))) { best = s; bestX = x; }
  };
  logspace(lo, hi, n).forEach(visit);
  for (const span of [1.15, 1.03, 1.006]) {
    if (!best) break;
    const center = bestX;
    logspace(1 / span, span, 11).forEach((g) => visit(center * g));
  }
  return best;
}

/** IL1鈥揚L focal lengths for every step of a mode. The target plane is conjugate to the specimen (tem-image, value = M)
 *  or to its far field (value = camera length L). IL1 (diffraction focus) and the image orientation are shared by all
 *  steps, so a step change only switches IL2 / IL3 / PL. Per step IL2 is searched; IL3 and PL follow in closed form
 *  from the intermediate image and the remaining magnification. */
export function solveProjection(system: OpticalSystem, modeId: ModeId, nominals: number[]): ProjectionSolution[] {
  const base = configure(system, { mode: modeId, step: 0 });
  // stem-scan: the rays of the probe at both ends of the scan must get through as well.
  const offsets = modeId === 'stem-scan' ? [0, system.optics.scan.radius, -system.optics.scan.radius] : [0];
  const rays = offsets.flatMap((offset) => {
    const c = configure(system, { mode: modeId, step: 0, scan: scanForOffset(system, offset) });
    return specimenRays(c, system.optics, illumination(c, system.optics));
  });
  const imaging = modeId === 'tem-image';
  const [z2, z3, z4] = (['il2', 'il3', 'pl'] as const).map((id) => zOf(system, id));
  const d34 = z3 - z4, v4 = z4 - base.targetZ;
  const [fMin, fMax] = F_RANGE;
  const inRange = (f: number) => f >= fMin && f <= fMax;

  const solveStep = (f1: number, sign: number, nominal: number, f2: number): ProjectionSolution | null => {
    const upper = withFocals(base, { il1: f1, il2: f2 });
    const [a, b, c, d]: Mat = mul(thinLens(f2), transfer(upper, base.specimenZ, z2));
    // Intermediate image below IL2 at distance s, with x = k路(specimen x) or k路(specimen 胃).
    const [s, k] = imaging ? [-b / d, 1 / d] : [-a / c, -1 / c];
    if (!Number.isFinite(s) || !Number.isFinite(k)) return null;
    const u3 = z2 - s - z3;
    const m34 = (sign * nominal) / k;
    const denom = v4 + m34 * u3;
    if (Math.abs(u3) < 1e-6 || Math.abs(denom) < 1e-9) return null;
    const v3 = (m34 * u3 * d34) / denom, u4 = d34 - v3;
    if (Math.abs(v3) < 1e-9 || Math.abs(u4) < 1e-9) return null;
    const f = { il1: f1, il2: f2, il3: lensFor(u3, v3), pl: lensFor(u4, v4) };
    if (!inRange(f.il3) || !inRange(f.pl)) return null;
    const config = withFocals(base, f);
    const m = transfer(config, base.specimenZ, base.targetZ);
    const [value, residual] = imaging ? [m[0], m[1]] : [m[1], m[0]];
    if (Math.abs(value - sign * nominal) > 1e-6 * nominal || Math.abs(residual) > 1e-6) return null;
    const margin = clearanceMargins(config, rays)[0] ?? Infinity;
    return { f, margin, value, score: [Math.min(margin, MARGIN_CAP), Math.min(f.il2, f.il3, f.pl)] };
  };

  let best: { steps: ProjectionSolution[]; score: Score } | null = null;
  for (const sign of [1, -1]) {
    const solution = logSearch(fMin, fMax, 32, (f1) => {
      const steps = nominals.map((n) => logSearch(fMin, fMax, 40, (f2) => solveStep(f1, sign, n, f2)));
      if (steps.some((s) => !s)) return null;
      const ok = steps as ProjectionSolution[];
      return { steps: ok, score: worst(ok.map((s) => [s.score[0], Math.min(s.score[1], f1)] as Score)) };
    });
    if (solution && (!best || better(solution.score, best.score))) best = solution;
  }
  if (!best) throw new Error(`妯″紡 ${modeId}锛氬湪 ${fMin}鈥?{fMax} mm 鍐呮壘涓嶅埌鍚勬。鍏辩敤 IL1 鐨勮В`);
  return best.steps;
}

export interface SolveReport { mode: ModeId; step: number; nominal: number; value: number; margin: number }

/** Re-derives every computed field of optics.json (objective, illumination, projector steps) from the geometry in
 *  parts.json and the nominal values of each step. Values are rounded to 6 decimals before later stages use them, so
 *  re-running on its own output reproduces it. */
export function solveAll(optics: OpticsData, parts: PartsData): { optics: OpticsData; report: SolveReport[] } {
  const out: OpticsData = structuredClone(optics);
  let system = buildSystem(out, parts);
  const { h, f } = solveObjective(system);
  const zSpec = zOf(system, 'specimen');
  for (const el of out.elements) {
    if (el.id === 'ol-pre') Object.assign(el, { z: round6(zSpec + h), f: round6(f) });
    if (el.id === 'ol-post') Object.assign(el, { z: round6(zSpec - h), f: round6(f) });
  }
  system = buildSystem(out, parts);
  for (const mode of out.modes) {
    const ill = solveIllumination(system, mode.group);
    mode.illumination = Object.fromEntries(Object.entries(ill).map(([id, v]) => [id, v === null ? null : round6(v)]));
  }
  system = buildSystem(out, parts);
  const report: SolveReport[] = [];
  for (const mode of out.modes) {
    const nominals = mode.steps.map((step, i) => {
      if (step.nominal === undefined) throw new Error(`妯″紡 ${mode.id} 绗?${i} 妗ｇ己灏?nominal`);
      return step.nominal;
    });
    solveProjection(system, mode.id, nominals).forEach((solution, i) => {
      mode.steps[i].f = Object.fromEntries(PROJECTOR.map((id) => [id, round6(solution.f[id])]));
      report.push({ mode: mode.id, step: i, nominal: nominals[i], value: solution.value, margin: solution.margin });
    });
  }
  return { optics: out, report };
}
