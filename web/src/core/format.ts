import type { Part, PartsData, System } from '../data/parts';

export const SYSTEMS: Record<System, { zh: string; color: string }> = {
  illumination: { zh: '照明系统', color: '#f2b441' },
  specimen: { zh: '样品系统', color: '#57c27d' },
  imaging: { zh: '成像系统', color: '#5aa9f0' },
  observation: { zh: '观察记录系统', color: '#c08cf0' },
  structure: { zh: '结构', color: '#9aa3ad' },
};

export const num = (n: number): string => String(Math.round(n * 10) / 10).replace('-', '−');

export function envelope(part: Part): string {
  const d = part.dims;
  if (d.shape === 'cylinder' && d.diameter !== undefined && d.height !== undefined)
    return `Ø${num(d.diameter)} × ${num(d.height)} mm`;
  if (d.x !== undefined && d.y !== undefined && d.z !== undefined)
    return `${num(d.x)} × ${num(d.y)} × ${num(d.z)} mm`;
  return '—';
}

export function dimsRows(part: Part, meta: PartsData['meta']): [string, string][] {
  const rows: [string, string][] = [[part.dims.shape === 'cylinder' ? '包络（Ø × 高）' : '包络（X × Y × Z）', envelope(part)]];
  if (part.zRange) rows.push(['高度区间 z', `${num(part.zRange[0])} ~ ${num(part.zRange[1])} mm`]);
  rows.push(['基准点 datum', `(${part.datum.map(num).join(', ')})`]);
  const legend = meta.confidenceLegend?.[part.confidence];
  rows.push(['尺寸来源', legend ? `${part.confidence}（${legend}）` : part.confidence]);
  return rows;
}
