// Abre o mapa no Edge (ou Chrome) sem janela e expõe um cliente mínimo do DevTools Protocol.
// Sem dependências: só o Node 22+ (fetch e WebSocket nativos).
import { spawn } from 'node:child_process';
import { existsSync, mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { pathToFileURL } from 'node:url';

// Navegador: FAROL_NAVEGADOR, se definido; senão o primeiro Edge ou Chrome encontrado
const CANDIDATOS = [
  process.env.FAROL_NAVEGADOR,
  'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Microsoft/Edge/Application/msedge.exe',
  'C:/Program Files/Google/Chrome/Application/chrome.exe',
  'C:/Program Files (x86)/Google/Chrome/Application/chrome.exe',
].filter(Boolean);
const NAVEGADOR = CANDIDATOS.find(c => existsSync(c));
const espera = ms => new Promise(r => setTimeout(r, ms));

// antesDeNavegar(pagina): para preparar a página (emulação, scripts de teste) antes de carregar o arquivo
export async function abrir(html, { largura = 1440, altura = 900, antesDeNavegar = null } = {}) {
  if (!NAVEGADOR) throw new Error('Edge ou Chrome não encontrado. Defina FAROL_NAVEGADOR com o caminho do msedge.exe ou chrome.exe.');
  const url = /^https?:\/\//.test(html) ? html : null;  // a tela do app vem do servidor local da API
  if (!url && !existsSync(html)) throw new Error(`Mapa não encontrado: ${html}. Rode o pipeline antes (py -m uv run comunidades --so-algoritmo).`);
  const porta = 9300 + Math.floor(Math.random() * 500);
  const perfil = mkdtempSync(join(tmpdir(), 'farol-navegador-'));  // perfil descartável, sem tocar no do usuário
  const proc = spawn(NAVEGADOR, ['--headless=new', `--remote-debugging-port=${porta}`, `--user-data-dir=${perfil}`,
    '--no-first-run', '--disable-extensions', `--window-size=${largura},${altura}`, 'about:blank'], { stdio: 'ignore' });
  let alvo;
  for (let i = 0; i < 100 && !alvo; i++) {
    await espera(200);
    try { alvo = (await (await fetch(`http://127.0.0.1:${porta}/json/list`)).json()).find(t => t.type === 'page'); } catch (e) { /* ainda abrindo */ }
  }
  const versao = await (await fetch(`http://127.0.0.1:${porta}/json/version`)).json();
  const pagina = await conectar(alvo.webSocketDebuggerUrl);
  const navegador = await conectar(versao.webSocketDebuggerUrl);
  pagina.logs = []; pagina.excecoes = [];
  pagina.on('Runtime.exceptionThrown', p => pagina.excecoes.push(p.exceptionDetails.exception?.description || p.exceptionDetails.text));
  pagina.on('Log.entryAdded', p => pagina.logs.push(`${p.entry.level} ${p.entry.source}: ${p.entry.text}`));
  pagina.on('Runtime.consoleAPICalled', p => pagina.logs.push(`console.${p.type}: ${p.args.map(a => a.value ?? a.description).join(' ')}`));
  await pagina.send('Runtime.enable'); await pagina.send('Log.enable'); await pagina.send('Page.enable');
  await pagina.send('Emulation.setDeviceMetricsOverride', { width: largura, height: altura, deviceScaleFactor: 1, mobile: false });
  // Violações de CSP também chegam como evento no documento
  await pagina.send('Page.addScriptToEvaluateOnNewDocument', { source:
    "window.__csp = []; document.addEventListener('securitypolicyviolation', e => window.__csp.push(e.violatedDirective + ' ' + e.blockedURI));" });
  if (antesDeNavegar) await antesDeNavegar(pagina);
  const carregou = pagina.uma('Page.loadEventFired');
  await pagina.send('Page.navigate', { url: url || pathToFileURL(html).href });
  await carregou;
  // O mapa termina de montar depois do "load" (por etapas, com a tela de abertura): espera o estado "pronto".
  // Páginas sem esse estado (a de entrada) seguem direto.
  pagina.estadoFinal = await pagina.avaliar(`new Promise(ok => { const t0 = Date.now(), ver = () => {
    const e = document.documentElement.dataset.farol;
    if (!e || e === 'pronto' || e === 'erro' || Date.now() - t0 > 60000) ok(e || 'sem estado'); else setTimeout(ver, 50); }; ver(); })`);
  if (pagina.estadoFinal !== 'pronto' && pagina.estadoFinal !== 'sem estado') throw new Error(`O mapa não ficou pronto: ${pagina.estadoFinal} ${JSON.stringify(pagina.excecoes)}`);
  await pagina.avaliar('new Promise(r => setTimeout(r, 300))');
  pagina.fechar = async () => { try { await navegador.send('Browser.close'); } catch (e) { proc.kill(); } };
  pagina.navegador = navegador;
  return pagina;
}

async function conectar(url) {
  const ws = new WebSocket(url);
  await new Promise((ok, erro) => { ws.onopen = ok; ws.onerror = erro; });
  let id = 0;
  const pendentes = new Map(), ouvintes = new Map();
  ws.onmessage = m => {
    const d = JSON.parse(m.data);
    if (d.id && pendentes.has(d.id)) { const [ok, erro] = pendentes.get(d.id); pendentes.delete(d.id); d.error ? erro(new Error(JSON.stringify(d.error))) : ok(d.result); }
    else if (d.method) (ouvintes.get(d.method) || []).forEach(f => f(d.params));
  };
  const c = {
    send: (method, params = {}) => new Promise((ok, erro) => { const i = ++id; pendentes.set(i, [ok, erro]); ws.send(JSON.stringify({ id: i, method, params })); }),
    on: (ev, f) => { if (!ouvintes.has(ev)) ouvintes.set(ev, []); ouvintes.get(ev).push(f); },
    uma: ev => new Promise(ok => c.on(ev, ok)),
    async avaliar(expr) {
      const r = await c.send('Runtime.evaluate', { expression: expr, awaitPromise: true, returnByValue: true });
      if (r.exceptionDetails) throw new Error(r.exceptionDetails.exception?.description || r.exceptionDetails.text);
      return r.result.value;
    },
  };
  return c;
}
