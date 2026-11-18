import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { sectionContent } from '../src/core/section';
import { validateParts } from '../src/data/parts';

const raw = () => JSON.parse(readFileSync(new URL('../../data/parts.json', import.meta.url), 'utf-8'));
const data = validateParts(raw());
const part = (id: string) => data.parts.find((p) => p.id === id)!;

describe('sectionContent', () => {
  it('shows the exterior outside section mode, even for parts hidden in it', () => {
    expect(sectionContent(part('ol'), false, true)).toBe('full');
    expect(sectionContent(part('bino'), false, false)).toBe('full');
  });

  it('shows the half-section asset when one is loaded, else falls back to the exterior', () => {
    expect(sectionContent(part('ol'), true, true)).toBe('section');
    expect(sectionContent(part('gonio'), true, false)).toBe('full');
  });

  it('hides the binocular in section mode', () => {
    expect(part('bino').hideInSection).toBe(true);
    expect(sectionContent(part('bino'), true, true)).toBe('none');
  });
});

describe('validateParts section fields', () => {
  it('rejects a non-boolean hideInSection', () => {
    const bad = raw();
    bad.parts[0].hideInSection = 'yes';
    expect(() => validateParts(bad)).toThrow(/hideInSection/);
  });

  it('rejects a non-string assets.section', () => {
    const bad = raw();
    bad.parts[0].assets.section = 1;
    expect(() => validateParts(bad)).toThrow(/assets.section/);
  });
});
