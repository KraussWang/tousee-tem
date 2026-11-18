import {
  ACESFilmicToneMapping, Color, DirectionalLight, Euler, HalfFloatType, type Object3D, PerspectiveCamera, PMREMGenerator,
  Scene, Vector2, Vector3, WebGLRenderer, WebGLRenderTarget,
} from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { EffectComposer } from 'three/addons/postprocessing/EffectComposer.js';
import { OutlinePass } from 'three/addons/postprocessing/OutlinePass.js';
import { OutputPass } from 'three/addons/postprocessing/OutputPass.js';
import { RenderPass } from 'three/addons/postprocessing/RenderPass.js';

// World space is millimetres, right-handed, +Z up; the operator stands on the -Y side.
const HOME_POSITION = new Vector3(1000, -6000, 900);
const HOME_TARGET = new Vector3(0, 0, -330);

export class Viewer {
  readonly scene = new Scene();
  readonly camera = new PerspectiveCamera(35, 1, 10, 50000);
  readonly renderer = new WebGLRenderer({ antialias: true, powerPreference: 'high-performance' });
  readonly controls: OrbitControls;
  private readonly composer: EffectComposer;
  private readonly hoverOutline: OutlinePass;
  private readonly selectOutline: OutlinePass;
  private dirty = true;

  constructor(private readonly container: HTMLElement) {
    const { renderer, scene, camera } = this;
    renderer.toneMapping = ACESFilmicToneMapping;
    renderer.toneMappingExposure = 0.85;
    container.appendChild(renderer.domElement);

    scene.background = new Color('#2a2f3a');
    const pmrem = new PMREMGenerator(renderer);
    scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.environmentRotation = new Euler(Math.PI / 2, 0, 0);
    scene.environmentIntensity = 0.55;
    pmrem.dispose();
    const key = new DirectionalLight('#ffffff', 1.1);
    key.position.set(-2000, -3500, 4500);
    scene.add(key);

    camera.up.set(0, 0, 1);
    this.controls = new OrbitControls(camera, renderer.domElement);
    this.controls.enableDamping = true;
    this.controls.dampingFactor = 0.12;
    this.controls.minDistance = 300;
    this.controls.maxDistance = 15000;
    this.controls.maxPolarAngle = Math.PI * 0.95;
    this.controls.addEventListener('change', this.invalidate);
    this.resetView();

    this.composer = new EffectComposer(renderer, new WebGLRenderTarget(1, 1, { type: HalfFloatType, samples: 4 }));
    this.composer.addPass(new RenderPass(scene, camera));
    this.selectOutline = this.outline('#ffb347', 4);
    this.hoverOutline = this.outline('#6fd3ff', 5);
    this.composer.addPass(new OutputPass());

    new ResizeObserver(this.resize).observe(container);
    this.resize();
    renderer.setAnimationLoop(() => {
      if (this.controls.update() || this.dirty) {
        this.dirty = false;
        this.composer.render();
      }
    });
  }

  private outline(color: string, strength: number): OutlinePass {
    const pass = new OutlinePass(new Vector2(1, 1), this.scene, this.camera);
    pass.visibleEdgeColor.set(color);
    pass.hiddenEdgeColor.set(color).multiplyScalar(0.45);
    pass.edgeStrength = strength;
    pass.edgeThickness = 1.5;
    pass.enabled = false;
    this.composer.addPass(pass);
    return pass;
  }

  private resize = (): void => {
    const width = Math.max(1, this.container.clientWidth), height = Math.max(1, this.container.clientHeight);
    const ratio = Math.min(window.devicePixelRatio, 2);
    this.camera.aspect = width / height;
    this.camera.updateProjectionMatrix();
    this.renderer.setPixelRatio(ratio);
    this.renderer.setSize(width, height);
    this.composer.setPixelRatio(ratio);
    this.composer.setSize(width, height);
    this.invalidate();
  };

  invalidate = (): void => {
    this.dirty = true;
  };

  resetView(): void {
    this.camera.position.copy(HOME_POSITION);
    this.controls.target.copy(HOME_TARGET);
    this.controls.update();
    this.invalidate();
  }

  setOutlined(kind: 'hover' | 'selected', object: Object3D | null): void {
    const pass = kind === 'hover' ? this.hoverOutline : this.selectOutline;
    pass.selectedObjects = object ? [object] : [];
    pass.enabled = object !== null;
    this.invalidate();
  }
}
