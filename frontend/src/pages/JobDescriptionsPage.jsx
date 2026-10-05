import React, { useState, useEffect, useRef } from 'react';
import { 
  FileText, 
  Plus, 
  Sparkles, 
  Save, 
  UploadCloud, 
  Clock, 
  AlertCircle, 
  Check, 
  ExternalLink,
  FileCheck,
  Loader2,
  Trash2,
  Info,
  X
} from 'lucide-react';
import { jdApi, retentionApi } from '../lib/api';

const ACCEPTED_FILE_TYPES = ".pdf,.docx,.doc,.txt,.rtf,.odt,.md,.jpg,.jpeg,.png,.webp,.bmp,.tiff,.tif,.jfif";

export default function JobDescriptionsPage() {
  const [jds, setJds] = useState([]);
  const [selectedJd, setSelectedJd] = useState(null);
  const [isCreating, setIsCreating] = useState(false);
  
  // Form fields
  const [title, setTitle] = useState('');
  const [jdText, setJdText] = useState('');
  const [fileUrl, setFileUrl] = useState(null);
  const [originalFilename, setOriginalFilename] = useState(null);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [summarizing, setSummarizing] = useState(false);
  const [extracting, setExtracting] = useState(false);
  const [notification, setNotification] = useState(null);
  const [dragActive, setDragActive] = useState(false);

  // Retention status
  const [retentionStatus, setRetentionStatus] = useState(null);
  const [showRetentionModal, setShowRetentionModal] = useState(false);
  const [cleaningRetention, setCleaningRetention] = useState(false);

  const fileInputRef = useRef(null);

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

  const loadRetentionStatus = async () => {
    try {
      const res = await retentionApi.getStatus();
      setRetentionStatus(res.data);
    } catch (err) {
      console.warn('Failed to load retention status:', err);
    }
  };

  useEffect(() => {
    loadJDs();
    loadRetentionStatus();
  }, []);

  const selectJd = (jd) => {
    setSelectedJd(jd);
    setIsCreating(false);
    setTitle(jd.title);
    setJdText(jd.jd_text);
    setFileUrl(jd.file_url || null);
    setOriginalFilename(jd.original_filename || null);
    setNotification(null);
  };

  const handleStartCreate = () => {
    setIsCreating(true);
    setSelectedJd(null);
    setTitle('');
    setJdText('');
    setFileUrl(null);
    setOriginalFilename(null);
    setNotification(null);
  };

  const handleFileUpload = async (file) => {
    if (!file) return;

    setExtracting(true);
    setNotification({
      type: 'info',
      message: `Analyzing and extracting text from "${file.name}" (OCR/Doc parsing)...`
    });

    const formData = new FormData();
    formData.append('file', file);

    try {
      const res = await jdApi.extractText(formData);
      const data = res.data;

      // Auto-populate title if empty or currently creating
      if (isCreating || !title.trim()) {
        setTitle(data.title || file.name.replace(/\.[^/.]+$/, ""));
      }
      setJdText(data.jd_text || '');
      setFileUrl(data.file_url || null);
      setOriginalFilename(data.original_filename || file.name);

      setNotification({
        type: 'success',
        message: `Successfully extracted text from "${file.name}"! You can review or edit below before saving.`
      });
    } catch (err) {
      console.error('Failed to extract text from JD file:', err);
      setNotification({
        type: 'error',
        message: err.response?.data?.detail || `Failed to extract text from "${file.name}". Please check the file format.`
      });
    } finally {
      setExtracting(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      if (!isCreating) {
        setIsCreating(true);
        setSelectedJd(null);
      }
      handleFileUpload(e.target.files[0]);
    }
  };

  const handleDrag = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      if (!isCreating) {
        setIsCreating(true);
        setSelectedJd(null);
      }
      handleFileUpload(e.dataTransfer.files[0]);
    }
  };

  const handleSave = async (e) => {
    e.preventDefault();
    if (!title.trim() || !jdText.trim()) return;

    setSaving(true);
    setNotification(null);

    const payload = {
      title: title.trim(),
      jd_text: jdText.trim(),
      file_url: fileUrl,
      original_filename: originalFilename,
    };

    try {
      if (isCreating) {
        const res = await jdApi.create(payload);
        setNotification({ type: 'success', message: 'Job Description created successfully!' });
        await loadJDs();
        selectJd(res.data);
      } else {
        const res = await jdApi.update(selectedJd.id, payload);
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

  const handleTriggerRetentionCleanup = async () => {
    setCleaningRetention(true);
    try {
      const res = await retentionApi.cleanup();
      await loadRetentionStatus();
      await loadJDs();
      setNotification({
        type: 'success',
        message: `Retention cleanup executed: Purged ${res.data.total_candidates_deleted} expired resume(s) and ${res.data.total_jds_deleted} expired JD(s).`
      });
    } catch (err) {
      setNotification({ type: 'error', message: 'Retention cleanup failed: ' + (err.response?.data?.detail || err.message) });
    } finally {
      setCleaningRetention(false);
    }
  };

  return (
    <div className="page-body">
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '2rem', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <h1 className="page-header-title" style={{ margin: 0 }}>
              Job Descriptions
            </h1>
            {retentionStatus && (
              <button
                onClick={() => setShowRetentionModal(true)}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.35rem',
                  fontSize: '0.75rem',
                  fontWeight: 600,
                  backgroundColor: 'var(--bg-subtle)',
                  color: 'var(--text-muted)',
                  border: '1px solid var(--border-color)',
                  borderRadius: '20px',
                  padding: '0.25rem 0.65rem',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease'
                }}
                title="Click to view data retention policy"
              >
                <Clock size={12} color="var(--primary)" />
                <span>{retentionStatus.data_retention_days}-Day Retention Active</span>
              </button>
            )}
          </div>
          <p className="page-header-subtitle" style={{ marginTop: '0.35rem' }}>
            Define, upload, version, and summarize job specifications. Upload PDF, Word, or Image formats with automatic OCR text extraction.
          </p>
        </div>

        <div style={{ display: 'flex', gap: '0.75rem' }}>
          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileChange}
            accept={ACCEPTED_FILE_TYPES}
            style={{ display: 'none' }}
          />

          <button
            onClick={() => fileInputRef.current?.click()}
            className="btn btn-secondary"
            disabled={extracting}
          >
            {extracting ? <Loader2 size={16} className="animate-spin" /> : <UploadCloud size={16} />}
            {extracting ? 'Extracting...' : 'Upload JD File'}
          </button>

          <button
            onClick={handleStartCreate}
            className="btn btn-primary"
          >
            <Plus size={16} /> Create Job Description
          </button>
        </div>
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
          backgroundColor: notification.type === 'success' 
            ? 'var(--success-bg)' 
            : notification.type === 'info' 
              ? 'var(--primary-light)' 
              : 'var(--danger-bg)',
          color: notification.type === 'success' 
            ? 'var(--success-text)' 
            : notification.type === 'info'
              ? 'var(--primary)'
              : 'var(--danger-text)'
        }}>
          {notification.type === 'success' && <Check size={16} />}
          {notification.type === 'info' && <Loader2 size={16} className="animate-spin" />}
          {notification.type === 'error' && <AlertCircle size={16} />}
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

                  {jd.original_filename && (
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.25rem', fontSize: '0.7rem', color: 'var(--primary)', marginBottom: '0.35rem' }}>
                      <FileCheck size={12} />
                      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {jd.original_filename}
                      </span>
                    </div>
                  )}

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
                No job descriptions yet. Click "Create Job Description" or "Upload JD File" above.
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
                <h3 style={{ fontSize: '1.125rem', fontWeight: 800, color: 'var(--text-main)', margin: 0 }}>
                  {isCreating ? 'New Job Description' : title}
                </h3>
                {!isCreating && selectedJd && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.75rem', color: 'var(--text-subtle)', marginTop: '0.2rem' }}>
                    <span>Version {selectedJd.jd_version}</span>
                    <span>•</span>
                    <span>Created {new Date(selectedJd.created_at).toLocaleDateString()}</span>
                    {selectedJd.file_url && (
                      <>
                        <span>•</span>
                        <a 
                          href={selectedJd.file_url} 
                          target="_blank" 
                          rel="noopener noreferrer"
                          style={{ display: 'inline-flex', alignItems: 'center', gap: '0.2rem', color: 'var(--primary)', textDecoration: 'none' }}
                        >
                          <FileCheck size={12} />
                          <span>{selectedJd.original_filename || 'Original Document'}</span>
                          <ExternalLink size={10} />
                        </a>
                      </>
                    )}
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

          {/* Drag & Drop File Upload Area */}
          <div 
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            style={{
              border: dragActive ? '2px dashed var(--primary)' : '1px dashed var(--border-color)',
              backgroundColor: dragActive ? 'var(--primary-light)' : 'var(--bg-subtle)',
              borderRadius: 'var(--radius-md)',
              padding: '1.25rem',
              textAlign: 'center',
              cursor: 'pointer',
              marginBottom: '1.5rem',
              transition: 'all 0.2s ease',
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: '0.4rem'
            }}
          >
            {extracting ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', color: 'var(--primary)' }}>
                <Loader2 size={20} className="animate-spin" />
                <span style={{ fontSize: '0.875rem', fontWeight: 600 }}>Extracting text from file using OCR...</span>
              </div>
            ) : originalFilename ? (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', padding: '0 0.5rem' }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <FileCheck size={18} color="var(--primary)" />
                  <span style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-main)' }}>
                    Attached file: {originalFilename}
                  </span>
                  {fileUrl && (
                    <a
                      href={fileUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={(e) => e.stopPropagation()}
                      style={{ fontSize: '0.75rem', color: 'var(--primary)', marginLeft: '0.5rem', textDecoration: 'underline' }}
                    >
                      View file
                    </a>
                  )}
                </div>
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    fileInputRef.current?.click();
                  }}
                  style={{
                    backgroundColor: 'transparent',
                    border: '1px solid var(--border-color)',
                    borderRadius: '4px',
                    padding: '0.2rem 0.5rem',
                    fontSize: '0.75rem',
                    cursor: 'pointer'
                  }}
                >
                  Replace File
                </button>
              </div>
            ) : (
              <>
                <UploadCloud size={24} color="var(--primary)" />
                <div style={{ fontSize: '0.875rem', fontWeight: 600, color: 'var(--text-main)' }}>
                  Drop JD file here or <span style={{ color: 'var(--primary)', textDecoration: 'underline' }}>browse</span>
                </div>
                <div style={{ fontSize: '0.75rem', color: 'var(--text-subtle)' }}>
                  Supports PDF (.pdf), Word Documents (.docx, .doc, .rtf, .txt), and Images (.jpg, .png, .webp, .bmp)
                </div>
              </>
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
                placeholder="Paste the full job requirements, skills, responsibilities, or upload a document/image above to extract automatically..."
                className="input-field"
                style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8125rem', lineHeight: 1.6 }}
              />
            </div>

            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', paddingTop: '0.5rem' }}>
              <div style={{ fontSize: '0.75rem', color: 'var(--text-subtle)' }}>
                {fileUrl ? `Stored in dedicated JD storage` : 'Direct text input'}
              </div>

              <div style={{ display: 'flex', gap: '0.75rem' }}>
                <button
                  type="submit"
                  disabled={saving || extracting}
                  className="btn btn-primary"
                  style={{ minWidth: '130px' }}
                >
                  <Save size={16} />
                  {saving ? 'Saving...' : isCreating ? 'Create JD' : 'Save Changes'}
                </button>
              </div>
            </div>
          </form>
        </div>
      </div>

      {/* Retention Policy Modal */}
      {showRetentionModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          backgroundColor: 'rgba(0,0,0,0.5)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1000,
          backdropFilter: 'blur(3px)'
        }}>
          <div className="card" style={{ maxWidth: '480px', width: '90%', padding: '1.5rem', boxShadow: '0 20px 25px -5px rgba(0,0,0,0.2)' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Clock size={20} color="var(--primary)" />
                <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 700 }}>Data Retention Policy</h3>
              </div>
              <button
                onClick={() => setShowRetentionModal(false)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }}
              >
                <X size={18} />
              </button>
            </div>

            <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', lineHeight: 1.5, marginBottom: '1.25rem' }}>
              Per configuration in <code>.env</code>, candidate resumes, chunk embeddings in Qdrant & OpenSearch, and Job Descriptions are stored for a maximum period of <strong>{retentionStatus?.data_retention_days || 30} days</strong>.
            </p>

            <div style={{ backgroundColor: 'var(--bg-subtle)', borderRadius: '8px', padding: '1rem', fontSize: '0.8125rem', marginBottom: '1.25rem', display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-subtle)' }}>Generic Retention Period:</span>
                <strong>{retentionStatus?.data_retention_days} days (.env)</strong>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-subtle)' }}>Resume Storage Folder:</span>
                <code>./uploads/resumes</code>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-subtle)' }}>JD Storage Folder:</span>
                <code>./uploads/job_descriptions</code>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-subtle)' }}>Auto-Cleanup Interval:</span>
                <span>Every {retentionStatus?.cleanup_interval_hours} hours</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-subtle)' }}>Currently Expired Resumes:</span>
                <span>{retentionStatus?.expired_candidates_count || 0}</span>
              </div>
              <div style={{ display: 'flex', justifyContent: 'space-between' }}>
                <span style={{ color: 'var(--text-subtle)' }}>Currently Expired JDs:</span>
                <span>{retentionStatus?.expired_positions_count || 0}</span>
              </div>
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
              <button
                type="button"
                onClick={handleTriggerRetentionCleanup}
                disabled={cleaningRetention}
                className="btn btn-secondary"
                style={{ fontSize: '0.8125rem' }}
              >
                {cleaningRetention ? <Loader2 size={14} className="animate-spin" /> : <Trash2 size={14} />}
                {cleaningRetention ? 'Purging...' : 'Run Cleanup Now'}
              </button>

              <button
                type="button"
                onClick={() => setShowRetentionModal(false)}
                className="btn btn-primary"
                style={{ fontSize: '0.8125rem' }}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
