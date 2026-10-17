// Teste de comportamento da tela: grava um "retrato" de tudo o que o mapa mostra em centenas de
// situações e, depois de uma reorganização do código, confere se a tela continua idêntica.
// O retrato tem a lateral (com o que está visível), a busca, a legenda, o popup, o roteiro do PDF
// (sem a hora de geração e o código, que mudam a cada vez), todas as camadas do mapa e o enquadramento.
//
// Uso (na raiz do projeto):
//   node testes/navegador/teste_tela.mjs [pasta de saída] --gravar   grava saida/referencias_passo12/tela.json
//   node testes/navegador/teste_tela.mjs [pasta de saída]            compara com o que foi gravado
import { createHash } from 'node:crypto';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { abrir } from './cdp.mjs';

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const args = process.argv.slice(2), gravar = args.includes('--gravar');
const saida = resolve(RAIZ, args.find(a => !a.startsWith('--')) || 'saida');
const ref = join(saida, 'referencias_passo12'), ARQ = join(ref, 'tela.json');
const AMOSTRA = 12;  // retratos guardados por inteiro (para mostrar a diferença); os demais só pelo SHA-256

const p = await abrir(join(saida, 'mapa_comunidades.html'));
const av = e => p.avaliar(e);
await av(`window.__areas = ${readFileSync(join(ref, 'areas.json'), 'utf8')}; window.__obra = ${readFileSync(join(ref, 'obra.json'), 'utf8')}; 0`);

// Sem animação de enquadramento nem de deslize (o retrato pega a vista final) e funções de retrato
await av(`(() => {
  { const o = mapa.panBy.bind(mapa); mapa.panBy = (d, op) => o(d, { ...(op || {}), animate: false }); }  // o popup desliza o mapa ao abrir
  for (const f of ['fitBounds', 'setView']) { const o = mapa[f].bind(mapa); mapa[f] = (a, b, c) => f === 'fitBounds' ? o(a, { ...(b || {}), animate: false }) : o(a, b, { ...(c || {}), animate: false }); }
  const mascarar = t => t.replace(/faltam \\d+ (dias|h)/g, 'faltam N $1').replace(/faltan \\d+ (días|h)/g, 'faltan N $1').replace(/\\d+ (days|h) left/g, 'N $1 left')
    .replace(/<code id="rtCodigo">[^<]*<\\/code>/, '<code id="rtCodigo">#</code>')
    .replace(/(gerado em|generated on|generado el) [^·<]*/, '$1 #');
  const ser = el => {
    const out = [];
    const andar = (n, d) => {
      if (n.nodeType === 3) { const t = n.textContent.replace(/\\s+/g, ' ').trim(); if (t) out.push(d + '"' + t); return; }
      if (n.nodeType !== 1 || n.tagName === 'SCRIPT') return;
      let s = d + n.tagName.toLowerCase() + (n.id ? '#' + n.id : '') + (typeof n.className === 'string' && n.className.trim() ? '.' + n.className.trim().split(/\\s+/).sort().join('.') : '');
      if (getComputedStyle(n).display === 'none') { out.push(s + ' [oculto]'); return; }
      for (const a of n.attributes) if (/^(aria-|data-|style$|href$|role$|type$|disabled$)/.test(a.name)) s += ' ' + a.name + '=' + a.value;
      if (n.tagName === 'INPUT' || n.tagName === 'SELECT') s += ' =' + n.value;
      if (n.disabled) s += ' (desabilitado)';
      out.push(s);
      n.childNodes.forEach(c => andar(c, d + ' '));
    };
    if (el) andar(el, '');
    return mascarar(out.join('\\n'));
  };
  const tipo = l => l instanceof L.TileLayer ? 'tile:' + l._url : l instanceof L.CircleMarker ? 'cm' : l instanceof L.Polygon ? 'pg' : l instanceof L.Polyline ? 'pl'
    : l instanceof L.Marker ? 'mk' : l instanceof L.GeoJSON ? 'gj' : l instanceof L.FeatureGroup ? 'fg' : l instanceof L.LayerGroup ? 'lg' : 'x';
  window.__retrato = () => {
    const camadas = [];
    mapa.eachLayer(l => {
      const o = l.options || {}, t = l.getTooltip && l.getTooltip();
      let geo = '';
      if (l.getLatLng) { const q = l.getLatLng(); geo = q.lat.toFixed(6) + ',' + q.lng.toFixed(6); }
      else if (l.getLatLngs) geo = JSON.stringify(l.getLatLngs()).length + ':' + l.getBounds().toBBoxString();
      camadas.push([tipo(l), o.pane, o.color, o.weight, o.opacity, o.dashArray, o.radius, o.fillColor, o.fillOpacity, o.interactive, o.stroke, geo,
        t ? (t.options.permanent ? 'P:' : 'T:') + String(t._content).slice(0, 120) : ''].join('|'));
    });
    camadas.sort();
    // o popup aberto (o que acabou de fechar ainda fica no DOM durante a animação de saída)
    const c = mapa.getCenter(), pp = mapa._popup, pop = pp && pp.isOpen() ? pp._contentNode : null;
    return JSON.stringify({
      lateral: ser($('lateral')), legenda: ser(document.querySelector('.legenda')), lugar: $('appLugar').textContent,
      busca: $('busca').value, sugestoes: ser($('sugestoes')), popup: pop ? mascarar(pop.innerHTML) : null,
      roteiro: mascarar($('roteiro').innerHTML), tema: document.documentElement.dataset.theme || '', apresentacao: document.documentElement.classList.contains('apresentacao'),
      mapaClasses: $('mapa').className, vista: [c.lat.toFixed(6), c.lng.toFixed(6), mapa.getZoom()], camadas,
    });
  };
  // Data fixa: o retrato não pode depender do dia em que o teste roda
  const d = $('avData'); d.value = '2026-11-12'; d.dispatchEvent(new Event('input', { bubbles: true }));
  return 0;
})()`);

