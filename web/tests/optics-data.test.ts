import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { refZ, validateOptics } from '../src/data/optics';
import { validateParts } from '../src/data/parts';

const read = (name: string) => JSON.parse(readFileSync(new URL(`../../data/${name}`, import.meta.url), 'utf-8'));
const parts = validateParts(read('parts.json'));
const raw = () => read('optics.json');

describe('validateOptics (acceptance 10)', () => {
  it('accepts the repository optics.json and resolves every ref in parts.json', () => {
    const data = validateOptics(raw(), parts);
    expect(data.modes.map((m) => m.id)).toEqual(['tem-image', 'tem-diff', 'stem-ronchi', 'stem-scan']);
    for (const el of data.elements)
      if (typeof el.z === 'object') expect(refZ(el.z.ref, parts), el.z.ref).toBeTypeOf('number');
    for (const mode of data.modes) expect(mode.steps.length).toBeGreaterThanOrEqual(3);
  });

  it('resolves the V2 hotspots to the PRD heights', () => {
    expect(refZ('ol.scan1', parts)).toBe(90);
    expect(refZ('ol.scan2', parts)).toBe(55);
    expect(refZ('vc.detector', parts)).toBe(-700);
    expect(refZ('sa', parts)).toBe(-228.17);
    expect(refZ('nope', parts)).toBeUndefined();
  });

  it('limits STEM to condenser aperture steps 1–2', () => {
    const data = validateOptics(raw(), parts);
    for (const mode of data.modes) expect(mode.apertureMax?.cla ?? 4).toBe(mode.group === 'stem' ? 2 : 4);
  });

  const reject = (mutate: (data: any) => void, message: RegExp) => {
    const data = raw();
    mutate(data);
    expect(() => validateOptics(data, parts)).toThrow(message);
  };

  it('rejects an unresolvable ref', () => reject((d) => { d.elements[1].z = { ref: 'cl.nope' }; }, /cl\.nope/));
  it('rejects a duplicate element id', () => reject((d) => { d.elements[2].id = 'cl1'; }, /重复/));
  it('rejects an unknown element type', () => reject((d) => { d.elements[1].type = 'mirror'; }, /type 无效/));
  it('rejects aperture radii that are not 4 numbers', () => reject((d) => { d.apertures.cla.radii = [1, 2, 3]; }, /radii/));
  it('rejects an unknown aperture host', () => reject((d) => { d.apertures.saa.host = 'nope'; }, /host 不存在/));
  it('rejects a default aperture step above apertureMax', () => reject((d) => { d.modes[2].apertures.cla = 3; }, /超过 apertureMax/));
  it('rejects a step without a projector focal length', () => reject((d) => { delete d.modes[0].steps[0].f.pl; }, /f\.pl/));
  it('rejects an out-of-range defaultStep', () => reject((d) => { d.modes[1].defaultStep = 9; }, /defaultStep/));
  it('rejects a bad detector ring', () => reject((d) => { d.detectors[0].rOuter = -1; }, /环带/));
  it('rejects a scan wider than the specimen', () => reject((d) => { d.scan.radius = 0.5; }, /scan\.radius/));
  it('rejects an unknown region kind', () => reject((d) => { d.specimen.regions[0].kind = 'liquid'; }, /kind/));
});
