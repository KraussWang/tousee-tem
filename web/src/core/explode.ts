import type { Part, Vec3 } from '../data/parts';

/** Displacement (mm) of a part at explode fraction t in [0, 1]; side-mounted parts ride with their explodeParent. */
export function explodeOffset(part: Part, byId: ReadonlyMap<string, Part>, t: number): Vec3 {
  const k = Math.min(1, Math.max(0, t)) * part.explodeDist;
  const parent = part.explodeParent === undefined ? undefined : byId.get(part.explodeParent);
  const base: Vec3 = parent ? explodeOffset(parent, byId, t) : [0, 0, 0];
  return [base[0] + k * part.explodeDir[0], base[1] + k * part.explodeDir[1], base[2] + k * part.explodeDir[2]];
}
