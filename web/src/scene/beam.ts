import { AdditiveBlending, BufferGeometry, DoubleSide, Group, LatheGeometry, Mesh, MeshBasicMaterial, Vector2 } from 'three';
import { type BeamPoint, explodedProfile } from '../core/beam';
import type { Part } from '../data/parts';

const SEGMENTS = 48;

/** Electron-beam envelope (F6): a lathe about the optical axis that follows the exploded column. */
export class Beam {
  readonly object = new Group();
  private readonly core: Mesh;
  private readonly ghost: Mesh;

  constructor(private readonly profile: BeamPoint[], private readonly byId: ReadonlyMap<string, Part>) {
    const material = { color: '#59d0ff', transparent: true, blending: AdditiveBlending, depthWrite: false, side: DoubleSide };
    // Bright inside the cut; a faint x-ray copy shows it through closed housings too.
    this.core = new Mesh(new BufferGeometry(), new MeshBasicMaterial({ ...material, opacity: 0.6 }));
    this.ghost = new Mesh(this.core.geometry, new MeshBasicMaterial({ ...material, opacity: 0.12, depthTest: false }));
    this.ghost.renderOrder = 10;
    this.object.add(this.core, this.ghost);
    this.object.rotation.x = Math.PI / 2; // lathe axis +Y -> world +Z
    this.object.visible = false;
  }

  update(t: number): void {
    const geometry = new LatheGeometry(explodedProfile(this.profile, this.byId, t).map((p) => new Vector2(p.r, p.z)), SEGMENTS);
    this.core.geometry.dispose();
    this.core.geometry = this.ghost.geometry = geometry;
  }
}
