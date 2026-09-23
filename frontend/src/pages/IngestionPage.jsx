import React, { useState, useEffect, useRef } from 'react';
import { 
  UploadCloud, 
  FileText, 
  CheckCircle, 
  AlertTriangle, 
  Copy, 
  RefreshCw, 
  AlertCircle,
  FileCheck,
  Clock
} from 'lucide-react';
import { ingestionApi } from '../lib/api';

export default function IngestionPage() {
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadMessage, setUploadMessage] = useState(null);
  const [activeBatchId, setActiveBatchId] = useState(null);
  const [batches, setBatches] = useState([]);
  const [selectedBatch, setSelectedBatch] = useState(null);
  const [loadingBatches, setLoadingBatches] = useState(true);
  const [dragActive, setDragActive] = useState(false);

  const fileInputRef = useRef(null);

  const loadBatches = async () => {
    try {
      const res = await ingestionApi.getBatches();
      setBatches(res.data.batches);
      if (res.data.batches.length > 0 && !selectedBatch) {
        setSelectedBatch(res.data.batches[0]);
      }
    } catch (err) {
      console.error('Failed to load batches:', err);
    } finally {
      setLoadingBatches(false);
    }
  };

  useEffect(() => {
    loadBatches();
  }, []);

  // Poll for active batch status updates
  useEffect(() => {
    if (!activeBatchId) return;

    const interval = setInterval(async () => {
      try {
        const res = await ingestionApi.getBatch(activeBatchId);
        setSelectedBatch(res.data);
        if (res.data.status === 'completed' || res.data.status === 'failed') {
          setActiveBatchId(null);
          loadBatches();
        }
      } catch (err) {
        console.error('Polling error:', err);
      }
    }, 1500);

    return () => clearInterval(interval);
  }, [activeBatchId]);

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
      setActiveBatchId(res.data.batch_id);
      setSelectedFiles([]);
      loadBatches();
    } catch (err) {
      setUploadMessage({
        type: 'error',
        text: err.response?.data?.detail || 'Failed to upload resume batch.'
      });
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="page-body">
      {/* Title & Stats Overview */}
      <div style={{ marginBottom: '2rem' }}>
        <h1 style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--text-main)' }}>
          Bulk Resume Ingestion
        </h1>
        <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
          Upload candidates to the global shared talent pool. Automatic PII redaction, SHA-256 deduplication, and vector indexing.
        </p>
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
                Supports PDF, TXT • Max 15 MB per file • Up to 50 files per batch
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
                  {isUploading ? 'Uploading & Enqueueing...' : `Ingest ${selectedFiles.length} Resumes`}
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
              <li>SHA-256 hash checking prevents duplicate entries across batches.</li>
            </ul>
          </div>
        </div>

        {/* Right Column: Ingestion Batches & Live Telemetry */}
        <div>
          <div className="card">
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '1.25rem' }}>
              <h3 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-main)' }}>
                Ingestion Batches
              </h3>
              <button
                onClick={loadBatches}
                className="btn btn-secondary"
                style={{ padding: '0.35rem 0.65rem', fontSize: '0.75rem' }}
              >
                <RefreshCw size={13} /> Refresh
              </button>
            </div>

            {/* Selected batch status card */}
            {selectedBatch ? (
              <div style={{
                padding: '1.25rem',
                border: '1px solid var(--border-color)',
                borderRadius: 'var(--radius-md)',
                backgroundColor: 'var(--bg-surface)',
                marginBottom: '1.5rem'
              }}>
                <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1rem' }}>
                  <div>
                    <div style={{ fontSize: '0.75rem', color: 'var(--text-subtle)' }}>Batch ID</div>
                    <div style={{ fontFamily: 'var(--font-mono)', fontSize: '0.8125rem', fontWeight: 600 }}>
                      {selectedBatch.id}
                    </div>
                  </div>
                  <span className={`badge ${
                    selectedBatch.status === 'completed' ? 'badge-success' :
                    selectedBatch.status === 'processing' ? 'badge-warning' : 'badge-danger'
                  }`}>
                    {selectedBatch.status}
                  </span>
                </div>

                {/* Progress bar */}
                <div className="progress-bar-bg" style={{ marginBottom: '1rem' }}>
                  <div
                    className="progress-bar-fill"
                    style={{
                      width: selectedBatch.total_files > 0
                        ? `${Math.min(100, Math.round(((selectedBatch.processed_count + selectedBatch.duplicate_count + selectedBatch.failed_count) / selectedBatch.total_files) * 100))}%`
                        : '0%'
                    }}
                  />
                </div>

                {/* Telemetry Metric Cards */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.75rem', textAlign: 'center' }}>
                  <div style={{ padding: '0.75rem 0.5rem', backgroundColor: 'var(--bg-subtle)', borderRadius: '6px' }}>
                    <div style={{ fontSize: '0.7rem', color: 'var(--text-subtle)' }}>Total</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--text-main)' }}>{selectedBatch.total_files}</div>
                  </div>
                  <div style={{ padding: '0.75rem 0.5rem', backgroundColor: 'var(--success-bg)', borderRadius: '6px' }}>
                    <div style={{ fontSize: '0.7rem', color: 'var(--success-text)' }}>Processed</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--success-text)' }}>{selectedBatch.processed_count}</div>
                  </div>
                  <div style={{ padding: '0.75rem 0.5rem', backgroundColor: 'var(--warning-bg)', borderRadius: '6px' }}>
                    <div style={{ fontSize: '0.7rem', color: 'var(--warning-text)' }}>Duplicates</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--warning-text)' }}>{selectedBatch.duplicate_count}</div>
                  </div>
                  <div style={{ padding: '0.75rem 0.5rem', backgroundColor: 'var(--danger-bg)', borderRadius: '6px' }}>
                    <div style={{ fontSize: '0.7rem', color: 'var(--danger-text)' }}>Failed</div>
                    <div style={{ fontSize: '1.25rem', fontWeight: 800, color: 'var(--danger-text)' }}>{selectedBatch.failed_count}</div>
                  </div>
                </div>

                {/* Per-file Error Log / Duplicates */}
                {selectedBatch.error_log && selectedBatch.error_log.length > 0 && (
                  <div style={{ marginTop: '1.25rem' }}>
                    <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--text-muted)', marginBottom: '0.5rem', textTransform: 'uppercase' }}>
                      File Notice & Error Log ({selectedBatch.error_log.length})
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
                      {selectedBatch.error_log.map((err, i) => (
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
                No batches recorded yet.
              </div>
            )}

            {/* Historical Batches Table */}
            <h4 style={{ fontSize: '0.8125rem', fontWeight: 700, color: 'var(--text-muted)', marginBottom: '0.75rem', textTransform: 'uppercase' }}>
              Batch History
            </h4>
            <div className="table-container" style={{ maxHeight: '240px' }}>
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Batch</th>
                    <th>Files</th>
                    <th>Processed</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {batches.map((b) => (
                    <tr
                      key={b.id}
                      onClick={() => setSelectedBatch(b)}
                      style={{
                        cursor: 'pointer',
                        backgroundColor: selectedBatch?.id === b.id ? 'var(--bg-hover)' : undefined
                      }}
                    >
                      <td style={{ fontFamily: 'var(--font-mono)', fontSize: '0.75rem' }}>
                        {b.id.substring(0, 8)}...
                      </td>
                      <td>{b.total_files}</td>
                      <td>{b.processed_count}</td>
                      <td>
                        <span className={`badge ${
                          b.status === 'completed' ? 'badge-success' :
                          b.status === 'processing' ? 'badge-warning' : 'badge-danger'
                        }`}>
                          {b.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                  {batches.length === 0 && (
                    <tr>
                      <td colSpan="4" style={{ textAlign: 'center', color: 'var(--text-subtle)' }}>
                        No batches available.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
