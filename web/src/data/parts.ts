export type Vec3 = [number, number, number];
export type System = 'illumination' | 'specimen' | 'imaging' | 'observation' | 'structure';

export interface Hotspot {
  id: string;
  name_zh: string;
  name_en?: string;
  local: Vec3;
  note: string;
}

export interface Dims {
  shape?: 'cylinder' | 'box';
  diameter?: number;
  height?: number;
  x?: number;
  y?: number;
  z?: number;
}

export interface Part {
  id: string;
  name_zh: string;
  name_en: string;
  level: 1;
  system: System;
  assets: { full: string; section?: string };
  dims: Dims;
  datum: Vec3;
  zRange?: [number, number];
  rotation?: Vec3;
  explodeDir: Vec3;
  explodeDist: number;
  explodeParent?: string;
  /** Hidden in section mode (F5), e.g. the binocular that would block the view into the cut. */
  hideInSection?: boolean;
  hotspots?: Hotspot[];
  description: string;
  source: string;
  confidence: 'A' | 'B' | 'C';
}

export interface PartsData {
  meta: { model: string; confidenceLegend?: Record<string, string>; [key: string]: unknown };
  parts: Part[];
  opticalPlanes: { id: string; name_zh: string; z: number; note?: string }[];
}

const REQUIRED = ['id', 'name_zh', 'name_en', 'level', 'system', 'dims', 'datum', 'explodeDir', 'explodeDist', 'description', 'source', 'confidence'] as const;
const SYSTEMS: System[] = ['illumination', 'specimen', 'imaging', 'observation', 'structure'];

const isVec3 = (v: unknown): v is Vec3 =>
  Array.isArray(v) && v.length === 3 && v.every((n) => typeof n === 'number' && Number.isFinite(n));

export function validateParts(raw: unknown): PartsData {
  const data = raw as PartsData;
  if (!data || typeof data !== 'object' || !data.meta || !Array.isArray(data.parts))
    throw new Error('parts.json：缺少 meta 或 parts');
  const byId = new Map<string, Part>();
  for (const part of data.parts) {
    const label = `parts.json：部件 ${part?.id ?? '?'}`;
    for (const key of REQUIRED) if (part?.[key] === undefined) throw new Error(`${label} 缺少字段 ${key}`);
    if (byId.has(part.id)) throw new Error(`${label} id 重复`);
    if (!SYSTEMS.includes(part.system)) throw new Error(`${label} system 无效：${part.system}`);
    if (!isVec3(part.datum) || !isVec3(part.explodeDir) || (part.rotation !== undefined && !isVec3(part.rotation)))
      throw new Error(`${label} 的 datum / explodeDir / rotation 必须是 3 个数`);
    if (typeof part.explodeDist !== 'number') throw new Error(`${label} explodeDist 必须是数字`);
    if (typeof part.assets?.full !== 'string') throw new Error(`${label} 缺少 assets.full`);
    if (part.assets.section !== undefined && typeof part.assets.section !== 'string') throw new Error(`${label} assets.section 必须是字符串`);
    if (part.hideInSection !== undefined && typeof part.hideInSection !== 'boolean') throw new Error(`${label} hideInSection 必须是布尔值`);
    byId.set(part.id, part);
  }
  for (const part of data.parts) {
    const seen = new Set([part.id]);
    for (let parent = part.explodeParent; parent !== undefined; parent = byId.get(parent)!.explodeParent) {
      if (!byId.has(parent)) throw new Error(`parts.json：部件 ${part.id} 的 explodeParent 不存在：${parent}`);
      if (seen.has(parent)) throw new Error(`parts.json：部件 ${part.id} 的 explodeParent 成环`);
      seen.add(parent);
    }
  }
  return data;
}

export async function loadParts(url: string): Promise<PartsData> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`无法加载 ${url}（HTTP ${response.status}）`);
  return validateParts(await response.json());
}
