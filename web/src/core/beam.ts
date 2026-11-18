import type { Part, PartsData } from '../data/parts';
import { explodeOffset } from './explode';

/** A point of the beam envelope: world z (mm, assembled), radius (mm) and the column part it rides with. */
export interface BeamPoint { z: number; r: number; owner: string | null }

// Schematic envelope radii (mm); a visual style, not optics. Every optical plane is a waist or image
// except the lens principal planes; the beam converges onto the specimen, its narrowest point.
const PLANE_RADIUS: Record<string, number> = {
  source: 0.6, cl1x: 0.9, cl2x: 1.2, cm: 5, specimen: 0.4, bfp: 2, sa: 2.5, il1: 1.6, il2: 2, il3: 2.5, pl: 8, small: 18, large: 45,
};
const DEFAULT_PLANE_RADIUS = 3;
// Lens coils between two waists, where the envelope bulges (hotspot id: radius).
const LENS_RADIUS: Record<string, number> = {
  'cl.cl1': 9, 'cl.cl2': 7, 'ol.om': 6, 'il.il1': 7, 'il.il2': 6, 'il.il3': 6,
};

/** Column parts: on the axis, moving (if at all) along it, not riding on another part. */
export function columnParts(parts: Part[]): Part[] {
  return parts.filter((p) => p.zRange && p.datum[0] === 0 && p.datum[1] === 0 && !p.explodeParent
    && p.explodeDir[0] === 0 && p.explodeDir[1] === 0);
}

function ownerAt(column: Part[], z: number): string | null {
  return column.find((p) => p.zRange![0] <= z && z < p.zRange![1])?.id
    ?? column.find((p) => p.zRange![1] === z)?.id ?? null;
}

/** Envelope from the gun's source down to the large screen, sorted top to bottom. Seams between column
 *  parts get a point on each side, so an exploded column stretches the beam across the gap. */
export function beamProfile(data: PartsData): BeamPoint[] {
  const column = columnParts(data.parts);
  const keys: { z: number; r: number }[] = data.opticalPlanes.map((p) => ({ z: p.z, r: PLANE_RADIUS[p.id] ?? DEFAULT_PLANE_RADIUS }));
  for (const part of data.parts)
    for (const spot of part.hotspots ?? [])
      if (spot.id in LENS_RADIUS) keys.push({ z: part.datum[2] + spot.local[2], r: LENS_RADIUS[spot.id] });
  keys.sort((a, b) => b.z - a.z);
  const top = keys[0].z, bottom = keys[keys.length - 1].z;
  const points: BeamPoint[] = keys.map((k) => ({ ...k, owner: ownerAt(column, k.z) }));
  for (const upper of column) {
    const seam = upper.zRange![0];
    const lower = column.find((p) => p.zRange![1] === seam);
    if (!lower || seam >= top || seam <= bottom) continue;
    const i = keys.findIndex((k) => k.z < seam);
    const a = keys[i - 1], b = keys[i];
    const r = b.r + ((seam - b.z) / (a.z - b.z)) * (a.r - b.r);
    points.push({ z: seam, r, owner: upper.id }, { z: seam, r, owner: lower.id });
  }
  // Stable for equal z: the upper part's seam point stays above the lower one's.
  return points.sort((a, b) => b.z - a.z);
}

/** Profile with each point moved by its owner's explode offset at fraction t. */
export function explodedProfile(profile: BeamPoint[], byId: ReadonlyMap<string, Part>, t: number): BeamPoint[] {
  return profile.map((p) => ({ ...p, z: p.z + (p.owner ? explodeOffset(byId.get(p.owner)!, byId, t)[2] : 0) }));
}
