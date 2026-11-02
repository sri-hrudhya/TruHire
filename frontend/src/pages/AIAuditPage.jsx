import React from 'react';
import AIAuditPanel from '../components/AIAuditPanel';

// Admin-only: the route is guarded in App.jsx and the API returns 403 to everyone else.
export default function AIAuditPage() {
  return (
    <div>
      <div style={{ marginBottom: '1.5rem' }}>
        <h1 className="page-header-title" style={{ margin: 0 }}>AI Audit</h1>
      </div>
      <AIAuditPanel />
    </div>
  );
}
