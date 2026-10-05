import React, { useState, useEffect, useRef } from 'react';
import {
  UploadCloud,
  FileText,
  RefreshCw,
  Clock,
} from 'lucide-react';
import { ingestionApi } from '../lib/api';

export default function IngestionPage() {
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState(null);
  const [activeUploadId, setActiveUploadId] = useState(null);
  const [uploadProgress, setUploadProgress] = useState(null);
  const [dragActive, setDragActive] = useState(false);

  const fileInputRef = useRef(null);

  // Poll progress of the upload the user just kicked off - internally this is the
  // backend's ingestion-batch tracking, but nothing about "batches" (IDs, history)
  // is meaningful to a user, so it's surfaced only as "your upload's progress."
  useEffect(() => {
    if (!activeUploadId) return;

    const interval = setInterval(async () => {
      try {
        const res = await ingestionApi.getBatch(activeUploadId);
        setUploadProgress(res.data);
        if (res.data.status === 'completed' || res.data.status === 'failed') {
          setActiveUploadId(null);
        }
      } catch (err) {
        console.error('Polling error:', err);
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [activeUploadId]);

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
      setSelectedFiles(Array.from(e.dataTransfer.files));
    }
  };

  const handleFileSelect = (e) => {
    if (e.target.files && e.target.files.length > 0) {
      setSelectedFiles(Array.from(e.target.files));
    }
  };

  const handleUpload = async () => {
    if (selectedFiles.length === 0) return;

    setIsUploading(true);
    setUploadMessage(null);

    const formData = new FormData();
    selectedFiles.forEach(file => {
      formData.append('files', file);
    });

    try {
      const res = await ingestionApi.uploadResumes(formData);
      setUploadMessage({ type: 'success', text: `Uploaded ${selectedFiles.length} file(s). Processing in background...` });
      setActiveUploadId(res.data.batch_id);
      setUploadProgress({ status: 'processing', total_files: res.data.total_files, processed_count: 0, duplicate_count: 0, failed_count: 0, error_log: [] });
      setSelectedFiles([]);
    } catch (err) {
      setUploadMessage({
        type: 'error',
        text: err.response?.data?.detail || 'Failed to upload resumes.'
      });
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="page-body">
      {/* Title & Stats Overview */}
      <div style={{ marginBottom: '2rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 className="page-header-title" style={{ margin: 0 }}>
            Bulk Resume Ingestion
          </h1>
          <p className="page-header-subtitle" style={{ marginTop: '0.35rem' }}>
            Upload candidates to the global shared talent pool. Automatic PII redaction, SHA-256 deduplication, and vector indexing.
          </p>
        </div>
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '0.4rem',
          fontSize: '0.75rem',
          fontWeight: 600,
          backgroundColor: 'var(--bg-subtle)',
          color: 'var(--text-muted)',
          border: '1px solid var(--border-color)',
          borderRadius: '20px',
          padding: '0.3rem 0.75rem'
        }}>
          <Clock size={13} color="var(--primary)" />
        </div>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem', alignItems: 'start' }}>
        {/* Left Column: Dropzone & Upload Action */}
        <div>
          <div className="card" style={{ marginBottom: '1.5rem' }}>
            <h3 style={{ fontSize: '1rem', fontWeight: 700, marginBottom: '1rem', color: 'var(--text-main)' }}>
              Upload Resumes
            </h3>

            {/* Drag & Drop Area */}
            <div
              onDragEnter={handleDrag}
              onDragLeave={handleDrag}
              onDragOver={handleDrag}
              onDrop={handleDrop}
              onClick={() => fileInputRef.current?.click()}
              style={{
                border: `2px dashed ${dragActive ? 'var(--primary)' : 'var(--border-color)'}`,
                borderRadius: 'var(--radius-md)',
                backgroundColor: dragActive ? 'var(--primary-light)' : 'var(--bg-subtle)',
                padding: '2.5rem 1.5rem',
                textAlign: 'center',
                cursor: 'pointer',
                transition: 'all 0.2s ease'
              }}
            >
              <input
                ref={fileInputRef}
                type="file"
                multiple
                accept=".pdf,.txt,.doc,.docx"
                onChange={handleFileSelect}
                style={{ display: 'none' }}
              />

              <div style={{
                width: '52px',
                height: '52px',
                borderRadius: '50%',
                backgroundColor: 'var(--bg-surface)',
                border: '1px solid var(--border-color)',
                color: 'var(--primary)',
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                marginBottom: '1rem'
              }}>
                <UploadCloud size={26} />
              </div>

              <div style={{ fontSize: '0.9375rem', fontWeight: 600, color: 'var(--text-main)' }}>
                Drag & drop resume files here, or <span style={{ color: 'var(--primary)', textDecoration: 'underline' }}>browse</span>
              </div>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-subtle)', marginTop: '0.5rem' }}>
                Supports PDF, TXT • Max 15 MB per file • Up to 50 files per upload
              </p>
            </div>

            {/* Selected files preview */}
            {selectedFiles.length > 0 && (
              <div style={{ marginTop: '1.25rem' }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8125rem', fontWeight: 600, marginBottom: '0.5rem' }}>
                  <span>Selected {selectedFiles.length} file(s)</span>
                  <button
                    onClick={() => setSelectedFiles([])}
                    style={{ background: 'none', border: 'none', color: 'var(--danger)', cursor: 'pointer', fontSize: '0.8125rem' }}
                  >
                    Clear All
                  </button>
                </div>

                <div style={{
                  maxHeight: '160px',
                  overflowY: 'auto',
                  border: '1px solid var(--border-color)',
                  borderRadius: '6px',
                  padding: '0.5rem',
                  backgroundColor: 'var(--bg-surface)',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '0.35rem'
                }}>
                  {selectedFiles.map((file, i) => (
                    <div key={i} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                      <FileText size={14} color="var(--primary)" />
                      <span style={{ flex: 1, textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>{file.name}</span>
                      <span>{(file.size / 1024).toFixed(0)} KB</span>
                    </div>
                  ))}
                </div>

                <button
                  onClick={handleUpload}
                  disabled={isUploading}
                  className="btn btn-primary"
                  style={{ width: '100%', marginTop: '1rem' }}
                >
                  {isUploading ? 'Uploading...' : `Upload ${selectedFiles.length} Resumes`}
                </button>
              </div>
            )}

            {uploadMessage && (
              <div style={{
                marginTop: '1rem',
                padding: '0.75rem 1rem',
                borderRadius: '6px',
                fontSize: '0.8125rem',
                backgroundColor: uploadMessage.type === 'success' ? 'var(--success-bg)' : 'var(--danger-bg)',
                color: uploadMessage.type === 'success' ? 'var(--success-text)' : 'var(--danger-text)'
              }}>
                {uploadMessage.text}
              </div>
            )}
          </div>

          {/* Guidelines note */}
          <div className="card" style={{ backgroundColor: 'var(--bg-subtle)', borderStyle: 'dashed' }}>
            <h4 style={{ fontSize: '0.875rem', fontWeight: 700, color: 'var(--text-main)', marginBottom: '0.5rem' }}>
              TruHire Privacy & Decoupled Architecture
            </h4>
            <ul style={{ fontSize: '0.8125rem', color: 'var(--text-muted)', paddingLeft: '1.25rem', lineHeight: 1.6 }}>
              <li>Candidates are added directly to the shared global pool, not tied to any single position.</li>
              <li>Strict PII redaction runs prior to any embedding generation or LLM call.</li>
              <li>SHA-256 hash checking prevents duplicate entries.</li>
            </ul>
          </div>
        </div>

        {/* Right Column: Live progress of the upload just kicked off */}
        <div>
          <div className="card">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem' }}>
              <h3 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-main)' }}>
                Upload Progress
              </h3>
              {activeUploadId && (
                <span className="badge badge-warning" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
                  <RefreshCw size={12} /> Processing
                </span>
              )}
            </div>

            {uploadProgress ? (
              <div style={{
                padding: '1.25rem',
                border: '1px solid var(--border-color)',
                borderRadius: 'var(--radius-md)',
                backgroundColor: 'var(--bg-surface)',
              }}>
                <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '1rem' }}>
                  <span className={`badge ${
                    uploadProgress.status === 'completed' ? 'badge-success' :
                    uploadProgress.status === 'processing' ? 'badge-warning' : 'badge-danger'
                  }`}>
                    {uploadProgress.status}
                  </span>
                </div>

                {/* Progress bar */}
                <div className="progress-bar-bg" style={{ marginBottom: '1rem' }}>
                  <div
                    className="progress-bar-fill"
                    style={{
                      width: uploadProgress.total_files > 0
                        ? `${Math.min(100, Math.round(((uploadProgress.processed_count + uploadProgress.duplicate_count + uploadProgress.failed_count) / uploadProgress.total_files) * 100))}%`
                        : '0%'
                    }}
                  />
                </div>

                {/* Telemetry Metric Cards */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.75rem', textAlign: 'center' }}>
                  <div style={{ padding: '0.75rem 0.5rem', backgroundColor: 'var(--bg-subtle)', borderRadius: '6px' }}>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-subtle)' }}>Total</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-main)' }}>{uploadProgress.total_files}</div>
                  </div>
                  <div style={{ padding: '0.75rem 0.5rem', backgroundColor: 'var(--success-bg)', borderRadius: '6px' }}>
                    <div style={{ fontSize: '0.7rem', color: 'var(--success-text)' }}>Processed</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--success-text)' }}>{uploadProgress.processed_count}</div>
                  </div>
                  <div style={{ padding: '0.75rem 0.5rem', backgroundColor: 'var(--warning-bg)', borderRadius: '6px' }}>
                    <div style={{ fontSize: '0.7rem', color: 'var(--warning-text)' }}>Duplicates</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--warning-text)' }}>{uploadProgress.duplicate_count}</div>
                  </div>
                  <div style={{ padding: '0.75rem 0.5rem', backgroundColor: 'var(--danger-bg)', borderRadius: '6px' }}>
                    <div style={{ fontSize: '0.7rem', color: 'var(--danger-text)' }}>Failed</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--danger-text)' }}>{uploadProgress.failed_count}</div>
                  </div>
                </div>

                {/* Per-file Error Log / Duplicates */}
                {uploadProgress.error_log && uploadProgress.error_log.length > 0 && (
                  <div style={{ marginTop: '1.25rem' }}>
                    <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', marginBottom: '0.5rem', textTransform: 'uppercase' }}>
                      Notices ({uploadProgress.error_log.length})
                    </div>
                    <div style={{
                      maxHeight: '140px',
                      overflowY: 'auto',
                      backgroundColor: 'var(--bg-subtle)',
                      borderRadius: '6px',
                      padding: '0.5rem',
                      display: 'flex',
                      flexDirection: 'column',
                      gap: '0.35rem'
                    }}>
                      {uploadProgress.error_log.map((err, i) => (
                        <div key={i} style={{ fontSize: '0.75rem', display: 'flex', gap: '0.5rem', color: 'var(--text-muted)' }}>
                          <span style={{ fontWeight: 600, color: 'var(--text-main)', flexShrink: 0 }}>{err.filename}:</span>
                          <span>{err.error}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-muted)', fontSize: '0.875rem' }}>
                Upload resumes to see progress here.
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