const retratos = {};
async function retrato(id) { retratos[id] = await av('window.__retrato()'); }
const ev = (sel, valor, evento = 'input') => av(`(() => { const el = document.querySelector(${JSON.stringify(sel)}); el.value = ${JSON.stringify(valor)}; el.dispatchEvent(new Event('${evento}', { bubbles: true })); return 0; })()`);
const clicar = sel => av(`(document.querySelector(${JSON.stringify(sel)}).click(), 0)`);

await retrato('inicial');
const chaves = await av('Object.keys(D.cenarios)');
for (const [i, cod] of chaves.entries()) {
  await av(`(simular(${JSON.stringify(cod)}), 0)`);
  await retrato(`chave ${cod}`);
  if (i % 40 === 0) {  // amostra: idiomas, abas, janela, horário e telefone, apresentação
    for (const idioma of ['en', 'es', 'pt-BR']) { await ev('#avIdioma', idioma, 'change'); await retrato(`chave ${cod} idioma ${idioma}`); }
    for (const aba of ['aviso', 'comunidades', 'desligamento']) { await clicar(`#tab-${aba}`); await retrato(`chave ${cod} aba ${aba}`); }
    if (await av(`!!document.querySelector('#blocoJanela button[data-ini]')`)) { await clicar('#blocoJanela button[data-ini]'); await retrato(`chave ${cod} usar janela`); }
    await ev('#avIni', '09:30'); await ev('#avFim', '15:15'); await ev('#avTel', ''); await retrato(`chave ${cod} horário e telefone`);
    await ev('#avIni', '08:00'); await ev('#avFim', '14:00'); await ev('#avTel', await av('DIST.telefone'));
    await clicar('#btnApresentacao'); await retrato(`chave ${cod} apresentação`); await clicar('#btnApresentacao');
  }
}
for (const t of ['claro', 'escuro', 'auto']) { await clicar('#btnTema'); await retrato(`tema ${t}`); }
await av('(limpar(), 0)'); await retrato('limpar');
await clicar('.modos button[data-modo="obra"]'); await retrato('modo obra');
const pontos = await av('window.__obra.pontos.map(x => [x.lat, x.lon])');
for (const [k, [lat, lon]] of pontos.entries()) { await av(`(marcarObra(${lat}, ${lon}), 0)`); await retrato(`obra ${k}`); }
await clicar('#btnLimparObra'); await retrato('obra limpa');
await clicar('.modos button[data-modo="area"]'); await retrato('modo área');
const nAreas = await av('window.__areas.areas.length');
for (let k = 0; k < nAreas; k++) {
  await av(`aplicarArea(window.__areas.areas[${k}].poligonos, ${k % 2 ? "'importada', 'teste.geojson'" : "'desenhada', null"})`);
  await retrato(`área ${k}`);
  if (k % 25 === 0 && await av("!$('cheio').classList.contains('oculto')")) {
    for (const idioma of ['es', 'pt-BR']) { await ev('#avIdioma', idioma, 'change'); await retrato(`área ${k} idioma ${idioma}`); }
    await clicar('#tab-comunidades'); await retrato(`área ${k} aba comunidades`); await clicar('#tab-desligamento');
  }
}
await clicar('.modos button[data-modo="chave"]'); await retrato('volta ao modo chave');
const excecoes = p.excecoes, csp = await av('window.__csp');
await p.fechar();

