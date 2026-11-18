import type { PartsData } from './parts';

export type ElementType = 'source' | 'lens' | 'aperture' | 'deflector' | 'specimen' | 'detector' | 'screen';
export type ModeId = 'tem-image' | 'tem-diff' | 'stem-ronchi' | 'stem-scan';
export type ModeGroup = 'tem' | 'stem';
export type DetectorId = 'bf' | 'abf' | 'adf' | 'haadf';
export type ApertureId = 'cla' | 'ola' | 'saa';
/** A global z (mm), or a reference to a hotspot id / opticalPlanes id of parts.json. */
export type ZSpec = number | { ref: string };

export interface OpticalElement {
  id: string;
  type: ElementType;
  z: ZSpec;
  name_zh?: string;
  clearRadius?: number;
  maxExcitation?: number;
  /** Lenses sharing one excitation slider (e.g. ol). */
  group?: string;
  /** Preset focal length (mm) of a lens that is the same in every mode (the objective). */
  f?: number;
}

export interface ApertureSpec { radii: [number, number, number, number]; host: string; name_zh?: string }
export interface Detector { id: DetectorId; rInner: number; rOuter: number; name_zh: string; note?: string }
export interface Step { label: string; nominal?: number; f: Record<string, number | null> }

export interface Mode {
  id: ModeId;
  group: ModeGroup;
  name_zh: string;
  /** cl1 / cl2 / cm focal lengths (mm); null = off. */
  illumination: Record<string, number | null>;
  steps: Step[];
  defaultStep: number;
  /** 0 = withdrawn, 1–4 = aperture step. */
  apertures: Record<ApertureId, number>;
  /** Highest aperture step offered in this mode (default 4). */
  apertureMax?: Partial<Record<ApertureId, number>>;
  description?: string;
}

export type Shape =
  | { type: 'circle'; center: [number, number]; radius: number }
  | { type: 'polygon'; points: [number, number][] };

export interface SpecimenBeam { azimuth: number; order: number; intensity: number }
export interface SpecimenRegion {
  id: string;
  name_zh?: string;
  kind: 'crystal' | 'amorphous' | 'hole';
  shape: Shape;
  beams?: SpecimenBeam[];
  z?: 'light' | 'medium' | 'heavy';
  thickness?: number;
}

export interface Specimen {
  radius: number;
  braggAngle: number;
  /** Largest scattering angle (rad, from the axis) traced for STEM high-angle scattering. */
  maxScatterAngle?: number;
  regions: SpecimenRegion[];
}

export interface OpticsData {
  meta?: Record<string, unknown>;
  source: { radius: number; halfAngle: number };
  /** STEM scan half-width: largest probe offset on the specimen (mm). */
  scan: { radius: number };
  elements: OpticalElement[];
  apertures: Record<ApertureId, ApertureSpec>;
  detectors: Detector[];
  modes: Mode[];
  specimen: Specimen;
}

const ELEMENT_TYPES: ElementType[] = ['source', 'lens', 'aperture', 'deflector', 'specimen', 'detector', 'screen'];
const MODE_IDS: ModeId[] = ['tem-image', 'tem-diff', 'stem-ronchi', 'stem-scan'];
const DETECTOR_IDS: DetectorId[] = ['bf', 'abf', 'adf', 'haadf'];
const APERTURE_IDS: ApertureId[] = ['cla', 'ola', 'saa'];
const PROJECTOR_LENSES = ['il1', 'il2', 'il3', 'pl'];
const ILLUMINATION_LENSES = ['cl1', 'cl2', 'cm'];
const REGION_KINDS = ['crystal', 'amorphous', 'hole'];

const isNum = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const isFocal = (v: unknown) => v === null || (isNum(v) && v > 0);
const isStep = (v: unknown, max: number) => Number.isInteger(v) && (v as number) >= 0 && (v as number) <= max;

/** Global z (mm) of a hotspot id (part datum z + local z) or an opticalPlanes id; undefined if unknown. */
export function refZ(ref: string, parts: PartsData): number | undefined {
  for (const part of parts.parts)
    for (const spot of part.hotspots ?? [])
      if (spot.id === ref) return part.datum[2] + spot.local[2];
  return parts.opticalPlanes.find((p) => p.id === ref)?.z;
}

export function resolveZ(z: ZSpec, parts: PartsData): number {
  if (isNum(z)) return z;
  const value = refZ(z.ref, parts);
  if (value === undefined) throw new Error(`optics.json：引用 ${z.ref} 在 parts.json 中不存在`);
  return value;
}

