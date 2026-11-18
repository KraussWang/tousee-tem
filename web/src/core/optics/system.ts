import type { ApertureId, ElementType, Mode, ModeId, OpticalElement, OpticsData } from '../../data/optics';
import { resolveZ } from '../../data/optics';
import type { PartsData } from '../../data/parts';
import { columnParts } from '../beam';

/** An element of optics.json with its global z resolved and the column part it rides with. */
export interface SystemElement extends OpticalElement { z: number; owner: string | null }

export interface OpticalSystem {
  optics: OpticsData;
  /** Sorted top to bottom (z descending). */
  elements: SystemElement[];
  byId: ReadonlyMap<string, SystemElement>;
}

export function buildSystem(optics: OpticsData, parts: PartsData): OpticalSystem {
  const column = columnParts(parts.parts);
  const ownerAt = (z: number) => column.find((p) => p.zRange![0] <= z && z < p.zRange![1])?.id
    ?? column.find((p) => p.zRange![1] === z)?.id ?? null;
  const elements = optics.elements
    .map((el) => { const z = resolveZ(el.z, parts); return { ...el, z, owner: ownerAt(z) }; })
    .sort((a, b) => b.z - a.z);
  return { optics, elements, byId: new Map(elements.map((e) => [e.id, e])) };
}

export interface OpticalState {
  mode: ModeId;
  /** Magnification / camera-length step; defaults to the mode's defaultStep. */
  step?: number;
  /** Relative excitation x per lens id or lens group (f = f₀ / x², 0 = off); default 1. */
  excitation?: Record<string, number>;
  /** Aperture steps (0 = withdrawn); default from the mode. */
  apertures?: Partial<Record<ApertureId, number>>;
  /** Objective aperture centred on the transmitted beam (default) or on the first diffracted beam. */
  olaCenter?: 'transmitted' | 'diffracted';
  /** Scan / tilt coil 1 deflection δ₁ (rad); coil 2 gets δ₂ = −δ₁ (z₁ − z_p) / (z₂ − z_p). */
  scan?: number;
}

/** An element as configured for one optical state. */
export interface ActiveElement {
  id: string;
  type: ElementType;
  z: number;
  name_zh?: string;
  /** Lens focal length (mm); null = off. */
  f?: number | null;
  /** Lenses: rays beyond this radius are stopped (beam blocked). */
  clearRadius?: number;
  /** Inserted aperture: rays with |x − center| > radius are stopped. */
  aperture?: { radius: number; center: number };
  deflection?: number;
}

export interface OpticalConfig {
  mode: Mode;
  step: number;
  apertures: Record<ApertureId, number>;
  elements: ActiveElement[];
  /** Plane the projector system images onto: the detector for stem-scan, else the screen. */
  targetZ: number;
  /** Radius of the useful area on the target plane (screen radius, or the outer detector ring). */
  targetRadius: number;
  sourceZ: number;
  specimenZ: number;
}

export function getMode(optics: OpticsData, id: ModeId): Mode {
  const mode = optics.modes.find((m) => m.id === id);
  if (!mode) throw new Error(`optics.json 中没有模式 ${id}`);
  return mode;
}

/** Preset focal length of a lens in a mode and step (null = off). */
export function presetFocal(system: OpticalSystem, mode: Mode, step: number, id: string): number | null {
  const el = system.byId.get(id)!;
  if (el.f !== undefined) return el.f;
  if (id in mode.illumination) return mode.illumination[id];
  const f = mode.steps[step].f[id];
  if (f === undefined) throw new Error(`模式 ${mode.id} 没有透镜 ${id} 的焦距`);
  return f;
}

/** Pivot of the double-deflection scan: the objective pre-field's front focal plane. */
export function scanPivotZ(system: OpticalSystem): number {
  const pre = system.byId.get('ol-pre')!;
  return pre.z + pre.f!;
}

/** Scan coil 1 deflection δ₁ that moves the probe to `offset` (mm) on the specimen: the ray through the pivot leaves the
 *  pre-field parallel at −f·δ₁. */
export function scanForOffset(system: OpticalSystem, offset: number): number {
  return -offset / system.byId.get('ol-pre')!.f!;
}

export function configure(system: OpticalSystem, state: OpticalState): OpticalConfig {
  const { optics } = system;
  const mode = getMode(optics, state.mode);
  const step = state.step ?? mode.defaultStep;
  if (!Number.isInteger(step) || step < 0 || step >= mode.steps.length) throw new Error(`模式 ${mode.id} 没有第 ${step} 档`);
  const apertures = { ...mode.apertures, ...state.apertures };
  for (const id of Object.keys(apertures) as ApertureId[]) {
    const max = mode.apertureMax?.[id] ?? 4;
    if (!Number.isInteger(apertures[id]) || apertures[id] < 0 || apertures[id] > max)
      throw new Error(`模式 ${mode.id} 下光阑 ${id} 只能取 0–${max} 档`);
  }
  const bragg = optics.specimen.braggAngle;
  const z1 = system.byId.get('scan1')!.z, z2 = system.byId.get('scan2')!.z, zp = scanPivotZ(system);
  const elements = system.elements.map((el): ActiveElement => {
    const active: ActiveElement = { id: el.id, type: el.type, z: el.z, name_zh: el.name_zh };
    if (el.type === 'lens') {
      const f0 = presetFocal(system, mode, step, el.id);
      const x = state.excitation?.[el.id] ?? (el.group ? state.excitation?.[el.group] : undefined) ?? 1;
      active.f = f0 === null || x <= 0 ? null : f0 / (x * x);
      active.clearRadius = el.clearRadius;
    } else if (el.type === 'aperture') {
      const level = apertures[el.id as ApertureId];
      if (level > 0) {
        const center = el.id === 'ola' && state.olaCenter === 'diffracted' ? system.byId.get('ol-post')!.f! * bragg : 0;
        active.aperture = { radius: optics.apertures[el.id as ApertureId].radii[level - 1], center };
      }
    } else if (el.type === 'deflector' && state.scan) {
      active.deflection = el.id === 'scan1' ? state.scan : el.id === 'scan2' ? -state.scan * (z1 - zp) / (z2 - zp) : 0;
    }
    return active;
  });
  const detector = mode.id === 'stem-scan';
  const target = system.byId.get(detector ? 'detector' : 'screen')!;
  return {
    mode, step, apertures, elements,
    targetZ: target.z,
    targetRadius: detector ? Math.max(...optics.detectors.map((d) => d.rOuter)) : target.clearRadius ?? Infinity,
    sourceZ: system.byId.get('source')!.z,
    specimenZ: system.byId.get('specimen')!.z,
  };
}
