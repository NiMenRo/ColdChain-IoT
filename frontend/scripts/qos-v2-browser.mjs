// Browser-level fixture check. Starts only a strict-port Vite server and a new
// isolated Chrome profile; all API calls are intercepted in the page.
import { createServer } from 'vite';
import { spawn } from 'node:child_process';
import { mkdtemp, writeFile } from 'node:fs/promises';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import assert from 'node:assert/strict';

process.env.VITE_API_BASE_URL = 'http://127.0.0.1:19999';
const root = process.cwd();
const temp = join(tmpdir(), 'opencode');
const profile = await mkdtemp(join(temp, 'qos-browser-'));
const server = await createServer({ root, server: { host: '127.0.0.1', port: 5173, strictPort: true } });
let chrome;
let ws;
try {
  await server.listen();
  const binary = process.env.B4_CHROME || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe';
  chrome = spawn(binary, [
    '--headless=new', '--disable-gpu', '--disable-background-networking', '--disable-sync',
    '--no-first-run', '--no-default-browser-check', '--remote-debugging-port=0',
    '--remote-allow-origins=*', `--user-data-dir=${profile}`, 'about:blank',
  ], { stdio: ['ignore', 'ignore', 'pipe'] });
  const browserUrl = await new Promise((resolve, reject) => {
    const timeout = setTimeout(() => reject(new Error('Chrome did not start')), 15000);
    let text = '';
    chrome.stderr.on('data', chunk => {
      text += chunk.toString();
      const match = text.match(/DevTools listening on (ws:\/\/[^\s]+)/);
      if (match) { clearTimeout(timeout); resolve(match[1]); }
    });
    chrome.once('error', reject);
    chrome.once('exit', code => reject(new Error(`Chrome exited: ${code}`)));
  });
  const port = new URL(browserUrl).port;
  const target = await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: 'PUT' }).then(r => r.json());
  ws = new WebSocket(target.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => { ws.onopen = resolve; ws.onerror = reject; });
  let nextId = 0;
  const pending = new Map();
  const exceptions = [];
  ws.onmessage = event => {
    const message = JSON.parse(event.data);
    if (message.method === 'Runtime.exceptionThrown') exceptions.push(message.params.exceptionDetails.text);
    if (!message.id) return;
    const pair = pending.get(message.id);
    if (!pair) return;
    pending.delete(message.id);
    if (message.error) pair.reject(new Error(message.error.message));
    else pair.resolve(message.result);
  };
  const send = (method, params = {}) => new Promise((resolve, reject) => {
    const id = ++nextId;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });
  const evalJs = async expression => {
    const response = await send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    if (response.exceptionDetails) throw new Error(response.exceptionDetails.text);
    return response.result.value;
  };
  await send('Page.enable');
  await send('Runtime.enable');
  await send('Emulation.setDeviceMetricsOverride', { width: 1365, height: 900, deviceScaleFactor: 1, mobile: false });
  const fixture = `(() => {
    const user = {id:'fixture-user',name:'Auditor fixture',email:'fixture@example.invalid',role:'admin',is_active:true};
    const stamp = '2026-11-19T12:00:00Z';
    const device = {id:'fixture-device',code:'CAVA-001',name:'Cava fixture',location:'Laboratorio',device_type:'cold_room',status:'active',registration_date:stamp};
    const row = (sensor, value) => ({id:sensor,device_id:device.id,temperature:sensor==='temperature'?value:null,humidity:sensor==='humidity'?value:null,energy:sensor==='energy'?value:null,timestamp:sensor==='humidity'?'2026-11-19T11:59:00Z':sensor==='energy'?'2026-11-19T11:58:00Z':stamp,run_id:null,processing_version:2,sensor_name:sensor});
    const list = results => ({total:results.length,page:1,per_page:100,count:results.length,results});
    const summary = {total_devices:1,total_readings:3,total_classifications:3,total_qos_metrics:1,total_alerts:0,total_predictions:0,alerts_by_type:{},readings_by_device:{},traffic_by_priority:{high:1,medium:1,low:1},qos_by_queue:{},energy_by_state:{on:1}};
    const dispatch = {admitted:5,rejected:2,completed:2,failed:0,cancelled:0,pending:3,in_flight:0,capacity:9,closed:false,draining:true,draining_run_id:'fixture-run',without_qos_pending:0,queues:{high:1,medium:1,low:1},pending_sample:{high:[{work_id:'one',source_message_id:'msg',device_code:'CAVA-001',sensor_name:'temperature',sequence:3,scenario:'WITH_QOS',priority:'high',run_id:'fixture-run',admitted_at:stamp}]}};
    const qosRow = {id:'qos-fixture',classification_id:'tc',latency:null,jitter:null,packet_loss:null,pdr:null,throughput:null,processing_version:2,queue_wait_ms:12.5,service_time_ms:null,timestamp:stamp};
    window.__b4 = {runtime:'running'};
    localStorage.setItem('coldchain_token','fixture-only');
    localStorage.setItem('coldchain_session',JSON.stringify(user));
    const nativeFetch = window.fetch.bind(window);
    window.fetch = async (input, init) => {
      const url = new URL(typeof input === 'string' ? input : input.url, location.href);
      if (url.origin === location.origin) return nativeFetch(input, init);
      if (url.origin !== 'http://127.0.0.1:19999') throw new Error('External request blocked in fixture');
      const path = url.pathname;
      let body;
      if (path === '/auth/me') body = user;
      else if (path === '/devices') body = list([device]);
      else if (path === '/devices/fixture-device') body = {device,sensors:['temperature','humidity','energy']};
      else if (path.endsWith('/latest-values')) body = {temperature:row('temperature',3.5),humidity:row('humidity',82),energy:row('energy','on')};
      else if (path.endsWith('/history')) body = {device,...list([row('temperature',3.5),row('humidity',82),row('energy','on')])};
      else if (path === '/history/summary') body = summary;
      else if (path === '/qos/runtime') {
        if (window.__b4.runtime === 'stopped') return new Response(JSON.stringify({detail:'not running'}),{status:409,headers:{'Content-Type':'application/json'}});
        body = {dispatch,transport:{pending:0,capacity:10,rejected:1},config:{class_quotas:{high:4,medium:2,low:1},timeouts:{drain_s:30}}};
      }
      else if (path === '/qos/queues') body = {count:0,queues:{high:[],medium:[],low:[]}};
      else if (path === '/qos/metrics') body = {count:0,summary:{latency:0,jitter:0,packet_loss:0,pdr:0,throughput:0},by_priority:{}};
      else if (path === '/history/qos') body = list([qosRow]);
      else if (path.endsWith('/trends')) body = [];
      else body = list([]);
      return new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}});
    };
  })();`;
  await send('Page.addScriptToEvaluateOnNewDocument', { source: fixture });
  const waitFor = async text => {
    const expression = `new Promise((resolve,reject)=>{const end=Date.now()+12000;const check=()=>{if(document.body?.innerText.includes(${JSON.stringify(text)}))resolve(true);else if(Date.now()>end)reject(new Error('Missing: '+${JSON.stringify(text)}));else setTimeout(check,50)};check()})`;
    assert.equal(await evalJs(expression), true);
  };
  const navigate = async route => {
    const response = await send('Page.navigate', { url: `http://127.0.0.1:5173${route}` });
    if (response.errorText) throw new Error(response.errorText);
  };
  const screenshot = async name => {
    const { data } = await send('Page.captureScreenshot', { format: 'png' });
    const file = join(temp, `qos-browser-${name}.png`);
    await writeFile(file, Buffer.from(data, 'base64'));
    console.log(`screenshot=${file}`);
  };

  await navigate('/app/traffic');
  await waitFor('CAVA-001/temperature');
  assert.equal(await evalJs(`document.body.innerText.includes('4 : 2 : 1') && document.body.innerText.includes('Activo') && document.body.innerText.includes('Colas de demostración')`), true);
  await evalJs(`new Promise(resolve=>{const e=[...document.querySelectorAll('.cc-card-header')].find(e=>e.textContent==='Despacho productivo — runtime'); if(e)window.scrollTo({top:window.scrollY+e.getBoundingClientRect().top-30,behavior:'instant'});requestAnimationFrame(()=>requestAnimationFrame(resolve))})`);
  await screenshot('traffic');
  await evalJs(`window.__b4.runtime='stopped'; document.dispatchEvent(new Event('visibilitychange'))`);
  await waitFor('El despacho productivo no está activo');
  await evalJs(`window.__b4.runtime='running'; [...document.querySelectorAll('button')].find(b=>b.textContent==='Reintentar' && b.parentElement?.innerText.includes('no está activo'))?.click()`);
  await waitFor('CAVA-001/temperature');
  console.log('traffic: runtime, drenaje, parada y reintento verificados');

  await navigate('/app/sensors');
  await waitFor('Cava fixture');
  await waitFor('3.5 °C');
  assert.equal(await evalJs(`document.body.innerText.includes('82 %') && document.body.innerText.includes('ON')`), true);
  await evalJs(`[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Ver historial'))?.click()`);
  await waitFor('Ocultar historial');
  await screenshot('sensors');
  console.log('sensors: últimos valores independientes e historial expandido verificados');

  await navigate('/app/qos');
  await waitFor('Registros QoS recientes');
  await waitFor('12,5 ms');
  assert.equal(await evalJs(`!document.body.innerText.includes('NaN')`), true);
  await evalJs(`new Promise(resolve=>{[...document.querySelectorAll('.cc-card-header')].find(e=>e.textContent.includes('Registros QoS recientes'))?.scrollIntoView({block:'start'});requestAnimationFrame(()=>requestAnimationFrame(resolve))})`);
  await screenshot('qos');
  console.log('qos: métricas nulas y espera medida verificadas');
  assert.deepEqual(exceptions, []);
} finally {
  if (ws) ws.close();
  if (chrome && chrome.exitCode === null) chrome.kill();
  await server.close();
}