export function validateOptics(raw: unknown, parts: PartsData): OpticsData {
  const data = raw as OpticsData;
  const fail = (msg: string): never => { throw new Error(`optics.json：${msg}`); };
  if (!data || typeof data !== 'object') fail('不是对象');
  for (const key of ['source', 'scan', 'elements', 'apertures', 'detectors', 'modes', 'specimen'] as const)
    if (data[key] === undefined) fail(`缺少 ${key}`);
  if (!isNum(data.source.radius) || !isNum(data.source.halfAngle)) fail('source 的 radius / halfAngle 必须是数字');
  if (!isNum(data.scan.radius) || data.scan.radius <= 0) fail('scan.radius 必须是正数');

  if (!Array.isArray(data.elements)) fail('elements 必须是数组');
  const elements = new Map<string, OpticalElement>();
  for (const el of data.elements) {
    const label = `元件 ${el?.id ?? '?'}`;
    if (typeof el?.id !== 'string' || !/^[a-z0-9-]+$/.test(el.id)) fail(`${label} 的 id 无效`);
    if (elements.has(el.id)) fail(`${label} id 重复`);
    if (!ELEMENT_TYPES.includes(el.type)) fail(`${label} type 无效：${el.type}`);
    if (!isNum(el.z)) {
      if (typeof el.z?.ref !== 'string') fail(`${label} 的 z 必须是数字或 { ref }`);
      if (refZ(el.z.ref, parts) === undefined) fail(`${label} 的引用 ${el.z.ref} 在 parts.json 中不存在`);
    }
    for (const key of ['clearRadius', 'maxExcitation', 'f'] as const)
      if (el[key] !== undefined && !(isNum(el[key]) && el[key]! > 0)) fail(`${label} 的 ${key} 必须是正数`);
    elements.set(el.id, el);
  }

  for (const id of APERTURE_IDS) {
    const ap = data.apertures[id];
    if (!ap) fail(`apertures 缺少 ${id}`);
    if (elements.get(id)?.type !== 'aperture') fail(`光阑 ${id} 在 elements 中没有对应的 aperture 元件`);
    if (!Array.isArray(ap.radii) || ap.radii.length !== 4 || !ap.radii.every((r) => isNum(r) && r > 0))
      fail(`光阑 ${id} 的 radii 必须是 4 个正数`);
    if (!parts.parts.some((p) => p.id === ap.host)) fail(`光阑 ${id} 的 host 不存在：${ap.host}`);
  }

  if (!Array.isArray(data.detectors)) fail('detectors 必须是数组');
  for (const d of data.detectors) {
    if (!DETECTOR_IDS.includes(d.id)) fail(`探测器 id 无效：${d.id}`);
    if (!isNum(d.rInner) || !isNum(d.rOuter) || d.rInner < 0 || d.rOuter <= d.rInner) fail(`探测器 ${d.id} 的环带半径无效`);
    if (typeof d.name_zh !== 'string') fail(`探测器 ${d.id} 缺少 name_zh`);
  }

  if (!Array.isArray(data.modes)) fail('modes 必须是数组');
  const seenModes = new Set<string>();
  for (const mode of data.modes) {
    const label = `模式 ${mode?.id ?? '?'}`;
    if (!MODE_IDS.includes(mode.id)) fail(`${label} id 无效`);
    if (seenModes.has(mode.id)) fail(`${label} 重复`);
    seenModes.add(mode.id);
    if (mode.group !== (mode.id.startsWith('stem') ? 'stem' : 'tem')) fail(`${label} 的 group 与 id 不符`);
    if (typeof mode.name_zh !== 'string') fail(`${label} 缺少 name_zh`);
    for (const lens of ILLUMINATION_LENSES)
      if (!isFocal(mode.illumination?.[lens])) fail(`${label} 的 illumination.${lens} 必须是正数或 null`);
    if (!Array.isArray(mode.steps) || mode.steps.length === 0) fail(`${label} 至少要有一档 steps`);
    for (const [i, step] of mode.steps.entries()) {
      if (typeof step.label !== 'string') fail(`${label} 第 ${i} 档缺少 label`);
      for (const lens of PROJECTOR_LENSES)
        if (!isFocal(step.f?.[lens])) fail(`${label} 第 ${i} 档的 f.${lens} 必须是正数或 null`);
    }
    if (!Number.isInteger(mode.defaultStep) || mode.defaultStep < 0 || mode.defaultStep >= mode.steps.length)
      fail(`${label} 的 defaultStep 越界`);
    for (const id of APERTURE_IDS) {
      const max = mode.apertureMax?.[id] ?? 4;
      if (!isStep(max, 4)) fail(`${label} 的 apertureMax.${id} 必须是 0–4 的整数`);
      if (!isStep(mode.apertures?.[id], 4)) fail(`${label} 的 apertures.${id} 必须是 0–4 的整数`);
      if (mode.apertures[id] > max) fail(`${label} 的默认光阑 ${id} 档位 ${mode.apertures[id]} 超过 apertureMax ${max}`);
    }
  }

  const sp = data.specimen;
  if (!isNum(sp.radius) || !isNum(sp.braggAngle) || !Array.isArray(sp.regions)) fail('specimen 需要 radius、braggAngle、regions');
  if (data.scan.radius > sp.radius) fail('scan.radius 不能超过试样半径');
  for (const region of sp.regions) {
    const label = `试样区域 ${region?.id ?? '?'}`;
    if (typeof region.id !== 'string') fail(`${label} 缺少 id`);
    if (!REGION_KINDS.includes(region.kind)) fail(`${label} 的 kind 无效`);
    if (region.shape?.type !== 'circle' && region.shape?.type !== 'polygon') fail(`${label} 的 shape 无效`);
    for (const beam of region.beams ?? [])
      if (!isNum(beam.azimuth) || !Number.isInteger(beam.order) || !isNum(beam.intensity)) fail(`${label} 的 beams 项无效`);
  }
  return data;
}

export async function loadOptics(url: string, parts: PartsData): Promise<OpticsData> {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`无法加载 ${url}（HTTP ${response.status}）`);
  return validateOptics(await response.json(), parts);
}
