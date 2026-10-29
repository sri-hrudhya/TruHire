import React, { useState, useEffect, useRef } from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  UploadCloud,
  FileText,
  RefreshCw,
  History,
} from 'lucide-react';
import { ingestionApi } from '../lib/api';
import { fromState, HISTORY_QUERY_KEY } from '../lib/navigation';
import { POLL_MS, STORAGE_KEYS } from '../config/env';
import IngestedResumes from '../components/ingestion/IngestedResumes';

// The most recent upload in this tab, so its progress is still shown after visiting
// Ingestion History (or any other section) and coming back.
const LAST_UPLOAD_KEY = STORAGE_KEYS.lastUploadBatch;

function readSession(key) {
  try { return sessionStorage.getItem(key); } catch { return null; }
}

function writeSession(key, value) {
  try {
    if (value) sessionStorage.setItem(key, value);
    else sessionStorage.removeItem(key);
  } catch {
    // Storage unavailable: progress simply isn't restored after navigating away.
  }
}

// Per-file pipeline states reported by the backend (see _Progress in routers/ingestion.py). Only their weight
// feeds the bulk progress bar; individual resume statuses are not shown.
const FILE_STATUS = {
  queued: { pct: 0 },
  extracting: { pct: 0.15 },
  analyzing: { pct: 0.4 },
  parsed: { pct: 0.55 },
  embedding: { pct: 0.7 },
  indexing: { pct: 0.85 },
  indexed: { pct: 1 },
  duplicate: { pct: 1 },
  failed: { pct: 1 },
};
const STAGES = [
  { key: 'reading', label: 'Reading & AI analysis' },
  { key: 'embedding', label: 'Embedding' },
  { key: 'indexing', label: 'Indexing' },
  { key: 'done', label: 'Done' },
];

function summarize(progress) {
  const files = progress?.file_status || [];
  const count = (st) => files.filter(f => f.status === st).length;
  const live = files.length > 0;
  return {
    files,
    pct: live
      ? Math.round((files.reduce((sum, f) => sum + (FILE_STATUS[f.status]?.pct ?? 0), 0) / files.length) * 100)
      : (progress?.total_files > 0
          ? Math.min(100, Math.round(((progress.processed_count + progress.duplicate_count + progress.failed_count) / progress.total_files) * 100))
          : 0),
    processed: live ? count('indexed') : progress?.processed_count ?? 0,
    duplicates: live ? count('duplicate') : progress?.duplicate_count ?? 0,
    failed: live ? count('failed') : progress?.failed_count ?? 0,
  };
}

