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
  runs: [], analyses: {}, runMeta: {}, status: 'empty', fetchAnalysis: async () => {},
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

test('runtime muestra drenaje y rechazos con fuentes separadas, sin cuotas ni UUID', () => {
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
  for (const text of ['Activo', '9 / 2', 'Colas de demostración', 'Despacho productivo', '— / —', 'CAVA-001/temperature']) {
    assert.ok(html.includes(text), text);
  }
  assert.ok(!html.includes('4 : 2 : 1'));
  assert.ok(!html.includes('run-fixture'));
});

test('Analytics no consulta ni presenta las métricas demostrativas', () => {
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
  const html = renderToStaticMarkup(React.createElement(require('react-router').MemoryRouter, null,
    React.createElement(AnalyticsView)));
  assert.ok(!html.includes('Métricas de demostración'));
  assert.ok(!html.includes('Registros QoS recientes'));
  assert.ok(html.includes('Comparación experimental'));
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

test('alertas pagina y filtra por ejecución, mantiene NULL y totales completos al refrescar', async () => {
  const { withHookHarness } = require('./hookHarness.cjs');
  const polling = require('../src/app/hooks/usePolling.ts');
  const alerts = require('../src/services/api/alerts.ts');
  const history = require('../src/services/api/history.ts');
  const devices = require('../src/services/api/devices.ts');
  const events = require('../src/services/api/events.ts');
  const notifications = require('../src/services/api/notifications.ts');
  const calls = [];
  let tick;
  let active = 71;
  const replacements = [
    [polling, 'usePolling', (_enabled, _ms, callback) => { tick = callback; }],
    [alerts, 'apiGetAlerts', async params => {
      calls.push(params);
      return { total: 81, results: [{
        id: 'alert', device_id: 'device', type: 'TEMPERATURE_EXCEEDED',
        message: 'Temperatura (9.5) fuera de rango (2–8)', criticality: null,
        created_at: '2026-01-01T00:00:00Z', acknowledged: false,
      }] };
    }],
    [history, 'apiGetHistorySummary', async params => {
      assert.deepEqual(params, { run_id: 'fifo-run' });
      return { total_alerts: 81, active_alerts: active, critical_active_alerts: 0,
        alerts_without_criticality: 81 };
    }],
    [devices, 'apiGetDevices', async () => ({ results: [] })],
    [events, 'apiGetEventsSummary', async () => ({})],
    [events, 'apiGetCriticalAlerts', async () => ({ alerts: [] })],
    [events, 'apiGetSessionEvents', async () => ({ events: [] })],
    [notifications, 'apiGetPersistentHistory', async () => ({ notifications: [] })],
  ];
  const originals = replacements.map(([obj, key]) => obj[key]);
  replacements.forEach(([obj, key, value]) => { obj[key] = value; });
  try {
    const { useAlertsData } = require('../src/app/hooks/useAlertsData.ts');
    await withHookHarness(async ({ render, settle }) => {
      const hook = () => useAlertsData({ page: 3, perPage: 20, runId: 'fifo-run' });
      render(hook);
      await settle();
      let result = render(hook);
      assert.deepEqual(calls[0], { page: 3, per_page: 20, type: undefined, run_id: 'fifo-run' });
      assert.equal(result.total, 81);
      assert.equal(result.pageCount, 5);
      assert.equal(result.alerts[0].criticality, null);
      assert.equal(result.historySummary.active_alerts, 71);
      active = 72;
      tick();
      render(hook);
      await settle();
      result = render(hook);
      assert.equal(result.historySummary.active_alerts, 72);
      assert.equal(calls.at(-1).page, 3);
    });
  } finally {
    replacements.forEach(([obj, key], i) => { obj[key] = originals[i]; });
  }
});

test('alertas muestra totales completos, navegación y No aplica para ejecución sin QoS', () => {
  const auth = require('../src/app/hooks/useAuth.ts');
  const experiments = require('../src/app/contexts/ExperimentContext.tsx');
  const alerts = require('../src/app/hooks/useAlertsData.ts');
  let selected = '';
  const originalState = React.useState;
  const replacements = [
    [auth, 'useAuth', () => ({ role: 'admin' })],
    [experiments, 'useExperiments', () => ({
      runs: [{ id: 'fifo-run', scenario: 'WITHOUT_QOS',
        started_at: '2026-01-01T00:00:00Z', config_snapshot: '{"sensor_condition":"altered"}' }],
      runMeta: {},
    })],
    [alerts, 'useAlertsData', options => {
      assert.equal(options.runId, selected || null);
      return {
        isLoading: false, summaryStatus: 'success', alertsStatus: 'success',
        historySummary: { total_alerts: 81, active_alerts: 71,
          critical_active_alerts: 0, alerts_without_criticality: 81,
          alerts_by_type: { TEMPERATURE_EXCEEDED: 81 } },
        alerts: [{ id: 'a', deviceId: 'device', deviceName: 'Cámara',
          label: 'Temperatura Excedida', message: 'Valor (9.5) fuera de rango (2–8)',
          criticality: null, timestamp: '2026-01-01T00:00:00Z', acknowledged: false }],
        notifications: [], criticalSessionAlerts: [], sessionEvents: [],
        filter: 'all', page: 2, perPage: 20, total: 81, pageCount: 5,
      };
    }],
  ];
  const originals = replacements.map(([obj, key]) => obj[key]);
  replacements.forEach(([obj, key, value]) => { obj[key] = value; });
  // Inject the selected-run state while using the actual server renderer.
  React.useState = initial => originalState(initial === '' ? selected : initial);
  try {
    const { AlertsView } = require('../src/app/components/views/AlertsView.tsx');
    const render = () => renderToStaticMarkup(React.createElement(
      require('react-router').MemoryRouter, null, React.createElement(AlertsView)));
    const global = render();
    for (const text of ['Todas las ejecuciones', '>71<', '>10<',
      '21–40 de 81 alertas', 'Página 2 de 5',
      'Sin priorización · criticidad no calculada', 'Valor (9.5)']) {
      assert.ok(global.includes(text), text);
    }
    assert.ok(!global.includes('No aplica'));
    selected = 'fifo-run';
    const scoped = render();
    assert.ok(scoped.includes('No aplica'));
    assert.ok(scoped.includes('Esta ejecución no calcula la criticidad QoS.'));
    assert.ok(!scoped.includes('Criticidad · 0'));
    assert.ok(!scoped.includes('Criticidad · 5'));
  } finally {
    React.useState = originalState;
    replacements.forEach(([obj, key], i) => { obj[key] = originals[i]; });
  }
});

const evidenceFixture = (status = 'final') => ({
  run_id: 'run-a', status, reasons: [], scope: 'managed_local_producer',
  counts: { sent_unique: 2, received_unique: 1, duplicate_receptions: 0, database_readings_persisted: 3 },
  pending_messages: 1, pdr_percent: 50, loss_percent: 50, received_payload_bytes: 521,
  payload_goodput_bytes_per_second: 52.1,
  window: { started_at: '2026-01-01T00:00:00Z', emission_ended_at: '2026-01-01T00:00:05Z',
    reception_deadline: '2026-01-01T00:00:10Z', observed_until: '2026-01-01T00:00:11Z',
    grace_seconds: 5, rate_interval_seconds: 10, closed: true },
  configuration: { wfq_policy: 'criticality_bands_v1', class_quotas: {high: 4, medium: 2, low: 1},
    wfq_band_weights: {H7: 1, H8: 2, H9: 3} },
  device_to_persist_ms: {count: 1, mean: 20, p95: 20},
  device_to_alert_persist_ms: {count: 0, mean: null, p95: null},
  by_priority: {high: {persist: {count: 1, mean: 20, p95: 20}, alert: {count: 0, mean: null, p95: null}}},
  clock_unmeasurable: 0,
});

test('medición real presenta resultados sin UUID, política, pesos ni protocolos', () => {
  const { EvidenceContent } = require('../src/app/components/experiments/RunEvidencePanel.tsx');
  const html = renderToStaticMarkup(React.createElement(EvidenceContent, {data: evidenceFixture()}));
  for (const text of ['Resultados finales', 'Mensajes recibidos', 'Duplicados recibidos',
    'No recibidos en la ventana', '95 %', '521 B', 'No disponible']) assert.ok(html.includes(text), text);
  for (const text of ['run-a', 'criticality_bands_v1', '4:2:1', '1:2:3', 'MQTT/TCP/TLS']) {
    assert.ok(!html.includes(text), text);
  }
  assert.ok(!html.includes('NaN'));
});

test('una medición provisional no publica tasas finales aunque lleguen números', () => {
  const { EvidenceContent } = require('../src/app/components/experiments/RunEvidencePanel.tsx');
  const html = renderToStaticMarkup(React.createElement(EvidenceContent, {data: evidenceFixture('provisional')}));
  assert.ok(html.includes('Resultados provisionales'));
  assert.ok(html.includes('No recibidos todavía'));
  assert.ok(!html.includes('50 %'));
  assert.ok(!html.includes('52,1 B/s'));
});

test('cero medido y captura ausente no se confunden en el resumen', () => {
  const { EvidenceContent } = require('../src/app/components/experiments/RunEvidencePanel.tsx');
  const zero = evidenceFixture();
  zero.counts = {sent_unique: 0, received_unique: 0, database_readings_persisted: 0};
  const absent = {...zero, status: 'unavailable', counts: {}, pending_messages: null,
    pdr_percent: null, loss_percent: null, received_payload_bytes: null};
  const zeroHtml = renderToStaticMarkup(React.createElement(EvidenceContent, {data: zero, compact: true}));
  const absentHtml = renderToStaticMarkup(React.createElement(EvidenceContent, {data: absent, compact: true}));
  assert.ok(zeroHtml.includes('>0</div>'));
  assert.ok(absentHtml.includes('No disponible'));
  assert.ok(!absentHtml.includes('>0</div>'));
  assert.ok(!zeroHtml.includes('<table'));
});

test('endpoint de evidencia codifica la ejecución y no recibe rutas de archivos', async () => {
  const previous = global.fetch;
  const requests = [];
  global.fetch = async url => {
    requests.push(new URL(url));
    return {ok: true, status: 200, json: async () => evidenceFixture()};
  };
  try {
    await require('../src/services/api/experiments.ts').apiGetRunEvidence('run/a');
    assert.equal(requests[0].pathname, '/experiment-runs/run%2Fa/evidence');
    assert.equal(requests[0].search, '');
  } finally { global.fetch = previous; }
});

test('evidencia ignora otra ejecución y respuestas posteriores al desmontaje', async () => {
  const { withHookHarness } = require('./hookHarness.cjs');
  const polling = require('../src/app/hooks/usePolling.ts');
  const api = require('../src/services/api/experiments.ts');
  const previousPolling = polling.usePolling, previousApi = api.apiGetRunEvidence;
  const pending = [];
  polling.usePolling = () => {};
  api.apiGetRunEvidence = id => new Promise(resolve => pending.push({id, resolve}));
  try {
    const {useRunEvidence} = require('../src/app/hooks/useRunEvidence.ts');
    await withHookHarness(async ({render, settle, unmount}) => {
      let selected = {id: 'run-a', finished_at: null};
      const hook = () => useRunEvidence(selected);
      render(hook);
      selected = {id: 'run-b', finished_at: null};
      render(hook);
      pending[1].resolve({...evidenceFixture(), run_id: 'run-b'});
      await settle();
      assert.equal(render(hook).data.run_id, 'run-b');
      pending[0].resolve(evidenceFixture());
      await settle();
      assert.equal(render(hook).data.run_id, 'run-b');
      selected = {id: 'run-c', finished_at: null};
      render(hook);
      unmount();
      pending[2].resolve({...evidenceFixture(), run_id: 'run-c'});
      await settle();
      assert.equal(render(hook).data, null);
    });
  } finally {
    polling.usePolling = previousPolling; api.apiGetRunEvidence = previousApi;
  }
});

test('sondeo se detiene con evidencia final y continúa durante cierre provisional', () => {
  const {shouldPollEvidence} = require('../src/app/hooks/useRunEvidence.ts');
  assert.equal(shouldPollEvidence({id: 'a', finished_at: null}, evidenceFixture()), false);
  assert.equal(shouldPollEvidence({id: 'a', finished_at: 'date'}, evidenceFixture('provisional')), true);
  assert.equal(shouldPollEvidence({id: 'a', finished_at: 'date'}, evidenceFixture('incomplete')), false);
  assert.equal(shouldPollEvidence(null, null), false);
});

test('Analytics abre la ejecución enlazada desde Simulación y separa sus escenarios', () => {
  const context = require('../src/app/contexts/ExperimentContext.tsx');
  const hook = require('../src/app/hooks/useRunEvidence.ts');
  const previousContext = context.useExperiments, previousHook = hook.useRunEvidence;
  const calls = [];
  const makeRun = (id, scenario, condition) => ({
    id, scenario, started_at: '2026-01-01T00:00:00Z', finished_at: '2026-01-01T00:01:00Z',
    config_snapshot: JSON.stringify({sensor_condition: condition}),
  });
  context.useExperiments = () => ({
    runs: [makeRun('normal-a', 'WITH_QOS', 'normal'), makeRun('altered-a', 'WITH_QOS', 'altered'),
      makeRun('selected-b', 'WITHOUT_QOS', 'altered')],
    analyses: {}, runMeta: {}, status: 'success', fetchAnalysis: async () => {}, retry: () => {},
  });
  hook.useRunEvidence = run => {
    calls.push(run?.id);
    return {data: run ? {...evidenceFixture(), run_id: run.id} : null, error: null,
      loading: false, retry: () => {}};
  };
  try {
    const {AnalyticsView} = require('../src/app/components/views/AnalyticsView.tsx');
    const html = renderToStaticMarkup(React.createElement(require('react-router').MemoryRouter,
      {initialEntries: ['/app/qos?run_id=selected-b']}, React.createElement(AnalyticsView)));
    assert.deepEqual(calls, ['altered-a', 'selected-b']);
    assert.ok(html.includes('Medición real — Con priorización'));
    assert.ok(html.includes('Medición real — Sin priorización'));
    assert.ok(!html.includes('<code>selected-b</code>'));
    assert.ok(html.includes('Cargando estadísticas'));
  } finally {
    context.useExperiments = previousContext; hook.useRunEvidence = previousHook;
  }
});

test('catálogo carga más de 100 ejecuciones y detecta páginas repetidas', async () => {
  const previous = global.fetch;
  let repeated = false;
  global.fetch = async url => {
    const page = Number(new URL(url).searchParams.get('page'));
    const start = repeated || page === 1 ? 0 : 100;
    const count = repeated || page === 1 ? 100 : 25;
    return {ok: true, status: 200, json: async () => ({
      total: 125, results: Array.from({length: count}, (_, i) => ({id: `run-${start + i}`})),
    })};
  };
  try {
    const {loadExperimentRuns, apiGetRunAnalysis} = require('../src/services/api/experiments.ts');
    assert.equal((await loadExperimentRuns()).length, 125);
    repeated = true;
    await assert.rejects(loadExperimentRuns(), /completar la lista/);
    global.fetch = async url => {
      assert.equal(new URL(url).pathname, '/experiment-runs/run%2Fa/analysis');
      return {ok: true, status: 200, json: async () => ({total_samples: 12001})};
    };
    assert.equal((await apiGetRunAnalysis('run/a')).total_samples, 12001);
    global.fetch = async url => {
      assert.equal(new URL(url).searchParams.get('bucket_seconds'), '0.5');
      return {ok: true, status: 200, json: async () => ({bucket_seconds: 0.5})};
    };
    assert.equal((await apiGetRunAnalysis('run/a', 0.5)).bucket_seconds, 0.5);
  } finally {global.fetch = previous;}
});

test('condiciones desconocidas no se mezclan y se prefiere una pareja completa', () => {
  const {runCondition, suggestedCondition} = require('../src/app/lib/runSelection.ts');
  const runs = [
    {id: 'unknown', started_at: '2026-01-03', scenario: 'WITH_QOS', finished_at: 'done'},
    {id: 'b', started_at: '2026-01-02', scenario: 'WITHOUT_QOS', finished_at: 'done',
      config_snapshot: '{"sensor_condition":"altered"}'},
    {id: 'a', started_at: '2026-01-01', scenario: 'WITH_QOS', finished_at: 'done',
      config_snapshot: '{"sensor_condition":"altered"}'},
  ];
  assert.equal(runCondition(runs[0], {}), 'unregistered');
  assert.equal(suggestedCondition(runs, {}), 'altered');
  assert.equal(runCondition({...runs[0], config_snapshot: '{broken'}, {}), 'unregistered');
  assert.equal(suggestedCondition([runs[0]], {}), 'normal');
});

test('p95 usa un límite comprensible y tablas separan columnas con ayudas nativas', () => {
  const {EvidenceContent} = require('../src/app/components/experiments/RunEvidencePanel.tsx');
  const html = renderToStaticMarkup(React.createElement(EvidenceContent, {data: evidenceFixture()}));
  for (const text of ['El 95 % tardó como máximo', 'table-bordered', 'table-light', 'scope="col"',
    '<details', '<summary', 'No es un porcentaje de éxito', 'desde el envío hasta guardar la lectura']) {
    assert.ok(html.includes(text), text);
  }
  const {AnalysisComparison} = require('../src/app/components/experiments/AnalysisComparison.tsx');
  const report = {metrics: {}, series: {}, bucket_seconds: 1};
  const comparison = renderToStaticMarkup(React.createElement(AnalysisComparison, {withQos: report, withoutQos: report}));
  assert.equal((comparison.match(/<table/g) ?? []).length, 4);
  assert.equal((comparison.match(/table-bordered/g) ?? []).length, 4);
  assert.ok(comparison.includes('Promedio'));
  assert.ok(comparison.includes('Máximo'));
  for (const text of ['espera anterior', 'transporte desde el dispositivo', 'entrega de correo']) {
    assert.ok(comparison.includes(text), text);
  }
});

test('gráficas alinean intervalos y conservan metadatos sin crear ceros', () => {
  const {comparisonInterval, comparisonSeries} = require('../src/app/lib/analysisSeries.ts');
  const makeRun = seconds => ({id: String(seconds), started_at: '2026-01-01T00:00:00Z',
    finished_at: new Date(Date.parse('2026-01-01T00:00:00Z') + seconds * 1000).toISOString()});
  assert.equal(comparisonInterval([makeRun(60), makeRun(120)]), 1);
  assert.equal(comparisonInterval([null, makeRun(0)]), 0.1);
  const point = (start, value) => ({start_seconds: start, end_seconds: start + 1, elapsedMin: (start + .5) / 60, value, max: 900, count: 3});
  const merged = comparisonSeries([point(0, 300), point(2, 0)], [point(0, 12)]);
  assert.equal(merged.length, 2);
  assert.equal(merged[0].withPoint.max, 900);
  assert.equal(merged[0].withoutPoint.value, 12);
  assert.equal(merged[1].withPoint.value, 0);
  assert.equal(merged[1].withoutPoint, undefined);
  const {IntervalTooltip} = require('../src/app/components/experiments/AnalysisLineChart.tsx');
  const html = renderToStaticMarkup(React.createElement(IntervalTooltip, {active: true, payload: [{payload: merged[0]}], unit: 'ms'}));
  for (const text of ['Desde ', 'hasta ', 'promedio ', 'máximo ', '900', '3', 'mediciones', 'ms']) {
    assert.ok(html.includes(text), text);
  }
});

test('gráfica densa oculta círculos, permite máximos y no anima ni suaviza datos', async () => {
  const {withHookHarness} = require('./hookHarness.cjs');
  const {AnalysisLineChart} = require('../src/app/components/experiments/AnalysisLineChart.tsx');
  const points = Array.from({length: 120}, (_, i) => ({
    elapsedMin: (i + .5) / 60, start_seconds: i, end_seconds: i + 1,
    value: 2, max: 900, count: 3,
  }));
  await withHookHarness(async ({render}) => {
    const chart = () => AnalysisLineChart({title: 'Espera', help: 'Ayuda', unit: 'ms',
      withQos: points, withoutQos: [], bucketSeconds: 1});
    let nodes = elements(render(chart));
    const lines = nodes.filter(n => n.props?.dataKey === 'withQos' || n.props?.dataKey === 'withoutQos');
    assert.equal(lines.length, 2);
    assert.equal(lines[0].props.dot, false);
    for (const line of lines) {
      assert.equal(line.props.type, 'linear');
      assert.equal(line.props.isAnimationActive, false);
      assert.equal(line.props.connectNulls, false);
    }
    assert.equal(nodes.find(n => n.props?.data)?.props.data[0].withQos, 2);
    nodes.find(n => n.type === 'button').props.onClick();
    nodes = elements(render(chart));
    assert.equal(nodes.find(n => n.props?.data)?.props.data[0].withQos, 900);
    assert.equal(nodes.find(n => n.type === 'button').props['aria-pressed'], true);
    assert.equal(nodes.find(n => n.props?.data)?.props.data[0].withoutQos, null);
  });
});

test('condición no registrada no es botón ni pareja automática y conserva enlace', () => {
  const context = require('../src/app/contexts/ExperimentContext.tsx');
  const hook = require('../src/app/hooks/useRunEvidence.ts');
  const previousContext = context.useExperiments, previousHook = hook.useRunEvidence;
  const calls = [];
  const legacy = {id: 'legacy-a', scenario: 'WITH_QOS', started_at: '2026-01-01T00:00:00Z',
    finished_at: '2026-01-01T00:01:00Z', config_snapshot: null};
  context.useExperiments = () => ({runs: [legacy], analyses: {}, runMeta: {}, status: 'success',
    fetchAnalysis: async () => {}, retry() {}});
  hook.useRunEvidence = run => {
    calls.push(run?.id);
    return {data: run ? evidenceFixture() : null, error: null, loading: false, retry() {}};
  };
  try {
    const {AnalyticsView} = require('../src/app/components/views/AnalyticsView.tsx');
    const html = renderToStaticMarkup(React.createElement(require('react-router').MemoryRouter,
      {initialEntries: ['/app/qos?run_id=legacy-a']}, React.createElement(AnalyticsView)));
    const buttons = html.match(/<button[\s\S]*?<\/button>/g) ?? [];
    assert.ok(buttons.some(b => b.includes('Sensores normales')));
    assert.ok(buttons.some(b => b.includes('Sensores alterados')));
    assert.ok(!buttons.some(b => b.includes('Condición no registrada')));
    assert.ok(html.includes('Se conservan en el histórico'));
    assert.deepEqual(calls, ['legacy-a', undefined, undefined]);
  } finally {context.useExperiments = previousContext; hook.useRunEvidence = previousHook;}
});

test('sondeo conserva paneles y datos durante carga; autorización invalida datos', async () => {
  const {withHookHarness} = require('./hookHarness.cjs');
  const polling = require('../src/app/hooks/usePolling.ts');
  const qos = require('../src/services/api/qos.ts');
  const {ApiError} = require('../src/services/api/client.ts');
  const previousPolling = polling.usePolling;
  for (const [file, hookName, apiName, result, field] of [
    ['useQosRuntime', 'useQosRuntime', 'apiGetQosRuntime', {dispatch: {pending: 3}}, 'runtime'],
    ['useLiveQueues', 'useLiveQueues', 'apiGetLiveQueues', {queues: {high: [], medium: [], low: []}}, 'queues'],
  ]) {
    const path = require.resolve(`../src/app/hooks/${file}.ts`);
    const previousModule = require.cache[path];
    delete require.cache[path]; // Test the real hook, not the view fixture above.
    const hook = require(path)[hookName];
    const previousApi = qos[apiName];
    let tick, resolve, reject;
    polling.usePolling = (_on, _ms, callback) => {tick = callback;};
    qos[apiName] = () => new Promise((yes, no) => {resolve = yes; reject = no;});
    try {
      await withHookHarness(async ({render, settle}) => {
        assert.equal(render(hook).isLoading, true);
        resolve(result);
        await settle();
        const loaded = render(hook);
        assert.equal(loaded.isLoading, false);
        tick();
        render(hook);
        const refreshing = render(hook);
        assert.equal(refreshing.isLoading, false);
        assert.equal(refreshing.status, loaded.status);
        assert.equal(refreshing[field], loaded[field]);
        reject(new ApiError('HTTP', 'Sesión expirada', 401));
        await settle();
        const blocked = render(hook);
        assert.equal(blocked.status, 'error');
        assert.equal(blocked.isAuthBlocked, true);
        assert.ok(field === 'runtime' ? blocked.runtime === null : blocked.queues.length === 0);
      });
    } finally {
      qos[apiName] = previousApi;
      require.cache[path] = previousModule;
      polling.usePolling = previousPolling;
    }
  }
});

test('Analytics distingue error, carga, ausencia de muestras y pareja incompleta', () => {
  const {ComparisonResults} = require('../src/app/components/experiments/AnalysisComparison.tsx');
  const base = {hasWith: true, hasWithout: true, conditionLabel: 'Sensores normales', retry() {}, error: null};
  for (const [overrides, expected] of [
    [{error: 'No se pudieron cargar las estadísticas'}, 'No se pudieron cargar las estadísticas'],
    [{}, 'Cargando estadísticas'],
    [{withQos: {total_samples: 0}, withoutQos: {total_samples: 1}}, 'no tiene mediciones'],
    [{hasWithout: false}, 'Falta una prueba sin'],
  ]) {
    const html = renderToStaticMarkup(React.createElement(ComparisonResults, {...base, ...overrides}));
    assert.ok(html.includes(expected), expected);
    if (overrides.hasWithout !== false) assert.ok(!html.includes('Falta una prueba'));
  }
});

test('contexto comparte solicitudes, separa errores por prueba y permite reintento', async () => {
  const {withHookHarness} = require('./hookHarness.cjs');
  const api = require('../src/services/api/experiments.ts');
  const originalLoad = api.loadExperimentRuns, originalAnalysis = api.apiGetRunAnalysis;
  const pending = [];
  api.loadExperimentRuns = async () => [];
  api.apiGetRunAnalysis = id => new Promise((resolve, reject) => pending.push({id, resolve, reject}));
  const {ExperimentProvider} = require('../src/app/contexts/ExperimentContext.tsx');
  try {
    await withHookHarness(async ({render, settle}) => {
      const provider = () => ExperimentProvider({children: null}).props.value;
      render(provider);
      await settle();
      let value = render(provider);
      const first = value.fetchAnalysis('a');
      assert.equal(value.fetchAnalysis('a'), first);
      const second = value.fetchAnalysis('b').catch(() => {});
      assert.deepEqual(pending.map(p => p.id), ['a', 'b']);
      pending[0].resolve({run_id: 'a', total_samples: 12001, metrics: {}, series: {}});
      pending[1].reject(new Error('network'));
      await Promise.all([first, second]);
      value = render(provider);
      assert.equal(value.analyses.a.total_samples, 12001);
      assert.ok(value.analysisErrors.b);
      assert.equal(value.analyses.b, undefined);
      const retry = value.fetchAnalysis('b');
      pending[2].resolve({run_id: 'b', total_samples: 2, metrics: {}, series: {}});
      await retry;
      value = render(provider);
      assert.equal(value.analyses.b.total_samples, 2);
      assert.equal(value.analysisErrors.b, undefined);
    });
  } finally {api.loadExperimentRuns = originalLoad; api.apiGetRunAnalysis = originalAnalysis;}
});

test('contexto serializa resoluciones distintas y rechaza una cuadrícula incompatible', async () => {
  const {withHookHarness} = require('./hookHarness.cjs');
  const api = require('../src/services/api/experiments.ts');
  const originalLoad = api.loadExperimentRuns, originalAnalysis = api.apiGetRunAnalysis;
  const pending = [];
  api.loadExperimentRuns = async () => [];
  api.apiGetRunAnalysis = (id, width) => new Promise(resolve => pending.push({id, width, resolve}));
  const {ExperimentProvider} = require('../src/app/contexts/ExperimentContext.tsx');
  try {
    await withHookHarness(async ({render, settle}) => {
      const provider = () => ExperimentProvider({children: null}).props.value;
      render(provider);
      await settle();
      let value = render(provider);
      const first = value.fetchAnalysis('a', 1);
      const second = value.fetchAnalysis('a', 2);
      assert.equal(pending.length, 1);
      pending[0].resolve({run_id: 'a', bucket_seconds: 1});
      await first;
      await settle();
      assert.equal(pending.length, 2);
      assert.equal(pending[1].width, 2);
      pending[1].resolve({run_id: 'a', bucket_seconds: 2});
      await second;
      value = render(provider);
      assert.equal(value.analyses.a.bucket_seconds, 2);
      assert.equal(value.intervalAnalyses.a[1].bucket_seconds, 1);
      assert.equal(value.intervalAnalyses.a[2].bucket_seconds, 2);
      const mismatch = value.fetchAnalysis('a', 3);
      const rejected = assert.rejects(mismatch, /duración de la prueba cambió/);
      pending[2].resolve({run_id: 'a', bucket_seconds: 4});
      await rejected;
      value = render(provider);
      assert.equal(value.analyses.a, undefined);
      assert.equal(value.intervalAnalyses.a[2].bucket_seconds, 2);
      assert.equal(value.intervalAnalyses.a[3], undefined);
      assert.ok(value.analysisErrors.a);
    });
  } finally {api.loadExperimentRuns = originalLoad; api.apiGetRunAnalysis = originalAnalysis;}
});
