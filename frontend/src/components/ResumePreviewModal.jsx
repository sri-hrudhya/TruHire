import React, { useState, useEffect } from 'react';
import { X, ExternalLink, Download, FileText, AlertCircle, FileCheck, Eye, Loader2 } from 'lucide-react';
import { candidatesApi } from '../lib/api';
import useAuthedFile from '../lib/useAuthedFile';

export default function ResumePreviewModal({ isOpen, onClose, candidate: candidateProp }) {
  const [activeTab, setActiveTab] = useState('doc'); // 'doc' | 'text'
  const [details, setDetails] = useState(null);
  const [loadingDetails, setLoadingDetails] = useState(false);

  useEffect(() => {
    if (!isOpen) return;

    // Handle Escape key press
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  // Search/match payloads omit resume_text; fetch the full record (served from the backend cache)
  useEffect(() => {
    setDetails(null);
    if (!isOpen || !candidateProp?.id || candidateProp.resume_text !== undefined) return;

    let cancelled = false;
    setLoadingDetails(true);
    candidatesApi.get(candidateProp.id)
      .then((res) => {
        if (!cancelled && res.data?.id === candidateProp.id) setDetails(res.data);
      })
      .catch((err) => console.warn('Failed to load resume details:', err))
      .finally(() => {
        if (!cancelled) setLoadingDetails(false);
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, candidateProp?.id, candidateProp?.resume_text]);

  const candidate = details ? { ...candidateProp, ...details } : candidateProp;
  const hasFile = Boolean(candidate?.resume_file_url);
  const file = useAuthedFile(
    () => candidatesApi.getResumeFile(candidate.id),
    isOpen && hasFile ? candidate.id : null
  );

  useEffect(() => {
    // If no file url exists but resume text exists, switch to text view by default
    if (candidate) {
      const isPdf = candidate.resume_file_url?.toLowerCase().endsWith('.pdf');
      setActiveTab(isPdf ? 'doc' : 'text');
    }
  }, [candidate?.id, candidate?.resume_file_url]);

  if (!isOpen || !candidate) return null;

  const isPdf = candidate.resume_file_url?.toLowerCase().endsWith('.pdf');
  const hasText = Boolean(candidate.resume_text && candidate.resume_text.trim());

  return (
    <div
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
      style={{
        position: 'fixed',
        inset: 0,
        backgroundColor: 'rgba(0, 0, 0, 0.65)',
        backdropFilter: 'blur(4px)',
        zIndex: 1200,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '1.5rem',
        animation: 'fadeIn 0.15s ease'
      }}
    >
      <div
        className="card"
        style={{
          width: '100%',
          maxWidth: '1000px',
          height: '90vh',
          display: 'flex',
          flexDirection: 'column',
          padding: 0,
          overflow: 'hidden',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.35)',
          borderRadius: 'var(--radius-lg)'
        }}
      >
        {/* Modal Header */}
        <div
          style={{
            padding: '1.25rem 1.75rem',
            borderBottom: '1px solid var(--border-color)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            backgroundColor: 'var(--bg-surface)',
            flexShrink: 0
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.85rem' }}>
            <div
              style={{
                width: '40px',
                height: '40px',
                borderRadius: '8px',
                backgroundColor: 'var(--primary-light)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: 'var(--primary)'
              }}
            >
              <FileText size={20} />
            </div>

            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span
                  className="badge badge-primary"
                  style={{
                    fontSize: '0.75rem',
                    fontFamily: 'var(--font-mono)',
                    fontWeight: 700
                  }}
                >
                  {candidate.display_id || 'TRU-CN-????'}
                </span>
                <h3 style={{ margin: 0, fontSize: '1.125rem', fontWeight: 800, color: 'var(--text-main)' }}>
                  {candidate.candidate_name}
                </h3>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '0.2rem' }}>
                <span>File: {candidate.original_filename || 'Resume Document'}</span>
                {candidate.email && (
                  <>
                    <span>•</span>
                    <span>{candidate.email}</span>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Header Controls */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            {/* View Mode Toggle if both file and text are available */}
            {hasFile && hasText && (
              <div
                style={{
                  display: 'flex',
                  backgroundColor: 'var(--bg-subtle)',
                  borderRadius: '6px',
                  padding: '3px',
                  fontSize: '0.75rem',
                  fontWeight: 600
                }}
              >
                <button
                  type="button"
                  onClick={() => setActiveTab('doc')}
                  style={{
                    padding: '0.3rem 0.65rem',
                    borderRadius: '4px',
                    border: 'none',
                    cursor: 'pointer',
                    backgroundColor: activeTab === 'doc' ? 'var(--bg-surface)' : 'transparent',
                    color: activeTab === 'doc' ? 'var(--primary)' : 'var(--text-muted)',
                    fontWeight: activeTab === 'doc' ? 700 : 500,
                    boxShadow: activeTab === 'doc' ? 'var(--shadow-sm)' : 'none'
                  }}
                >
                  Document Viewer
                </button>
                <button
                  type="button"
                  onClick={() => setActiveTab('text')}
                  style={{
                    padding: '0.3rem 0.65rem',
                    borderRadius: '4px',
                    border: 'none',
                    cursor: 'pointer',
                    backgroundColor: activeTab === 'text' ? 'var(--bg-surface)' : 'transparent',
                    color: activeTab === 'text' ? 'var(--primary)' : 'var(--text-muted)',
                    fontWeight: activeTab === 'text' ? 700 : 500,
                    boxShadow: activeTab === 'text' ? 'var(--shadow-sm)' : 'none'
                  }}
                >
                  Extracted Text
                </button>
              </div>
            )}

            {/* Download / Open in new tab */}
            {hasFile && file.url && (
              <a
                href={file.url}
                target="_blank"
                rel="noopener noreferrer"
                className="btn btn-secondary"
                style={{ fontSize: '0.75rem', padding: '0.4rem 0.75rem', textDecoration: 'none' }}
                title="Open original file in new browser window"
              >
                <ExternalLink size={14} />
                <span>Open File</span>
              </a>
            )}

            {/* Close Button */}
            <button
              onClick={onClose}
              className="icon-btn"
              title="Close preview (Esc)"
              aria-label="Close resume preview"
              style={{
                width: '36px',
                height: '36px',
                borderRadius: '8px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center'
              }}
            >
              <X size={20} />
            </button>
          </div>
        </div>

        {/* Modal Body */}
        <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column', backgroundColor: 'var(--bg-app)' }}>
          {activeTab === 'doc' && hasFile && (file.loading || file.error) ? (
            <div style={{ padding: '3rem', textAlign: 'center', margin: 'auto', color: 'var(--text-muted)' }}>
              {file.loading ? (
                <Loader2 size={32} className="animate-spin" color="var(--primary)" style={{ margin: '0 auto 1rem' }} />
              ) : (
                <AlertCircle size={32} color="var(--text-subtle)" style={{ margin: '0 auto 1rem' }} />
              )}
              <div style={{ fontSize: '0.9375rem', fontWeight: 600 }}>{file.loading ? 'Loading document...' : file.error}</div>
            </div>
          ) : activeTab === 'doc' && hasFile && file.url ? (
            isPdf ? (
              <iframe
                src={file.url}
                title={`Resume for ${candidate.candidate_name}`}
                style={{
                  width: '100%',
                  height: '100%',
                  border: 'none',
                  backgroundColor: '#ffffff'
                }}
              />
            ) : (
              <div style={{ padding: '2rem', textAlign: 'center', margin: 'auto' }}>
                <FileCheck size={48} color="var(--primary)" style={{ margin: '0 auto 1rem' }} />
                <h4 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '0.5rem' }}>
                  {candidate.original_filename}
                </h4>
                <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', maxWidth: '420px', margin: '0 auto 1.5rem' }}>
                  This resume is stored as a Word document or alternative format. You can download the original file or view the parsed text.
                </p>
                <div style={{ display: 'flex', justifyContent: 'center', gap: '0.75rem' }}>
                  <a
                    href={file.url}
                    download={candidate.original_filename || true}
                    className="btn btn-primary"
                    style={{ textDecoration: 'none' }}
                  >
                    <Download size={16} /> Download Original Document
                  </a>
                  {hasText && (
                    <button
                      type="button"
                      onClick={() => setActiveTab('text')}
                      className="btn btn-secondary"
                    >
                      <Eye size={16} /> View Extracted Text
                    </button>
                  )}
                </div>
              </div>
            )
          ) : loadingDetails ? (
            <div style={{ padding: '3rem', textAlign: 'center', margin: 'auto', color: 'var(--text-muted)' }}>
              <Loader2 size={32} className="animate-spin" color="var(--primary)" style={{ margin: '0 auto 1rem' }} />
              <div style={{ fontSize: '0.9375rem', fontWeight: 600 }}>Loading resume...</div>
            </div>
          ) : hasText ? (
            <div style={{ flex: 1, overflowY: 'auto', padding: '1.5rem 2rem' }}>
              <div
                style={{
                  maxWidth: '850px',
                  margin: '0 auto',
                  backgroundColor: 'var(--bg-surface)',
                  padding: '2rem',
                  borderRadius: 'var(--radius-md)',
                  border: '1px solid var(--border-color)',
                  boxShadow: 'var(--shadow-sm)'
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.5rem', borderBottom: '1px solid var(--border-color)', paddingBottom: '1rem' }}>
                  <div style={{ fontSize: '0.8125rem', fontWeight: 700, color: 'var(--text-subtle)', textTransform: 'uppercase' }}>
                    Parsed Resume Content
                  </div>
                  {candidate.original_filename && (
                    <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      Source: {candidate.original_filename}
                    </span>
                  )}
                </div>

                <pre
                  style={{
                    fontFamily: 'var(--font-sans)',
                    fontSize: '0.875rem',
                    lineHeight: 1.7,
                    whiteSpace: 'pre-wrap',
                    wordBreak: 'break-word',
                    color: 'var(--text-main)',
                    margin: 0
                  }}
                >
                  {candidate.resume_text}
                </pre>
              </div>
            </div>
          ) : (
            <div style={{ padding: '3rem', textAlign: 'center', margin: 'auto', color: 'var(--text-muted)' }}>
              <AlertCircle size={36} color="var(--text-subtle)" style={{ margin: '0 auto 1rem' }} />
              <div style={{ fontSize: '1rem', fontWeight: 600 }}>No resume preview available</div>
              <p style={{ fontSize: '0.8125rem', color: 'var(--text-subtle)', marginTop: '0.25rem' }}>
                No file upload or extracted resume text was found for this candidate.
              </p>
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div
          style={{
            padding: '0.85rem 1.75rem',
            borderTop: '1px solid var(--border-color)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            backgroundColor: 'var(--bg-surface)',
            fontSize: '0.75rem',
            color: 'var(--text-subtle)',
            flexShrink: 0
          }}
        >
          <span>Press <kbd style={{ padding: '2px 5px', borderRadius: '4px', backgroundColor: 'var(--bg-subtle)', border: '1px solid var(--border-color)' }}>Esc</kbd> or click outside to return to profile</span>

          <button
            onClick={onClose}
            className="btn btn-secondary"
            style={{ fontSize: '0.8125rem', padding: '0.4rem 1rem' }}
          >
            Close Preview
          </button>
        </div>
      </div>
    </div>
  );
}
