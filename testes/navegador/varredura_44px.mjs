// Varredura de alvos de toque: nenhum botão, link ou campo visível com menos de 44 × 44 px.
// Percorre as situações principais do mapa (e a página de entrada, se existir), no computador e no celular.
// Uso (na raiz do projeto): node testes/navegador/varredura_44px.mjs [pasta de saída]
import { existsSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { abrir } from './cdp.mjs';

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const saida = resolve(RAIZ, process.argv[2] || 'saida');
const MINIMO = 44;
const medir = `(() => {
  const alvos = [...document.querySelectorAll('button, a[href], input, select, summary, [role="button"], [role="switch"], [role="tab"], [role="radio"], [role="option"]')];
  return alvos.filter(el => {
    const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
    if (!r.width || !r.height || cs.visibility === 'hidden' || el.closest('[hidden], #roteiro, .abertura')) return false;
    if (el.type === 'file') return false;  // o seletor de arquivo fica escondido; quem abre é o botão "Importar contorno"
    return r.width < ${MINIMO} - 0.5 || r.height < ${MINIMO} - 0.5;
  }).map(el => (el.id ? '#' + el.id : el.tagName.toLowerCase() + (el.className && typeof el.className === 'string' ? '.' + el.className.trim().split(/\\s+/).join('.') : ''))
    + ' "' + (el.textContent || el.getAttribute('aria-label') || '').trim().slice(0, 30) + '" ' + Math.round(el.getBoundingClientRect().width) + '×' + Math.round(el.getBoundingClientRect().height));
})()`;

const problemas = new Map();
const anotar = (situacao, lista) => lista.forEach(x => { if (!problemas.has(x)) problemas.set(x, []); problemas.get(x).push(situacao); });
for (const [largura, altura, nome] of [[1440, 900, 'computador'], [390, 844, 'celular']]) {
  const p = await abrir(join(saida, 'mapa_comunidades.html'), { largura, altura });
  const av = e => p.avaliar(e);
  const passo = async (situacao, acao) => { if (acao) await av(acao); await av('new Promise(r => setTimeout(r, 150))'); anotar(`${nome}: ${situacao}`, await av(medir)); };
  await passo('inicial');
  await passo('camadas abertas', "($('btnCamadas').click(), 0)");
  await passo('camadas fechadas', "($('btnCamadas').click(), 0)");
  const cod = await av("Object.keys(D.cenarios).find(k => D.cenarios[k].rural >= 0.8 && D.cenarios[k].n > 50)");
  await passo('chave simulada', `(simular('${cod}'), 0)`);
  await passo('aba aviso', "($('tab-aviso').click(), document.querySelector('details.antigo').open = true, 0)");
  await passo('aba comunidades', "($('tab-comunidades').click(), 0)");
  await passo('popup de chave', `($('tab-desligamento').click(), mapa.eachLayer(l => { if (l.feature && l.feature.properties.COD_CHAVE === '${cod}') l.openPopup(); }), 0)`);
  await passo('busca', "(($('busca').value = 'cf-00'), $('busca').dispatchEvent(new Event('input')), 0)");
  await passo('ponto da obra', "(document.dispatchEvent(new MouseEvent('click')), document.querySelector('.modos button[data-modo=\"obra\"]').click(), marcarObra(...window.__p = (() => { const c = D.camadas.mt.features[5].geometry.coordinates[0]; return [c[1], c[0]]; })()), 0)");
  await passo('modo área', "(document.querySelector('.modos button[data-modo=\"area\"]').click(), 0)");
  await passo('desenhando', "($('btnDesenhar').click(), 0)");
  await p.fechar();
  const entrada = join(resolve(RAIZ, 'saida'), 'index.html');
  if (existsSync(entrada)) {
    const q = await abrir(entrada, { largura, altura });
    await q.avaliar('new Promise(r => setTimeout(r, 1600))');  // depois da abertura animada
    anotar(`${nome}: página de entrada`, await q.avaliar(medir));
    await q.fechar();
  }
}
if (!problemas.size) console.log(`Nenhum alvo de toque abaixo de ${MINIMO} px.`);
for (const [alvo, onde] of problemas) console.log(`ABAIXO DE ${MINIMO} PX: ${alvo}  (${onde.join('; ')})`);
process.exit(problemas.size ? 1 : 0);
