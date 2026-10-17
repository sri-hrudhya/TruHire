import React from 'react';
import { Sparkles, Menu } from 'lucide-react';

export default function Navbar({ title, subtitle, onOpenChat, onOpenMenu, menuOpen = false }) {
  return (
    <header className="navbar">
      <div className="flex items-center gap-2" style={{ minWidth: 0 }}>
        {onOpenMenu && (
          <button
            type="button"
            onClick={onOpenMenu}
            className="icon-btn mobile-menu-btn"
            aria-label="Open navigation"
            aria-controls="app-sidebar"
            aria-expanded={menuOpen}
          >
            <Menu size={20} />
          </button>
        )}
        <div style={{ minWidth: 0 }}>
          <h2 className="text-lg font-bold text-main">{title}</h2>
          {subtitle && <p className="text-sm text-muted navbar-subtitle">{subtitle}</p>}
        </div>
      </div>

      <div className="flex items-center gap-4">
        {onOpenChat && (
          <button onClick={onOpenChat} className="btn btn-secondary text-sm" aria-label="AI Copilot">
            <Sparkles size={16} color="var(--primary)" />
            <span className="navbar-chat-label">AI Copilot</span>
          </button>
        )}
      </div>
    </header>
  );
}
