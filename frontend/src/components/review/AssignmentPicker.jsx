import { useAuth } from '../../context/AuthContext';
import { assignmentControl } from '../../lib/review';
import './review.css';

// Who reviews this candidate for this requirement. Admins pick anyone; a recruiter can take an
// unassigned candidate. The server enforces the same rule.
export default function AssignmentPicker({ candidateName, assignment, users, onAssign }) {
  const { user } = useAuth();
  const mode = assignmentControl(user, assignment);
  const assignee = assignment?.assignee;

  if (mode === 'select') {
    return (
      <label className="assign">
        <span className="sr-only">Assignee for {candidateName}</span>
        <select className="input-field assign-select" value={assignee?.id || ''} onChange={(e) => onAssign(e.target.value || null)}>
          <option value="">Unassigned</option>
          {users.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
        </select>
      </label>
    );
  }
  if (mode === 'take') {
    return <button type="button" className="btn btn-secondary btn-compact" onClick={() => onAssign(user.id)}>Take review</button>;
  }
  return <span className="assign-name">{assignee.id === user.id ? 'You' : assignee.name}</span>;
}
