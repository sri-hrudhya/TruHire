import { useState } from 'react';
import { ChevronRight, Clock, History, LayoutGrid, List } from 'lucide-react';
import useRequirements from '../hooks/useRequirements';
import Notice from '../components/ui/Notice';
import ResumePreviewModal from '../components/ResumePreviewModal';
import DemandCards from '../components/requirements/DemandCards';
import JdCards from '../components/requirements/JdCards';
import JdDetails from '../components/requirements/JdDetails';
import JdStatusBadge from '../components/requirements/JdStatusBadge';
import JdTable from '../components/requirements/JdTable';
import RequirementHistory from '../components/requirements/RequirementHistory';
import RequirementEditor from '../components/requirements/RequirementEditor';
import RequirementMatches from '../components/requirements/RequirementMatches';
import { DeleteRequirementModal, EmailShortlistModal, RetentionModal } from '../components/requirements/RequirementModals';
import { sortByStatus } from '../lib/requirements';
import '../components/requirements/requirements.css';

const TABS = (count) => [['details', 'Details'], ['matches', `Candidates (${count})`]];

// Progressive disclosure: five folder cards -> that folder's demand cards -> one demand's full details.
export default function JobDescriptionsPage() {
  const r = useRequirements();
  const [tab, setTab] = useState('details');
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(null);
  const [emailing, setEmailing] = useState(false);
  const [showRetention, setShowRetention] = useState(false);
  const [preview, setPreview] = useState(null);
  const [view, setView] = useState('cards');  // 'cards' or 'list' (spreadsheet-style table)

  const jd = r.selectedJd;
  const demand = r.demands.find((d) => d.id === r.demandId);
  const forEmail = r.matches.map((m) => ({
    ...m.candidate, match_score: m.match_score, requirement_status: m.requirement_status, last_email: m.last_email,
  }));
  const shortlisted = forEmail.filter((c) => c.requirement_status === 'Shortlisted');
  const create = () => { r.startCreate(); setEditing(false); };
  const duplicate = (source) => { r.startCreate(source); setEditing(false); };
  const practiceName = (id) => r.demands.find((d) => d.id === id)?.name;
  const toggleView = () => {
    if (jd || r.creating) r.closeJd();
    setView((v) => (v === 'list' ? 'cards' : 'list'));
  };
  const save = async (payload) => {
    const ok = await r.saveJd(payload);
    if (ok && !r.creating) setEditing(false);
    return ok;
  };

  const crumbs = [{ label: 'Requirements', onClick: () => r.setDemand(null) }];
  if (r.historyOpen) crumbs.push({ label: 'Requirement History' });
  else {
    if (demand) crumbs.push({ label: demand.name, onClick: jd || r.creating ? () => r.setDemand(demand.id) : undefined });
    if (r.creating) crumbs.push({ label: 'New demand' });
    else if (jd) crumbs.push({ label: jd.title });
  }

  return (
    <div className="page-body page">
      <header className="page-head">
        <div>
          <h1 className="page-header-title">Requirements</h1>
        </div>
        <span className="cluster">
          {r.retention && (
            <button type="button" className="link-btn" onClick={() => setShowRetention(true)}>
              <Clock size={13} aria-hidden="true" /> {r.retention.data_retention_days}-day retention
            </button>
          )}
          {!r.historyOpen && (
            <button type="button" className="btn btn-secondary" onClick={toggleView} aria-pressed={view === 'list'}>
              {view === 'list' ? <><LayoutGrid size={16} /> Card view</> : <><List size={16} /> List view</>}
            </button>
          )}
          <button type="button" className={`btn ${r.historyOpen ? 'btn-primary' : 'btn-secondary'}`} onClick={() => r.showHistory(!r.historyOpen)} aria-pressed={r.historyOpen}>
            <History size={16} /> Requirement History
          </button>
        </span>
      </header>

      {r.notice && <div className="page-notice"><Notice type={r.notice.type} onDismiss={() => r.setNotice(null)}>{r.notice.message}</Notice></div>}

      {crumbs.length > 1 && (
        <nav className="crumbs" aria-label="Requirements navigation">
          {crumbs.map((c, i) => (
            <span key={`${c.label}-${i}`} className="crumb">
              {i > 0 && <ChevronRight size={13} aria-hidden="true" />}
              {c.onClick ? <button type="button" className="link-btn" onClick={c.onClick}>{c.label}</button> : <span aria-current="page">{c.label}</span>}
            </span>
          ))}
        </nav>
      )}

      <section className="req-detail" aria-live="polite">
        {r.historyOpen ? (
          <RequirementHistory />
        ) : r.creating ? (
          <>
            <div className="section-head"><h2>{r.template ? 'Duplicate demand' : 'New demand'}</h2></div>
            <RequirementEditor key={r.template ? `copy-${r.template.id}` : 'new'} jd={null} creating template={r.template} defaultDemandId={r.demandId} demands={r.demands} onSave={save} onSummarize={r.summarize} onNotice={r.setNotice} />
          </>
        ) : jd ? (
          <>
            <div className="section-head">
              <h2>{jd.title}</h2>
              <span className="cluster cluster-tight slug">
                {jd.display_id} <JdStatusBadge status={jd.status} />
              </span>
            </div>
            <div className="category-row" role="tablist" aria-label="Requirement sections">
              {TABS(r.matches.length).map(([id, label]) => (
                <button key={id} type="button" role="tab" className="category-tab" aria-selected={tab === id} onClick={() => { setTab(id); setEditing(false); }}>{label}</button>
              ))}
            </div>
            {tab === 'details' && !editing && (
              <JdDetails
                jd={jd}
                demandName={r.demands.find((d) => d.id === jd.demand_id)?.name}
                onStatus={r.changeJdStatus}
                onEdit={() => setEditing(true)}
                onDuplicate={() => duplicate(jd)}
                onEndDate={r.changeEndDate}
                onOpenFile={() => r.openJdFile(jd.id)}
              />
            )}
            {tab === 'details' && editing && (
              <RequirementEditor key={`${jd.id}-${jd.jd_version}`} jd={jd} creating={false} demands={r.demands} onSave={save} onSummarize={r.summarize} onNotice={r.setNotice} onCancel={() => setEditing(false)} />
            )}
            {tab === 'matches' && (
              <RequirementMatches
                jd={jd}
                matches={r.matches}
                loading={r.loadingMatches}
                minScore={r.minMatchScore}
                coverage={r.coverage}
                statusError={r.statusError}
                assignments={r.assignments}
                users={r.users}
                shortlistedCount={shortlisted.length}
                onStatus={r.changeStatus}
                onAssign={r.assign}
                onPreview={setPreview}
                onEmail={() => setEmailing(true)}
              />
            )}
          </>
        ) : view === 'list' ? (
          <>
            {demand && <div className="section-head"><h2>{demand.name}</h2></div>}
            <JdTable
              key={demand?.id || 'all'}
              jds={demand ? r.visibleJds : sortByStatus(r.jds)}
              loading={r.loading}
              practiceName={practiceName}
              onOpen={(item) => { r.selectJd(item); setTab('details'); setEditing(false); }}
              onDelete={setDeleting}
              onDuplicate={duplicate}
              onCreate={create}
            />
          </>
        ) : demand ? (
          <>
            <div className="section-head"><h2>{demand.name} <span className="slug">{demand.jd_count} {demand.jd_count === 1 ? 'demand' : 'demands'}{r.visibleJds.length > demand.jd_count ? ` · ${r.visibleJds.length} including cancelled` : ''}</span></h2></div>
            <JdCards
              key={demand.id}
              jds={r.visibleJds}
              loading={r.loading}
              onOpen={(item) => { r.selectJd(item); setTab('details'); setEditing(false); }}
              onDelete={setDeleting}
              onDuplicate={duplicate}
              onCreate={create}
            />
          </>
        ) : (
          <DemandCards demands={r.demands} loading={r.loading} onOpen={r.setDemand} onCreate={create} />
        )}
      </section>

      {deleting && <DeleteRequirementModal jd={deleting} onConfirm={r.removeJd} onClose={() => setDeleting(null)} />}
      {showRetention && <RetentionModal retention={r.retention} onCleanup={r.runRetentionCleanup} onClose={() => setShowRetention(false)} />}
      {emailing && jd && <EmailShortlistModal jd={jd} candidates={shortlisted} onSent={() => r.loadMatches(jd.id)} onClose={() => setEmailing(false)} />}
      <ResumePreviewModal isOpen={!!preview} onClose={() => setPreview(null)} candidate={preview} />
    </div>
  );
}
