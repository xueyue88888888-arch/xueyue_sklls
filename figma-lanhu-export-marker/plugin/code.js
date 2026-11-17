// Figma → 蓝湖 图层整理与导出标记（v6，清单驱动）
//
// 目标：把设计源 SVG 导入 Figma 后，一次性把「该能下载的素材」全部标上 Export，
//       并且**同一素材的每个实例都标**，再交给蓝湖插件上传。
//
// v6 相对 v5 的改动：
//   * 不再把素材清单写死在代码里 —— 支持三种来源（预设 / 粘贴 CSV / 按命名自动推断）
//   * 多实例：card__mini-metric-3 这类后缀自动归一到基名，每个实例都标
//   * 预览：先出「将要标记什么」的 CSV，确认后再真正写
//   * 分类统计、缺失清单、重复检测都在诊断里一次说清
//
// 完全离线：只改当前文件图层的 exportSettings，不联网、不写本地磁盘。

figma.showUI(__html__, { width: 520, height: 720, title: '图层整理与导出标记 v6' });

// ---------------------------------------------------------------- 预设清单
// 一鸣大屏（61 类）作为示例；换项目时用「粘贴清单」覆盖，或点「自动推断」。
const PRESET = [
  'image__bg-top', 'image__header-logo', 'image__title-decoration', 'image__brand-slogan',
  'image__sales-showcase', 'image__location', 'image__distribution-map',
  'card__top-metric', 'card__band-metric-strip', 'card__mini-metric', 'card__chart-default',
  'card__gauge', 'card__sales-kpi', 'card__feature', 'card__feed', 'card__sales-trend',
  'card__chart-distribution', 'card__chart-delivery', 'card__chart-channel',
  'card__chart-online', 'card__chart-top-products',
  'panelbg__agriculture', 'panelbg__factory', 'panelbg__sales', 'panelbg__logistics', 'panelbg__ecommerce',
  'photo__agriculture', 'photo__factory', 'photo__logistics', 'photo__ecommerce',
  'icon__top-cow', 'icon__top-store', 'icon__top-truck',
  'icon__chevron-cyan', 'icon__chevron-gold', 'icon__cart',
  'icon__agri-farm', 'icon__agri-cow', 'icon__agri-output', 'icon__agri-quality',
  'icon__factory-core', 'icon__factory-capacity', 'icon__factory-sku', 'icon__factory-quality',
  'icon__sales-store', 'icon__sales-member', 'icon__sales-yen', 'icon__sales-order',
  'icon__feature-pin', 'icon__feature-ai',
  'icon__logistics-center', 'icon__logistics-truck', 'icon__logistics-clock', 'icon__logistics-snow',
  'icon__ecommerce-sales', 'icon__ecommerce-order', 'icon__ecommerce-channel', 'icon__ecommerce-growth',
  'china-map-base', 'china-map-routes', 'china-map-glow'
];

// 自动推断时认的命名前缀（与 html-screen-to-design-source 的图层命名约定一致）
const AUTO_PREFIXES = ['panelbg__', 'card__', 'icon__', 'image__', 'photo__', 'chartref__', 'china-map-'];

const PAGE_BG_NAMES = /^(页面底色|背景光晕|page-?bg|__PAGE_BG__)$/i;
const LEGACY_RE = /素材板|矢量图标板|位图资产板|资产板|assets-(visual|brand|icons)|完整大屏板|00_|03_/i;

let MANIFEST = {};   // name -> 'PNG' | 'SVG'
let SOURCE = 'preset';

// ---------------------------------------------------------------- 工具
function norm(name) {
  return String(name || '').replace(/\s+\d+$/, '').trim();
}

function baseName(name) {
  const s = norm(name);
  if (MANIFEST[s]) return s;
  const m = s.match(/^(.*)-(\d+)$/);
  if (m && MANIFEST[m[1]]) return m[1];
  return s;
}

function roots() {
  try { return Array.prototype.slice.call(figma.currentPage.children); } catch (e) { return []; }
}

function kids(n) {
  try { return ('children' in n && n.children) ? Array.prototype.slice.call(n.children) : []; }
  catch (e) { return []; }
}

function walk(n, out) {
  out.push(n);
  for (const c of kids(n)) walk(c, out);
  return out;
}

function hasExport(n) {
  try { return !!(n.exportSettings && n.exportSettings.length); } catch (e) { return false; }
}

function clearNode(n) {
  try { if (hasExport(n)) n.exportSettings = []; } catch (e) { /* 不可导出节点 */ }
}

function clearAll(node) {
  let c = 0;
  for (const x of walk(node, [])) { if (hasExport(x)) { clearNode(x); c++; } }
  return c;
}

