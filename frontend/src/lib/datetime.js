// The API stores UTC timestamps without a timezone marker; read them as UTC and show Indian Standard Time.
export function formatIst(value) {
  if (!value) return '';
  const text = String(value);
  const date = new Date(/[zZ]|[+-]\d\d:?\d\d$/.test(text) ? text : `${text}Z`);
  if (Number.isNaN(date.getTime())) return '';
  return `${date.toLocaleString('en-IN', {
    timeZone: 'Asia/Kolkata', day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit', hour12: true,
  })} IST`;
}
