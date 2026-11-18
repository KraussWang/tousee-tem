// Re-solves the computed fields of data/optics.json (objective, illumination, projector steps) and writes them back.
// Usage (in web/): npm run solve-optics
import { readFileSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { runnerImport } from 'vite';

const WEB = fileURLToPath(new URL('..', import.meta.url));
const OPTICS = fileURLToPath(new URL('../../data/optics.json', import.meta.url));
const PARTS = fileURLToPath(new URL('../../data/parts.json', import.meta.url));

const load = async (path) => (await runnerImport(fileURLToPath(new URL(path, import.meta.url)), { root: WEB, configFile: false })).module;
const { validateParts } = await load('../src/data/parts.ts');
const { validateOptics } = await load('../src/data/optics.ts');
const { solveAll } = await load('../src/core/optics/presets.ts');

const parts = validateParts(JSON.parse(readFileSync(PARTS, 'utf-8')));
const optics = validateOptics(JSON.parse(readFileSync(OPTICS, 'utf-8')), parts);
const { optics: solved, report } = solveAll(optics, parts);
validateOptics(solved, parts);

// Same layout as parts.json: anything that fits on one line stays on one line.
const inline = (v) => Array.isArray(v) ? `[${v.map(inline).join(', ')}]`
  : v && typeof v === 'object' ? `{ ${Object.entries(v).map(([k, x]) => `${JSON.stringify(k)}: ${inline(x)}`).join(', ')} }`
  : JSON.stringify(v);
const format = (v, indent = '') => {
  const one = inline(v);
  if (!v || typeof v !== 'object' || indent.length + one.length <= 150) return one;
  const inner = indent + '  ';
  const items = Array.isArray(v) ? v.map((x) => inner + format(x, inner))
    : Object.entries(v).map(([k, x]) => `${inner}${JSON.stringify(k)}: ${format(x, inner)}`);
  return Array.isArray(v) ? `[\n${items.join(',\n')}\n${indent}]` : `{\n${items.join(',\n')}\n${indent}}`;
};
writeFileSync(OPTICS, format(solved) + '\n');

for (const r of report)
  console.log(`${r.mode.padEnd(12)} 档 ${r.step}  标称 ${String(r.nominal).padStart(4)}  实得 ${r.value.toFixed(2).padStart(8)}  净孔径裕量 ${(r.margin * 100).toFixed(1)}%`);
if (report.some((r) => r.margin < 0)) {
  console.error('有档位在净孔径处挡束（裕量 < 0）');
  process.exitCode = 1;
}
