import { useEffect, useId, useRef, useState } from 'react';
import { ListChecks, Loader2, MessagesSquare, Pencil } from 'lucide-react';

// The interactive side of the guided demand workflow. The server decides the mode, the current field and what is
// valid; this component only renders the session it is given (fields, options, errors) and sends the user's input back.

const toInput = (field) => {
  const v = field.value;
  if (v === null || v === undefined) return field.default === undefined || field.source ? '' : String(field.default);
  return Array.isArray(v) ? v.join(', ') : String(v);
};

// One control per field type, using the same field definitions the New Demand page uses.
function FieldControl({ field, value, onChange, autoFocus }) {
  const id = useId();
  const labelledBy = `${id}-label`;
  const common = { id, 'aria-labelledby': labelledBy, 'aria-invalid': !!field.error, 'aria-describedby': field.error ? `${id}-error` : undefined, autoFocus };
  if (field.type === 'select') {
    return (
      <fieldset className="demand-radios" aria-labelledby={labelledBy}>
        {field.options.map((o) => (
          <label key={o.value} className="demand-radio">
            <input type="radio" name={id} value={o.value} checked={value === o.value} onChange={() => onChange(o.value)} autoFocus={autoFocus && value === o.value} />
            <span>{o.label}</span>
          </label>
        ))}
      </fieldset>
    );
  }
  if (field.type === 'select_or_text') {
    const known = field.options.some((o) => o.value === value);
    const other = value !== '' && !known;
    return (
      <div className="demand-radios" role="group" aria-labelledby={labelledBy}>
        {field.options.map((o) => (
          <label key={o.value} className="demand-radio">
            <input type="radio" name={id} checked={value === o.value} onChange={() => onChange(o.value)} />
            <span>{o.label}</span>
          </label>
        ))}
        <label className="demand-radio">
          <input type="radio" name={id} checked={other} onChange={() => onChange(' ')} />
          <span>Others</span>
        </label>
        {(other || value === ' ') && (
          <input className="input-field" maxLength={field.max} value={value.trim() === '' ? '' : value} onChange={(e) => onChange(e.target.value || ' ')}
            placeholder="Type the client name" aria-label="Client name" autoFocus />
        )}
      </div>
    );
  }
  if (field.type === 'textarea') return <textarea {...common} className="input-field" rows={5} maxLength={field.max} value={value} onChange={(e) => onChange(e.target.value)} />;
  if (field.type === 'number') return <input {...common} className="input-field" type="number" min={field.min} max={field.max} step={field.step} value={value} onChange={(e) => onChange(e.target.value)} />;
  if (field.type === 'date') return <input {...common} className="input-field" type="date" value={value} onChange={(e) => onChange(e.target.value)} />;
  if (field.type === 'tags') return <input {...common} className="input-field" value={value} onChange={(e) => onChange(e.target.value)} placeholder="For example: Pune, Mumbai" />;
  return <input {...common} className="input-field" maxLength={field.max} value={value} onChange={(e) => onChange(e.target.value)} />;
}

// `label` replaces the field label (the step view asks the question instead); `marked` adds the required/optional hint.
function FieldRow({ field, label, marked = true, value, onChange, autoFocus }) {
  const id = useId();
  return (
    <div className="demand-field">
      <span id={`${id}-label`} className="input-label">
        {label ?? field.label}
        {marked && (field.required ? <abbr title="Required" className="demand-required"> *</abbr> : <span className="slug"> (optional)</span>)}
      </span>
      <FieldControl field={field} value={value} onChange={onChange} autoFocus={autoFocus} />
      {field.error && <p className="demand-error" role="alert">{field.error}</p>}
    </div>
  );
}

const Actions = ({ children }) => <div className="demand-actions">{children}</div>;

