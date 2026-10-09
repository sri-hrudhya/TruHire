import React, { useState, useEffect, useRef } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
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
  X,
  Users,
  User,
  Search,
  Mail
} from 'lucide-react';
import { jdApi, retentionApi } from '../lib/api';
import ResumePreviewModal from '../components/ResumePreviewModal';
import EmailComposer, { RecipientSelector, REQUIREMENT_STATUSES, EmailStatusBadge } from '../components/EmailComposer';

const ACCEPTED_FILE_TYPES = ".pdf,.docx,.doc,.txt,.rtf,.odt,.md,.jpg,.jpeg,.png,.webp,.bmp,.tiff,.tif,.jfif";

export default function JobDescriptionsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [jds, setJds] = useState([]);
  const [selectedJd, setSelectedJd] = useState(null);
  const [isCreating, setIsCreating] = useState(false);
  const [activeTab, setActiveTab] = useState('matches'); // 'matches' | 'spec'
  
  // Matching candidates state
  const [matches, setMatches] = useState([]);
  const [loadingMatches, setLoadingMatches] = useState(false);
  const [minMatchScore, setMinMatchScore] = useState(50);
  const [matchCoverage, setMatchCoverage] = useState(null); // { unindexed, lexicalDown }
  const [statusError, setStatusError] = useState(null);

  // Email shortlisted candidates (step: null | 'select' | 'compose')
  const [emailStep, setEmailStep] = useState(null);
  const [emailSelection, setEmailSelection] = useState([]);

  // Resume preview state
  const [previewCandidate, setPreviewCandidate] = useState(null);
  const [isResumePreviewOpen, setIsResumePreviewOpen] = useState(false);

  // Deletion confirmation modal
  const [deletingJd, setDeletingJd] = useState(null);
  const [isDeleting, setIsDeleting] = useState(false);

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
  const [searchFilter, setSearchFilter] = useState('');

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
        // Restore the requirement in the URL (e.g. after returning from a candidate profile)
        const requestedId = searchParams.get('id');
        selectJd(res.data.find((jd) => jd.id === requestedId) || res.data[0]);
      }
    } catch (err) {
      console.error('Failed to load Requirements:', err);
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

  // Files are served only to authenticated requests, so fetch as a blob. The tab is opened
  // synchronously (inside the click) so popup blockers allow it, then pointed at the blob.
  const openJdFile = async (jdId) => {
    const tab = window.open('', '_blank');
    try {
      const res = await jdApi.getFile(jdId);
      const url = URL.createObjectURL(res.data);
      if (tab) tab.location.href = url;
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    } catch (err) {
      if (tab) tab.close();
      setStatusError('Could not open the requirement file.');
    }
  };

  const loadMatches = async (jdId) => {
    setLoadingMatches(true);
    try {
      const res = await jdApi.getMatches(jdId, 50);
      setMatches(res.data?.matches || []);
      if (typeof res.data?.min_match_score === 'number') setMinMatchScore(res.data.min_match_score);
      setMatchCoverage({
        unindexed: res.data?.unindexed_candidates || 0,
        lexicalDown: res.data?.retrieval ? !res.data.retrieval.lexical : false,
      });
    } catch (err) {
      console.error('Failed to load matches for requirement:', err);
      setMatches([]);
      setMatchCoverage(null);
    } finally {
      setLoadingMatches(false);
    }
  };

  useEffect(() => {
    loadJDs();
    loadRetentionStatus();
  }, []);

  const handleRequirementStatusChange = async (candidateId, status) => {
    const jdId = selectedJd.id;
    const previous = matches;
    setStatusError(null);
    setMatches((ms) => ms.map((m) => (m.candidate.id === candidateId ? { ...m, requirement_status: status } : m)));
    try {
      await jdApi.setCandidateStatus(jdId, candidateId, status);
    } catch (err) {
      setMatches(previous);
      setStatusError(err?.response?.data?.detail || 'Could not update the candidate status.');
    }
  };

  const emailCandidates = matches.map((m) => ({
    ...m.candidate,
    match_score: m.match_score,
    requirement_status: m.requirement_status,
    last_email: m.last_email,
  }));
  const shortlistedForEmail = emailCandidates.filter((c) => c.requirement_status === 'Shortlisted');

  const openEmailShortlisted = () => {
    setEmailSelection(shortlistedForEmail.filter((c) => c.email).map((c) => c.id));
    setEmailStep('select');
  };

  const selectJd = (jd) => {
    setSelectedJd(jd);
    setEmailStep(null);
    setStatusError(null);
    setIsCreating(false);
    setTitle(jd.title);
    setJdText(jd.jd_text);
    setFileUrl(jd.file_url || null);
    setOriginalFilename(jd.original_filename || null);
    setNotification(null);
    setActiveTab('matches');
    loadMatches(jd.id);
    setSearchParams({ id: jd.id }, { replace: true });
  };

  const handleStartCreate = () => {
    setIsCreating(true);
    setSelectedJd(null);
    setTitle('');
    setJdText('');
    setFileUrl(null);
    setOriginalFilename(null);
    setNotification(null);
    setActiveTab('spec');
    setMatches([]);
    setSearchParams({}, { replace: true });
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
      console.error('Failed to extract text from requirement file:', err);
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
        setActiveTab('spec');
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
        setActiveTab('spec');
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
        setNotification({ type: 'success', message: 'Requirement created successfully!' });
        await loadJDs();
        selectJd(res.data);
      } else {
        const res = await jdApi.update(selectedJd.id, payload);
        setNotification({ 
          type: 'success', 
          message: res.data.jd_version > selectedJd.jd_version 
            ? `Saved! Requirement text modified: Version bumped to v${res.data.jd_version}`
            : 'Requirement updated successfully.'
        });
        setSelectedJd(res.data);
        await loadJDs();
        loadMatches(res.data.id);
      }
    } catch (err) {
      setNotification({ type: 'error', message: err.response?.data?.detail || 'Failed to save requirement.' });
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
      setNotification({ type: 'error', message: 'Failed to summarize requirement.' });
    } finally {
      setSummarizing(false);
    }
  };

  const handleConfirmDelete = async () => {
    if (!deletingJd) return;

    setIsDeleting(true);
    try {
      await jdApi.delete(deletingJd.id);
      
      // Update UI immediately after deletion
      const updatedList = jds.filter(item => item.id !== deletingJd.id);
      setJds(updatedList);
      
      setNotification({
        type: 'success',
        message: `Requirement ${deletingJd.display_id || ''} ("${deletingJd.title}") removed successfully. Candidates and resumes were not deleted.`
      });

      if (selectedJd?.id === deletingJd.id) {
        if (updatedList.length > 0) {
          selectJd(updatedList[0]);
        } else {
          handleStartCreate();
        }
      }

      setDeletingJd(null);
    } catch (err) {
      console.error('Failed to delete requirement:', err);
      setNotification({
        type: 'error',
        message: err.response?.data?.detail || 'Failed to remove requirement.'
      });
    } finally {
      setIsDeleting(false);
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
        message: `Retention cleanup executed: Purged ${res.data.total_candidates_deleted} expired resume(s) and ${res.data.total_jds_deleted} expired requirement(s).`
      });
    } catch (err) {
      setNotification({ type: 'error', message: 'Retention cleanup failed: ' + (err.response?.data?.detail || err.message) });
    } finally {
      setCleaningRetention(false);
    }
  };

  // Filtered requirements list
  const filteredJds = jds.filter(jd => {
    if (!searchFilter.trim()) return true;
    const q = searchFilter.toLowerCase();
    return (
      jd.title?.toLowerCase().includes(q) ||
      (jd.display_id && jd.display_id.toLowerCase().includes(q)) ||
      jd.jd_text?.toLowerCase().includes(q)
    );
  });

  return (
    <div className="page-body">
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '2rem', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <h1 className="page-header-title" style={{ margin: 0 }}>
              Requirements
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
            Define, upload, version, and match candidates against hiring requirements. Upload PDF, Word, or Image formats with automatic text extraction.
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
            {extracting ? 'Extracting...' : 'Upload Requirement File'}
          </button>

          <button
            onClick={handleStartCreate}
            className="btn btn-primary"
          >
            <Plus size={16} /> Create Requirement
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
              : 'var(--danger-text)',
          border: `1px solid ${notification.type === 'success' ? 'var(--success)' : notification.type === 'info' ? 'var(--primary-border)' : 'var(--danger)'}`
        }}>
          {notification.type === 'success' && <Check size={16} />}
          {notification.type === 'info' && <Loader2 size={16} className="animate-spin" />}
          {notification.type === 'error' && <AlertCircle size={16} />}
          <span>{notification.message}</span>
          <button
            onClick={() => setNotification(null)}
            style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: 'inherit' }}
          >
            <X size={15} />
          </button>
        </div>
      )}

      {/* Main 2-column layout: List on left, Matches & Editor on right */}
      <div style={{ display: 'grid', gridTemplateColumns: '340px 1fr', gap: '2rem', alignItems: 'start' }}>
        {/* Left: Requirements Directory */}
        <div className="card" style={{ padding: '1.25rem' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.75rem' }}>
            <div style={{ fontSize: '0.75rem', fontWeight: 800, color: 'var(--text-subtle)', textTransform: 'uppercase' }}>
              All Requirements ({jds.length})
            </div>
            <button
              onClick={handleStartCreate}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--primary)',
                fontSize: '0.75rem',
                fontWeight: 700,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '0.2rem'
              }}
            >
              <Plus size={14} /> New
            </button>
          </div>

          {/* Search requirements */}
          {jds.length > 4 && (
            <div style={{ position: 'relative', marginBottom: '0.75rem' }}>
              <Search size={14} color="var(--text-subtle)" style={{ position: 'absolute', left: '10px', top: '10px' }} />
              <input
                type="text"
                value={searchFilter}
                onChange={(e) => setSearchFilter(e.target.value)}
                placeholder="Filter requirements..."
                className="input-field"
                style={{ paddingLeft: '32px', fontSize: '0.75rem', padding: '0.4rem 0.6rem 0.4rem 32px' }}
              />
            </div>
          )}

          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem', maxHeight: '720px', overflowY: 'auto' }}>
            {filteredJds.map((jd) => {
              const isSelected = selectedJd?.id === jd.id && !isCreating;
              return (
                <div
                  key={jd.id}
                  onClick={() => selectJd(jd)}
                  style={{
                    padding: '0.875rem 1rem',
                    borderRadius: '8px',
                    cursor: 'pointer',
                    backgroundColor: isSelected ? 'var(--primary-light)' : 'transparent',
                    border: isSelected ? '1px solid var(--primary-border)' : '1px solid var(--border-color)',
                    transition: 'all 0.15s ease',
                    position: 'relative'
                  }}
                  className="card-hover"
                >
                  {/* Top row: Display ID + Version + Remove Button */}
                  <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                      <span
                        className="badge badge-primary"
                        style={{
                          fontSize: '0.7rem',
                          fontFamily: 'var(--font-mono)',
                          fontWeight: 800,
                          padding: '0.15rem 0.45rem'
                        }}
                      >
                        {jd.display_id || 'TRU-JD-????'}
                      </span>
                      <span className="badge badge-neutral" style={{ fontSize: '0.65rem', padding: '0.1rem 0.4rem' }}>
                        v{jd.jd_version}
                      </span>
                    </div>

                    {/* Requirement Remove Button */}
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setDeletingJd(jd);
                      }}
                      title="Remove Requirement"
                      className="icon-btn"
                      style={{
                        padding: '4px',
                        color: 'var(--danger-text)',
                        opacity: isSelected ? 1 : 0.65
                      }}
                    >
                      <Trash2 size={14} />
                    </button>
                  </div>

                  {/* Title */}
                  <div style={{ fontSize: '0.875rem', fontWeight: 700, color: isSelected ? 'var(--primary)' : 'var(--text-main)', marginBottom: '0.25rem' }}>
                    {jd.title}
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
                    lineHeight: 1.4,
                    margin: 0
                  }}>
                    {jd.jd_summary || jd.jd_text}
                  </p>
                </div>
              );
            })}

            {filteredJds.length === 0 && !loading && (
              <div style={{ textAlign: 'center', padding: '2rem 1rem', color: 'var(--text-subtle)', fontSize: '0.8125rem' }}>
                {jds.length === 0
                  ? 'No requirements yet. Click "Create Requirement" or "Upload Requirement File" above.'
                  : 'No requirements match your filter.'}
              </div>
            )}
          </div>
        </div>

        {/* Right: Active Requirement View with Tabs (Matching Candidates vs Specification) */}
        <div className="card" style={{ padding: '1.75rem' }}>
          {/* Header */}
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '1.25rem', flexWrap: 'wrap', gap: '1rem' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
              <div style={{
                width: '42px',
                height: '42px',
                borderRadius: '8px',
                backgroundColor: 'var(--bg-subtle)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--primary)'
              }}>
                <FileText size={22} />
              </div>
              <div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', flexWrap: 'wrap' }}>
                  {!isCreating && selectedJd?.display_id && (
                    <span
                      className="badge badge-primary"
                      style={{
                        fontSize: '0.75rem',
                        fontFamily: 'var(--font-mono)',
                        fontWeight: 800
                      }}
                    >
                      {selectedJd.display_id}
                    </span>
                  )}
                  <h3 style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-main)', margin: 0 }}>
                    {isCreating ? 'New Requirement' : title}
                  </h3>
                </div>

                {!isCreating && selectedJd && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.75rem', color: 'var(--text-subtle)', marginTop: '0.25rem' }}>
                    <span>Version {selectedJd.jd_version}</span>
                    <span>•</span>
                    <span>Created {new Date(selectedJd.created_at).toLocaleDateString()}</span>
                    {selectedJd.file_url && (
                      <>
                        <span>•</span>
                        <button
                          type="button"
                          onClick={() => openJdFile(selectedJd.id)}
                          style={{ display: 'inline-flex', alignItems: 'center', gap: '0.2rem', color: 'var(--primary)', background: 'none', border: 'none', padding: 0, cursor: 'pointer', font: 'inherit' }}
                        >
                          <FileCheck size={12} />
                          <span>{selectedJd.original_filename || 'Original Document'}</span>
                          <ExternalLink size={10} />
                        </button>
                      </>
                    )}
                  </div>
                )}
              </div>
            </div>

            {/* Right Header Actions */}
            {!isCreating && selectedJd && (
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <button
                  type="button"
                  onClick={handleSummarize}
                  disabled={summarizing}
                  className="btn btn-secondary"
                  style={{ fontSize: '0.8125rem', padding: '0.45rem 0.85rem' }}
                >
                  <Sparkles size={15} color="var(--primary)" />
                  {summarizing ? 'Summarizing...' : selectedJd.jd_summary ? 'Re-Summarize' : 'AI Summarize'}
                </button>

                <button
                  type="button"
                  onClick={() => setDeletingJd(selectedJd)}
                  className="btn btn-secondary"
                  style={{ fontSize: '0.8125rem', padding: '0.45rem 0.85rem', color: 'var(--danger-text)' }}
                  title="Remove this requirement"
                >
                  <Trash2 size={15} />
                  <span>Remove</span>
                </button>
              </div>
            )}
          </div>

          {/* Navigation Tabs (when viewing existing requirement) */}
          {!isCreating && selectedJd && (
            <div style={{
              display: 'flex',
              gap: '0.5rem',
              borderBottom: '1px solid var(--border-color)',
              marginBottom: '1.5rem',
              paddingBottom: '0.5rem'
            }}>
              <button
                type="button"
                onClick={() => setActiveTab('matches')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.45rem',
                  padding: '0.5rem 1rem',
                  borderRadius: '6px',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: '0.875rem',
                  fontWeight: activeTab === 'matches' ? 700 : 500,
                  backgroundColor: activeTab === 'matches' ? 'var(--primary-light)' : 'transparent',
                  color: activeTab === 'matches' ? 'var(--primary)' : 'var(--text-muted)'
                }}
              >
                <Users size={16} />
                <span>Matching Candidates ({matches.length})</span>
              </button>

              <button
                type="button"
                onClick={() => setActiveTab('spec')}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.45rem',
                  padding: '0.5rem 1rem',
                  borderRadius: '6px',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: '0.875rem',
                  fontWeight: activeTab === 'spec' ? 700 : 500,
                  backgroundColor: activeTab === 'spec' ? 'var(--primary-light)' : 'transparent',
                  color: activeTab === 'spec' ? 'var(--primary)' : 'var(--text-muted)'
                }}
              >
                <FileText size={16} />
                <span>Requirement Specification & Edit</span>
              </button>
            </div>
          )}

          {/* TAB 1: MATCHING CANDIDATES */}
          {!isCreating && activeTab === 'matches' && (
            <div>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem' }}>
                <div>
                  <h4 style={{ margin: 0, fontSize: '1rem', fontWeight: 700 }}>
                    Candidates Matching {selectedJd?.display_id}
                  </h4>
                  <p style={{ margin: 0, fontSize: '0.8125rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                    Candidates scoring {minMatchScore}% or higher, ranked by hybrid semantic similarity, skill coverage, and experience fit. Use Search to see the full ranked pool.
                  </p>
                </div>

                <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <button
                    type="button"
                    onClick={openEmailShortlisted}
                    disabled={loadingMatches || shortlistedForEmail.length === 0}
                    className="btn btn-primary"
                    style={{ fontSize: '0.75rem', padding: '0.35rem 0.75rem' }}
                    title={shortlistedForEmail.length ? 'Draft personalized emails for shortlisted candidates' : 'Mark candidates as Shortlisted first'}
                  >
                    <Mail size={13} /> Email Shortlisted Candidates ({shortlistedForEmail.length})
                  </button>
                  <Link
                    to={`/search`}
                    className="btn btn-secondary"
                    style={{ fontSize: '0.75rem', padding: '0.35rem 0.75rem' }}
                  >
                    <Search size={13} /> Deep Search
                  </Link>
                </div>
              </div>

              {!loadingMatches && matchCoverage && (matchCoverage.unindexed > 0 || matchCoverage.lexicalDown) && (
                <div style={{ marginBottom: '1rem', color: 'var(--warning-text, var(--text-muted))', fontSize: '0.8125rem', display: 'flex', alignItems: 'flex-start', gap: '0.4rem' }}>
                  <AlertCircle size={14} style={{ flexShrink: 0, marginTop: '0.15rem' }} />
                  <span>
                    {matchCoverage.unindexed > 0 && `${matchCoverage.unindexed} resume(s) are not in the search index and cannot be scored for any requirement until they are reindexed. `}
                    {matchCoverage.lexicalDown && 'Keyword search (OpenSearch) is unavailable, so match scores are currently based on semantic similarity only and will read lower than usual.'}
                  </span>
                </div>
              )}

              {statusError && (
                <div style={{ marginBottom: '1rem', color: 'var(--danger-text)', fontSize: '0.8125rem', display: 'flex', alignItems: 'center', gap: '0.4rem' }}>
                  <AlertCircle size={14} /> {statusError}
                </div>
              )}

              {loadingMatches ? (
                <div style={{ textAlign: 'center', padding: '3rem' }}>
                  <Loader2 size={32} className="animate-spin" color="var(--primary)" style={{ margin: '0 auto 1rem' }} />
                  <div style={{ fontSize: '0.9375rem', fontWeight: 600 }}>Evaluating and scoring candidates against requirement...</div>
                </div>
              ) : matches.length === 0 ? (
                <div style={{ textAlign: 'center', padding: '3rem', backgroundColor: 'var(--bg-subtle)', borderRadius: '8px' }}>
                  <Users size={36} color="var(--text-subtle)" style={{ margin: '0 auto 1rem' }} />
                  <div style={{ fontSize: '1rem', fontWeight: 700 }}>No candidates at or above {minMatchScore}%</div>
                  <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', maxWidth: '400px', margin: '0.5rem auto 0' }}>
                    Upload more resumes in the Ingestion tab, or use the Search console to see every candidate's score against this requirement.
                  </p>
                </div>
              ) : (
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                  {matches.map((item, idx) => {
                    const cand = item.candidate;
                    const score = item.match_score ?? 0;
                    const scoreBadgeClass = score >= 80 ? 'badge-success' : score >= 60 ? 'badge-warning' : 'badge-neutral';
                    const matchedSkills = item.score_breakdown?.matched_skills || [];
                    const missingSkills = item.score_breakdown?.missing_skills || [];

                    return (
                      <div
                        key={cand.id || idx}
                        style={{
                          padding: '1.25rem',
                          borderRadius: 'var(--radius-md)',
                          border: '1px solid var(--border-color)',
                          backgroundColor: 'var(--bg-surface)',
                          borderLeft: `4px solid ${score >= 80 ? 'var(--success)' : score >= 60 ? 'var(--warning)' : 'var(--primary)'}`
                        }}
                        className="card-hover"
                      >
                        {/* Header: Candidate ID + Name + Match Score + Actions */}
                        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: '0.75rem', marginBottom: '0.75rem' }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                            <span
                              className="badge badge-primary"
                              style={{
                                fontFamily: 'var(--font-mono)',
                                fontSize: '0.75rem',
                                fontWeight: 800
                              }}
                            >
                              {cand.display_id || 'TRU-CN-????'}
                            </span>
                            <span style={{ fontSize: '1.0625rem', fontWeight: 800, color: 'var(--text-main)' }}>
                              {cand.candidate_name}
                            </span>
                            <select
                              className="input-field"
                              value={item.requirement_status || 'Pending Review'}
                              onChange={(e) => handleRequirementStatusChange(cand.id, e.target.value)}
                              aria-label={`Status of ${cand.candidate_name} for this requirement`}
                              style={{ width: 'auto', fontSize: '0.75rem', padding: '0.25rem 0.5rem' }}
                            >
                              {REQUIREMENT_STATUSES.map((st) => <option key={st} value={st}>{st}</option>)}
                            </select>
                            {item.last_email && <EmailStatusBadge status={item.last_email.status} />}
                          </div>

                          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                            <span className={`badge ${scoreBadgeClass}`} style={{ fontSize: '0.8125rem', fontWeight: 800 }}>
                              {score.toFixed(1)}% Match
                            </span>

                            <button
                              type="button"
                              onClick={() => {
                                setPreviewCandidate(cand);
                                setIsResumePreviewOpen(true);
                              }}
                              className="btn btn-secondary"
                              style={{ fontSize: '0.75rem', padding: '0.35rem 0.75rem' }}
                              title="Preview resume document in modal"
                            >
                              <FileText size={14} color="var(--primary)" /> View Resume
                            </button>

                            <Link
                              to={`/candidates/${cand.id}`}
                              className="btn btn-primary"
                              style={{ fontSize: '0.75rem', padding: '0.35rem 0.75rem' }}
                            >
                              <User size={14} /> Profile
                            </Link>
                          </div>
                        </div>

                        {/* Experience & Education */}
                        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.75rem' }}>
                          <span>{cand.years_experience} yrs experience</span>
                          <span>•</span>
                          <span>{cand.education || 'Education not specified'}</span>
                          {cand.email && (
                            <>
                              <span>•</span>
                              <span>{cand.email}</span>
                            </>
                          )}
                        </div>

                        {/* LLM Evaluation Narrative */}
                        {item.llm_summary && (
                          <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', lineHeight: 1.5, marginBottom: '0.75rem' }}>
                            {item.llm_summary}
                          </p>
                        )}

                        {/* Requirement citation */}
                        {item.cited_quote && (
                          <div style={{
                            padding: '0.5rem 0.75rem',
                            backgroundColor: 'var(--bg-subtle)',
                            borderRadius: '6px',
                            borderLeft: '3px solid var(--primary)',
                            fontSize: '0.75rem',
                            color: 'var(--text-muted)',
                            fontStyle: 'italic',
                            marginBottom: '0.75rem'
                          }}>
                            "{item.cited_quote}"
                          </div>
                        )}

                        {/* Skills breakdown */}
                        {(matchedSkills.length > 0 || missingSkills.length > 0) && (
                          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', paddingTop: '0.5rem', borderTop: '1px solid var(--border-color)' }}>
                            {matchedSkills.length > 0 && (
                              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                                <span style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--success-text)' }}>
                                  Matched Skills:
                                </span>
                                {matchedSkills.map((s, sIdx) => (
                                  <span key={sIdx} className="badge badge-success" style={{ fontSize: '0.65rem' }}>
                                    ✓ {s}
                                  </span>
                                ))}
                              </div>
                            )}

                            {missingSkills.length > 0 && (
                              <div style={{ display: 'flex', alignItems: 'center', gap: '0.4rem', flexWrap: 'wrap' }}>
                                <span style={{ fontSize: '0.7rem', fontWeight: 700, color: 'var(--text-subtle)' }}>
                                  Gaps / Missing:
                                </span>
                                {missingSkills.slice(0, 8).map((s, sIdx) => (
                                  <span key={sIdx} className="badge badge-neutral" style={{ fontSize: '0.65rem', opacity: 0.85 }}>
                                    {s}
                                  </span>
                                ))}
                                {missingSkills.length > 8 && (
                                  <span style={{ fontSize: '0.65rem', color: 'var(--text-subtle)' }}>
                                    +{missingSkills.length - 8} more
                                  </span>
                                )}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          )}

          {/* TAB 2: SPECIFICATION & EDIT */}
          {(isCreating || activeTab === 'spec') && (
            <div>
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
                      Drop requirement file here or <span style={{ color: 'var(--primary)', textDecoration: 'underline' }}>browse</span>
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
                  <label className="input-label">Requirement Title</label>
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
                    <label className="input-label" style={{ marginBottom: 0 }}>Requirement Specification & Criteria</label>
                    {!isCreating && (
                      <span style={{ fontSize: '0.75rem', color: 'var(--warning-text)', backgroundColor: 'var(--warning-bg)', padding: '0.15rem 0.5rem', borderRadius: '4px' }}>
                        Note: Modifying text bumps Requirement version
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
                    {fileUrl ? `Stored in dedicated requirements storage` : 'Direct text input'}
                  </div>

                  <div style={{ display: 'flex', gap: '0.75rem' }}>
                    <button
                      type="submit"
                      disabled={saving || extracting}
                      className="btn btn-primary"
                      style={{ minWidth: '150px' }}
                    >
                      <Save size={16} />
                      {saving ? 'Saving...' : isCreating ? 'Create Requirement' : 'Save Changes'}
                    </button>
                  </div>
                </div>
              </form>
            </div>
          )}
        </div>
      </div>

      {/* Confirmation Modal for Deleting Requirement */}
      {deletingJd && (
        <div style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(0,0,0,0.6)',
          backdropFilter: 'blur(3px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 1100
        }}>
          <div className="card" style={{ maxWidth: '480px', width: '90%', padding: '1.75rem', boxShadow: 'var(--shadow-lg)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem', marginBottom: '1rem', color: 'var(--danger-text)' }}>
              <div style={{
                width: '40px',
                height: '40px',
                borderRadius: '8px',
                backgroundColor: 'var(--danger-bg)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}>
                <Trash2 size={20} color="var(--danger)" />
              </div>
              <h3 style={{ margin: 0, fontSize: '1.15rem', fontWeight: 800, color: 'var(--text-main)' }}>
                Remove Requirement
              </h3>
            </div>

            <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', lineHeight: 1.5, marginBottom: '1rem' }}>
              Are you sure you want to remove requirement <strong>{deletingJd.display_id}</strong> (<em>{deletingJd.title}</em>)?
            </p>

            <div style={{
              padding: '0.75rem 1rem',
              backgroundColor: 'var(--bg-subtle)',
              borderRadius: '8px',
              borderLeft: '3px solid var(--info)',
              fontSize: '0.8125rem',
              color: 'var(--text-muted)',
              marginBottom: '1.5rem'
            }}>
              <strong>Note:</strong> Candidate profiles and resume files will <u>NOT</u> be deleted. Only this requirement specification and its match scores will be removed.
            </div>

            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem' }}>
              <button
                type="button"
                onClick={() => setDeletingJd(null)}
                className="btn btn-secondary"
                disabled={isDeleting}
              >
                Cancel
              </button>

              <button
                type="button"
                onClick={handleConfirmDelete}
                disabled={isDeleting}
                className="btn"
                style={{ backgroundColor: 'var(--danger)', color: '#ffffff', border: 'none' }}
              >
                {isDeleting ? <Loader2 size={16} className="animate-spin" /> : <Trash2 size={16} />}
                {isDeleting ? 'Removing...' : 'Confirm Removal'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Email Shortlisted Candidates Modal (same composer and history as the Email page) */}
      {emailStep && selectedJd && (
        <div style={{
          position: 'fixed',
          inset: 0,
          backgroundColor: 'rgba(0,0,0,0.6)',
          backdropFilter: 'blur(3px)',
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'center',
          overflowY: 'auto',
          padding: '2rem 1rem',
          zIndex: 1100
        }}>
          <div className="card" style={{ maxWidth: '920px', width: '100%', padding: '1.5rem', boxShadow: 'var(--shadow-lg)' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1rem' }}>
              <h3 style={{ margin: 0, fontSize: '1.1rem', fontWeight: 800, display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <Mail size={18} color="var(--primary)" />
                Email Shortlisted Candidates · {selectedJd.display_id}
              </h3>
              <button type="button" onClick={() => setEmailStep(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-muted)' }} aria-label="Close">
                <X size={18} />
              </button>
            </div>

            {emailStep === 'select' ? (
              <>
                <RecipientSelector candidates={shortlistedForEmail} selectedIds={emailSelection} onChange={setEmailSelection} />
                <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '0.75rem', marginTop: '1.25rem' }}>
                  <button type="button" className="btn btn-secondary" onClick={() => setEmailStep(null)}>Cancel</button>
                  <button type="button" className="btn btn-primary" disabled={!emailSelection.length} onClick={() => setEmailStep('compose')}>
                    <Sparkles size={15} /> Generate {emailSelection.length} personalized email{emailSelection.length === 1 ? '' : 's'}
                  </button>
                </div>
              </>
            ) : (
              <EmailComposer
                position={selectedJd}
                recipients={shortlistedForEmail.filter((c) => emailSelection.includes(c.id))}
                onSent={() => loadMatches(selectedJd.id)}
                onCancel={() => setEmailStep(null)}
              />
            )}
          </div>
        </div>
      )}

      {/* Resume Preview Modal */}
      <ResumePreviewModal
        isOpen={isResumePreviewOpen}
        onClose={() => {
          setIsResumePreviewOpen(false);
          setPreviewCandidate(null);
        }}
        candidate={previewCandidate}
      />

      {/* Retention Policy Modal */}
      {showRetentionModal && (
        <div style={{
          position: 'fixed',
          inset: 0,
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
              Per configuration in <code>.env</code>, candidate resumes, chunk embeddings in Qdrant & OpenSearch, and Requirements are stored for a maximum period of <strong>{retentionStatus?.data_retention_days || 30} days</strong>.
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
                <span style={{ color: 'var(--text-subtle)' }}>Requirements Storage Folder:</span>
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
                <span style={{ color: 'var(--text-subtle)' }}>Currently Expired Requirements:</span>
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
