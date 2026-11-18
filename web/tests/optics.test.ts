import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import type { ModeId } from '../src/data/optics';
import { validateOptics } from '../src/data/optics';
import { validateParts } from '../src/data/parts';
import { solveAll } from '../src/core/optics/presets';
import { illumination, readout } from '../src/core/optics/readout';
import { buildSystem, configure, type OpticalState, scanForOffset } from '../src/core/optics/system';
import { conjugatePlanes, transfer, traceRay } from '../src/core/optics/trace';

const read = (name: string) => JSON.parse(readFileSync(new URL(`../../data/${name}`, import.meta.url), 'utf-8'));
const parts = validateParts(read('parts.json'));
const optics = validateOptics(read('optics.json'), parts);
const system = buildSystem(optics, parts);
const cfg = (state: OpticalState) => configure(system, state);
const z = (id: string) => system.byId.get(id)!.z;
const bragg = optics.specimen.braggAngle;
const MODES: ModeId[] = ['tem-image', 'tem-diff', 'stem-ronchi', 'stem-scan'];
const stepsOf = (mode: ModeId) => optics.modes.find((m) => m.id === mode)!.steps.map((s, i) => ({ step: i, nominal: s.nominal! }));
const linspace = (a: number, b: number, n: number) => Array.from({ length: n }, (_, i) => a + ((b - a) * i) / (n - 1));
const spread = (xs: number[]) => Math.max(...xs) - Math.min(...xs);

describe('system and tracing', () => {
  it('sorts elements top to bottom and assigns column owners', () => {
    const zs = system.elements.map((e) => e.z);
    expect(zs).toEqual([...zs].sort((a, b) => b - a));
    expect(system.byId.get('cl2')!.owner).toBe('cl');
    expect(system.byId.get('scan1')!.owner).toBe('ol');
    expect(system.byId.get('il1')!.owner).toBe('il');
    expect(system.byId.get('detector')!.owner).toBe('vc');
  });

  it('matches matrix transfer and ray tracing, with unit determinant', () => {
    const c = cfg({ mode: 'tem-diff' });
    const [a, b, cc, d] = transfer(c, 0, c.targetZ);
    expect(a * d - b * cc).toBeCloseTo(1, 9);
    const end = traceRay(c, { z: 0, x: 0.1, t: 0.02 }, c.targetZ).end;
    expect(end.x).toBeCloseTo(a * 0.1 + b * 0.02, 9);
    expect(end.t).toBeCloseTo(cc * 0.1 + d * 0.02, 9);
  });

  it('applies relative excitation f = f鈧€ / x虏, x = 0 switching a lens off, groups sharing one value', () => {
    const lens = (state: OpticalState, id: string) => cfg(state).elements.find((e) => e.id === id)!.f;
    const f0 = lens({ mode: 'tem-image' }, 'cl2')!;
    expect(lens({ mode: 'tem-image', excitation: { cl2: 2 } }, 'cl2')).toBeCloseTo(f0 / 4, 9);
    expect(lens({ mode: 'tem-image', excitation: { cl2: 0 } }, 'cl2')).toBeNull();
    expect(lens({ mode: 'stem-scan' }, 'cm')).toBeNull();
    const fo = system.byId.get('ol-post')!.f!;
    for (const id of ['ol-pre', 'ol-post']) expect(lens({ mode: 'tem-image', excitation: { ol: 1.1 } }, id)).toBeCloseTo(fo / 1.21, 9);
  });

  it('stops rays at apertures (with centre offset) and at clear radii', () => {
    const bf = cfg({ mode: 'tem-image', apertures: { ola: 1 } });
    expect(traceRay(bf, { z: 0, x: 0, t: 0 }, bf.targetZ).blocked).toBeUndefined();
    expect(traceRay(bf, { z: 0, x: 0, t: bragg }, bf.targetZ).blocked).toEqual({ id: 'ola', kind: 'aperture' });
    const df = cfg({ mode: 'tem-image', apertures: { ola: 1 }, olaCenter: 'diffracted' });
    expect(traceRay(df, { z: 0, x: 0, t: 0 }, df.targetZ).blocked?.id).toBe('ola');
    expect(traceRay(df, { z: 0, x: 0, t: bragg }, df.targetZ).blocked).toBeUndefined();
    const result = traceRay(bf, { z: -250, x: 11, t: 0 }, bf.targetZ);
    expect(result.blocked).toEqual({ id: 'il1', kind: 'clear' });
    expect(result.points.at(-1)!.z).toBe(z('il1'));
    expect(traceRay(bf, { z: -250, x: 11, t: 0 }, bf.targetZ, false).end.z).toBe(bf.targetZ);
  });

  it('rejects condenser aperture steps 3鈥? in STEM', () => {
    expect(() => cfg({ mode: 'stem-scan', apertures: { cla: 3 } })).toThrow(/0鈥?/);
    expect(() => cfg({ mode: 'tem-image', apertures: { cla: 4 } })).not.toThrow();
  });

  it('finds the TEM illumination crossovers +400, +230 and the pre-field front focal plane +20', () => {
    const r = readout(cfg({ mode: 'tem-image' }), optics);
    for (const target of [400, 230, 20]) expect(Math.min(...r.crossovers.map((c) => Math.abs(c - target)))).toBeLessThan(0.01);
  });

  it('reports the STEM detector collection angles at the current camera length', () => {
    const r = readout(cfg({ mode: 'stem-scan' }), optics);
    const haadf = r.collection!.find((c) => c.id === 'haadf')!;
    expect(haadf.outer).toBeCloseTo(40 / Math.abs(r.cameraLength!), 9);
  });
});

