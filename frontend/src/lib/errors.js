// One place that turns an API/axios error into text for the user.
// FastAPI sends a string for its own errors and a list of { msg } objects for request validation errors;
// a request that never got a response (offline, timeout) falls back to the transport message.
export const errorText = (err, fallback) => {
  const detail = err?.response?.data?.detail;
  if (Array.isArray(detail)) return detail.map((d) => d?.msg).filter(Boolean).join(' ') || fallback;
  if (typeof detail === 'string' && detail) return detail;
  if (err && !err.response && err.message) return err.message;
  return fallback;
};
