/** Native disclosure: works with mouse, touch, Enter and Space, without hover. */
export function InfoHelp({ label, children }: { label: string; children: string }) {
  return <details className="d-inline-block ms-1 align-middle position-relative">
    <summary aria-label={`Información sobre ${label}`}
      className="text-primary rounded-circle"
      style={{ cursor: 'pointer', listStyle: 'none', fontSize: 15, lineHeight: 1.2 }}>
      ⓘ
    </summary>
    <div className="bg-white border rounded-3 p-3 mt-2 small text-start fw-normal"
      style={{ width: 'min(280px, 75vw)', color: '#17232D' }}>
      {children}
    </div>
  </details>;
}
