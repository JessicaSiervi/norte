// Teste JS × Python: o navegador reproduz as referências do Python (chaves, áreas e ponto da obra)?
// Uso (na raiz do projeto): node testes/navegador/teste_equivalencia.mjs [pasta de saída]
//   sem argumento: saida/ (Leopoldina); para Muriaé: node testes/navegador/teste_equivalencia.mjs saida/muriae
import { readFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { abrir } from './cdp.mjs';

const RAIZ = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..');
const saida = resolve(RAIZ, process.argv[2] || 'saida');
const ref = join(saida, 'referencias_passo12');
const p = await abrir(join(saida, 'mapa_comunidades.html'));
for (const [nome, arq] of [['avisos', 'avisos.json'], ['janelas', 'janelas.json'], ['tamanhoHoje', 'tamanho_hoje.json'], ['areas', 'areas.json'], ['obra', 'obra.json']])
  await p.avaliar(`window.__${nome} = ${readFileSync(join(ref, arq), 'utf8')}; 0`);

const chaves = await p.avaliar(`(() => {
  const erros = [], R = window.__avisos;
  let n = 0;
  for (const [cod, r] of Object.entries(R.avisos_pt)) {
    const c = D.cenarios[cod]; n++;
    if (montarAviso(c, '12/11', '8h às 14h') !== r.novo) erros.push(['aviso pt', cod]);
    if (c.antigo !== r.antigo) erros.push(['aviso de hoje', cod]);
  }
  for (const [cod, L, dia, mes, ini, fim, texto] of R.avisos_idiomas) {
    const t = comTelefone(montarAviso(D.cenarios[cod], formatarData(dia, mes, L), formatarHorario(ini, fim, L), L), DIST.telefone, L);
    if (t !== texto) erros.push(['aviso ' + L, cod, dia + '/' + mes]);
  }
  for (const [cod, data, dur, sug, notaPadrao] of window.__janelas) {
    const [a, m, d] = data.split('-'), tipo = tipoDia(a, m, d), cont = contagemAtiv(D.cenarios[cod]);
    const s = sugerirJanelas(cont, tipo, dur).map(j => [j.inicio, j.nota, j.explicacao]);
    if (JSON.stringify(s) !== JSON.stringify(sug) || notaDano(cont, tipo, 8 * 60, dur) !== notaPadrao) erros.push(['janela', cod, data, dur]);
  }
  // tamanho do aviso de hoje pelos códigos de local (como no modo área), nas UCs dos transformadores da chave
  const porTrafo = new Map();
  D.ucs.forEach((u, i) => { if (!porTrafo.has(u[2])) porTrafo.set(u[2], []); porTrafo.get(u[2]).push(i); });
  for (const [cod, dia, mes, ini, fim, ...esperado] of window.__tamanhoHoje) {
    const c = D.cenarios[cod], idx = c.trafos.flatMap(t => porTrafo.get(t) || []);
    if (idx.length !== c.n) { erros.push(['UCs da chave', cod, idx.length, c.n]); continue; }
    const t = tamanhoAvisoHoje(new Set(idx.map(i => D.ucs[i][13]).filter(l => l >= 0)), formatarData(dia, mes, 'pt-BR'), formatarHorario(ini, fim, 'pt-BR'));
    if (JSON.stringify([t.locais, t.palavras, t.s]) !== JSON.stringify(esperado)) erros.push(['tamanho do aviso de hoje', cod, dia + '/' + mes, [t.locais, t.palavras, t.s], esperado]);
  }
  return { chaves: n, avisosIdiomas: R.avisos_idiomas.length, janelas: window.__janelas.length, tamanhoHoje: window.__tamanhoHoje.length, erros: erros.length, exemplos: erros.slice(0, 8) };
})()`);
console.log('Por chave:', JSON.stringify(chaves));

const areas = await p.avaliar(`(async () => {
  const erros = [], cont = {}, J = x => JSON.stringify(x);
  let comparacoes = 0;
  for (const a of window.__areas.areas) {
    const e = a.esperado, r = analisarArea(a.poligonos), err = (o, x, y) => erros.push([a.id, o, J(x).slice(0, 160), J(y).slice(0, 160)]);
    cont[r.situacao] = (cont[r.situacao] || 0) + 1;
    const cmp = (o, x, y) => { comparacoes++; if (J(x) !== J(y)) err(o, x, y); };
    cmp('situação', r.situacao, e.situacao);
    cmp('UCs dentro', r.ucs, e.ucs);
    cmp('resumo', { poligonos: a.poligonos.length, vertices: nVertices(a.poligonos), sha256: await sha256hex(formaCanonica(a.poligonos)) }, e.resumo);
    if (e.situacao !== 'ok' || r.situacao !== 'ok') continue;
    const c = cenarioDaArea(r.ucs);
    cmp('comunidades e classificação', c.com.map(x => [x[0], x[1], x[2], x[3], x[5], x[6]]), e.com);
    cmp('aviso pt-BR', montarAviso(c, '12/11', '8h às 14h'), e.aviso);
    for (const [, L, dia, mes, ini, fim, texto] of e.avisos_idiomas)
      cmp('aviso ' + L, comTelefone(montarAviso(c, formatarData(dia, mes, L), formatarHorario(ini, fim, L), L), DIST.telefone, L), texto);
    cmp('atividades (cargas sensíveis)', c.ativ, e.ativ);
    cmp('alimentadores', c.alims, e.alimentadores);
    for (const [, dia, mes, ini, fim, ...esperado] of e.hoje) {
      const t = tamanhoAvisoHoje(c.locaisHoje, formatarData(dia, mes, 'pt-BR'), formatarHorario(ini, fim, 'pt-BR'));
      cmp('tamanho do aviso de hoje ' + dia + '/' + mes, [t.locais, t.palavras, t.s], esperado);
    }
    for (const [, data, dur, sug, notaPadrao] of e.janelas) {
      const [y, m, d] = data.split('-'), tipo = tipoDia(y, m, d), ct = contagemAtiv(c);
      cmp('janela ' + data + ' ' + dur, [sugerirJanelas(ct, tipo, dur).map(j => [j.inicio, j.nota, j.explicacao]), notaDano(ct, tipo, 8 * 60, dur)], [sug, notaPadrao]);
    }
  }
  return { areas: window.__areas.areas.length, situacoes: cont, comparacoes, erros: erros.length, exemplos: erros.slice(0, 8) };
})()`);
console.log('Por área:', JSON.stringify(areas));
const obra = await p.avaliar(`(() => {
  const erros = [], cont = {};
  for (const { lat, lon, esperado } of window.__obra.pontos) {
    const r = analisarPonto(lat, lon);
    cont[r.situacao] = (cont[r.situacao] || 0) + 1;
    if (JSON.stringify(r) !== JSON.stringify(esperado)) erros.push([lat, lon, JSON.stringify(r).slice(0, 160), JSON.stringify(esperado).slice(0, 160)]);
  }
  return { pontos: window.__obra.pontos.length, situacoes: cont, erros: erros.length, exemplos: erros.slice(0, 5) };
})()`);
console.log('Ponto da obra:', JSON.stringify(obra));
console.log('Exceções na página:', JSON.stringify(p.excecoes), '| CSP:', JSON.stringify(await p.avaliar('window.__csp')));
await p.fechar();
process.exit(chaves.erros || areas.erros || obra.erros || p.excecoes.length ? 1 : 0);
