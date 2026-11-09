import { useState } from 'react';
import { Building2, ChevronRight, History, LayoutGrid, Layers, List } from 'lucide-react';
import useRequirements from '../hooks/useRequirements';
import Notice from '../components/ui/Notice';
import ResumePreviewModal from '../components/ResumePreviewModal';
import DemandCards from '../components/requirements/DemandCards';
import ClientCards from '../components/requirements/ClientCards';
import JdCards from '../components/requirements/JdCards';
import JdDetails from '../components/requirements/JdDetails';
import JdStatusBadge from '../components/requirements/JdStatusBadge';
import JdTable from '../components/requirements/JdTable';
import RequirementHistory from '../components/requirements/RequirementHistory';
import RequirementEditor from '../components/requirements/RequirementEditor';
import RequirementMatches from '../components/requirements/RequirementMatches';
import { DeleteRequirementModal, EmailShortlistModal } from '../components/requirements/RequirementModals';
import { UNASSIGNED_CLIENT, inClient, sortByStatus } from '../lib/requirements';
import '../components/requirements/requirements.css';

const TABS = (count) => [['details', 'Details'], ['matches', `Candidates (${count})`]];

// Progressive disclosure: five folder cards -> that folder's demand cards -> one demand's full details.
export default function JobDescriptionsPage() {
  const r = useRequirements();
  const [tab, setTab] = useState('details');
  const [editing, setEditing] = useState(false);
  const [deleting, setDeleting] = useState(null);
  const [emailing, setEmailing] = useState(false);
  const [preview, setPreview] = useState(null);
  const [view, setView] = useState('cards');  // 'cards' or 'list' (spreadsheet-style table)

  const jd = r.selectedJd;
  const byClient = r.groupBy === 'client';
  // Client-wise, the practice in the URL (kept so a requirement still opens in its practice) does not narrow the list.
  const demand = byClient ? null : r.demands.find((d) => d.id === r.demandId);
  const clientSource = byClient ? sortByStatus(r.jds) : r.visibleJds;
  const clientJds = r.clientName ? clientSource.filter((item) => inClient(item, r.clientName)) : clientSource;
  const clientLabel = r.clientName === UNASSIGNED_CLIENT ? 'No client assigned' : r.clientName;
  const plural = (n) => `${n} ${n === 1 ? 'demand' : 'demands'}`;
  const listError = r.loadError && (!r.jds.length || !r.demands.length);
  const retryLoad = () => { r.loadJDs(); r.loadDemands(); };
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
  else if (byClient) {
    if (r.clientName) crumbs.push({ label: clientLabel, onClick: jd || r.creating ? () => r.setClient(r.clientName) : undefined });
    if (r.creating) crumbs.push({ label: 'New demand' });
    else if (jd) crumbs.push({ label: jd.title });
  } else {
    if (demand) crumbs.push({ label: demand.name, onClick: r.clientName || jd || r.creating ? () => r.setDemand(demand.id) : undefined });
    if (r.clientName) crumbs.push({ label: clientLabel, onClick: jd || r.creating ? () => r.setClient(r.clientName) : undefined });
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
          {!r.historyOpen && (
            <span className="group-switch" role="group" aria-label="Group requirements by">
              <span className="group-switch-label" aria-hidden="true">Group by</span>
              <span className="group-switch-options">
                <button type="button" onClick={() => r.setGroupBy('practice')} aria-pressed={!byClient}><Layers size={15} aria-hidden="true" /> Practice</button>
                <button type="button" onClick={() => r.setGroupBy('client')} aria-pressed={byClient}><Building2 size={15} aria-hidden="true" /> Client</button>
              </span>
            </span>
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
            <RequirementEditor key={r.template ? `copy-${r.template.id}` : 'new'} jd={null} creating template={r.template} defaultDemandId={byClient ? '' : r.demandId} demands={r.demands} onSave={save} onSummarize={r.summarize} onNotice={r.setNotice} />
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
        ) : listError ? (
          <div className="req-error" role="alert">
            <p>{r.loadError}</p>
            <button type="button" className="btn btn-secondary btn-compact" onClick={retryLoad}>Try again</button>
          </div>
        ) : view === 'list' && (byClient || !demand || r.clientName) ? (
          <>
            {(demand || r.clientName) && <div className="section-head"><h2>{r.clientName ? clientLabel : demand.name}</h2></div>}
            <JdTable
              key={`${r.groupBy}-${demand?.id || 'all'}-${r.clientName}`}
              jds={demand || r.clientName ? clientJds : sortByStatus(r.jds)}
              loading={r.loading}
              groupBy={byClient ? (r.clientName ? 'practice' : 'client') : (demand ? undefined : 'practice')}
              practiceName={practiceName}
              onOpen={(item) => { r.selectJd(item); setTab('details'); setEditing(false); }}
              onDelete={setDeleting}
              onDuplicate={duplicate}
              onCreate={create}
            />
          </>
        ) : byClient && !r.clientName ? (
          <>
            <div className="section-head"><h2>Clients <span className="slug">{plural(r.jds.filter((item) => item.status !== 'Cancelled').length)}</span></h2><button type="button" className="btn btn-primary" onClick={create}>New demand</button></div>
            <ClientCards jds={r.jds} loading={r.loading} onCreate={create} label="Clients" emptyText="No demands yet." onOpen={(name) => r.setClient(name || UNASSIGNED_CLIENT)} />
          </>
        ) : demand && !r.clientName && r.visibleJds.length > 0 ? (
          <>
            <div className="section-head"><h2>{demand.name} <span className="slug">Clients · {r.visibleJds.length} {r.visibleJds.length === 1 ? 'demand' : 'demands'}</span></h2><button type="button" className="btn btn-primary" onClick={create}>New demand</button></div>
            <ClientCards jds={r.visibleJds} loading={r.loading} onOpen={(name) => r.setClient(name || UNASSIGNED_CLIENT)} />
          </>
        ) : byClient || demand ? (
          <>
            <div className="section-head"><h2>{r.clientName ? clientLabel : demand.name}<span className="slug">{r.clientName ? ` · ${plural(clientJds.length)}` : ` · ${plural(demand.jd_count)}${r.visibleJds.length > demand.jd_count ? ` · ${r.visibleJds.length} including cancelled` : ''}`}</span></h2></div>
            <JdCards
              key={`${r.groupBy}-${demand?.id}-${r.clientName}`}
              jds={r.clientName ? clientJds : r.visibleJds}
              loading={r.loading}
              scope={byClient ? 'client' : 'practice'}
              practiceName={byClient ? practiceName : undefined}
              onOpen={(item) => { r.selectJd(item); setTab('details'); setEditing(false); }}
              onDelete={setDeleting}
              onDuplicate={duplicate}
              onCreate={create}
              onUpdateField={r.updateJdFields}
            />
          </>
        ) : (
          <DemandCards demands={r.demands} loading={r.loading} onOpen={r.setDemand} onCreate={create} />
        )}
      </section>

      {deleting && <DeleteRequirementModal jd={deleting} onConfirm={r.removeJd} onClose={() => setDeleting(null)} />}
      {emailing && jd && <EmailShortlistModal jd={jd} candidates={shortlisted} onSent={() => r.loadMatches(jd.id)} onClose={() => setEmailing(false)} />}
      <ResumePreviewModal isOpen={!!preview} onClose={() => setPreview(null)} candidate={preview} />
    </div>
  );
}
