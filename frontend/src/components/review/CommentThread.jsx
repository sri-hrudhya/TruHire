import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../../context/AuthContext';
import { useMeta } from '../../context/MetaContext';
import { reviewApi } from '../../lib/api';
import { canEditComment, formatRelativeTime } from '../../lib/review';
import './review.css';

const RATINGS = [1, 2, 3, 4, 5];

// Shared feedback on a candidate. Everyone signed in reads it; the author (or an admin) can edit or delete.
export default function CommentThread({ candidateId, positionId = null }) {
  const { user } = useAuth();
  const { comment_max_chars: maxChars } = useMeta();
  const [comments, setComments] = useState(null);
  const [body, setBody] = useState('');
  const [rating, setRating] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(null); // { id, body }

  const load = useCallback(async () => {
    try {
      setComments((await reviewApi.listComments(candidateId, positionId)).data);
    } catch (err) {
      setComments([]);
      setError(err.response?.data?.detail || 'Could not load comments.');
    }
  }, [candidateId, positionId]);

  useEffect(() => { load(); }, [load]);

  const run = async (action) => {
    setBusy(true);
    setError(null);
    try { await action(); await load(); } catch (err) {
      const detail = err.response?.data?.detail;
      setError(Array.isArray(detail) ? detail.map((d) => d.msg).join('; ') : detail || 'That did not save. Try again.');
    } finally { setBusy(false); }
  };

  const post = (e) => {
    e.preventDefault();
    if (!body.trim()) return;
    run(async () => {
      await reviewApi.addComment(candidateId, { body, rating: rating ? Number(rating) : null, position_id: positionId });
      setBody('');
      setRating('');
    });
  };

  const saveEdit = () => run(async () => {
    await reviewApi.updateComment(editing.id, { body: editing.body });
    setEditing(null);
  });

  return (
    <section className="thread" aria-label="Feedback">
      {comments === null && <p className="dek">Loading feedback…</p>}
      {comments?.length === 0 && !error && <p className="dek">No feedback yet. Add the first note.</p>}

      <ul className="thread-list">
        {(comments || []).map((c) => (
          <li key={c.id} className="thread-item">
            <div className="cluster cluster-tight">
              <strong>{c.author?.name || 'Former user'}</strong>
              {c.rating && <span className="thread-rating" aria-label={`Rated ${c.rating} out of 5`}>{c.rating}/5</span>}
              <span className="slug">{formatRelativeTime(Date.now(), c.created_at)}{c.edited_at ? ' · edited' : ''}</span>
            </div>
            {editing?.id === c.id ? (
              <div className="stack stack-tight">
                <textarea className="input-field" rows={3} maxLength={maxChars} value={editing.body} onChange={(e) => setEditing({ ...editing, body: e.target.value })} aria-label="Edit comment" />
                <span className="cluster cluster-tight">
                  <button type="button" className="btn btn-primary btn-compact" onClick={saveEdit} disabled={busy || !editing.body.trim()}>Save</button>
                  <button type="button" className="btn btn-secondary btn-compact" onClick={() => setEditing(null)}>Cancel</button>
                </span>
              </div>
            ) : (
              <p className="thread-body">{c.body}</p>
            )}
            {canEditComment(user, c) && c.can_edit && editing?.id !== c.id && (
              <span className="cluster cluster-tight thread-actions">
                <button type="button" className="link-btn" onClick={() => setEditing({ id: c.id, body: c.body })}>Edit</button>
                <button type="button" className="link-btn" onClick={() => run(() => reviewApi.deleteComment(c.id))}>Delete</button>
              </span>
            )}
          </li>
        ))}
      </ul>

      <form className="thread-form" onSubmit={post}>
        <label className="sr-only" htmlFor={`comment-${candidateId}`}>Add feedback</label>
        <textarea id={`comment-${candidateId}`} className="input-field" rows={2} maxLength={maxChars} value={body} onChange={(e) => setBody(e.target.value)} placeholder="Add feedback for the team" />
        <div className="cluster cluster-between">
          <label className="cluster cluster-tight dek">
            Rating
            <select className="input-field thread-rating-select" value={rating} onChange={(e) => setRating(e.target.value)}>
              <option value="">None</option>
              {RATINGS.map((r) => <option key={r} value={r}>{r}</option>)}
            </select>
          </label>
          <span className="cluster cluster-tight">
            <span className="slug">{body.length}/{maxChars}</span>
            <button type="submit" className="btn btn-primary btn-compact" disabled={busy || !body.trim()}>Post</button>
          </span>
        </div>
        {error && <p className="thread-error" role="alert">{error}</p>}
      </form>
    </section>
  );
}
