import { h } from './dom';

export interface Toolbar {
  setSection(on: boolean): void;
  setBeam(on: boolean): void;
}

export function createToolbar(
  container: HTMLElement, initialPercent: number,
  handlers: { onExplode(percent: number): void; onResetView(): void; onToggleSection(): void; onToggleBeam(): void },
): Toolbar {
  const slider = h('input', { type: 'range', min: '0', max: '100', step: '1', value: String(initialPercent), id: 'explode', 'aria-label': '爆炸程度' });
  const readout = h('output', { for: 'explode' }, `${initialPercent}%`);
  slider.addEventListener('input', () => {
    readout.textContent = `${slider.value}%`;
    handlers.onExplode(Number(slider.value));
  });
  const toggle = (label: string, key: string, onClick: () => void) => {
    const button = h('button', { type: 'button', class: 'toggle', 'aria-pressed': 'false', 'aria-keyshortcuts': key, title: `快捷键 ${key}` }, `${label} (${key})`);
    button.addEventListener('click', onClick);
    return button;
  };
  const section = toggle('半剖', 'F5', handlers.onToggleSection);
  const beam = toggle('光路', 'F6', handlers.onToggleBeam);
  const reset = h('button', { type: 'button' }, '复位视角');
  reset.addEventListener('click', handlers.onResetView);
  container.append(h('label', { for: 'explode' }, '装配'), slider, h('span', {}, '爆炸'), readout, section, beam, reset);
  const press = (button: HTMLButtonElement) => (on: boolean) => button.setAttribute('aria-pressed', String(on));
  return { setSection: press(section), setBeam: press(beam) };
}
