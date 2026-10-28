import { useState } from 'react';
import { useMeta } from '../../context/MetaContext';
import { CANCELLED } from '../../lib/requirements';
import { CancelReasonModal, MapResumesModal } from './StatusModals';

// Demand status dropdown. Cancelled asks for a reason and Mapped / Fulfilled for the resume(s) in a popup;
// the choice only reaches onChange once that popup is confirmed, so a status is never saved half-filled.
//   value      the status currently shown
//   reason     the saved cancellation reason (pre-fills the popup)
//   resumes    the saved resumes, [{ id, display_id, candidate_name }] (pre-selects them)
//   onChange   (status, extras, resumes) => Promise<string | null>; extras is { cancellation_reason } or { candidate_ids };
//              resolve to an error message to keep the popup open and show it
export default function StatusSelect({ id, value, reason = '', resumes = [], onChange, className = 'input-field', ariaLabel }) {
  const { jd_statuses: statuses, resume_linked_jd_statuses: linked } = useMeta();
  const [asking, setAsking] = useState(null);  // the status whose popup is open

  const pick = (status) => {
    if (status === value) return;
    if (status === CANCELLED || linked.includes(status)) setAsking(status);
    else onChange(status, {}, []);
  };

  return (
    <>
      <select id={id} className={className} value={value} onChange={(e) => pick(e.target.value)} aria-label={ariaLabel}>
        {statuses.map((st) => <option key={st} value={st}>{st}</option>)}
        {!statuses.includes(value) && <option value={value}>{value}</option>}
      </select>
      {asking === CANCELLED && (
        <CancelReasonModal initial={value === CANCELLED ? reason : ''} onClose={() => setAsking(null)}
          onConfirm={(text) => onChange(CANCELLED, { cancellation_reason: text }, [])} />
      )}
      {asking && asking !== CANCELLED && (
        <MapResumesModal status={asking} initial={resumes} onClose={() => setAsking(null)}
          onConfirm={(ids, picked) => onChange(asking, { candidate_ids: ids }, picked)} />
      )}
    </>
  );
}
