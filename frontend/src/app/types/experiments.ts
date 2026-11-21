export type ExperimentScenario = 'WITH_QOS' | 'WITHOUT_QOS';

export interface ExperimentRun {
  id: string;
  scenario: ExperimentScenario;
  started_at: string;
  finished_at: string | null;
  config_snapshot: string | null;
}

export type ExperimentMetricType =
  | 'messages_received'
  | 'messages_invalid'
  | 'messages_rejected_transport'
  | 'readings_persisted'
  | 'alerts_generated'
  | 'backlog'
  | 'ingest_to_persist_ms'
  | 'ingest_to_alert_ms'
  | 'readings_admitted'
  | 'readings_rejected'
  | 'readings_failed'
  | 'queue_wait_ms'
  | 'service_time_ms';

export interface ExperimentMetric {
  id: string;
  run_id: string;
  metric_type: ExperimentMetricType;
  value: number;
  timestamp: string;
}

export type SensorCondition = 'normal' | 'altered';

export interface ExperimentRunMeta {
  sensorCondition: SensorCondition;
  scope: 'all';
}

export const COUNTER_METRICS: ExperimentMetricType[] = [
  'messages_received',
  'messages_invalid',
  'messages_rejected_transport',
  'readings_persisted',
  'alerts_generated',
  'readings_admitted',
  'readings_rejected',
  'readings_failed',
];

export const LATENCY_METRICS: ExperimentMetricType[] = [
  'ingest_to_persist_ms',
  'ingest_to_alert_ms',
  'queue_wait_ms',
  'service_time_ms',
];

export const METRIC_LABELS: Record<ExperimentMetricType, string> = {
  messages_received:     'Mensajes recibidos',
  messages_invalid:      'Mensajes inválidos',
  messages_rejected_transport: 'Mensajes rechazados en transporte',
  readings_persisted:    'Lecturas persistidas',
  alerts_generated:      'Alertas generadas',
  backlog:               'Backlog',
  ingest_to_persist_ms:  'Ingesta → persistencia',
  ingest_to_alert_ms:    'Ingesta → alerta',
  readings_admitted:     'Lecturas admitidas',
  readings_rejected:     'Lecturas rechazadas',
  readings_failed:       'Atenciones fallidas',
  queue_wait_ms:         'Espera en cola',
  service_time_ms:       'Tiempo de atención',
};

export const METRIC_UNITS: Record<ExperimentMetricType, string> = {
  messages_received:     'mensajes',
  messages_invalid:      'mensajes',
  messages_rejected_transport: 'mensajes',
  readings_persisted:    'lecturas',
  alerts_generated:      'alertas',
  backlog:               'profundidad de cola',
  ingest_to_persist_ms:  'ms',
  ingest_to_alert_ms:    'ms',
  readings_admitted:     'lecturas',
  readings_rejected:     'lecturas',
  readings_failed:       'atenciones',
  queue_wait_ms:         'ms',
  service_time_ms:       'ms',
};

export const SCENARIO_LABELS: Record<ExperimentScenario, string> = {
  WITH_QOS:    'Con priorización',
  WITHOUT_QOS: 'Sin priorización',
};

export const SENSOR_CONDITION_LABELS: Record<SensorCondition, string> = {
  normal:  'Sensores normales',
  altered: 'Sensores alterados',
};
