// Fixtures sin servidor, navegador ni dependencias nuevas.
// Ejecutar desde frontend: node --test scripts/qos-v2.test.cjs
const assert = require('node:assert/strict');
const { test } = require('node:test');
const fs = require('node:fs');
const ts = require('typescript');
const React = require('react');
const { renderToStaticMarkup } = require('react-dom/server');

// Carga TS/TSX con el compilador ya declarado por el proyecto. Solo en este
// proceso de pruebas; no cambia el cliente ni la configuración de Vite.
for (const extension of ['.ts', '.tsx']) {
  require.extensions[extension] = (module, filename) => {
    const source = fs.readFileSync(filename, 'utf8')
      .replaceAll('import.meta.env', '({ VITE_API_BASE_URL: "http://fixture.invalid" })');
    module._compile(ts.transpileModule(source, {
      compilerOptions: {
        module: ts.ModuleKind.CommonJS,
        target: ts.ScriptTarget.ES2020,
        jsx: ts.JsxEmit.ReactJSX,
        esModuleInterop: true,
      },
      fileName: filename,
    }).outputText, filename);
  };
}

const agg = require('../src/app/lib/experimentAggregations.ts');
const types = require('../src/app/types/experiments.ts');
const { deviceLatestSnapshot } = require('../src/app/lib/deviceLatestValues.ts');
const charts = require('../src/app/components/experiments/ExperimentCharts.tsx');
const metric = (run, type, value, minute = 0) => ({
  id: `${run}-${type}-${minute}`, run_id: run, metric_type: type, value,
  timestamp: new Date(Date.UTC(2026, 0, 1, 0, minute)).toISOString(),
});
const run = id => ({ id, started_at: '2026-01-01T00:00:00Z' });

function elements(element) {
  if (!element || typeof element !== 'object') return [];
  return [element, ...React.Children.toArray(element.props?.children).flatMap(elements)];
}

test('los cinco tipos v2 tienen etiquetas, unidades y grupos correctos', () => {
  for (const type of ['readings_admitted', 'readings_rejected', 'readings_failed']) {
    assert.ok(types.COUNTER_METRICS.includes(type));
    assert.ok(types.METRIC_LABELS[type]);
    assert.ok(types.METRIC_UNITS[type]);
  }
  for (const type of ['queue_wait_ms', 'service_time_ms']) {
    assert.ok(types.LATENCY_METRICS.includes(type));
    assert.equal(types.METRIC_UNITS[type], 'ms');
  }
});

test('sin muestras no equivale a una medición cero', () => {
  assert.equal(agg.sumMetricOrNull([], 'readings_failed'), null);
  assert.equal(agg.sumMetricOrNull([metric('a', 'readings_failed', 0)], 'readings_failed'), 0);
  assert.equal(agg.avgMetric([], 'queue_wait_ms'), null);
  assert.equal(agg.maxMetric([], 'service_time_ms'), null);
  assert.equal(agg.avgMetric([metric('a', 'queue_wait_ms', 2), metric('a', 'queue_wait_ms', 4)], 'queue_wait_ms'), 3);
  assert.equal(agg.delta(null, 0), null);
});

test('comparación sin muestra renderiza —, no un cero ficticio', () => {
  const html = renderToStaticMarkup(React.createElement(charts.MetricComparisonCard, {
    label: 'Espera', unit: 'ms', withQosValue: null, withoutQosValue: 0,
  }));
  assert.ok(html.includes('—'));
  assert.ok(html.includes('>0 '));
});

test('backlog filtra cada ejecución sin inventar muestras de la otra', () => {
  const tree = charts.BacklogChart({
    withQosRun: run('a'), withoutQosRun: run('b'),
    allMetrics: [metric('a', 'backlog', 7), metric('b', 'backlog', 2, 1), metric('other', 'backlog', 999)],
  });
  const nodes = elements(tree);
  const data = nodes.find(n => n.props?.data)?.props.data;
  assert.deepEqual(data, [
    { elapsedMin: 0, withQos: 7, withoutQos: null },
    { elapsedMin: 1, withQos: null, withoutQos: 2 },
  ]);
  assert.equal(nodes.filter(n => 'connectNulls' in (n.props ?? {})).every(n => n.props.connectNulls), true);
});

