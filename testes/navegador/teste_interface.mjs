// Teste da interface do modo área (Leopoldina): desenho, importação, erros, segurança, download, PDF e capturas
// Uso (na raiz do projeto): node testes/navegador/teste_interface.mjs
import { createHash } from 'node:crypto';
import { mkdirSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { abrir } from './cdp.mjs';

const AQUI = dirname(fileURLToPath(import.meta.url)), RAIZ = resolve(AQUI, '..', '..');
const SAIDA = join(RAIZ, 'saida'), CAP = join(SAIDA, 'capturas_passo12'), EX = join(AQUI, 'exemplos');
const TMP = mkdtempSync(join(tmpdir(), 'farol-interface-'));  // arquivos de erro gerados e o GeoJSON baixado
mkdirSync(CAP, { recursive: true });
const espera = ms => new Promise(r => setTimeout(r, ms));
const resultados = [];
const conferir = (nome, ok, extra = '') => { resultados.push([ok ? 'OK  ' : 'FALHA', nome, extra]); };

const p = await abrir(join(SAIDA, 'mapa_comunidades.html'));
const av = e => p.avaliar(e);
async function clicarEm(x, y) {
  for (const type of ['mouseMoved', 'mousePressed', 'mouseReleased'])
    await p.send('Input.dispatchMouseEvent', { type, x, y, button: 'left', clickCount: type === 'mouseMoved' ? 0 : 1 });
  await espera(120);
}
async function clicar(sel) {
  const r = await av(`(() => { const el = document.querySelector(${JSON.stringify(sel)}); el.scrollIntoView({ block: 'center' });
    const b = el.getBoundingClientRect(); return [b.x + b.width / 2, b.y + b.height / 2]; })()`);
  await clicarEm(r[0], r[1]);
}
async function captura(nome) {
  const r = await p.send('Page.captureScreenshot', { format: 'png' });
  writeFileSync(join(CAP, nome), Buffer.from(r.data, 'base64'));
}
async function importar(arquivo) {
  const doc = await p.send('DOM.getDocument', { depth: 0 });
  const { nodeId } = await p.send('DOM.querySelector', { nodeId: doc.root.nodeId, selector: '#arqArea' });
  await p.send('DOM.setFileInputFiles', { nodeId, files: [arquivo] });
  await espera(900);
}
const erroArea = () => av(`$('areaErro').classList.contains('oculto') ? '' : $('areaErro').textContent`);
// Guarda a entrada do código de verificação para recalcular fora do navegador
await av(`(() => { const original = sha256hex; sha256hex = t => { window.__entradas = (window.__entradas || []).concat([t]); return original(t); }; return 0; })()`);
async function conferirCodigo(rotulo, esperadoNaEntrada) {
  await av(`(window.__entradas = [], atualizarAviso(), hashPronto)`);
  const [entrada, codigo] = await av(`[window.__entradas.at(-1), $('rtCodigo').textContent]`);
  const sha = createHash('sha256').update(entrada, 'utf8').digest('hex');
  conferir(`${rotulo}: código de verificação recalculado fora do navegador`, sha === codigo, codigo.slice(0, 16) + '…');
  conferir(`${rotulo}: entrada do código tem "${esperadoNaEntrada}"`, entrada.split('\n')[3].startsWith(esperadoNaEntrada), entrada.split('\n')[3]);
  return entrada;
}
async function pdf(nome) {
  const r = await p.send('Page.printToPDF', { printBackground: true, preferCSSPageSize: true });
  writeFileSync(join(CAP, nome), Buffer.from(r.data, 'base64'));
}

// ---------- 1. Área desenhada perto da CF-0066 (cliques de verdade no mapa) ----------
await clicar('.modos button[data-modo="area"]');
conferir('seletor: modo área mostra a mensagem fixa', await av(`!$('blocoArea').classList.contains('oculto') && getComputedStyle(document.querySelector('.area-alerta')).display !== 'none'`));
const cf = await av(`(() => { const c = D.cenarios['CF-0066'], t = new Set(c.trafos), pts = D.ucs.filter(u => t.has(u[2]));
  const lat = pts.map(u => u[0]), lon = pts.map(u => u[1]);
  return { n: c.n, com: c.com.map(x => x[0]), b: [Math.min(...lat), Math.min(...lon), Math.max(...lat), Math.max(...lon)] }; })()`);
await av(`mapa.fitBounds([[${cf.b[0]}, ${cf.b[1]}], [${cf.b[2]}, ${cf.b[3]}]], { padding: [80, 80], animate: false }); 0`);
await clicar('#btnDesenhar');
const cy = (cf.b[0] + cf.b[2]) / 2, cx = (cf.b[1] + cf.b[3]) / 2, ry = (cf.b[2] - cf.b[0]) * 0.6, rx = (cf.b[3] - cf.b[1]) * 0.6;
const vertices = [0, 1, 2, 3, 4, 5, 6].map(k => [cy + ry * Math.sin(2 * Math.PI * k / 7 + 0.3), cx + rx * Math.cos(2 * Math.PI * k / 7 + 0.3)]);
const mapaXY = await av(`(() => { const b = $('mapa').getBoundingClientRect(); return [b.x, b.y]; })()`);
for (const [lat, lon] of [...vertices, [cy, cx]]) {  // o último é um ponto a mais, para testar "Desfazer ponto"
  const [x, y] = await av(`(() => { const q = mapa.latLngToContainerPoint([${lat}, ${lon}]); return [q.x, q.y]; })()`);
  await clicarEm(mapaXY[0] + x, mapaXY[1] + y);
}
conferir('desenho: cada clique virou um vértice', (await av('estado.desenho.length')) === 8, `${await av('estado.desenho.length')} pontos`);
conferir('desenho: nenhum popup de chave ou UC abriu durante o desenho', await av(`!document.querySelector('.leaflet-popup')`));
await clicar('#btnDesfazer');
conferir('desenho: "Desfazer ponto" tira o último vértice', (await av('estado.desenho.length')) === 7);
await clicar('#btnConcluir');
await espera(800);
const area1 = await av(`({ n: estado.cenario?.n, area: estado.cenario?.area, com: estado.cenario?.com.map(x => [x[0], x[1], x[3] ? 'parte' : 'inteira', x[5] ? 'vizinha' : 'citada']),
  rotulo: $('cdChave').textContent, meta: $('cdMeta').textContent, vert: estado.area?.resumo.vertices, aviso: estado.textos.novo,
  cargas: [...document.querySelectorAll('.carga')].map(e => e.textContent.trim()), janela: $('janelaMelhor').textContent.trim() })`);
conferir('área desenhada: clientes dentro destacados e aviso montado', area1.area === true && area1.n > 0, `${area1.n} clientes, ${area1.vert} vértices`);
conferir('legenda: "Área informada" no lugar de "Ramal desligado"', await av(`$('legRamal').classList.contains('oculto') && !$('legArea').classList.contains('oculto')`));
conferir('área desenhada: contorno âmbar tracejado no mapa', await av(`(() => { let ok = false; areaCamada.eachLayer(g => g.eachLayer(l => { ok = l.options.dashArray === '8 6' && l.options.color === css('--ambar'); })); return ok; })()`));
conferir('modo área: validação com o Censo escondida (mesmo no modo apresentação)', await (async () => {
  await clicar('#btnApresentacao'); const oculto = await av(`getComputedStyle($('validCen')).display === 'none'`); await clicar('#btnApresentacao'); return oculto; })());
await captura('1_area_desenhada_perto_CF-0066.png');
await clicar('#tab-aviso');
// passo 14: a comparação volta (só o tamanho do aviso de hoje); o texto e o "Ouvir" do aviso de hoje continuam fora
const cmpArea = await av(`({ cmp: !$('blocoComparacao').classList.contains('oculto'), antigo: !$('blocoAntigo').classList.contains('oculto'),
  nota: !$('notaSemComparacao').classList.contains('oculto'), rot: $('tAntigo').previousElementSibling.textContent, t: $('tAntigo').textContent, ganho: $('ganho').textContent })`);
conferir('aba Aviso: comparação com o tamanho do aviso de hoje, sem o texto dele; nota visível', cmpArea.cmp && !cmpArea.antigo && cmpArea.nota
  && /^Hoje: [\d.]+ locais citados · [\d.]+ palavras$/.test(cmpArea.rot) && / no ar$/.test(cmpArea.t) && /% mais curto/.test(cmpArea.ganho), `${cmpArea.rot} | ${cmpArea.t}`);
await captura('2_aviso_da_area_desenhada.png');
const ent1 = await conferirCodigo('área desenhada', 'area=desenhada;poligonos=1;vertices=7;sha256=');
const canon = await av(`formaCanonica(estado.area.poligonos)`);
conferir('área desenhada: SHA-256 da forma canônica confere', ent1.includes(createHash('sha256').update(canon, 'utf8').digest('hex')));
conferir('PDF: registro mostra "Área desenhada" e os vértices', await av(`document.querySelector('#roteiro').textContent.includes('Área desenhada · 7 vértices')`));
await pdf('roteiro_area_desenhada.pdf');

// Download do GeoJSON (sem exceção na CSP)
await p.navegador.send('Browser.setDownloadBehavior', { behavior: 'allow', downloadPath: TMP, eventsEnabled: true });
await clicar('#tab-desligamento');
await clicar('#btnBaixarArea');
await espera(1500);
const baixados = readdirSync(TMP).filter(f => f.endsWith('.geojson'));
let gjOk = false;
if (baixados.length) {
  const gj = JSON.parse(readFileSync(join(TMP, baixados[0]), 'utf8'));
  gjOk = gj.features[0].geometry.type === 'Polygon' && gj.features[0].geometry.coordinates[0].length === 8;
  writeFileSync(join(CAP, 'area_desenhada_baixada.geojson'), readFileSync(join(TMP, baixados[0])));
}
conferir('download: "Baixar área (GeoJSON)" gera o arquivo, sem mexer na CSP', gjOk, baixados.join(', ') || 'nenhum arquivo');

// ---------- 2. Importação do GeoJSON de exemplo ----------
await importar(join(EX, 'area_exemplo_leopoldina.geojson').replace(/\//g, '\\'));
const area2 = await av(`({ n: estado.cenario?.n, desc: $('areaDesc').textContent, com: estado.cenario?.com.length })`);
conferir('importação GeoJSON: área aplicada', area2.n > 0, `${area2.n} clientes · ${area2.desc}`);
await captura('3_importacao_geojson_exemplo.png');
await conferirCodigo('área importada', 'area=importada;poligonos=1;');
conferir('PDF: registro mostra "Área importada (nome do arquivo)"', await av(`document.querySelector('#roteiro').textContent.includes('Área importada (area_exemplo_leopoldina.geojson)')`));
await pdf('roteiro_area_importada.pdf');

// ---------- 3. Segurança: KML com HTML e script na descrição ----------
await importar(join(EX, 'area_teste_html_na_descricao.kml').replace(/\//g, '\\'));
await espera(500);
const kml = await av(`({ xss: window.__xss, img: !!document.querySelector('img[src="x"], img[src*="exemplo.invalid"]'), n: estado.cenario?.n,
  texto: ['negrito', 'Área com HTML', 'Teste de segurança', 'rastreio', 'exemplo.invalid'].filter(t => document.body.innerText.includes(t) || [...document.querySelectorAll('body *:not(script)')].some(e => [...e.attributes].some(x => x.value.includes(t)))),
  atributosOn: [...document.querySelectorAll('body *')].filter(e => [...e.attributes].some(x => /^on/i.test(x.name))).length,
  links: [...document.querySelectorAll('a[href^="javascript:"]')].length, csp: window.__csp })`);
conferir('KML com HTML: só as coordenadas são usadas (nenhum script, imagem ou texto do arquivo na página)',
  kml.xss === undefined && !kml.img && !kml.texto.length && !kml.atributosOn && !kml.links && kml.n > 0, JSON.stringify(kml));

// ---------- 4. Mensagens de erro ----------
const erros = {};
const casos = [
  ['vazio.geojson', ''],
  ['contorno.txt', '{"type":"Polygon","coordinates":[]}'],
  ['quebrado.json', '{"type": "FeatureCollection", "features": ['],
  ['nao_geojson.json', '{"nome": "qualquer"}'],
  ['projetado.geojson', JSON.stringify({ type: 'Polygon', coordinates: [[[700000, 7600000], [701000, 7600000], [701000, 7601000], [700000, 7600000]]] })],
  ['fora.geojson', JSON.stringify({ type: 'Polygon', coordinates: [[[-43.2, -22.9], [-43.1, -22.9], [-43.1, -22.8], [-43.2, -22.9]]] })],
  ['sem_clientes.geojson', null],
  ['muitos_vertices.geojson', null],
  ['grande.geojson', null],
  ['kml_quebrado.kml', '<kml><Placemark><Polygon>'],
];
for (const [nome, conteudo] of casos) {
  let c = conteudo;
  if (nome === 'sem_clientes.geojson') {  // quadradinho de 40 m num ponto do município sem UCs perto
    const [lat, lon] = await av(`(() => { const b = limMun;
      for (let lat = b.getSouth(); lat < b.getNorth(); lat += 0.003) for (let lon = b.getWest(); lon < b.getEast(); lon += 0.003)
        if (dentroDaArea(lat, lon) && !D.ucs.some(u => Math.abs(u[0] - lat) < 0.002 && Math.abs(u[1] - lon) < 0.002)) return [lat, lon]; })()`);
    const d = 0.0002;
    c = JSON.stringify({ type: 'Polygon', coordinates: [[[lon, lat], [lon + d, lat], [lon + d, lat + d], [lon, lat + d], [lon, lat]]] });
  }
  if (nome === 'muitos_vertices.geojson') {
    const anel = Array.from({ length: 20001 }, (_, k) => [-42.64 + 0.01 * Math.cos(2 * Math.PI * k / 20001), -21.53 + 0.01 * Math.sin(2 * Math.PI * k / 20001)]);
    c = JSON.stringify({ type: 'Polygon', coordinates: [[...anel, anel[0]]] });
  }
  if (nome === 'grande.geojson') c = JSON.stringify({ type: 'Polygon', coordinates: [[[-42.64, -21.53], [-42.63, -21.53], [-42.63, -21.52], [-42.64, -21.53]]], enchimento: 'x'.repeat(6 * 1024 * 1024) });
  writeFileSync(join(TMP, nome), c);
  await importar(join(TMP, nome).replace(/\//g, '\\'));
  erros[nome] = await erroArea();
}
await av(`mapa.fitBounds(limMun, { animate: false }); 0`);
await importar(join(EX, 'area_teste_sem_poligono.geojson').replace(/\//g, '\\'));
erros['area_teste_sem_poligono.geojson'] = await erroArea();
await captura('4_erro_sem_poligono.png');
for (const [nome, msg] of Object.entries(erros)) conferir(`erro: ${nome}`, !!msg, msg);

// ---------- 5. Troca de modo e regressão por chave ----------
await clicar('.modos button[data-modo="chave"]');
conferir('trocar para "Por chave" limpa a área', await av(`!estado.area && !estado.cenario && areaCamada.getLayers().length === 0 && !$('vazio').classList.contains('oculto')`));
await av(`simular('CF-0066'); 0`);
const cf66 = await av(`({ n: estado.cenario.n, cmp: !$('blocoComparacao').classList.contains('oculto'), valid: $('validCen').className, rot: $('cdRot').textContent })`);
conferir('por chave: CF-0066 continua com comparação, validação e rótulo "Chave aberta"', cf66.cmp && cf66.valid === 'valid-cen so-ap bloco' && cf66.rot === 'Chave aberta', JSON.stringify(cf66));
await conferirCodigo('por chave', 'chave=CF-0066');
await pdf('roteiro_CF-0066_por_chave.pdf');
await clicar('.modos button[data-modo="obra"]');
conferir('modo ponto da obra: mostra a instrução e mantém a chave simulada', await av(`!$('instrObra').classList.contains('oculto') && estado.cenario && estado.cod === 'CF-0066'`));
await clicar('.modos button[data-modo="area"]');
conferir('trocar para "Por área" limpa a simulação por chave', await av(`!estado.cenario && !estado.cod`));

// ---------- 6. Celular: sem rolagem horizontal ----------
await p.send('Emulation.setDeviceMetricsOverride', { width: 390, height: 844, deviceScaleFactor: 2, mobile: true });
await espera(400);
conferir('celular (390 px): sem rolagem horizontal no modo área', await av(`document.documentElement.scrollWidth <= innerWidth`));

conferir('nenhuma exceção na página', p.excecoes.length === 0, JSON.stringify(p.excecoes));
conferir('nenhuma violação de CSP', (await av('window.__csp')).length === 0, JSON.stringify(await av('window.__csp')));
await p.fechar();
rmSync(TMP, { recursive: true, force: true });
console.log(`CF-0066 por chave: ${cf.n} clientes (${cf.com.join(', ')})`);
console.log(`Área desenhada perto da CF-0066: ${area1.n} clientes, ${area1.vert} vértices\n  comunidades: ${JSON.stringify(area1.com)}\n  aviso: ${area1.aviso}\n  cargas: ${area1.cargas.join(' | ')}\n  janela: ${area1.janela}`);
console.log(`GeoJSON de exemplo: ${area2.n} clientes, ${area2.com} comunidades (${area2.desc})\n`);
for (const r of resultados) console.log(r[0], r[1], r[2] ? `→ ${r[2]}` : '');
const falhas = resultados.filter(r => r[0] !== 'OK  ').length;
console.log(`\n${resultados.length - falhas} de ${resultados.length} verificações OK`);
process.exit(falhas ? 1 : 0);
