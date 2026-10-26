import { useRef, useState } from 'react';
import { FileCheck, Loader2, Save, Sparkles, UploadCloud } from 'lucide-react';
import { jdApi } from '../../lib/api';
import { changedDetails, detailsPayload, validateDetails } from '../../lib/requirements';
import { useMeta } from '../../context/MetaContext';
import './requirements.css';

// Create or edit one requirement: title, specification text and an optional source file (text is extracted).
// Detail fields as form strings; the same shape is used to detect what the user actually changed.
const initialDetails = (jd, creating, defaultStatus) => ({
  location: creating ? '' : jd?.location || '',
  experience: creating || jd?.experience_years == null ? '' : String(jd.experience_years),
  startDate: creating ? '' : jd?.start_date || '',
  endDate: creating ? '' : jd?.end_date || '',
  status: creating ? defaultStatus : jd?.status || defaultStatus,
});

export default function RequirementEditor({ jd, creating, onSave, onSummarize, onNotice, onCancel }) {
  const { accepted_jd_file_types: acceptedTypes, jd_statuses: statuses, default_jd_status: defaultStatus } = useMeta();
  const [initial] = useState(() => initialDetails(jd, creating, defaultStatus));
  const [details, setDetails] = useState(initial);
  const [formError, setFormError] = useState(null);
  const setField = (key) => (e) => setDetails((d) => ({ ...d, [key]: e.target.value }));
  const fileRef = useRef(null);
  const [title, setTitle] = useState(creating ? '' : jd?.title || '');
  const [text, setText] = useState(creating ? '' : jd?.jd_text || '');
  const [fileUrl, setFileUrl] = useState(creating ? null : jd?.file_url || null);
  const [originalFilename, setOriginalFilename] = useState(creating ? null : jd?.original_filename || null);
  const [extracting, setExtracting] = useState(false);
  const [saving, setSaving] = useState(false);
  const [summarizing, setSummarizing] = useState(false);
  const [dragging, setDragging] = useState(false);

  // Fill only blank fields from what the JD states, so nothing the user typed is overwritten.
  const prefill = (found) => {
    if (!title.trim() && found.detected_title) setTitle(found.detected_title);
    setDetails((d) => ({
      ...d,
      location: d.location.trim() ? d.location : found.location || '',
      experience: d.experience !== '' ? d.experience : found.experience_years == null ? '' : String(found.experience_years),
    }));
  };

  // Pasted or typed text: read the details once per distinct text, when the user leaves the box or pastes.
  const lastDetected = useRef('');
  const detectFromText = async (value) => {
    const body = (value || '').trim();
    if (!creating || body.length < 40 || body === lastDetected.current) return;
    lastDetected.current = body;
    try {
      prefill((await jdApi.extractDetails({ title, jd_text: body })).data);
    } catch {
      // Detection is a convenience; the fields simply stay as they are.
    }
  };

  const extract = async (file) => {
    if (!file) return;
    setExtracting(true);
    onNotice({ type: 'info', message: `Extracting text from "${file.name}"…` });
    const body = new FormData();
    body.append('file', file);
    try {
      const data = (await jdApi.extractText(body)).data;
      if (creating || !title.trim()) setTitle(data.detected_title || data.title || file.name.replace(/\.[^/.]+$/, ''));
      setText(data.jd_text || '');
      lastDetected.current = (data.jd_text || '').trim();
      prefill({ ...data, detected_title: null });
      setFileUrl(data.file_url || null);
      setOriginalFilename(data.original_filename || file.name);
      onNotice({ type: 'success', message: `Text extracted from "${file.name}". Review the details filled in from it, then save.${data.category ? ` It will be filed under ${data.category}.` : ''}${data.classification_note ? ` ${data.classification_note}` : ''}` });
    } catch (err) {
      onNotice({ type: 'error', message: err.response?.data?.detail || `Could not read "${file.name}". Check the file format.` });
    } finally {
      setExtracting(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const drag = (e) => {
    e.preventDefault();
    setDragging(e.type === 'dragenter' || e.type === 'dragover');
  };

  const submit = async (e) => {
    e.preventDefault();
    if (!title.trim() || !text.trim()) return;
    const problem = validateDetails(details);
    setFormError(problem);
    if (problem) return;
    setSaving(true);
    // Creating sends everything entered; editing sends only the detail fields that changed.
    await onSave({ title, text, fileUrl, originalFilename, details: creating ? detailsPayload(details) : changedDetails(initial, details) });
    setSaving(false);
  };

  const summarize = async () => {
    setSummarizing(true);
    await onSummarize();
    setSummarizing(false);
  };

  return (
    <form className="req-editor stack stack-loose" onSubmit={submit}>
      <input ref={fileRef} type="file" className="sr-only" accept={acceptedTypes.join(',')} onChange={(e) => extract(e.target.files?.[0])} tabIndex={-1} aria-hidden="true" />

      <div
        className={`req-drop${dragging ? ' is-dragging' : ''}`}
        onDragEnter={drag}
        onDragOver={drag}
        onDragLeave={drag}
        onDrop={(e) => { drag(e); extract(e.dataTransfer.files?.[0]); }}
      >
        {extracting ? (
          <span className="cluster cluster-tight"><Loader2 size={16} className="animate-spin" /> Extracting text…</span>
        ) : originalFilename ? (
          <span className="cluster cluster-tight">
            <FileCheck size={16} aria-hidden="true" />
            <span>Source file: {originalFilename}</span>
            <button type="button" className="btn btn-secondary btn-compact" onClick={() => fileRef.current?.click()}>Replace file</button>
          </span>
        ) : (
          <span className="cluster cluster-tight">
            <UploadCloud size={16} aria-hidden="true" />
            <span>Drop a requirement file here, or</span>
            <button type="button" className="btn btn-secondary btn-compact" onClick={() => fileRef.current?.click()}>Choose file</button>
          </span>
        )}
      </div>

      {!creating && jd?.jd_summary && (
        <div className="req-summary">
          <h3>Summary · version {jd.jd_version}</h3>
          <p>{jd.jd_summary}</p>
        </div>
      )}

      <div>
        <label className="input-label" htmlFor="req-title">Title</label>
        <input id="req-title" className="input-field" required value={title} onChange={(e) => setTitle(e.target.value)} />
      </div>

      <div className="detail-form">
        <div>
          <label className="input-label" htmlFor="req-exp">Experience (years)</label>
          <input id="req-exp" className="input-field" type="number" step="0.5" value={details.experience} onChange={setField('experience')} />
        </div>
        <div>
          <label className="input-label" htmlFor="req-location">Location</label>
          <input id="req-location" className="input-field" maxLength={200} value={details.location} onChange={setField('location')} />
        </div>
        <div>
          <label className="input-label" htmlFor="req-status">JD Status</label>
          <select id="req-status" className="input-field" value={details.status} onChange={setField('status')}>
            {statuses.map((st) => <option key={st} value={st}>{st}</option>)}
          </select>
        </div>
        <div>
          <label className="input-label" htmlFor="req-start">Start Date</label>
          <input id="req-start" className="input-field" type="date" value={details.startDate} onChange={setField('startDate')} />
        </div>
        <div>
          <label className="input-label" htmlFor="req-end">End Date</label>
          <input id="req-end" className="input-field" type="date" value={details.endDate} onChange={setField('endDate')} />
        </div>
      </div>
      {formError && <p className="req-error" role="alert">{formError}</p>}

      <div>
        <div className="cluster cluster-between">
          <label className="input-label" htmlFor="req-text">Specification</label>
        </div>
        <textarea id="req-text" className="input-field req-text" required rows={14} value={text} onChange={(e) => setText(e.target.value)}
          onPaste={(e) => { const pasted = e.clipboardData?.getData('text'); if (pasted) setTimeout(() => detectFromText(e.target.value), 0); }}
          onBlur={(e) => detectFromText(e.target.value)} />
      </div>

      <div className="cluster cluster-between">
        <span />
        <span className="cluster">
          {!creating && (
            <button type="button" className="btn btn-secondary" onClick={summarize} disabled={summarizing}>
              <Sparkles size={15} /> {summarizing ? 'Summarizing…' : jd?.jd_summary ? 'Summarize again' : 'Summarize'}
            </button>
          )}
          {onCancel && <button type="button" className="btn btn-secondary" onClick={onCancel}>Cancel</button>}
          <button type="submit" className="btn btn-primary" disabled={saving || extracting}>
            <Save size={15} /> {saving ? 'Saving…' : creating ? 'Create requirement' : 'Save changes'}
          </button>
        </span>
      </div>
    </form>
  );
}
