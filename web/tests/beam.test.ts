import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { beamProfile, columnParts, explodedProfile } from '../src/core/beam';
import { validateParts } from '../src/data/parts';

const data = validateParts(JSON.parse(readFileSync(new URL('../../data/parts.json', import.meta.url), 'utf-8')));
const byId = new Map(data.parts.map((p) => [p.id, p]));
const profile = beamProfile(data);
const radiusAt = (z: number) => profile.find((p) => p.z === z)!.r;

describe('beamProfile', () => {
  it('runs top to bottom from the gun source to the large screen through every optical plane', () => {
    const zs = profile.map((p) => p.z);
    expect(zs).toEqual([...zs].sort((a, b) => b - a));
    expect(zs[0]).toBe(1110);
    expect(zs[zs.length - 1]).toBe(-830);
    for (const plane of data.opticalPlanes) expect(zs).toContain(plane.z);
  });

  it('converges onto the specimen', () => {
    const r = radiusAt(0);
    for (const p of profile) if (p.z !== 0) expect(p.r).toBeGreaterThan(r);
  });

  it('stays inside the Ø60 bore down to the viewing chamber', () => {
    for (const p of profile) if (p.z > -610) expect(p.r).toBeLessThanOrEqual(25);
  });

  it('assigns every point to a column part and splits each seam between both neighbours', () => {
    expect(columnParts(data.parts).map((p) => p.id).sort()).toEqual(['accel', 'base', 'cl', 'gun', 'il', 'ol', 'pl', 'vc']);
    expect(profile.every((p) => p.owner !== null)).toBe(true);
    expect(profile.filter((p) => p.z === 120).map((p) => p.owner)).toEqual(['cl', 'ol']);
    expect(profile.find((p) => p.z === 0)!.owner).toBe('ol');
    expect(profile.find((p) => p.z === -830)!.owner).toBe('vc');
  });
});

describe('explodedProfile', () => {
  it('is the assembled profile at 0 %', () => {
    expect(explodedProfile(profile, byId, 0)).toEqual(profile);
  });

  it('moves each point with its part and stretches the beam across the gaps at 100 %', () => {
    const moved = explodedProfile(profile, byId, 1);
    const shift = (z: number, owner: string) => moved[profile.findIndex((p) => p.z === z && p.owner === owner)].z - z;
    expect(shift(400, 'cl')).toBe(600);
    expect(shift(0, 'ol')).toBe(450);
    expect(shift(120, 'cl') - shift(120, 'ol')).toBe(150);
    expect(shift(-830, 'vc')).toBe(0);
    const zs = moved.map((p) => p.z);
    expect(zs).toEqual([...zs].sort((a, b) => b - a));
  });
});
