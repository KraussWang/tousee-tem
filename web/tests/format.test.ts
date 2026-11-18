import { describe, expect, it } from 'vitest';
import { dimsRows, envelope, num, SYSTEMS } from '../src/core/format';
import type { Part } from '../src/data/parts';

const part = (over: Partial<Part>): Part => ({
  id: 'x', name_zh: '', name_en: '', level: 1, system: 'imaging', assets: { full: '' }, dims: {},
  datum: [0, 0, 0], explodeDir: [0, 0, 1], explodeDist: 0, description: '', source: '', confidence: 'B', ...over,
});

describe('format', () => {
  it('formats numbers with a typographic minus and one decimal at most', () => {
    expect(num(-228.17)).toBe('−228.2');
    expect(num(400)).toBe('400');
  });

  it('summarises cylinders as diameter × height even when x/y/z are also present', () => {
    expect(envelope(part({ dims: { shape: 'cylinder', diameter: 380, height: 395, x: 490, y: 490, z: 395 } }))).toBe('Ø380 × 395 mm');
  });

  it('summarises boxes as X × Y × Z', () => {
    expect(envelope(part({ dims: { shape: 'box', x: 720, y: 640, z: 370 } }))).toBe('720 × 640 × 370 mm');
  });

  it('builds the dimension rows with z range, datum and confidence legend', () => {
    const rows = dimsRows(part({ dims: { shape: 'box', x: 1, y: 2, z: 3 }, zRange: [-980, -610], datum: [0, 0, -980] }),
      { model: '', confidenceLegend: { B: '剖面图推算' } });
    expect(rows).toEqual([
      ['包络（X × Y × Z）', '1 × 2 × 3 mm'],
      ['高度区间 z', '−980 ~ −610 mm'],
      ['基准点 datum', '(0, 0, −980)'],
      ['尺寸来源', 'B（剖面图推算）'],
    ]);
  });

  it('names all five systems', () => {
    expect(Object.values(SYSTEMS).map((s) => s.zh)).toEqual(['照明系统', '样品系统', '成像系统', '观察记录系统', '结构']);
  });
});
