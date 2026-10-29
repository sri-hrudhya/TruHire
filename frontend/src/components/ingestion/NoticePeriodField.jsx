import { useId, useState } from 'react';
import { Check } from 'lucide-react';
import { candidatesApi } from '../../lib/api';
import { useMeta } from '../../context/MetaContext';
import { formatNotice, noticePayload } from '../../lib/ingestion';

// Editable notice period: a numeric input plus a Days / Weeks / Months dropdown, saved per candidate.
export default function NoticePeriodField({ candidate, onSaved }) {
  const id = useId();
  const { notice_period_units: units } = useMeta();
  const savedValue = candidate.notice_period_value ?? '';
  const savedUnit = candidate.notice_period_unit || units[0];
  const [value, setValue] = useState(String(savedValue));
  const [unit, setUnit] = useState(savedUnit);
  const [state, setState] = useState({ saving: false, error: null, saved: false });
  const dirty = value !== String(savedValue) || (value !== '' && unit !== savedUnit);

  const submit = async (e) => {
    e.preventDefault();
    const payload = noticePayload(value.trim(), unit);
    if (payload.error) { setState({ saving: false, error: payload.error, saved: false }); return; }
    setState({ saving: true, error: null, saved: false });
    try {
      const res = await candidatesApi.setNoticePeriod(candidate.id, payload.value, payload.unit);
      onSaved({ ...candidate, notice_period_value: res.data.notice_period_value, notice_period_unit: res.data.notice_period_unit });
      setState({ saving: false, error: null, saved: true });
    } catch (err) {
      const detail = err.response?.data?.detail;
      setState({ saving: false, error: typeof detail === 'string' ? detail : 'Could not save the notice period.', saved: false });
    }
  };

  return (
    <form className="notice-field" onSubmit={submit}>
      <label className="sr-only" htmlFor={`${id}-v`}>Notice period of {candidate.candidate_name}</label>
      <input
        id={`${id}-v`}
        className="input-field notice-input"
        type="number"
        inputMode="decimal"
        step="any"
        placeholder="—"
        value={value}
        onChange={(e) => { setValue(e.target.value); setState((s) => ({ ...s, error: null, saved: false })); }}
      />
      <label className="sr-only" htmlFor={`${id}-u`}>Notice period unit</label>
      <select id={`${id}-u`} className="input-field notice-unit" value={unit} onChange={(e) => { setUnit(e.target.value); setState((s) => ({ ...s, error: null, saved: false })); }}>
        {units.map((u) => <option key={u} value={u}>{u}</option>)}
      </select>
      {dirty && <button type="submit" className="btn btn-primary btn-compact" disabled={state.saving}>{state.saving ? 'Saving…' : 'Save'}</button>}
      {!dirty && state.saved && <span className="notice-saved"><Check size={13} aria-hidden="true" /> Saved{candidate.notice_period_value === null ? ' (cleared)' : `: ${formatNotice(candidate.notice_period_value, candidate.notice_period_unit)}`}</span>}
      {state.error && <span className="req-error notice-error" role="alert">{state.error}</span>}
    </form>
  );
}
