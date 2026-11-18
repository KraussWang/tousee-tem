import { copyFileSync, createReadStream, existsSync, mkdirSync, readdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { defineConfig, type Plugin } from 'vite';

const REPO = fileURLToPath(new URL('..', import.meta.url));
const DATA_FILES = ['parts.json', 'optics.json'];
const GLB_DIR = resolve(REPO, 'outputs/blender-assembly/assets');

function repoFile(url: string): string | null {
  const path = decodeURIComponent(url.split('?')[0]);
  const data = /^\/data\/([\w.-]+\.json)$/.exec(path);
  if (data && DATA_FILES.includes(data[1])) return resolve(REPO, 'data', data[1]);
  const glb = /^\/assets\/([\w.-]+\.glb)$/.exec(path);
  return glb ? join(GLB_DIR, glb[1]) : null;
}

function repoAssets(): Plugin {
  let outDir = '';
  let isBuild = false;
  return {
    name: 'tem-repo-assets',
    configResolved(config) {
      outDir = resolve(config.root, config.build.outDir);
      isBuild = config.command === 'build';
    },
    configureServer(server) {
      server.middlewares.use((req, res, next) => {
        const file = repoFile(req.url ?? '');
        if (!file) return next();
        if (!existsSync(file)) {
          // A missing GLB (e.g. a part without a section asset) is a 404, not the SPA fallback page.
          res.statusCode = 404;
          return res.end();
        }
        res.setHeader('Content-Type', file.endsWith('.json') ? 'application/json; charset=utf-8' : 'model/gltf-binary');
        res.setHeader('Cache-Control', 'no-cache');
        createReadStream(file).pipe(res);
      });
    },
    closeBundle() {
      if (!isBuild) return;
      mkdirSync(join(outDir, 'data'), { recursive: true });
      mkdirSync(join(outDir, 'assets'), { recursive: true });
      for (const name of DATA_FILES) copyFileSync(resolve(REPO, 'data', name), join(outDir, 'data', name));
      for (const name of readdirSync(GLB_DIR).filter((n) => n.endsWith('.glb')))
        copyFileSync(join(GLB_DIR, name), join(outDir, 'assets', name));
    },
  };
}

export default defineConfig({
  base: './',
  plugins: [repoAssets()],
  build: { assetsDir: 'static', chunkSizeWarningLimit: 1200 },
});