export default function DemandSessionCard({ session, busy, error, onAct, onCancel }) {
  const [showEdit, setShowEdit] = useState(false);
  const fields = session.fields;
  const current = fields.find((f) => f.key === session.current_field);

  // Local, editable copy of every field. A value the server changes (a document was attached) replaces the local one.
  const [local, setLocal] = useState(() => Object.fromEntries(fields.map((f) => [f.key, toInput(f)])));
  const serverRef = useRef(JSON.stringify(fields.map((f) => f.value)));
  useEffect(() => {
    const now = JSON.stringify(fields.map((f) => f.value));
    if (now === serverRef.current) return;
    serverRef.current = now;
    setLocal(Object.fromEntries(fields.map((f) => [f.key, toInput(f)])));
  }, [fields]);
  useEffect(() => { setShowEdit(false); }, [session.status]);

  // A new step starts from what is already stored for that field.
  const stepKey = session.current_field;
  useEffect(() => {
    if (!stepKey) return;
    const f = session.fields.find((x) => x.key === stepKey);
    setLocal((l) => ({ ...l, [stepKey]: toInput(f) }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stepKey]);

  const set = (key) => (value) => setLocal((l) => ({ ...l, [key]: value }));
  const cancel = <button type="button" className="link-btn demand-cancel" onClick={onCancel} disabled={busy}>Cancel demand</button>;
  const spinner = busy && <Loader2 size={14} className="animate-spin" aria-hidden="true" />;
  const errorLine = error && <p className="demand-error" role="alert">{error}</p>;

  if (session.status === 'creating') {
    return <div className="demand-card" role="status"><Loader2 size={15} className="animate-spin" aria-hidden="true" /> Creating your demand…</div>;
  }

  if (session.status === 'choose_mode') {
    return (
      <section className="demand-card" aria-label="Create a demand">
        <h3 className="demand-title">How would you like to fill in the demand details?</h3>
        <div className="demand-options">
          <button type="button" className="demand-option" onClick={() => onAct('mode', { mode: 'all_fields' })} disabled={busy}>
            <span className="demand-option-title"><ListChecks size={16} aria-hidden="true" /> Fill all fields at once</span>
            <span>Complete the entire demand form in one step.</span>
          </button>
          <button type="button" className="demand-option" onClick={() => onAct('mode', { mode: 'step_by_step' })} disabled={busy}>
            <span className="demand-option-title"><MessagesSquare size={16} aria-hidden="true" /> Fill one by one</span>
            <span>I&rsquo;ll ask for each field individually, in form order.</span>
          </button>
        </div>
        <p className="demand-hint">Tip: attach a demand document with the paperclip and I&rsquo;ll fill in what it states.</p>
        {errorLine}
        <Actions>{cancel}</Actions>
      </section>
    );
  }

  if (session.status === 'review') {
    return (
      <section className="demand-card" aria-label="Review demand">
        <h3 className="demand-title">Review your demand</h3>
        <dl className="demand-summary">
          {fields.map((f) => (
            <div key={f.key}>
              <dt>{f.label}</dt>
              <dd className={f.value === null || f.value === '' ? 'is-empty' : undefined}>
                <span className="demand-summary-text">{f.key === 'jd_text' && f.text.length > 160 ? `${f.text.slice(0, 160)}…` : f.text}</span>
                {showEdit && <button type="button" className="icon-btn" onClick={() => onAct('edit', { field: f.key })} disabled={busy} aria-label={`Edit ${f.label}`}><Pencil size={13} /></button>}
              </dd>
            </div>
          ))}
          <div><dt>Demand Status</dt><dd>Open</dd></div>
        </dl>
        {errorLine}
        <Actions>
          <button type="button" className="btn btn-primary" onClick={() => onAct('confirm')} disabled={busy}>{spinner} {error ? 'Try again' : 'Confirm and Create Demand'}</button>
          <button type="button" className="btn btn-secondary" onClick={() => setShowEdit((v) => !v)} disabled={busy} aria-pressed={showEdit}>Edit Details</button>
          {cancel}
        </Actions>
      </section>
    );
  }

  if (session.input_mode === 'all_fields') {
    const submit = (e) => {
      e.preventDefault();
      onAct('answers', { values: Object.fromEntries(fields.map((f) => [f.key, local[f.key] ?? ''])) });
    };
    return (
      <form className="demand-card" onSubmit={submit} aria-label="Demand form" noValidate>
        <h3 className="demand-title">Demand details</h3>
        {fields.map((f, i) => <FieldRow key={f.key} field={f} value={local[f.key] ?? ''} onChange={set(f.key)} autoFocus={i === 0 && !f.value} />)}
        {errorLine}
        <Actions>
          <button type="submit" className="btn btn-primary" disabled={busy}>{spinner} Continue to review</button>
          <button type="button" className="btn btn-secondary" onClick={() => onAct('mode', { mode: 'step_by_step' })} disabled={busy}>Fill one by one instead</button>
          {cancel}
        </Actions>
      </form>
    );
  }

  if (!current) return null;
  const value = local[current.key] ?? '';
  const empty = value.trim() === '';
  const submit = (e) => {
    e.preventDefault();
    if (current.required && empty) return;
    onAct('answer', { field: current.key, value });
  };
  return (
    <form className="demand-card" onSubmit={submit} aria-label={current.label}>
      <div className="demand-step-head">
        <h3 className="demand-title">{current.label}</h3>
        {session.progress && <span className="demand-step" aria-label={`Step ${session.progress.step} of ${session.progress.total}`}>Step {session.progress.step} of {session.progress.total}</span>}
      </div>
      <FieldRow field={current} label={session.question || current.prompt} marked={false} value={value} onChange={set(current.key)} autoFocus />
      {errorLine}
      <Actions>
        <button type="submit" className="btn btn-primary" disabled={busy || (current.required && empty)}>{spinner} Continue</button>
        {!current.required && <button type="button" className="btn btn-secondary" onClick={() => onAct('skip')} disabled={busy}>Skip</button>}
        <button type="button" className="btn btn-secondary" onClick={() => onAct('back')} disabled={busy}>Back</button>
        <button type="button" className="link-btn" onClick={() => onAct('mode', { mode: 'all_fields' })} disabled={busy}>Show all fields</button>
        {cancel}
      </Actions>
    </form>
  );
}
