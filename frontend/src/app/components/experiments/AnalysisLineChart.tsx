import { useState } from 'react';
import { CartesianGrid, LineChart, Line, XAxis, YAxis, Tooltip, Legend, ResponsiveContainer } from 'recharts';
import type { AnalysisPoint } from '../../types/experiments';
import { comparisonSeries } from '../../lib/analysisSeries';
import { InfoHelp } from './InfoHelp';

const number = (value: number) => value.toLocaleString('es-CO', { maximumFractionDigits: 2 });
type Row = ReturnType<typeof comparisonSeries>[number];

export function IntervalTooltip({ active, payload, unit }: {
  active?: boolean; payload?: { payload?: Row }[]; unit: string;
}) {
  const row = payload?.find(item => item.payload)?.payload;
  if (!active || !row) return null;
  const point = row.withPoint ?? row.withoutPoint;
  if (!point) return null;
  return <div className="bg-white border rounded p-2 small">
    <strong>Desde {number(point.start_seconds)} hasta {number(point.end_seconds)} s</strong>
    <div className="text-muted">Tiempo transcurrido desde el inicio de cada prueba</div>
    {([['Con priorización', row.withPoint], ['Sin priorización', row.withoutPoint]] as const).map(([label, sample]) =>
      <div key={label} className="mt-1"><strong>{label}</strong>: {sample
        ? <>promedio {number(sample.value)} {unit} · máximo {number(sample.max)} {unit} · {sample.count} mediciones</>
        : 'sin mediciones en este intervalo'}</div>)}
  </div>;
}

export function AnalysisLineChart({ title, help, unit, withQos, withoutQos, bucketSeconds }: {
  title: string; help: string; unit: string; withQos: AnalysisPoint[]; withoutQos: AnalysisPoint[]; bucketSeconds: number;
}) {
  const [showMax, setShowMax] = useState(false);
  const data = comparisonSeries(withQos, withoutQos).map(row => ({
    ...row,
    withQos: row.withPoint ? (showMax ? row.withPoint.max : row.withPoint.value) : null,
    withoutQos: row.withoutPoint ? (showMax ? row.withoutPoint.max : row.withoutPoint.value) : null,
  }));
  return <section className="cc-card p-3">
    <h4 className="small fw-semibold">{title}<InfoHelp label={title}>{help}</InfoHelp></h4>
    <div className="d-flex flex-wrap align-items-center gap-2 small mb-2">
      <span>Intervalos de {number(bucketSeconds)} s · {showMax ? 'Máximo' : 'Promedio'}</span>
      <button type="button" className="btn btn-sm btn-outline-secondary" aria-pressed={showMax}
        onClick={() => setShowMax(value => !value)}>{showMax ? 'Ver promedios' : 'Ver máximos'}</button>
    </div>
    <ResponsiveContainer width="100%" height={280}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 30, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#D9E2E8" />
        <XAxis dataKey="elapsedMin" type="number" domain={['dataMin', 'dataMax']}
          tickFormatter={v => number(Number(v))} tick={{fontSize: 11}}
          label={{value: 'Minutos transcurridos', position: 'insideBottom', offset: -18, fontSize: 11}} />
        <YAxis unit={` ${unit}`} tick={{fontSize: 11}} />
        <Tooltip content={<IntervalTooltip unit={unit} />} />
        <Legend verticalAlign="top" wrapperStyle={{fontSize: 12}} />
        <Line type="linear" dataKey="withQos" name="Con priorización" stroke="#16835B" strokeWidth={2}
          dot={withQos.length <= 12 ? {r: 2} : false} activeDot={{r: 4}} isAnimationActive={false} connectNulls={false} />
        <Line type="linear" dataKey="withoutQos" name="Sin priorización" stroke="#C83B3B" strokeWidth={2}
          dot={withoutQos.length <= 12 ? {r: 2} : false} activeDot={{r: 4}} isAnimationActive={false} connectNulls={false} />
      </LineChart>
    </ResponsiveContainer>
  </section>;
}
