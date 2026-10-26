const TONE = { Open: 'badge-success', Closed: 'badge-neutral', Cancelled: 'badge-danger', Fulfilled: 'badge-primary', Map: 'badge-warning' };

// JD status (Open, Closed, Cancelled, Fulfilled, Map); distinct from a candidate's review status.
export default function JdStatusBadge({ status }) {
  return <span className={`badge ${TONE[status] || 'badge-neutral'}`}><span className="sr-only">JD status: </span>{status || 'Open'}</span>;
}
