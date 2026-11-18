import { readFileSync } from 'node:fs';
import { describe, expect, it } from 'vitest';
import { validateParts } from '../src/data/parts';

const raw = () => JSON.parse(readFileSync(new URL('../../data/parts.json', import.meta.url), 'utf-8'));

describe('validateParts', () => {
  it('accepts the repository parts.json with 13 L1 parts', () => {
    const data = validateParts(raw());
    expect(data.parts).toHaveLength(13);
    expect(data.parts.find((p) => p.id === 'gonio')!.explodeParent).toBe('ol');
    expect(data.parts.find((p) => p.id === 'sa')!.explodeParent).toBe('il');
  });

  it('rejects a missing required field', () => {
    const data = raw();
    delete data.parts[0].explodeDist;
    expect(() => validateParts(data)).toThrow(/gun 缺少字段 explodeDist/);
  });

  it('rejects a malformed datum', () => {
    const data = raw();
    data.parts[1].datum = [0, 0];
    expect(() => validateParts(data)).toThrow(/accel/);
  });

  it('rejects duplicate ids', () => {
    const data = raw();
    data.parts[1].id = 'gun';
    expect(() => validateParts(data)).toThrow(/重复/);
  });

  it('rejects an unknown explodeParent', () => {
    const data = raw();
    data.parts[0].explodeParent = 'nope';
    expect(() => validateParts(data)).toThrow(/explodeParent 不存在/);
  });

  it('rejects an explodeParent cycle', () => {
    const data = raw();
    data.parts.find((p: { id: string }) => p.id === 'ol').explodeParent = 'gonio';
    expect(() => validateParts(data)).toThrow(/成环/);
  });
});
