import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  UploadCloud,
  FileText,
  Search,
  BarChart3,
  Mail,
  Sun,
  Moon,
  LogOut,
  User as UserIcon,
  Sparkles,
  PanelLeftClose,
  PanelLeftOpen,
  X
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';

// Ingestion History lives inside the Ingestion section (/ingestion/history), so "Ingestion"
// matches its sub-routes (end: false) and stays highlighted there.
const NAV_ITEMS = [
  { name: 'Ingestion', path: '/ingestion', icon: UploadCloud, end: false },
  { name: 'Requirements', path: '/requirements', icon: FileText, end: true },
  { name: 'Search', path: '/search', icon: Search, end: true },
  { name: 'Email', path: '/email', icon: Mail, end: true },
  { name: 'Analytics', path: '/analytics', icon: BarChart3, end: true },
];

export default function Sidebar({ collapsed = false, onToggleCollapse, mobileOpen = false, onCloseMobile }) {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const toggleLabel = collapsed ? 'Expand sidebar' : 'Collapse sidebar';
  const themeLabel = theme === 'dark' ? 'Dark Mode' : 'Light Mode';

  return (
    <aside
      id="app-sidebar"
      className={`sidebar${collapsed ? ' collapsed' : ''}${mobileOpen ? ' mobile-open' : ''}`}
      aria-label="Main navigation"
    >
      <div className="sidebar-brand">
        <div className="sidebar-brand-icon">
          <Sparkles size={20} />
        </div>
        <div className="sidebar-label sidebar-brand-text">
          <h1 className="font-extrabold text-lg text-main">TruHire</h1>
          <span className="text-xs font-semibold uppercase" style={{ color: 'var(--primary)' }}>
            AI Hiring Platform
          </span>
        </div>
        <button
          type="button"
          onClick={onToggleCollapse}
          className="icon-btn sidebar-toggle sidebar-collapse-toggle"
          aria-label={toggleLabel}
          aria-expanded={!collapsed}
          aria-controls="app-sidebar"
          data-tooltip={toggleLabel}
        >
          {collapsed ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
        </button>
        <button
          type="button"
          onClick={onCloseMobile}
          className="icon-btn sidebar-toggle sidebar-mobile-close"
          aria-label="Close navigation"
        >
          <X size={18} />
        </button>
      </div>

      <nav className="sidebar-nav">
        <div className="sidebar-nav-label">Platform</div>
        {NAV_ITEMS.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.end}
              aria-label={item.name}
              data-tooltip={item.name}
              className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}
            >
              <Icon size={18} className="sidebar-icon" />
              <span className="sidebar-label">{item.name}</span>
            </NavLink>
          );
        })}
      </nav>

      <div className="sidebar-footer">
        <button
          onClick={toggleTheme}
          className="theme-toggle"
          aria-label={`Switch theme (currently ${themeLabel})`}
          data-tooltip={themeLabel}
        >
          <span className="flex items-center gap-2">
            {theme === 'dark' ? <Moon size={15} /> : <Sun size={15} />}
            <span className="sidebar-label">{themeLabel}</span>
          </span>
          <span className="text-xs text-subtle sidebar-label">Switch</span>
        </button>

        <div className="sidebar-user">
          <div className="flex items-center gap-2" style={{ minWidth: 0 }}>
            <div className="avatar" title={user?.email || user?.name || 'Recruiter'}>
              <UserIcon size={16} />
            </div>
            <div className="sidebar-label" style={{ minWidth: 0 }}>
              <div className="text-sm font-semibold text-main truncate">
                {user?.name || 'Recruiter'}
              </div>
              <div className="text-xs text-subtle truncate">
                {user?.email}
              </div>
            </div>
          </div>

          <button onClick={logout} title="Logout" aria-label="Logout" className="icon-btn">
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </aside>
  );
}
