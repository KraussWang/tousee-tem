import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { explodeOffset } from '../src/core/explode';
import { validateParts, type Part } from '../src/data/parts';

const data = validateParts(JSON.parse(readFileSync(new URL('../../data/parts.json', import.meta.url), 'utf-8')));
const byId = new Map(data.parts.map((p) => [p.id, p]));
const part = (id: string): Part => byId.get(id)!;
const offset = (id: string, t: number) => explodeOffset(part(id), byId, t);
const zAt = (id: string, t: number) => part(id).zRange!.map((z) => z + offset(id, t)[2]);

describe('explodeOffset', () => {
  it('is zero for every part at 0 %', () => {
    for (const p of data.parts) expect(offset(p.id, 0)).toEqual([0, 0, 0]);
  });

  it('keeps vc and base fixed', () => {
    expect(offset('vc', 1)).toEqual([0, 0, 0]);
    expect(offset('base', 1)).toEqual([0, 0, 0]);
  });

  it('matches the PRD §7.2 column positions at 100 % with gaps >= 150', () => {
    const column = ['vc', 'pl', 'il', 'ol', 'cl', 'accel', 'gun'];
    expect(column.map((id) => zAt(id, 1))).toEqual([
      [-980, -610], [-460, -290], [-140, 120], [270, 570], [720, 1135], [1285, 1600], [1750, 2145],
    ]);
    for (let i = 1; i < column.length; i++)
      expect(zAt(column[i], 1)[0] - zAt(column[i - 1], 1)[1]).toBeGreaterThanOrEqual(150);
  });

  it('scales linearly and clamps t', () => {
    expect(offset('gun', 0.5)).toEqual([0, 0, 450]);
    expect(offset('gun', 2)).toEqual([0, 0, 900]);
    expect(offset('gun', -1)).toEqual([0, 0, 0]);
  });

  it('moves side-mounted parts with their host, then out along their own direction', () => {
    expect(offset('gonio', 1)).toEqual([350, 0, 450]);
    expect(offset('sa', 1)).toEqual([-300, 0, 300]);
    expect(offset('gonio', 0.5)).toEqual([175, 0, 225]);
  });

  it('keeps exploded side parts clear of the column segments above and below their host', () => {
    expect(zAt('gonio', 1)[1]).toBeLessThan(zAt('cl', 1)[0]);
    expect(zAt('gonio', 1)[0]).toBeGreaterThan(zAt('il', 1)[1]);
    expect(zAt('sa', 1)[1]).toBeLessThan(zAt('ol', 1)[0]);
    expect(zAt('sa', 1)[0]).toBeGreaterThan(zAt('pl', 1)[1]);
  });

  it('retracts screen and bino toward the operator without z overlap', () => {
    expect(offset('screen', 1)).toEqual([0, -450, 0]);
    expect(offset('bino', 1)).toEqual([0, -300, 0]);
    expect(offset('film', 1)).toEqual([0, -600, 0]);
  });
});