export default function IngestionPage() {
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState(null);
  const location = useLocation();
  // Resume polling (or show the final result of) the last upload made in this tab.
  const [activeUploadId, setActiveUploadId] = useState(() => readSession(LAST_UPLOAD_KEY));
  const [uploadProgress, setUploadProgress] = useState(null);
  const [dragActive, setDragActive] = useState(false);
  const [resumesVersion, setResumesVersion] = useState(0);

  const fileInputRef = useRef(null);

  // Poll progress of the upload the user just kicked off - internally this is the
  // backend's ingestion-batch tracking, but nothing about "batches" (IDs, history)
  // is meaningful to a user, so it's surfaced only as "your upload's progress."
  useEffect(() => {
    if (!activeUploadId) return;

    let cancelled = false;
    const poll = async () => {
      try {
        const res = await ingestionApi.getBatch(activeUploadId);
        if (cancelled) return;
        setUploadProgress(res.data);
        if (res.data.status === 'completed' || res.data.status === 'failed') {
          setActiveUploadId(null);
          setResumesVersion((v) => v + 1);
        }
      } catch (err) {
        if (cancelled) return;
        // The batch no longer exists (or is not visible): stop polling instead of retrying forever.
        if (err.response?.status === 404 || err.response?.status === 403) {
          writeSession(LAST_UPLOAD_KEY, null);
          setActiveUploadId(null);
          return;
        }
        console.error('Polling error:', err);
      }
    };
    poll();
    const interval = setInterval(poll, POLL_MS.uploadProgress);

    return () => { cancelled = true; clearInterval(interval); };
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
      writeSession(LAST_UPLOAD_KEY, res.data.batch_id);
      setUploadProgress({
        status: 'processing', stage: 'queued', total_files: res.data.total_files, processed_count: 0, duplicate_count: 0, failed_count: 0, error_log: [],
        file_status: selectedFiles.map(f => ({ filename: f.name, status: 'queued', detail: '' })),
      });
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
      <header className="ingest-head">
        <h1 className="page-header-title">Bulk Resume Ingestion</h1>
        <Link
          to={`/ingestion/history${readSession(HISTORY_QUERY_KEY) || ''}`}
          state={fromState(location, 'Ingestion')}
          className="btn btn-secondary"
        >
          <History size={16} /> Ingestion History
        </Link>
      </header>

      <div className="ingest-grid">
        {/* Left: dropzone & upload action */}
        <div className="ingest-col">
          <div className="card ingest-panel">
            <h3 className="ingest-panel-title">Upload Resumes</h3>

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
        </div>

        {/* Right: live progress of the upload just kicked off */}
        <div className="ingest-col">
          <div className="card ingest-panel">
            <div className="ingest-panel-head">
              <h3 className="ingest-panel-title">Upload Progress</h3>
              {activeUploadId && uploadProgress?.status === 'processing' && (
                <span className="badge badge-warning" style={{ display: 'inline-flex', alignItems: 'center', gap: '0.35rem' }}>
                  <RefreshCw size={12} /> Processing
                </span>
              )}
            </div>

            {uploadProgress ? ((() => {
              const sum = summarize(uploadProgress);
              const stageIdx = uploadProgress.stage === 'done' ? STAGES.length - 1 : Math.max(0, STAGES.findIndex(st => st.key === uploadProgress.stage));
              const finished = uploadProgress.status === 'completed' || uploadProgress.status === 'failed';
              return (
              <div style={{
                padding: '1.25rem',
                border: '1px solid var(--border-color)',
                borderRadius: 'var(--radius-md)',
                backgroundColor: 'var(--bg-surface)',
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                  <span style={{ fontSize: '1.5rem', fontWeight: 800, color: 'var(--text-main)' }}>{sum.pct}%</span>
                  <span className={`badge ${
                    uploadProgress.status === 'completed' ? 'badge-success' :
                    uploadProgress.status === 'processing' ? 'badge-warning' : 'badge-danger'
                  }`}>
                    {uploadProgress.status}
                  </span>
                </div>

                {/* Overall stage tracker */}
                <div style={{ display: 'flex', gap: '0.35rem', marginBottom: '0.9rem' }}>
                  {STAGES.map((st, i) => {
                    const done = finished || i < stageIdx;
                    const current = !finished && i === stageIdx;
                    return (
                      <div key={st.key} style={{
                        flex: 1, textAlign: 'center', fontSize: '0.68rem', fontWeight: 700, padding: '0.35rem 0.25rem', borderRadius: '6px',
                        backgroundColor: done ? 'var(--success-bg)' : current ? 'var(--primary-light)' : 'var(--bg-subtle)',
                        color: done ? 'var(--success-text)' : current ? 'var(--primary)' : 'var(--text-subtle)',
                        border: current ? '1px solid var(--primary)' : '1px solid transparent',
                      }}>
                        {st.label}
                      </div>
                    );
                  })}
                </div>

                {/* Progress bar */}
                <div className="progress-bar-bg" style={{ marginBottom: '1rem' }}>
                  <div className="progress-bar-fill" style={{ width: `${sum.pct}%`, transition: 'width 0.4s ease' }} />
                </div>

                {/* Telemetry Metric Cards */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.75rem', textAlign: 'center' }}>
                  <div style={{ padding: '0.75rem 0.5rem', backgroundColor: 'var(--bg-subtle)', borderRadius: '6px' }}>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-subtle)' }}>Total</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-main)' }}>{uploadProgress.total_files}</div>
                  </div>
                  <div style={{ padding: '0.75rem 0.5rem', backgroundColor: 'var(--success-bg)', borderRadius: '6px' }}>
                    <div style={{ fontSize: '0.7rem', color: 'var(--success-text)' }}>Processed</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--success-text)' }}>{sum.processed}</div>
                  </div>
                  <div style={{ padding: '0.75rem 0.5rem', backgroundColor: 'var(--warning-bg)', borderRadius: '6px' }}>
                    <div style={{ fontSize: '0.7rem', color: 'var(--warning-text)' }}>Duplicates</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--warning-text)' }}>{sum.duplicates}</div>
                  </div>
                  <div style={{ padding: '0.75rem 0.5rem', backgroundColor: 'var(--danger-bg)', borderRadius: '6px' }}>
                    <div style={{ fontSize: '0.7rem', color: 'var(--danger-text)' }}>Failed</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--danger-text)' }}>{sum.failed}</div>
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
              );
            })()
            ) : (
              <div className="ingest-empty">Upload resumes to see progress here.</div>
            )}
          </div>
        </div>
      </div>

      <IngestedResumes refreshKey={resumesVersion} />
    </div>
  );
}
