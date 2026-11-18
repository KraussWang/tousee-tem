import { SYSTEMS } from '../core/format';
import type { Part } from '../data/parts';
import { h } from './dom';

export interface PartList {
  setHover(id: string | null): void;
  setSelected(id: string | null): void;
  /** Greys out parts that are not shown (e.g. hidden in section mode). */
  setUnavailable(ids: readonly string[]): void;
}

export function createPartList(
  container: HTMLElement, parts: Part[],
  handlers: { onHover(id: string | null): void; onSelect(id: string): void },
): PartList {
  const items = new Map<string, HTMLButtonElement>();
  const list = h('ul');
  for (const part of parts) {
    const dot = h('span', { class: 'dot', title: SYSTEMS[part.system].zh });
    dot.style.background = SYSTEMS[part.system].color;
    const button = h('button', { type: 'button' }, dot, h('span', { class: 'zh' }, part.name_zh), h('span', { class: 'en' }, part.name_en));
    button.addEventListener('pointerenter', () => !button.disabled && handlers.onHover(part.id));
    button.addEventListener('pointerleave', () => handlers.onHover(null));
    button.addEventListener('focus', () => handlers.onHover(part.id));
    button.addEventListener('blur', () => handlers.onHover(null));
    button.addEventListener('click', () => handlers.onSelect(part.id));
    items.set(part.id, button);
    list.append(h('li', {}, button));
  }
  container.append(h('h2', {}, '部件'), list);

  const mark = (name: string) => (id: string | null) => {
    for (const [partId, button] of items) button.classList.toggle(name, partId === id);
  };
  const setUnavailable = (ids: readonly string[]) => {
    for (const [partId, button] of items) {
      button.disabled = ids.includes(partId);
      button.title = button.disabled ? '半剖模式下隐藏' : '';
    }
  };
  return { setHover: mark('hover'), setSelected: mark('selected'), setUnavailable };
}
