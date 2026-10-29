import { useCallback, useEffect, useState } from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ChevronDown, ChevronRight, FileText, Loader2 } from 'lucide-react';
import { candidatesApi } from '../../lib/api';
import { fromState } from '../../lib/navigation';
import { FRESHNESS_LABEL, formatUploaded, freshness } from '../../lib/ingestion';
import NoticePeriodField from './NoticePeriodField';
import './ingestion.css';

const PAGE = 20;

// Every ingested resume with its upload date, a recent/old marker and an editable notice period.
// Deliberately no per-resume processing status: bulk-upload progress lives in the panel above.
export default function IngestedResumes({ refreshKey }) {
  const location = useLocation();
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const load = useCallback(async (offset = 0) => {
    setLoading(true);
    setError(null);
    try {
      const res = await candidatesApi.list({ limit: PAGE, offset }, true);
      setTotal(res.data.total);
      setRows((prev) => (offset === 0 ? res.data.candidates : [...prev, ...res.data.candidates]));
    } catch (err) {
      setError(err.response?.data?.detail || 'Could not load ingested resumes.');
    } finally {
      setLoading(false);
    }
  }, []);

  // Nothing is fetched until the section is opened; after that it follows finished uploads.
  useEffect(() => { if (open) load(0); }, [open, load, refreshKey]);

  const replace = (updated) => setRows((prev) => prev.map((c) => (c.id === updated.id ? updated : c)));

  return (
    <section className="card ingested" aria-label="Ingested resumes">
      <button type="button" className="ingested-toggle" onClick={() => setOpen((v) => !v)} aria-expanded={open} aria-controls="ingested-body">
        {open ? <ChevronDown size={16} aria-hidden="true" /> : <ChevronRight size={16} aria-hidden="true" />}
        <span>Ingested Resumes</span>
        {open && <span className="slug">{total}</span>}
      </button>

      {open && (
        <div id="ingested-body">
          {error && <p className="req-error" role="alert">{error}</p>}

          <ul className="ingested-list">
            {rows.map((c) => {
              const fresh = freshness(c.uploaded_at);
              return (
                <li key={c.id} className="ingested-row">
                  <div className="ingested-main">
                    <Link className="ingested-name" to={`/candidates/${c.id}`} state={fromState(location, 'Ingestion')}>{c.candidate_name}</Link>
                    <span className="slug ingested-file"><FileText size={12} aria-hidden="true" /> {c.original_filename}</span>
                  </div>
                  <div className="ingested-date">
                    <span className="slug">Uploaded {formatUploaded(c.uploaded_at)}</span>
                    {fresh && <span className={`badge ${fresh === 'recent' ? 'badge-success' : 'badge-neutral'}`}>{FRESHNESS_LABEL[fresh]}</span>}
                  </div>
                  <div className="ingested-notice">
                    <span className="input-label">Notice Period</span>
                    <NoticePeriodField candidate={c} onSaved={replace} />
                  </div>
                </li>
              );
            })}
          </ul>

          {loading && <p className="req-empty"><Loader2 size={16} className="animate-spin" /> Loading resumes…</p>}
          {!loading && !error && rows.length === 0 && <p className="req-empty">No resumes ingested yet. Upload some above.</p>}
          {rows.length < total && !loading && (
            <p><button type="button" className="btn btn-secondary btn-compact" onClick={() => load(rows.length)}>Load more</button></p>
          )}
        </div>
      )}
    </section>
  );
}