test('series conservan muestras del mismo minuto y timestamps repetidos', () => {
  const samples = [metric('a', 'queue_wait_ms', 10), metric('a', 'queue_wait_ms', 20),
    { ...metric('a', 'queue_wait_ms', 30), timestamp: '2026-01-01T00:00:15Z' },
    { ...metric('a', 'queue_wait_ms', 40), timestamp: '2026-01-01T00:00:20Z' }];
  const series = agg.seriesByElapsed(samples, 'queue_wait_ms', run('a').started_at);
  assert.deepEqual(series.map(p => p.value), [10, 20, 30, 40]);
  assert.equal(series[2].elapsedMin, 0.25);
  const merged = agg.mergeLineSeries(series, [{ elapsedMin: 0, value: 99 }]);
  assert.deepEqual(merged.map(p => p.withQos), [10, 20, 30, 40]);
  assert.deepEqual(merged.map(p => p.withoutQos), [99, null, null, null]);
  assert.deepEqual(agg.mergeLineSeries([], series).map(p => p.withoutQos), [10, 20, 30, 40]);
  assert.deepEqual(agg.mergeLineSeries([], []), []);
});

test('comparativas usan eje temporal numérico sin redondear los datos', () => {
  const data = [{ elapsedMin: 0.001, withQos: 3, withoutQos: null },
    { elapsedMin: 0.002, withQos: 4, withoutQos: null }];
  const nodes = elements(charts.LineComparisonChart({ title: 'Espera', data }));
  const axis = nodes.find(n => n.props?.dataKey === 'elapsedMin');
  assert.equal(axis.props.type, 'number');
  assert.deepEqual(nodes.find(n => n.props?.data)?.props.data, data);
});

test('indicadores usan agregados globales, distinguiendo ausencia y cero', () => {
  const { dashboardIndicators } = require('../src/app/lib/dashboardIndicators.ts');
  assert.deepEqual(dashboardIndicators(null), {
    totalDevices: null, activeDevices: null, errorDevices: null, totalAlerts: null, criticalAlerts: null,
  });
  assert.deepEqual(dashboardIndicators({
    total_devices: 107, active_devices: 100, error_devices: 7,
    total_alerts: 12, active_alerts: 11, critical_active_alerts: 8,
  }), { totalDevices: 107, activeDevices: 100, errorDevices: 7, totalAlerts: 11, criticalAlerts: 8 });
  assert.equal(dashboardIndicators({ active_alerts: 0 }).totalAlerts, 0);
  assert.equal(dashboardIndicators({ total_alerts: 100 }).totalAlerts, null);
});

test('barras no fabrican muestras para ejecuciones o tipos ausentes', () => {
  const nodes = elements(charts.CountMetricsBarChart({
    withQosRun: run('a'), withoutQosRun: null, allMetrics: [metric('a', 'readings_admitted', 3)],
  }));
  const data = nodes.find(n => n.props?.data)?.props.data;
  assert.ok(data.every(p => p.withoutQos === null));
  assert.equal(data.find(p => p.metric === types.METRIC_LABELS.readings_admitted).withQos, 3);
  assert.equal(data.find(p => p.metric === types.METRIC_LABELS.readings_failed).withQos, null);
});

test('últimos valores conservan sensores hermanos y sus fechas independientes', () => {
  const values = {
    temperature: { temperature: 4, humidity: null, energy: null, timestamp: '2026-01-01T00:03:00Z' },
    humidity: { temperature: null, humidity: 80, energy: null, timestamp: '2026-01-01T00:02:00Z' },
    energy: { temperature: null, humidity: null, energy: 'on', timestamp: '2026-01-01T00:01:00Z' },
  };
  const snapshot = deviceLatestSnapshot(values);
  assert.equal(snapshot.temperature, 4);
  assert.equal(snapshot.humidity, 80);
  assert.equal(snapshot.energy, 'on');
  assert.equal(snapshot.sensor_timestamps.energy, values.energy.timestamp);
  assert.equal(snapshot.timestamp, values.temperature.timestamp);
  assert.equal(deviceLatestSnapshot({ temperature: null, humidity: null, energy: null }), undefined);
});

test('servicios conservan filtros, paginación y separación del runtime', async () => {
  const originalFetch = global.fetch;
  const requests = [];
  global.fetch = async url => {
    requests.push(new URL(url));
    return { ok: true, status: 200, json: async () => ({ results: [] }) };
  };
  try {
    const api = require('../src/services/api/experiments.ts');
    const history = require('../src/services/api/history.ts');
    const qos = require('../src/services/api/qos.ts');
    await api.apiGetRunMetrics('run a', { metric_type: 'queue_wait_ms', page: 2, per_page: 25 });
    await history.apiGetReadings({ processing_version: 2, page: 3 });
    await history.apiGetDeviceLatestValues('CAVA/1');
    await qos.apiGetQosRuntime();
    const acquisition = require('../src/services/api/acquisition.ts');
    await acquisition.apiGetAcquisitionStatus();
    assert.equal(requests[0].searchParams.get('metric_type'), 'queue_wait_ms');
    assert.equal(requests[0].searchParams.get('page'), '2');
    assert.equal(requests[0].searchParams.get('per_page'), '25');
    assert.equal(requests[1].searchParams.get('processing_version'), '2');
    assert.ok(requests[2].pathname.endsWith('/CAVA%2F1/latest-values'));
    assert.equal(requests[3].pathname, '/qos/runtime');
    assert.equal(requests[4].pathname, '/acquisition/status');
  } finally {
    global.fetch = originalFetch;
  }
});

