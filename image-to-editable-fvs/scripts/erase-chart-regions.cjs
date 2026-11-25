'use strict';
/**
 * 从原生版 FVS 提取图表坐标，在参考图上擦除这些区域，生成"擦除底图"。
 * node erase-chart-regions.cjs <参考图> <原生版FVS> <输出擦除底图> [画布宽 画布高]
 * 依赖：项目 packages/engine/fvs.cjs + jszip + sharp（用 FVS_ENGINE 指定引擎路径）。
 */
const fs = require('node:fs/promises');
const path = require('node:path');
const { createRequire } = require('node:module');
const ENGINE = process.env.FVS_ENGINE || path.resolve('packages/engine/fvs.cjs');
const projectRequire = createRequire(ENGINE);
const JSZip = projectRequire('jszip');
const sharp = projectRequire('sharp');

const [, , refImg, nativeFvs, outImg, coordsJson, cwArg, chArg] = process.argv;
if (!refImg || !nativeFvs || !outImg) {
  console.error('用法: node erase-chart-regions.cjs <参考图> <原生版FVS> <输出擦除底图> [坐标表.json] [画布宽 画布高]');
  process.exit(1);
}
const fvs = projectRequire(ENGINE);

(async () => {
  const zin = await JSZip.loadAsync(await fs.readFile(nativeFvs));
  const raw = await zin.files['editor.tpl'].async('string');
  const root = fvs.readXML(raw);
  const store = JSON.parse(root.Duchamp.DuchampTemplateAttr._attributes.store);
  const canvasW = Number(cwArg) || store.width || 1920;
  const canvasH = Number(chArg) || store.height || 1080;
  const charts = store.stories[0].widgets.filter((w) => /^d-chart/.test(w.type));
  if (!charts.length) throw new Error('原生版 FVS 里没有 d-chart 组件');

  const { data, info } = await sharp(refImg).raw().toBuffer({ resolveWithObject: true });
  const rw = info.width, rh = info.height, ch = info.channels;
  const sx = rw / canvasW, sy = rh / canvasH;
  const median = (arr) => { const v = arr.slice().sort((a, b) => a - b); return v[Math.floor(v.length / 2)] || 6; };

  // 若提供坐标表(原图像素坐标)，用它；否则退回从 FVS 图表坐标换算
  const coords = coordsJson ? JSON.parse(await fs.readFile(coordsJson, 'utf8')) : null;
  const overlays = [];
  const items = coords
    ? coords.charts
    : charts.map((c) => ({ x: c.states.matrix[4] * sx, y: c.states.matrix[5] * sy, w: c.states.width * sx, h: c.states.height * sy }));
  for (const it of items) {
    const x1 = Math.max(0, Math.floor(it.x) - 2), y1 = Math.max(0, Math.floor(it.y) - 2);
    const x2 = Math.min(rw, Math.ceil(it.x + it.w) + 2), y2 = Math.min(rh, Math.ceil(it.y + it.h) + 2);
    const px = [];
    for (const ry of [Math.max(0, y1 - 5), Math.min(rh - 1, y2 + 4)]) {
      for (let xx = x1; xx < x2; xx++) {
        const i = (ry * rw + xx) * ch;
        px.push([data[i], data[i + 1], data[i + 2]]);
      }
    }
    const fill = [0, 1, 2].map((k) => median(px.map((p) => p[k])));
    overlays.push(`<rect x="${x1}" y="${y1}" width="${x2 - x1}" height="${y2 - y1}" fill="rgb(${fill.join(',')})"/>`);
  }

  const svg = `<svg width="${rw}" height="${rh}">${overlays.join('')}</svg>`;
  await sharp(refImg).composite([{ input: Buffer.from(svg), top: 0, left: 0 }]).png().toFile(outImg);
  console.log(`擦除底图: ${outImg} (${rw}x${rh}, 擦除 ${items.length} 个图表区)`);
})().catch((e) => { console.error('FAIL', e.message); process.exit(1); });
