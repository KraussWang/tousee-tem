import { Group, MathUtils, type Object3D } from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { explodeOffset } from '../core/explode';
import { sectionContent } from '../core/section';
import type { Part } from '../data/parts';

type Progress = (done: number, total: number, failed: string[]) => void;

/** True when `url` serves a file (not a 404, nor a dev-server SPA fallback page). */
async function exists(url: string): Promise<boolean> {
  try {
    const response = await fetch(url, { method: 'HEAD' });
    return response.ok && !(response.headers.get('content-type') ?? '').startsWith('text/html');
  } catch {
    return false;
  }
}

export class Assembly {
  readonly root = new Group();
  /** Parts that section mode hides. */
  readonly hiddenInSection: string[];
  private readonly groups = new Map<string, Group>();
  private readonly byId: Map<string, Part>;
  private readonly loader = new GLTFLoader();
  private readonly full = new Map<string, Object3D>();
  private readonly section = new Map<string, Object3D>();
  private sectionLoad: Promise<void> | null = null;
  private sectioned = false;

  constructor(private readonly parts: Part[], private readonly baseUrl: string) {
    this.byId = new Map(parts.map((p) => [p.id, p]));
    this.hiddenInSection = parts.filter((p) => p.hideInSection).map((p) => p.id);
    for (const part of parts) {
      const group = new Group();
      group.name = part.id;
      group.userData.partId = part.id;
      group.position.fromArray(part.datum);
      // parts.json rotations are Blender XYZ Eulers (Rz·Ry·Rx), which is three.js order 'ZYX'.
      const [rx, ry, rz] = (part.rotation ?? [0, 0, 0]).map(MathUtils.degToRad);
      group.rotation.set(rx, ry, rz, 'ZYX');
      this.groups.set(part.id, group);
      this.root.add(group);
    }
  }

  group(id: string | null): Group | null {
    return id === null ? null : this.groups.get(id) ?? null;
  }

  /** Loads every part's exterior GLB in parallel; a failed part is reported and skipped. */
  load(onProgress: Progress): Promise<void> {
    return this.loadAll(this.parts, (part) => part.assets.full, this.full, onProgress);
  }

  /** Loads the half-section GLBs once (first use of section mode). Parts without one keep their exterior. */
  loadSections(onProgress: Progress): Promise<void> {
    this.sectionLoad ??= (async () => {
      const wanted = this.parts.filter((p) => p.assets.section && !p.hideInSection);
      const available = await Promise.all(wanted.map((p) => exists(this.baseUrl + p.assets.section)));
      const missing = wanted.filter((_, i) => !available[i]).map((p) => p.id);
      if (missing.length) console.info(`无半剖资产，半剖模式沿用外观：${missing.join('、')}`);
      await this.loadAll(wanted.filter((_, i) => available[i]), (part) => part.assets.section!, this.section, onProgress);
    })();
    return this.sectionLoad;
  }

  /** Swaps every part between its exterior and its section content. Content is detached rather than
   *  hidden: raycasting ignores `visible`, and OutlinePass toggles it. Part placement is untouched. */
  setSectioned(on: boolean): void {
    this.sectioned = on;
    for (const part of this.parts) this.show(part);
  }

  applyExplode(t: number): void {
    for (const part of this.parts) {
      const offset = explodeOffset(part, this.byId, t);
      this.groups.get(part.id)!.position.set(part.datum[0] + offset[0], part.datum[1] + offset[1], part.datum[2] + offset[2]);
    }
  }

  private show(part: Part): void {
    const group = this.groups.get(part.id)!;
    const kind = sectionContent(part, this.sectioned, this.section.has(part.id));
    const target = kind === 'none' ? undefined : (kind === 'section' ? this.section : this.full).get(part.id);
    for (const child of [...group.children]) if (child !== target) group.remove(child);
    if (target && target.parent !== group) group.add(target);
  }

  private loadAll(parts: Part[], url: (part: Part) => string, into: Map<string, Object3D>, onProgress: Progress): Promise<void> {
    const failed: string[] = [];
    let done = 0;
    onProgress(0, parts.length, failed);
    return Promise.all(parts.map(async (part) => {
      try {
        const gltf = await this.loader.loadAsync(this.baseUrl + url(part));
        // The GLBs are datum-local millimetres, glTF +Y up, under a 0.001 root:
        // undo the root scale and turn +Y up into +Z up.
        const adapter = new Group();
        adapter.rotation.x = Math.PI / 2;
        adapter.scale.setScalar(1000);
        adapter.add(gltf.scene);
        into.set(part.id, adapter);
        this.show(part);
      } catch (error) {
        console.error(`加载 ${url(part)} 失败`, error);
        failed.push(part.id);
      }
      onProgress(++done, parts.length, failed);
    })).then(() => undefined);
  }
}
