import { type Camera, type Object3D, Raycaster, Vector2 } from 'three';

const CLICK_SLOP_PX = 5;

export interface PickingHandlers {
  onHover(partId: string | null, clientX: number, clientY: number): void;
  onClick(partId: string | null): void;
}

export function attachPicking(element: HTMLElement, camera: Camera, root: Object3D, handlers: PickingHandlers): void {
  const raycaster = new Raycaster();
  const pointer = new Vector2();
  let down: { x: number; y: number } | null = null;
  let pending: PointerEvent | null = null;

  const pick = (event: PointerEvent): string | null => {
    const rect = element.getBoundingClientRect();
    pointer.set(((event.clientX - rect.left) / rect.width) * 2 - 1, -((event.clientY - rect.top) / rect.height) * 2 + 1);
    raycaster.setFromCamera(pointer, camera);
    for (let object: Object3D | null = raycaster.intersectObject(root, true)[0]?.object ?? null; object; object = object.parent)
      if (typeof object.userData.partId === 'string') return object.userData.partId;
    return null;
  };

  element.addEventListener('pointermove', (event) => {
    if (event.pointerType !== 'mouse' || event.buttons !== 0) return handlers.onHover(null, 0, 0);
    if (!pending) requestAnimationFrame(() => {
      const latest = pending!;
      pending = null;
      handlers.onHover(pick(latest), latest.clientX, latest.clientY);
    });
    pending = event;
  });
  element.addEventListener('pointerleave', () => handlers.onHover(null, 0, 0));
  element.addEventListener('pointerdown', (event) => {
    down = event.isPrimary && event.button === 0 ? { x: event.clientX, y: event.clientY } : null;
  });
  element.addEventListener('pointerup', (event) => {
    if (down && Math.hypot(event.clientX - down.x, event.clientY - down.y) < CLICK_SLOP_PX) handlers.onClick(pick(event));
    down = null;
  });
}
