# 透见 TEM · 交互式三维透射电子显微镜

从镜柱顶部的电子枪到下方的荧光屏，在浏览器中沿光路探索 13 个部件。拖动滑块可以拆开镜柱，切换半剖可以看到透镜线圈、极靴和光阑。点击模型或左侧部件名称，可查看工作原理、子部件与尺寸。

## 下载项目

模型文件通过 Git LFS 分发。安装 Git 和 Git LFS 后执行以下命令。已有克隆可在仓库中运行 `git lfs pull` 下载模型。

```sh
git lfs install
git clone https://github.com/KraussWang/tousee-tem.git
cd tousee-tem
git lfs pull
```

## 运行网页

使用 Node.js 24 和 npm，在仓库根目录运行以下命令。

```sh
cd web
npm ci
npm run dev
```

打开终端显示的本地地址。左键拖动旋转，滚轮缩放，右键拖动平移。工具栏或快捷键 **F5** 切换半剖，**F6** 切换电子束光路。可在地址后加上 `?explode=40&part=ol&section=1&beam=1`，直接打开带光路的物镜半剖视图。

在 `web/` 中运行 `npm test` 验证结构数据、装配和光学计算，运行 `npm run typecheck` 检查类型。用 `npm run build` 生成含运行数据和模型的静态站点，再用 `npm run preview` 预览。

## 从源模型重建

网页直接使用仓库内的 13 个外观和 7 个半剖 GLB。重新建模时，Blender 从 `models/source/` 读取源网格，从 `data/` 读取部件基准、接口与热点坐标。以下 PowerShell 命令从仓库根目录运行，要求 Blender 5.2 的 `blender` 命令在 PATH 中。

```powershell
blender -b --factory-startup --python-exit-code 1 --python scripts/assemble_blender.py
if ($LASTEXITCODE) { throw '外观组装失败' }
blender -b --factory-startup outputs/blender-assembly/TEM_assembly.blend --python-exit-code 1 --python scripts/verify_scene.py
if ($LASTEXITCODE) { throw '场景校验失败' }
blender -b --factory-startup --python-exit-code 1 --python scripts/verify_assembly.py
if ($LASTEXITCODE) { throw '外观文件校验失败' }
foreach ($id in 'gun','accel','cl','ol','il','pl','vc') {
    blender -b --factory-startup --python-exit-code 1 --python "scripts/build_section_${id}.py"
    if ($LASTEXITCODE) { throw "半剖生成失败 $id" }
}
blender -b --factory-startup --python-exit-code 1 --python scripts/verify_sections.py
```

重建结果位于 `outputs/blender-assembly/`。其中 `assets/` 存放网页模型，`previews/` 存放渲染图。组装与半剖校验同时输出 JSON 报告。

## 教学模型的范围

尺寸数据标明了手册取值、剖面图推算和估计值。镜柱下部按观察位置重新分配了高度。试样杆和选区光阑杆的工作孔以光路示意表示，当前外观网格在光轴附近未形成贯通孔。

网页提供结构交互和光束包络显示。近轴追迹、共轭面计算及四种光学模式的预设求解位于 `web/src/core/optics/`。变更光学几何、标称焦距、光阑或试样后，在 `web/` 运行 `npm run solve-optics` 重新求解预设。结构和光学设计分别见 [结构说明](PRD.md) 与 [电子光学说明](PRD-v2.md)。