// Solo los hooks de datos se sustituyen por fixtures. Se renderiza la vista
// real, incluidos sus estados de error/detenido y los indicadores de runtime.
let runtimeFixture;
require('../src/app/hooks/useTrafficData.ts').useTrafficData = () => ({
  rows: [], total: 0, recent: [], status: 'empty', recentStatus: 'empty',
});
require('../src/app/hooks/useHistoricalAnalytics.ts').useHistoricalAnalytics = () => ({
  classSample: [], criticalityBuckets: [], classSampleCount: 0, classStatus: 'empty',
  range: '24h', rangeLabel: 'Últimas 24 horas', readingTrends: [], qosTrends: [],
  alertsPerDay: [], summary: null,
});
require('../src/app/hooks/useLiveQueues.ts').useLiveQueues = () => ({
  status: 'empty', total: 0, queues: [],
});
require('../src/app/contexts/ExperimentContext.tsx').useExperiments = () => ({
  runs: [], metrics: [], runMeta: {}, status: 'empty', fetchMetrics: async () => {},
});
require('../src/app/hooks/useQosRuntime.ts').useQosRuntime = () => runtimeFixture;
const { TrafficView } = require('../src/app/components/views/TrafficView.tsx');
const renderRuntime = fixture => {
  runtimeFixture = { retry() {}, ...fixture };
  return renderToStaticMarkup(React.createElement(TrafficView));
};

test('vista distingue carga, despacho detenido y error de autenticación', () => {
  assert.ok(renderRuntime({ status: 'loading' }).includes('Cargando estado del despacho'));
  assert.ok(renderRuntime({ status: 'stopped' }).includes('no está activo'));
  assert.ok(renderRuntime({ status: 'error', errorMessage: 'No autenticado' }).includes('No autenticado'));
});

test('runtime muestra cuotas efectivas, drenaje, rechazos y fuentes separadas', () => {
  const html = renderRuntime({
    status: 'running',
    runtime: {
      dispatch: { admitted: 9, rejected: 2, completed: 4, failed: 1, pending: 3, in_flight: 1,
        capacity: 7, closed: false, draining: true, draining_run_id: 'run-fixture', without_qos_pending: 1,
        queues: { high: 1, medium: 1, low: 0 },
        pending_sample: { high: [{ device_code: 'CAVA-001', sensor_name: 'temperature', sequence: 3 }] } },
      transport: null, config: { class_quotas: { high: 4, medium: 2, low: 1 }, timeouts: { drain_s: 30 } },
    },
  });
  for (const text of ['4 : 2 : 1', 'Activo', '9 / 2', 'Colas de demostración', 'Despacho productivo', '— / —', 'CAVA-001/temperature']) {
    assert.ok(html.includes(text), text);
  }
});

test('registros v2 NULL y legado sin campos nuevos renderizan sin fallar', () => {
  require('../src/app/hooks/useQosSnapshot.ts').useQosSnapshot = () => ({
    status: 'empty', cells: [], recentStatus: 'success', recent: [
      { id: 'v2', processing_version: 2, latency: null, jitter: null, packet_loss: null,
        throughput: null, pdr: null, queue_wait_ms: 1.25, service_time_ms: 2.5,
        timestamp: '2026-01-01T00:00:00Z' },
      { id: 'legacy', processing_version: 1, latency: 0.1, jitter: 0, packet_loss: 0,
        throughput: 100, pdr: 100, timestamp: '2026-01-01T00:00:00Z' },
    ],
  });
  const { AnalyticsView } = require('../src/app/components/views/AnalyticsView.tsx');
  const html = renderToStaticMarkup(React.createElement(AnalyticsView));
  for (const text of ['Espera cola', 'Atención (ms)', 'legado', '—', '100 ms']) {
    assert.ok(html.includes(text), text);
  }
  assert.ok(!html.includes('NaN'));
});

