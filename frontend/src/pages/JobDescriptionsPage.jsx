import React, { useState, useEffect } from 'react';
import { 
  FileText, 
  Plus, 
  Sparkles, 
  Save, 
  History, 
  Layers,
  AlertCircle,
  Check
} from 'lucide-react';
import { jdApi } from '../lib/api';

export default function JobDescriptionsPage() {
  const [jds, setJds] = useState([]);
  const [selectedJd, setSelectedJd] = useState(null);
  const [isCreating, setIsCreating] = useState(false);
  
  // Form fields
  const [title, setTitle] = useState('');
  const [jdText, setJdText] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [summarizing, setSummarizing] = useState(false);
  const [notification, setNotification] = useState(null);

  const loadJDs = async () => {
    try {
      const res = await jdApi.list();
      setJds(res.data);
      if (res.data.length > 0 && !selectedJd && !isCreating) {
        selectJd(res.data[0]);
      }
    } catch (err) {
      console.error('Failed to load JDs:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadJDs();
  }, []);

  const selectJd = (jd) => {
    setSelectedJd(jd);
    setIsCreating(false);
    setTitle(jd.title);
    setJdText(jd.jd_text);
    setNotification(null);
  };

  const handleStartCreate = () => {
    setIsCreating(true);
    setSelectedJd(null);
    setTitle('');
    setJdText('');
    setNotification(null);
  };

  const handleSave = async (e) => {
    e.preventDefault();
    if (!title.trim() || !jdText.trim()) return;

    setSaving(true);
    setNotification(null);

    try {
      if (isCreating) {
        const res = await jdApi.create({ title: title.trim(), jd_text: jdText.trim() });
        setNotification({ type: 'success', message: 'Job Description created successfully!' });
        await loadJDs();
        selectJd(res.data);
      } else {
        const res = await jdApi.update(selectedJd.id, { title: title.trim(), jd_text: jdText.trim() });
        setNotification({ 
          type: 'success', 
          message: res.data.jd_version > selectedJd.jd_version 
            ? `Saved! JD text modified: Version bumped to v${res.data.jd_version}`
            : 'Job Description updated successfully.'
        });
        setSelectedJd(res.data);
        await loadJDs();
      }
    } catch (err) {
      setNotification({ type: 'error', message: err.response?.data?.detail || 'Failed to save JD.' });
    } finally {
      setSaving(false);
    }
  };

  const handleSummarize = async () => {
    if (!selectedJd) return;

    setSummarizing(true);
    setNotification(null);

    try {
      const res = await jdApi.summarize(selectedJd.id);
      setSelectedJd(prev => ({ ...prev, jd_summary: res.data.jd_summary }));
      setNotification({ type: 'success', message: 'AI Summary generated successfully!' });
      await loadJDs();
    } catch (err) {
      setNotification({ type: 'error', message: 'Failed to summarize Job Description.' });
    } finally {
      setSummarizing(false);
    }
  };

  return (
    <div className="page-body">
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '2rem' }}>
        <div>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--text-main)' }}>
            Job Descriptions
          </h1>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
            Define, version, and summarize job specifications. Used for candidate matching and scoring in Search.
          </p>
        </div>

        <button
          onClick={handleStartCreate}
          className="btn btn-primary"
        >
          <Plus size={16} /> Create Job Description
        </button>
      </div>

      {notification && (
        <div style={{
          padding: '0.75rem 1rem',
          borderRadius: '8px',
          marginBottom: '1.5rem',
          fontSize: '0.875rem',
          display: 'flex',
          alignItems: 'center',
          gap: '0.5rem',
          backgroundColor: notification.type === 'success' ? 'var(--success-bg)' : 'var(--danger-bg)',
          color: notification.type === 'success' ? 'var(--success-text)' : 'var(--danger-text)'
        }}>
          {notification.type === 'success' ? <Check size={16} /> : <AlertCircle size={16} />}
          <span>{notification.message}</span>
        </div>
      )}

      {/* Main 2-column layout: List on left, Flat Editor on right */}
      <div style={{ display: 'grid', gridTemplateColumns: '320px 1fr', gap: '2rem', alignItems: 'start' }}>
        {/* Left: JDs Directory */}
        <div className="card" style={{ padding: '1rem' }}>
          <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-subtle)', textTransform: 'uppercase', marginBottom: '0.75rem', padding: '0 0.5rem' }}>
            All Job Descriptions ({jds.length})
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem', maxHeight: '680px', overflowY: 'auto' }}>
            {jds.map((jd) => {
              const isSelected = selectedJd?.id === jd.id && !isCreating;
              return (
                <div
                  key={jd.id}
                  onClick={() => selectJd(jd)}
                  style={{
                    padding: '0.875rem',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    backgroundColor: isSelected ? 'var(--primary-light)' : 'transparent',
                    border: isSelected ? '1px solid var(--primary-border)' : '1px solid transparent',
                    transition: 'all 0.15s ease'
                  }}
                  className="card-hover"
                >
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.25rem' }}>
                    <span style={{ fontSize: '0.875rem', fontWeight: 700, color: isSelected ? 'var(--primary)' : 'var(--text-main)' }}>
                      {jd.title}
                    </span>
                    <span className="badge badge-primary" style={{ fontSize: '0.65rem', padding: '0.15rem 0.45rem' }}>
                      v{jd.jd_version}
                    </span>
                  </div>
                  <p style={{
                    fontSize: '0.75rem',
                    color: 'var(--text-muted)',
                    overflow: 'hidden',
                    display: '-webkit-box',
                    WebkitLineClamp: 2,
                    WebkitBoxOrient: 'vertical',
                    lineHeight: 1.4
                  }}>
                    {jd.jd_summary || jd.jd_text}
                  </p>
                </div>
              );
            })}

            {jds.length === 0 && !loading && (
              <div style={{ textAlign: 'center', padding: '2rem 1rem', color: 'var(--text-subtle)', fontSize: '0.8125rem' }}>
                No job descriptions yet. Click "Create Job Description" above.
              </div>
            )}
          </div>
        </div>

        {/* Right: Flat Editor & Summarizer */}
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
              <div style={{
                width: '36px',
                height: '36px',
                borderRadius: '8px',
                backgroundColor: 'var(--bg-subtle)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--primary)'
              }}>
                <FileText size={20} />
              </div>
              <div>
                <h3 style={{ fontSize: '1.125rem', fontWeight: 800, color: 'var(--text-main)' }}>
                  {isCreating ? 'New Job Description' : title}
                </h3>
                {!isCreating && selectedJd && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.75rem', color: 'var(--text-subtle)' }}>
                    <span>Version {selectedJd.jd_version}</span>
                    <span>•</span>
                    <span>Created {new Date(selectedJd.created_at).toLocaleDateString()}</span>
                  </div>
                )}
              </div>
            </div>

            {!isCreating && selectedJd && (
              <button
                type="button"
                onClick={handleSummarize}
                disabled={summarizing}
                className="btn btn-secondary"
                style={{ fontSize: '0.8125rem', padding: '0.5rem 0.875rem' }}
              >
                <Sparkles size={15} color="var(--primary)" />
                {summarizing ? 'Summarizing...' : selectedJd.jd_summary ? 'Re-Summarize' : 'Summarize JD'}
              </button>
            )}
          </div>

          {/* AI Summary Banner (if generated) */}
          {!isCreating && selectedJd?.jd_summary && (
            <div style={{
              backgroundColor: 'var(--primary-light)',
              border: '1px solid var(--primary-border)',
              borderRadius: 'var(--radius-md)',
              padding: '1.25rem',
              marginBottom: '1.5rem'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '0.5rem', color: 'var(--primary)', fontWeight: 700, fontSize: '0.8125rem' }}>
                <Sparkles size={15} />
                <span>AI Structured Summary (v{selectedJd.jd_version})</span>
              </div>
              <div style={{ fontSize: '0.875rem', lineHeight: 1.6, color: 'var(--text-main)', whiteSpace: 'pre-wrap' }}>
                {selectedJd.jd_summary}
              </div>
            </div>
          )}

          {/* Edit / Create Form */}
          <form onSubmit={handleSave} style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            <div>
              <label className="input-label">Job Title</label>
              <input
                type="text"
                required
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. Senior Machine Learning Engineer"
                className="input-field"
              />
            </div>

            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
                <label className="input-label" style={{ marginBottom: 0 }}>Full Job Description & Requirements</label>
                {!isCreating && (
                  <span style={{ fontSize: '0.75rem', color: 'var(--warning-text)', backgroundColor: 'var(--warning-bg)', padding: '0.15rem 0.5rem', borderRadius: '4px' }}>
                    Note: Modifying text bumps JD version
                  </span>
                )}
              </div>
              <textarea
                required
                rows={14}
                value={jdText}
                onChange={(e) => setJdText(e.target.value)}
                placeholder="Paste the full job requirements, skills, responsibilities, and qualifications..."
                className="input-field"
                style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8125rem', lineHeight: 1.6 }}
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', paddingTop: '0.5rem' }}>
              <button
                type="submit"
                disabled={saving}
                className="btn btn-primary"
                style={{ minWidth: '130px' }}
              >
                <Save size={16} />
                {saving ? 'Saving...' : isCreating ? 'Create JD' : 'Save Changes'}
              </button>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
}
