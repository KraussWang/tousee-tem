import type { Part } from '../data/parts';
import { h } from './dom';

export function createTooltip(element: HTMLElement): (part: Part | null, clientX?: number, clientY?: number) => void {
  const zh = h('strong'), en = h('span');
  element.append(zh, en);
  return (part, clientX = 0, clientY = 0) => {
    element.hidden = part === null;
    if (!part) return;
    zh.textContent = part.name_zh;
    en.textContent = part.name_en;
    const x = Math.min(clientX + 14, window.innerWidth - element.offsetWidth - 8);
    const y = Math.min(clientY + 16, window.innerHeight - element.offsetHeight - 8);
    element.style.transform = `translate(${x}px, ${y}px)`;
  };
}
