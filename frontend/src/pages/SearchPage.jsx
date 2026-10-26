import { useState } from 'react';
import { Download, FileSpreadsheet } from 'lucide-react';
import useSearch from '../hooks/useSearch';
import SearchForm from '../components/search/SearchForm';
import ResultsPanel from '../components/search/ResultsPanel';
import Notice from '../components/ui/Notice';
import { COPY } from '../config/copy';
import ResumePreviewModal from '../components/ResumePreviewModal';
import '../components/requirements/requirements.css';

export default function SearchPage() {
  const s = useSearch();
  const [preview, setPreview] = useState(null);

  return (
    <div className="page-body page">
      <header className="page-head">
        <div>
          <h1 className="page-header-title">Search</h1>
        </div>
        <span className="cluster cluster-tight">
          <button type="button" className="btn btn-primary btn-compact" onClick={() => s.exportCandidates('xlsx')} disabled={s.exporting !== null}>
            <FileSpreadsheet size={14} /> {s.exporting === 'xlsx' ? 'Exporting…' : 'Export Excel'}
          </button>
          <button type="button" className="btn btn-secondary btn-compact" onClick={() => s.exportCandidates('csv')} disabled={s.exporting !== null}>
            <Download size={14} /> {s.exporting === 'csv' ? 'Exporting…' : 'Export CSV'}
          </button>
        </span>
      </header>

      <SearchForm s={s} />
      {s.notice && <div className="page-notice"><Notice type={s.notice === COPY.nothingToSearch ? 'warning' : 'info'}>{s.notice}</Notice></div>}
      <ResultsPanel s={s} onPreview={setPreview} />
      <ResumePreviewModal isOpen={!!preview} onClose={() => setPreview(null)} candidate={preview} />
    </div>
  );
}
