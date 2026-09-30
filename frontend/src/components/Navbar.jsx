import React from 'react';
import { Sparkles } from 'lucide-react';

export default function Navbar({ title, subtitle, onOpenChat }) {
  return (
    <header className="navbar">
      <div>
        <h2 className="text-lg font-bold text-main">{title}</h2>
        {subtitle && <p className="text-sm text-muted">{subtitle}</p>}
      </div>

      <div className="flex items-center gap-4">
        {onOpenChat && (
          <button onClick={onOpenChat} className="btn btn-secondary text-sm">
            <Sparkles size={16} color="var(--primary)" />
            <span>AI Copilot</span>
          </button>
        )}
      </div>
    </header>
  );
}