test('MQTT consulta estado real, refleja desconexión y no conserva verde tras error', async () => {
  const { withHookHarness } = require('./hookHarness.cjs');
  const polling = require('../src/app/hooks/usePolling.ts');
  const api = require('../src/services/api/acquisition.ts');
  const originalPolling = polling.usePolling;
  const originalApi = api.apiGetAcquisitionStatus;
  let tick;
  let response = { connected: true };
  polling.usePolling = (_enabled, _interval, callback) => { tick = callback; };
  api.apiGetAcquisitionStatus = async () => {
    if (response instanceof Error) throw response;
    return response;
  };
  try {
    const { useMqttStatus } = require('../src/app/hooks/useMqttStatus.ts');
    await withHookHarness(async ({ render, settle }) => {
      assert.equal(render(useMqttStatus), 'loading');
      await settle();
      assert.equal(render(useMqttStatus), 'connected');
      for (const [result, expected] of [
        [{ connected: false }, 'disconnected'],
        [new Error('API unavailable'), 'error'],
        [{ connected: null }, 'unknown'],
        [{ connected: true }, 'connected'],
      ]) {
        response = result;
        tick();
        render(useMqttStatus);
        await settle();
        assert.equal(render(useMqttStatus), expected);
      }
    });
  } finally {
    polling.usePolling = originalPolling;
    api.apiGetAcquisitionStatus = originalApi;
  }
});

test('MQTT ignora respuestas viejas y respuestas posteriores al desmontaje', async () => {
  const { withHookHarness } = require('./hookHarness.cjs');
  const polling = require('../src/app/hooks/usePolling.ts');
  const api = require('../src/services/api/acquisition.ts');
  const originalPolling = polling.usePolling;
  const originalApi = api.apiGetAcquisitionStatus;
  const pending = [];
  let tick;
  polling.usePolling = (_enabled, _interval, callback) => { tick = callback; };
  api.apiGetAcquisitionStatus = () => new Promise(resolve => pending.push(resolve));
  try {
    const { useMqttStatus } = require('../src/app/hooks/useMqttStatus.ts');
    await withHookHarness(async ({ render, settle, unmount }) => {
      render(useMqttStatus);
      tick();
      render(useMqttStatus);
      pending[1]({ connected: false });
      await settle();
      assert.equal(render(useMqttStatus), 'disconnected');
      pending[0]({ connected: true });
      await settle();
      assert.equal(render(useMqttStatus), 'disconnected');
      tick();
      render(useMqttStatus);
      unmount();
      pending[2]({ connected: true });
      await settle();
      assert.equal(render(useMqttStatus), 'disconnected');
    });
  } finally {
    polling.usePolling = originalPolling;
    api.apiGetAcquisitionStatus = originalApi;
  }
});

test('dashboard no deriva indicadores de las cinco alertas ni de la primera página', async () => {
  const { withHookHarness } = require('./hookHarness.cjs');
  const polling = require('../src/app/hooks/usePolling.ts');
  const history = require('../src/services/api/history.ts');
  const devices = require('../src/services/api/devices.ts');
  const qos = require('../src/services/api/qos.ts');
  const replacements = [
    [polling, 'usePolling', () => {}],
    [devices, 'apiGetDevices', async () => ({ total: 107, results: [] })],
    [history, 'apiGetHistoryAlerts', async () => ({ total: 12, results: [] })],
    [history, 'apiGetHistorySummary', async () => ({
      total_devices: 107, active_devices: 100, error_devices: 7,
      total_alerts: 12, active_alerts: 11, critical_active_alerts: 8,
    })],
    [history, 'apiGetReadingTrends', async () => []],
    [qos, 'apiGetQosMetrics', async () => ({ count: 0 })],
  ];
  const originals = replacements.map(([obj, key]) => obj[key]);
  replacements.forEach(([obj, key, value]) => { obj[key] = value; });
  try {
    const { useDashboardData } = require('../src/app/hooks/useDashboardData.ts');
    await withHookHarness(async ({ render, settle }) => {
      assert.equal(render(useDashboardData).totalDevices, null);
      await settle();
      const result = render(useDashboardData);
      assert.equal(result.totalDevices, 107);
      assert.equal(result.activeDevices, 100);
      assert.equal(result.errorDevices, 7);
      assert.equal(result.totalAlerts, 11);
      assert.equal(result.criticalAlerts, 8);
      assert.deepEqual(result.recentAlerts, []);
    });
  } finally {
    replacements.forEach(([obj, key], i) => { obj[key] = originals[i]; });
  }
});
