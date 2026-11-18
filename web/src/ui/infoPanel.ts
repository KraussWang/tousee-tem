import { dimsRows, SYSTEMS } from '../core/format';
import type { Part, PartsData } from '../data/parts';
import { h } from './dom';

export function createInfoPanel(container: HTMLElement, meta: PartsData['meta'], onClose: () => void): (part: Part | null) => void {
  return (part) => {
    container.classList.toggle('empty', part === null);
    if (!part) {
      container.replaceChildren(
        h('h2', {}, meta.model),
        h('p', { class: 'hint' }, '点击模型或左侧列表中的部件查看说明。'),
        h('p', { class: 'hint' }, '左键拖动旋转 · 滚轮缩放 · 右键拖动平移；触屏：单指旋转、双指缩放/平移。'),
      );
      return;
    }
    const system = SYSTEMS[part.system];
    const badge = h('span', { class: 'badge' }, system.zh);
    badge.style.borderColor = badge.style.color = system.color;
    const close = h('button', { type: 'button', class: 'close', 'aria-label': '关闭' }, '×');
    close.addEventListener('click', onClose);
    const hotspots = part.hotspots ?? [];
    container.replaceChildren(
      close,
      h('h2', {}, part.name_zh),
      h('p', { class: 'en' }, part.name_en),
      h('p', {}, h('span', { class: 'label' }, '所属系统'), badge),
      h('h3', {}, '功能说明'),
      h('p', { class: 'description' }, part.description),
      h('h3', {}, `子部件（L2）· ${hotspots.length}`),
      hotspots.length === 0
        ? h('p', { class: 'hint' }, '无')
        : h('ul', { class: 'hotspots' }, ...hotspots.map((spot) => h('li', {},
            h('span', { class: 'zh' }, spot.name_zh),
            spot.name_en ? h('span', { class: 'en' }, spot.name_en) : null,
            spot.note ? h('span', { class: 'note' }, spot.note) : null))),
      h('h3', {}, '尺寸摘要'),
      h('dl', {}, ...dimsRows(part, meta).flatMap(([label, value]) => [h('dt', {}, label), h('dd', {}, value)])),
    );
    container.scrollTop = 0;
  };
}
