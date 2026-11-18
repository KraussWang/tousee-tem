# 透见 TEM

透射电子显微镜交互式三维教学模型。需求见 `PRD.md`（V1，已实现）与 `PRD-v2.md`（V2 电子光学模拟，M5 已实现，M6 起未做）；几何数据源是 `data/parts.json`，光学数据源是 `data/optics.json`。

## 目录

- `data/parts.json` — 13 个 L1 部件的 datum、旋转、爆炸参数、文案（mm，Z-up）
- `data/optics.json` — V2 光学元件（z 用 `{ref}` 引用 parts.json 的热点 / opticalPlanes）、光阑档位、探测器、4 个模式的预设、示意试样；Schema 在 `data/optics.schema.json`，运行时校验在 `web/src/data/optics.ts`。物镜 `ol-pre`/`ol-post` 的 z 与 f、各模式 `illumination` 与 `steps[].f` 是求解器输出：改了几何、`nominal`、光阑或试样后，在 `web/` 下运行 `npm run solve-optics` 重写，切勿手改（测试会断言文件与重新求解的结果一致）
- `web/src/core/optics/` — 纯函数光学核心：`system.ts`（元件序列与按状态配置）、`trace.ts`（近轴矩阵、光线追迹、共轭面）、`readout.ts`（照明相空间、M/L/α/束径/束流/挡束）、`presets.ts`（求解器）
- `models/source/<id>_full.glb` — 用于重建的 13 个原始外观网格
- `outputs/blender-assembly/assets/<id>_full.glb` — 外观资产，由 `scripts/assemble_blender.py` 生成，勿手改
- `outputs/blender-assembly/assets/<id>_section.glb` — 半剖资产（gun/accel/cl/ol/il/pl/vc 七件），由 `scripts/build_section_<id>.py`（公共逻辑在 `section_lib.py`）以 `<id>_full.glb` 为外壳生成，须在 assemble 之后运行；自检结果写 `section_<id>.json`，预览在 `previews/<id>_section_*.png`。其余部件在 parts.json 里也写了 `assets.section`，但没有文件，前端沿用外观

## Blender 命令（仓库根目录，`blender` = `C:\Program Files\Blender Foundation\Blender 5.2\blender.exe`）

- `blender -b --factory-startup --python scripts/assemble_blender.py` — 重生成 13 个外观 GLB、`.blend`、`assembly.json`
- `blender -b --factory-startup outputs/blender-assembly/TEM_assembly.blend --python scripts/verify_scene.py` — 同轴、接缝、侧口方位等校验
- `blender -b --factory-startup --python scripts/build_section_cl.py` — 聚光镜半剖：外壳沿 y=0 剖去 −Y 半侧（侧挂标准件不剖），内部件为 180° 回转体，z 取自 parts.json 热点；网格名 `cl__shell` / `cl__attachments` / `cl__housing` / `<hotspot id>`（线圈）/ `<hotspot id>__yoke|__former|__rod|__port`
- `blender -b --factory-startup --python scripts/verify_sections.py` — 整列半剖校验（换装包围盒、光轴遮挡），并渲 `previews/assembly_section_{front,iso}.png`
- `blender -b --factory-startup --python scripts/inspect_section.py [-- <id> ...]` — 外观与半剖同机位 7 视角对照图，输出到 `previews/inspect/`，用于视觉验收（`INSPECT_KINDS=section` 只渲半剖）
- 半剖侧挂件判定：`split_shell` 在 −Y 侧要求面的各顶点（向面心收 35%）也满足 `is_attachment`，以免长扇形三角面在剖后成为尖刺；面积小于 60 mm² 的碎片会被删除（按顶点坐标判连通，因为导入的网格在 UV 缝处拆了顶点）
- `web/` — three.js 前端（Vite + TypeScript，无 UI 框架）；已实现 F1–F6

## 前端命令（在 `web/` 下）

- `npm run dev` — 开发服务器；`/data/parts.json` 与 `/assets/*.glb` 由 `vite.config.ts` 的插件直接从仓库目录提供，不复制
- `npm test` — vitest（爆炸位移、parts.json / optics.json 校验、尺寸格式化、半剖内容选择、光束包络、PRD-v2 验收 1–6 与 10）
- `npm run solve-optics` — 重新求解 optics.json 的预设（用 vite `runnerImport` 加载 TS），并打印各档的净孔径裕量；裕量 < 0 时以非零码退出
- `npm run typecheck` / `npm run build` — build 会把 parts.json 与 GLB 拷入 `dist/`
- 深链：`?explode=0..100&part=<id>&section=1&beam=1`
- F5 半剖：首次开启时先发 HEAD 探测，再懒加载 section GLB；`Assembly.setSectioned` 通过摘挂 adapter 切换，不改 `visible`（Raycaster 不看 visible，OutlinePass 会改写它）
- F6 光路：`core/beam.ts` 由 opticalPlanes、透镜热点和部件接缝生成包络，各点随所属轴线部件爆炸；`scene/beam.ts` 用 LatheGeometry 渲染，不放进 `assembly.root`，因此不参与拾取
- 无头截图：`chrome --headless=new --use-angle=swiftshader --enable-unsafe-swiftshader --window-size=1600,1000 --virtual-time-budget=60000 --screenshot=<png> "http://localhost:5173/?section=1&beam=1"`

## 约定

- 世界坐标：毫米、右手系、+Z 向上、操作者在 −Y。GLB 是 datum 局部毫米、glTF Y-up、根节点 scale 0.001；加载时包一层 `rotateX(+90°)` + `scale(1000)`（`web/src/scene/assembly.ts`）。
- `parts.json` 的 `rotation` 是 Blender XYZ 欧拉角 = three.js `Euler(x, y, z, 'ZYX')`。
- 爆炸位移 = `t × explodeDist × explodeDir`，带 `explodeParent` 的部件再叠加宿主位移（`web/src/core/explode.ts`）。
- `film`、`screen` 各一个 GLB 已含两件，`secondDatum` / `smallDatum` 前端不使用。
- 新增依赖用 `npm add --save-exact`，选发布满 7 天的版本。
- 改 `parts.json` 的字段时同步 `PRD.md` 对应表格与附录 A Schema；改 `optics.json` 的字段时同步 `data/optics.schema.json`、`validateOptics` 与 `PRD-v2.md` §6.1 / 附录 A。
- `ol.scan1`、`ol.scan2`、`vc.detector` 热点只在前端生成几何，`build_section_ol.py` 的热点自检会跳过 `ol.scan*`。
- 光学约定：光线状态 (x, θ) 在 y = 0 的子午面内追迹，θ 是相对向下传播方向的斜率；STEM 只开放聚光镜光阑档 1–2（`apertureMax`），扫描半幅为 `scan.radius`；用 `scanForOffset` 把探针偏移换算成线圈偏转。
