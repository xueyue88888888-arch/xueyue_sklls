'use strict';
/**
 * 合并：擦除图表区的原图做底 + 原生图表叠加（数据可改）。
 * node merge-editable-fvs.cjs <擦除底图png> <原生版FVS> <输出FVS路径> [画布宽 画布高]
 * 关键：用 fvs.readXML/writeXML 精确改 editor.tpl，绝不手工 replace HTML 实体
 *       （手工 replace 会导致 &amp;amp; 双重转义、帆软打不开）。
 */
const fs = require('node:fs/promises');
const path = require('node:path');
const { randomUUID } = require('node:crypto');
const { createRequire } = require('node:module');
const ENGINE = process.env.FVS_ENGINE || path.resolve('packages/engine/fvs.cjs');
const projectRequire = createRequire(ENGINE);
const JSZip = projectRequire('jszip');

const [, , erasedPng, nativeFvs, outFvs, coordsJson, cwArg, chArg] = process.argv;
if (!erasedPng || !nativeFvs || !outFvs) {
  console.error('用法: node merge-editable-fvs.cjs <擦除底图png> <原生版FVS> <输出FVS路径> [坐标表.json] [画布宽 画布高]');
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

  const bases = await fvs.loadBases();
  const erasedBuf = await fs.readFile(erasedPng);
  const assetName = randomUUID() + '.png';
  const baseWidget = fvs.imageWidget(bases, '底图 · 原图擦除图表区',
    { x: 0, y: 0, w: canvasW, h: canvasH }, assetName);

  // 关键：图表原本挂在 d-group 下(parent 指向 group id)。合并时删掉了 group，
  // 若不清空 parent，图表成孤儿、帆软不渲染。清空后图表挂根，坐标用 matrix(画布绝对坐标)。
  for (const c of charts) { c.parent = ''; c.children = []; }

  // 若提供坐标表，把每个图表 widget 重定位到原图真实位置(原图像素→画布坐标)
  if (coordsJson) {
    const cfg = JSON.parse(await fs.readFile(coordsJson, 'utf8'));
    const refW = cfg.refW || 1024, refH = cfg.refH || 568;
    const kx = canvasW / refW, ky = canvasH / refH;
    for (const c of charts) {
      const name = String(c.name || '');
      const item = (cfg.charts || []).find((it) => name.includes(it.match));
      if (!item) continue;
      // 只平移到目标区中心，保留图表原始尺寸：缩放会裁掉图表内部文字(数字变"65...")
      const ow = c.states.width, oh = c.states.height;
      const cx = (item.x + item.w / 2) * kx, cy = (item.y + item.h / 2) * ky;
      const nx = Math.round(cx - ow / 2), ny = Math.round(cy - oh / 2);
      c.states.matrix = [1, 0, 0, 1, nx, ny];
    }
  }
  store.stories[0].widgets = [baseWidget, ...charts];
  root.Duchamp.DuchampTemplateAttr._attributes.store = JSON.stringify(store);
  let newRaw = fvs.writeXML(root);

  // 关键保护：TableDataMap 的 RowData 是帆软私有逐行编码，xml-js 往返会破坏换行导致图表读不到数据。
  // 用原文件里的整段原文替换回去（__raw 机制在手工合并路径下不生效）。
  const rawTdm = /<TableDataMap>[\s\S]*?<\/TableDataMap>/.exec(raw);
  const newTdm = /<TableDataMap>[\s\S]*?<\/TableDataMap>/.exec(newRaw);
  if (rawTdm && newTdm) {
    newRaw = newRaw.replace(newTdm[0], rawTdm[0]);
    console.log('TableDataMap 原文已保留(' + rawTdm[0].length + '字节)');
  }

  const zout = new JSZip();
  for (const [name, file] of Object.entries(zin.files)) {
    if (file.dir) { zout.folder(name); continue; }
    zout.file(name, name === 'editor.tpl' ? newRaw : await file.async('nodebuffer'));
  }
  zout.file(assetName, erasedBuf);

  const outBuf = await zout.generateAsync({ type: 'nodebuffer', compression: 'DEFLATE' });
  await fs.mkdir(path.dirname(path.resolve(outFvs)), { recursive: true });
  await fs.writeFile(outFvs, outBuf);
  console.log(`生成: ${outFvs} (1 擦除底图 + ${charts.length} 原生图表, 数据集保留)`);
})().catch((e) => { console.error('FAIL', e.message); process.exit(1); });