describe('presets', () => {
  it('are reproduced exactly by the solver (optics.json is generated, not hand-edited)', () => {
    const { optics: solved, report } = solveAll(optics, parts);
    expect(solved).toEqual(optics);
    for (const r of report) expect(Math.abs(Math.abs(r.value) - r.nominal) / r.nominal).toBeLessThan(1e-3);
  }, 60_000);

  // Acceptance 1
  it.each(stepsOf('tem-image'))('tem-image step $step: one specimen point, all directions 鈫?one screen point; M matches', ({ step, nominal }) => {
    const c = cfg({ mode: 'tem-image', step });
    const ill = illumination(c, optics);
    const r = readout(c, optics);
    const tMax = ill.alpha + 2 * bragg;
    for (const x of [-ill.radius, 0, ill.radius]) {
      const hits = linspace(-tMax, tMax, 9).map((t) => traceRay(c, { z: 0, x, t }, c.targetZ));
      for (const h of hits) expect(h.blocked).toBeUndefined();
      expect(spread(hits.map((h) => h.end.x))).toBeLessThanOrEqual(0.5);
    }
    const traced = (traceRay(c, { z: 0, x: 0.1, t: 0 }, c.targetZ).end.x - traceRay(c, { z: 0, x: 0, t: 0 }, c.targetZ).end.x) / 0.1;
    expect(r.magnification!).toBeCloseTo(traced, 6);
    expect(Math.abs(r.imagePlanes.at(-1)! - c.targetZ)).toBeLessThanOrEqual(0.5);
    expect(Math.abs(Math.abs(r.magnification!) - nominal) / nominal).toBeLessThan(0.01);
  });

  // Acceptance 2
  it.each(stepsOf('tem-diff'))('tem-diff step $step: one direction, all specimen points 鈫?one spot; R = L路胃_B', ({ step, nominal }) => {
    const c = cfg({ mode: 'tem-diff', step });
    const ill = illumination(c, optics);
    const r = readout(c, optics);
    for (const t of [-2 * bragg, -bragg, 0, bragg, 2 * bragg]) {
      const hits = linspace(-ill.radius, ill.radius, 7).map((x) => traceRay(c, { z: 0, x, t }, c.targetZ));
      for (const h of hits) expect(h.blocked).toBeUndefined();
      expect(spread(hits.map((h) => h.end.x))).toBeLessThanOrEqual(0.5);
    }
    const R = Math.abs(traceRay(c, { z: 0, x: 0, t: bragg }, c.targetZ).end.x - traceRay(c, { z: 0, x: 0, t: 0 }, c.targetZ).end.x);
    const L = Math.abs(r.cameraLength!);
    expect(Math.abs(R - L * bragg) / (L * bragg)).toBeLessThanOrEqual(0.02);
    expect(Math.abs(L - nominal) / nominal).toBeLessThan(0.01);
    expect(Math.abs(r.diffractionPlanes.at(-1)! - c.targetZ)).toBeLessThanOrEqual(0.5);
  });

  // Acceptance 3
  it('TEM illumination is parallel (伪 鈮?5 mrad); the STEM probe radius is 鈮?0.001 mm', () => {
    for (const mode of ['tem-image', 'tem-diff'] as const) {
      const r = readout(cfg({ mode }), optics);
      expect(r.alpha).toBeLessThanOrEqual(0.005);
      expect(r.beamRadius).toBeGreaterThan(0.2);
    }
    for (const mode of ['stem-ronchi', 'stem-scan'] as const) {
      const r = readout(cfg({ mode }), optics);
      expect(r.beamRadius).toBeLessThanOrEqual(0.001);
      expect(r.alpha).toBeGreaterThan(0.05);
    }
  });

  // Acceptance 4
  it.each(stepsOf('stem-scan'))('stem-scan step $step: the probe stays parallel and the pattern stays put while scanning', ({ step }) => {
    const centers: number[] = [];
    for (const offset of linspace(-optics.scan.radius, optics.scan.radius, 9)) {
      const c = cfg({ mode: 'stem-scan', step, scan: scanForOffset(system, offset) });
      const chief = traceRay(c, { z: c.sourceZ, x: 0, t: 0 }, 0);
      expect(chief.blocked).toBeUndefined();
      expect(Math.abs(chief.end.t)).toBeLessThanOrEqual(0.001);
      expect(chief.end.x).toBeCloseTo(offset, 9);
      const r = readout(c, optics);
      expect(r.beamCenter).toBeCloseTo(chief.end.x, 9);
      expect(r.blocked).toEqual([]);
      const toDetector = traceRay(c, chief.end, c.targetZ);
      expect(toDetector.blocked).toBeUndefined();
      centers.push(toDetector.end.x);
    }
    expect(spread(centers)).toBeLessThanOrEqual(0.5);
  });

  // Acceptance 5
  it.each(MODES.flatMap((mode) => stepsOf(mode).map(({ step }) => ({ mode, step }))))(
    '$mode step $step: nothing is cut by a clear radius under the default apertures', ({ mode, step }) => {
      expect(readout(cfg({ mode, step }), optics).blocked).toEqual([]);
    });

  it('puts the objective back focal plane on the objective aperture and the image on the selected-area aperture', () => {
    for (const mode of MODES) {
      const c = cfg({ mode });
      expect(Math.abs(conjugatePlanes(c, 0, c.targetZ, 'diffraction')[0] - z('ola'))).toBeLessThanOrEqual(0.1);
      expect(Math.abs(conjugatePlanes(c, 0, c.targetZ, 'image')[0] - z('saa'))).toBeLessThanOrEqual(0.1);
    }
    const pre = system.byId.get('ol-pre')!, post = system.byId.get('ol-post')!;
    expect(pre.z).toBeGreaterThan(0);
    expect(pre.z).toBeLessThan(15);
    expect(pre.z).toBeCloseTo(-post.z, 9);
  });

  // Acceptance 6
  it('a larger condenser aperture gives a larger TEM illumination radius and a larger STEM 伪', () => {
    const temRadius = [1, 2, 3, 4].map((cla) => readout(cfg({ mode: 'tem-image', apertures: { cla } }), optics).beamRadius);
    const stemAlpha = [1, 2].map((cla) => readout(cfg({ mode: 'stem-scan', apertures: { cla } }), optics).alpha);
    const current = [1, 2, 3, 4].map((cla) => readout(cfg({ mode: 'tem-image', apertures: { cla } }), optics).relativeCurrent);
    for (const series of [temRadius, stemAlpha, current])
      for (let i = 1; i < series.length; i++) expect(series[i]).toBeGreaterThan(series[i - 1]);
  });
});