function exp(fmt) {
  return [{ format: fmt, suffix: '', constraint: { type: 'SCALE', value: 1 } }];
}

function send(summary, ok, log) {
  figma.ui.postMessage({ type: 'done', ok: ok, summary: summary, log: log });
}

// ---------------------------------------------------------------- 清单
function parseManifest(text) {
  const map = {};
  String(text || '').split(/\r?\n/).forEach(function (line) {
    line = line.trim();
    if (!line || line.charAt(0) === '#') return;
    const parts = line.split(/[,\t;]/).map(function (s) { return s.trim(); });
    const name = parts[0];
    if (!name) return;
    const fmt = (parts[1] || 'PNG').toUpperCase().replace(/[^A-Z]/g, '');
    map[name] = (fmt === 'SVG') ? 'SVG' : 'PNG';
  });
  return map;
}

function autoManifest(root) {
  const map = {};
  for (const x of walk(root, [])) {
    const nm = norm(x.name);
    if (!nm || PAGE_BG_NAMES.test(nm)) continue;
    let hit = false;
    for (const p of AUTO_PREFIXES) { if (nm.indexOf(p) === 0) { hit = true; break; } }
    if (!hit) continue;
    const base = nm.replace(/-\d+$/, '');
    map[base] = /vec|vector/i.test(base) ? 'SVG' : 'PNG';
  }
  return map;
}

function applyManifest(mode, text, root) {
  if (mode === 'auto') {
    MANIFEST = autoManifest(root);
    SOURCE = 'auto';
    return Object.keys(MANIFEST).length;
  }
  const parsed = parseManifest(text);
  if (Object.keys(parsed).length) {
    MANIFEST = parsed;
    SOURCE = 'pasted';
    return Object.keys(MANIFEST).length;
  }
  MANIFEST = {};
  PRESET.forEach(function (n) { MANIFEST[n] = 'PNG'; });
  SOURCE = 'preset';
  return Object.keys(MANIFEST).length;
}

function manifestText() {
  return Object.keys(MANIFEST).sort().map(function (k) { return k + ',' + MANIFEST[k]; }).join('\n');
}

// ---------------------------------------------------------------- 顶层分类
function classify(node) {
  const nm = norm(node.name);
  if (LEGACY_RE.test(nm)) return 'legacy';
  if (/大屏设计源|蓝湖设计源|设计源/.test(nm)) return 'screen';
  if (/素材总板|素材板|组件库/.test(nm)) return 'lib';
  const w = Math.round(node.width || 0);
  const h = Math.round(node.height || 0);
  if (h > 4000 || w > 4000 || h > w * 2) return 'lib';   // 竖长条 = 素材总板
  return 'screen';                                        // 其余默认当大屏稿
}

// ---------------------------------------------------------------- 采集
function collect(root) {
  const groups = {};        // 基名 -> [图层]
  const others = [];        // 不在清单里但看着像素材的
  let texts = 0;
  for (const x of walk(root, [])) {
    if (x.type === 'TEXT') { texts++; continue; }
    const nm = norm(x.name);
    if (!nm || PAGE_BG_NAMES.test(nm)) continue;
    const base = baseName(nm);
    if (MANIFEST[base]) {
      (groups[base] = groups[base] || []).push(x);
    } else {
      for (const p of AUTO_PREFIXES) {
        if (nm.indexOf(p) === 0) { others.push(nm); break; }
      }
    }
  }
  const missing = Object.keys(MANIFEST).filter(function (n) { return !groups[n]; });
  let total = 0;
  Object.keys(groups).forEach(function (k) { total += groups[k].length; });
  return { groups: groups, missing: missing, others: others, total: total, texts: texts };
}

// ---------------------------------------------------------------- 标记
function markAll(info, log) {
  let ok = 0, single = 0, multi = 0;
  Object.keys(MANIFEST).forEach(function (name) {
    const list = info.groups[name] || [];
    const fmt = MANIFEST[name];
    if (list.length > 1) multi++; else if (list.length === 1) single++;
    list.forEach(function (node) {
      clearNode(node);
      try { node.exportSettings = exp(fmt); }
      catch (e) { log.push('  ! 写入失败：' + node.name + ' / ' + e.message); return; }
      if (hasExport(node) && node.exportSettings[0].format === fmt) ok++;
      else log.push('  ! 回读校验失败：' + node.name);
    });
  });
  log.push('· 已标导出 ' + ok + '/' + info.total + ' 个实例（' + single + ' 类单件 + ' + multi + ' 类多实例）');
  return ok;
}

