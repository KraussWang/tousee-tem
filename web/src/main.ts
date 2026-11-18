import './ui/style.css';
import { beamProfile } from './core/beam';
import { loadParts } from './data/parts';
import { Assembly } from './scene/assembly';
import { Beam } from './scene/beam';
import { attachPicking } from './scene/picking';
import { Viewer } from './scene/viewer';
import { createInfoPanel } from './ui/infoPanel';
import { createPartList } from './ui/partList';
import { createToolbar } from './ui/toolbar';
import { createTooltip } from './ui/tooltip';

const $ = (id: string): HTMLElement => document.getElementById(id)!;
const status = $('status');

const progress = (label: string) => (done: number, total: number, failed: string[]): void => {
  status.classList.toggle('error', failed.length > 0);
  status.textContent = failed.length > 0 ? `加载失败：${failed.join('、')}（${done}/${total}）` : `${label} ${done}/${total}`;
  status.hidden = done === total && failed.length === 0;
};

async function start(): Promise<void> {
  const base = import.meta.env.BASE_URL;
  const data = await loadParts(`${base}data/parts.json`);
  const byId = new Map(data.parts.map((p) => [p.id, p]));
  const viewer = new Viewer($('viewport'));
  const assembly = new Assembly(data.parts, base);
  const beam = new Beam(beamProfile(data), byId);
  viewer.scene.add(assembly.root, beam.object);

  const showTooltip = createTooltip($('tooltip'));
  let selectedId: string | null = null;
  let sectioned = false;

  const setHover = (id: string | null): void => {
    list.setHover(id);
    viewer.setOutlined('hover', assembly.group(id === selectedId ? null : id));
    viewer.renderer.domElement.style.cursor = id ? 'pointer' : '';
  };
  const setSelected = (id: string | null): void => {
    selectedId = id;
    list.setSelected(id);
    showInfo(id ? byId.get(id)! : null);
    viewer.setOutlined('selected', assembly.group(id));
    viewer.setOutlined('hover', null);
  };
  const setExplode = (percent: number): void => {
    assembly.applyExplode(percent / 100);
    beam.update(percent / 100);
    viewer.invalidate();
  };
  // F5: half-section assets are fetched on first use; a toggle back during the fetch wins.
  const setSection = async (on: boolean): Promise<void> => {
    sectioned = on;
    toolbar.setSection(on);
    if (on) await assembly.loadSections(progress('加载半剖模型'));
    if (sectioned !== on) return;
    assembly.setSectioned(on);
    const hidden = on ? assembly.hiddenInSection : [];
    list.setUnavailable(hidden);
    if (selectedId !== null && hidden.includes(selectedId)) setSelected(null);
    setHover(null);
    viewer.invalidate();
  };
  const setBeam = (on: boolean): void => {
    beam.object.visible = on;
    toolbar.setBeam(on);
    viewer.invalidate();
  };

  const list = createPartList($('part-list'), data.parts, { onHover: setHover, onSelect: setSelected });
  const showInfo = createInfoPanel($('info-panel'), data.meta, () => setSelected(null));
  attachPicking(viewer.renderer.domElement, viewer.camera, assembly.root, {
    onHover(id, x, y) {
      setHover(id);
      showTooltip(id ? byId.get(id)! : null, x, y);
    },
    onClick: setSelected,
  });

  // Optional deep link, e.g. ?explode=60&part=ol&section=1&beam=1
  const query = new URLSearchParams(location.search);
  const percent = Math.min(100, Math.max(0, Number(query.get('explode')) || 0));
  const toolbar = createToolbar($('toolbar'), percent, {
    onExplode: setExplode,
    onResetView: () => viewer.resetView(),
    onToggleSection: () => void setSection(!sectioned),
    onToggleBeam: () => setBeam(!beam.object.visible),
  });
  window.addEventListener('keydown', (event) => {
    if ((event.key !== 'F5' && event.key !== 'F6') || event.ctrlKey || event.shiftKey || event.altKey || event.metaKey) return;
    event.preventDefault(); // F5 would reload, F6 would move focus to the address bar
    if (event.repeat) return;
    if (event.key === 'F5') void setSection(!sectioned);
    else setBeam(!beam.object.visible);
  });
  setExplode(percent);
  setSelected(byId.has(query.get('part') ?? '') ? query.get('part') : null);
  setBeam(query.get('beam') === '1');

  const exterior = assembly.load((done, total, failed) => {
    viewer.invalidate();
    progress('加载模型')(done, total, failed);
  });
  if (query.get('section') === '1') await exterior.then(() => setSection(true));
  await exterior;
}

start().catch((error: unknown) => {
  console.error(error);
  status.hidden = false;
  status.classList.add('error');
  status.textContent = error instanceof Error ? error.message : String(error);
});
