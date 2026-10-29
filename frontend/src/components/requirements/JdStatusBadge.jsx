const TONE = { Open: 'badge-primary', Cancelled: 'badge-danger', Fulfilled: 'badge-success', Mapped: 'badge-warning', Map: 'badge-warning' };

// JD status (Open, Cancelled, Fulfilled, Mapped); distinct from a candidate's review status.
export default function JdStatusBadge({ status }) {
  return <span className={`badge ${TONE[status] || 'badge-neutral'}`}><span className="sr-only">Demand status: </span>{status === 'Map' ? 'Mapped' : status || 'Open'}</span>;
}
