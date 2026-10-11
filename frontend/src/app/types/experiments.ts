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
  | 'readings_persisted'
  | 'alerts_generated'
  | 'backlog'
  | 'ingest_to_persist_ms'
  | 'ingest_to_alert_ms';

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
  'readings_persisted',
  'alerts_generated',
];

export const LATENCY_METRICS: ExperimentMetricType[] = [
  'ingest_to_persist_ms',
  'ingest_to_alert_ms',
];

export const METRIC_LABELS: Record<ExperimentMetricType, string> = {
  messages_received:     'Mensajes recibidos',
  messages_invalid:      'Mensajes inválidos',
  readings_persisted:    'Lecturas persistidas',
  alerts_generated:      'Alertas generadas',
  backlog:               'Backlog',
  ingest_to_persist_ms:  'Ingesta → persistencia',
  ingest_to_alert_ms:    'Ingesta → alerta',
};

export const METRIC_UNITS: Record<ExperimentMetricType, string> = {
  messages_received:     'mensajes',
  messages_invalid:      'mensajes',
  readings_persisted:    'lecturas',
  alerts_generated:      'alertas',
  backlog:               'profundidad de cola',
  ingest_to_persist_ms:  'ms',
  ingest_to_alert_ms:    'ms',
};

export const SCENARIO_LABELS: Record<ExperimentScenario, string> = {
  WITH_QOS:    'Con priorización',
  WITHOUT_QOS: 'Sin priorización',
};

export const SENSOR_CONDITION_LABELS: Record<SensorCondition, string> = {
  normal:  'Sensores normales',
  altered: 'Sensores alterados',
};