// ---------------------------------------------------------------- CSV
function csvEsc(v) {
  const s = String(v == null ? '' : v);
  return /[",\n\r]/.test(s) ? '"' + s.replace(/"/g, '""') + '"' : s;
}

function buildRows(screenRoot) {
  const rows = [];
  if (!screenRoot) return rows;
  const info = collect(screenRoot);
  Object.keys(MANIFEST).sort().forEach(function (base) {
    (info.groups[base] || []).forEach(function (node) {
      rows.push({
        base: base, name: node.name, type: node.type,
        size: Math.round(node.width) + 'x' + Math.round(node.height),
        format: MANIFEST[base]
      });
    });
  });
  return rows;
}

function previewCsv() {
  const screen = roots().filter(function (r) { return classify(r) === 'screen'; })[0];
  const rows = buildRows(screen);
  const lines = [['序号', '素材基名', '图层名', '类型', '尺寸', '导出格式'].join(',')];
  rows.forEach(function (r, i) {
    lines.push([i + 1, r.base, r.name, r.type, r.size, r.format].map(csvEsc).join(','));
  });
  figma.ui.postMessage({ type: 'csv', text: lines.join('\n'), filename: '导出预览_' + rows.length + '条.csv' });
  send('预览：将标记 ' + rows.length + ' 个实例（未写入任何标记）。', true,
    ['· 清单来源：' + SOURCE + '（' + Object.keys(MANIFEST).length + ' 类）',
     '· 预览条数 ' + rows.length,
     '   确认无误后再点「整理并标记」。']);
}

function exportCsv() {
  const lines = [['序号', '所属顶层', 'Figma图层名', '类型', '尺寸', '导出格式', '倍率', '回读校验', '清单基名'].join(',')];
  let n = 0, unlisted = 0;
  for (const root of roots()) {
    for (const x of walk(root, [])) {
      if (!hasExport(x)) continue;
      for (const s of x.exportSettings) {
        n++;
        const base = baseName(x.name);
        const reg = MANIFEST[base] || '（未登记）';
        if (reg.indexOf('未登记') >= 0) unlisted++;
        lines.push([n, root.name, x.name, x.type,
          Math.round(x.width) + 'x' + Math.round(x.height),
          s.format, s.constraint ? s.constraint.value : '1',
          s.constraint && s.constraint.value === 1 ? 'OK' : 'CHECK', reg].map(csvEsc).join(','));
      }
    }
  }
  const text = lines.join('\n');
  send('已导出标记结果 CSV：' + n + ' 条', unlisted === 0,
    ['· 合计 ' + n + ' 条 Export 设置' + (unlisted ? '（其中 ' + unlisted + ' 条不在清单内）' : ''),
     '· 与「导出预览」条数一致即为正常', '', text]);
  figma.ui.postMessage({ type: 'csv', text: text, filename: '导出标记结果_' + n + '条.csv' });
}

// ---------------------------------------------------------------- 诊断
function diagnose() {
  const list = roots();
  const lines = ['当前 Page：' + figma.currentPage.name, '顶层节点 ' + list.length + ' 个：'];
  list.forEach(function (r, i) {
    const cls = classify(r);
    let ne = 0, texts = 0;
    for (const x of walk(r, [])) { if (hasExport(x)) ne++; if (x.type === 'TEXT') texts++; }
    lines.push('  [' + (i + 1) + '] "' + r.name + '" ' + r.type + ' ' +
      Math.round(r.width) + '×' + Math.round(r.height) + '  [' + cls + ']' +
      '  子级 ' + kids(r).length + '  文字 ' + texts + '  已带 Export ' + ne);
    if (cls === 'screen') {
      const info = collect(r);
      lines.push('      清单 ' + Object.keys(MANIFEST).length + ' 类，匹配 ' +
        (Object.keys(MANIFEST).length - info.missing.length) + ' 类 / 实例 ' + info.total + ' 个');
      if (info.missing.length) lines.push('      缺失：' + info.missing.slice(0, 10).join('、') +
        (info.missing.length > 10 ? ' …' : ''));
      if (info.others.length) lines.push('      未登记但像素材：' + info.others.slice(0, 8).join('、'));
      lines.push('      子级样例：' + kids(r).slice(0, 4).map(function (c) { return c.name; }).join('、'));
    }
  });
  lines.push('');
  lines.push('清单来源：' + SOURCE + '（' + Object.keys(MANIFEST).length + ' 类）');
  lines.push('预期：大屏稿上每个素材实例都带 1x Export；素材总板保持 0。');
  send('诊断完成，见下方日志。', true, lines);
}

// ---------------------------------------------------------------- 主流程
async function run(msg) {
  const log = [];
  try { if (figma.currentPage.loadAsync) await figma.currentPage.loadAsync(); } catch (e) { /* old */ }

  const all = roots();
  const screen = all.filter(function (r) { return classify(r) === 'screen'; })[0];
  const lib = all.filter(function (r) { return classify(r) === 'lib'; })[0];

  // 清单
  const count = applyManifest(msg.mode || 'manifest', msg.manifest, screen || figma.currentPage);
  log.push('· 清单来源：' + SOURCE + '，' + count + ' 类');

  if (msg.type === 'manifest' || msg.type === 'auto') {
    send('清单已载入：' + count + ' 类（来源 ' + SOURCE + '）', true,
      log.concat(['  点「诊断」看匹配情况，或「导出预览」看将标记哪些图层。']));
    return;
  }
  if (msg.type === 'diagnose') { diagnose(); return; }
  if (msg.type === 'preview') { previewCsv(); return; }
  if (msg.type === 'csv') { exportCsv(); return; }
  if (msg.type === 'clear') {
    let total = 0;
    all.forEach(function (r) { total += clearAll(r); });
    send('已清空全部导出标记（' + total + ' 处）', true, ['重新点「整理并标记」即可。']);
    figma.notify('已清空 ' + total + ' 处导出标记');
    return;
  }
  if (msg.type === 'remove-legacy') {
    const names = [];
    all.forEach(function (r) {
      if (classify(r) !== 'legacy') return;
      names.push(r.name);
      try { r.remove(); } catch (e) { /* ignore */ }
    });
    send(names.length ? '已移除 ' + names.length + ' 个旧板' : '没有需要清理的旧板',
      true, names.length ? ['已删除：' + names.join('、')] : ['无需操作。']);
    return;
  }

  // organize / organize-lib
  if (!screen) {
    send('未找到大屏设计源：当前页没有尺寸像 2752×1204 / 1920×1080 的顶层节点。', false,
      log.concat(['请把设计源 SVG 拖进画布（SVG 只能拖入画布或 Shift+Ctrl+K）。']));
    return;
  }

  let cleared = 0;
  all.forEach(function (r) { cleared += clearAll(r); });
  log.push('· 清理旧标记 ' + cleared + ' 处');

  const info = collect(screen);
  if (!info.total) {
    send('清单和大屏稿一个都对不上，未写入任何标记。', false,
      log.concat(['点「诊断」看清单来源与图层名是否一致；或改用「自动推断」。',
        '缺失类：' + info.missing.slice(0, 10).join('、')]));
    return;
  }
  if (info.missing.length) {
    log.push('⚠ 有 ' + info.missing.length + ' 类在稿子里没找到：' + info.missing.slice(0, 10).join('、'));
    log.push('  这些不会标；如果是命名不一致，先用「导出预览」核对。');
  }

  const ok = markAll(info, log);

  if (msg.type === 'organize-lib' && lib) {
    let libOk = 0;
    kids(lib).forEach(function (t) {
      const nm = norm(t.name);
      if (!nm || PAGE_BG_NAMES.test(nm)) return;
      clearNode(t);
      try { t.exportSettings = exp('PNG'); if (hasExport(t)) libOk++; } catch (e) { /* skip */ }
    });
    log.push('· 素材总板额外标了 ' + libOk + ' 件（注意：蓝湖会出现两套下载项）');
  } else if (lib) {
    log.push('· 素材总板：默认 0 标记（避免重复下载项）');
  }

  log.push('');
  log.push('下一步：蓝湖插件 → Web @1X → 只上传大屏稿 → 在标注页验收');
  log.push('点「导出标记结果 CSV」留档，条数应与「导出预览」一致。');

  send(ok === info.total
    ? '完成：' + ok + '/' + info.total + ' 个实例可下载（' + Object.keys(MANIFEST).length + ' 类素材）'
    : '标记数异常：' + ok + '/' + info.total + '，请查看日志',
    ok === info.total, log);
  figma.notify(ok === info.total ? '整理完成 · ' + ok + ' 个实例可下载' : '标记数异常，请看日志');
}

figma.ui.onmessage = function (msg) {
  if (!msg) return;
  if (msg.type === 'ui-ready') { figma.ui.postMessage({ type: 'init', preset: manifestInit() }); return; }
  if (msg.type === 'close') { figma.closePlugin(); return; }
  run(msg);
};

function manifestInit() {
  MANIFEST = {};
  PRESET.forEach(function (n) { MANIFEST[n] = 'PNG'; });
  SOURCE = 'preset';
  return manifestText();
}
