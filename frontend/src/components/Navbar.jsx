import React from 'react';
import { Sparkles, HelpCircle } from 'lucide-react';

export default function Navbar({ title, subtitle, onOpenChat }) {
  return (
    <header style={{
      height: '70px',
      borderBottom: '1px solid var(--border-color)',
      backgroundColor: 'var(--bg-surface)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      padding: '0 2rem',
      position: 'sticky',
      top: 0,
      zIndex: 10,
    }}>
      <div>
        <h2 style={{ fontSize: '1.25rem', fontWeight: 700, color: 'var(--text-main)' }}>
          {title}
        </h2>
        {subtitle && (
          <p style={{ fontSize: '0.8125rem', color: 'var(--text-muted)' }}>
            {subtitle}
          </p>
        )}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        {onOpenChat && (
          <button
            onClick={onOpenChat}
            className="btn btn-secondary"
            style={{
              padding: '0.5rem 0.875rem',
              fontSize: '0.8125rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem'
            }}
          >
            <Sparkles size={16} color="var(--primary)" />
            <span>AI Copilot</span>
          </button>
        )}

        <div className="badge badge-success" style={{ padding: '0.35rem 0.65rem' }}>
          <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: 'var(--success)' }}></span>
          <span>OpenSearch Ready</span>
        </div>
      </div>
    </header>
  );
}