const hash = s => createHash('sha256').update(s, 'utf8').digest('hex');
const ids = Object.keys(retratos);
if (gravar) {
  writeFileSync(ARQ, JSON.stringify({ hashes: Object.fromEntries(ids.map(id => [id, hash(retratos[id])])),
    amostra: Object.fromEntries(ids.filter((_, i) => i % Math.ceil(ids.length / AMOSTRA) === 0).map(id => [id, retratos[id]])) }));
  console.log(`Gravado: ${ARQ} (${ids.length} retratos) | exceções: ${excecoes.length} | CSP: ${csp.length}`);
  process.exit(excecoes.length ? 1 : 0);
}
if (!existsSync(ARQ)) { console.log(`Falta ${ARQ}: rode antes com --gravar.`); process.exit(1); }
const gravado = JSON.parse(readFileSync(ARQ, 'utf8'));
const diferentes = ids.filter(id => gravado.hashes[id] !== hash(retratos[id]));
const faltando = Object.keys(gravado.hashes).filter(id => !(id in retratos));
console.log(`Tela: ${ids.length} retratos | iguais: ${ids.length - diferentes.length} | diferentes: ${diferentes.length} | faltando: ${faltando.length} | exceções: ${excecoes.length} | CSP: ${csp.length}`);
for (const id of diferentes.slice(0, 5)) {
  console.log(`  diferente: ${id}`);
  const antes = gravado.amostra[id];
  if (antes) {  // mostra o primeiro campo e a primeira linha que mudaram
    const a = JSON.parse(antes), b = JSON.parse(retratos[id]);
    for (const k of Object.keys(b)) if (JSON.stringify(a[k]) !== JSON.stringify(b[k])) {
      const la = String(Array.isArray(a[k]) ? a[k].join('\n') : a[k]).split('\n'), lb = String(Array.isArray(b[k]) ? b[k].join('\n') : b[k]).split('\n');
      const i = la.findIndex((l, j) => l !== lb[j]);
      console.log(`    campo ${k}, linha ${i}:\n      antes: ${String(la[i]).slice(0, 200)}\n      agora: ${String(lb[i]).slice(0, 200)}`);
      break;
    }
  }
}
process.exit(diferentes.length || faltando.length || excecoes.length ? 1 : 0);
