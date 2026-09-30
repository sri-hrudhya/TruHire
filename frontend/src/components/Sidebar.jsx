import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  UploadCloud,
  FileText,
  Search,
  BarChart3,
  Sun,
  Moon,
  LogOut,
  User as UserIcon,
  Sparkles
} from 'lucide-react';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';

export default function Sidebar() {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();

  const navItems = [
    { name: 'Ingestion', path: '/ingestion', icon: UploadCloud },
    { name: 'Job Descriptions', path: '/job-descriptions', icon: FileText },
    { name: 'Search', path: '/search', icon: Search },
    { name: 'Analytics', path: '/analytics', icon: BarChart3 },
  ];

  return (
    <aside className="sidebar">
      <div className="sidebar-brand">
        <div className="sidebar-brand-icon">
          <Sparkles size={20} />
        </div>
        <div>
          <h1 className="font-extrabold text-lg text-main">TruHire</h1>
          <span className="text-xs font-semibold uppercase" style={{ color: 'var(--primary)' }}>
            AI Hiring Platform
          </span>
        </div>
      </div>

      <nav className="sidebar-nav">
        <div className="sidebar-nav-label">Platform</div>
        {navItems.map((item) => {
          const Icon = item.icon;
          return (
            <NavLink
              key={item.path}
              to={item.path}
              className={({ isActive }) => `sidebar-link${isActive ? ' active' : ''}`}
            >
              <Icon size={18} />
              <span>{item.name}</span>
            </NavLink>
          );
        })}
      </nav>

      <div className="sidebar-footer">
        <button onClick={toggleTheme} className="theme-toggle">
          <span className="flex items-center gap-2">
            {theme === 'dark' ? <Moon size={15} /> : <Sun size={15} />}
            <span>{theme === 'dark' ? 'Dark Mode' : 'Light Mode'}</span>
          </span>
          <span className="text-xs text-subtle">Switch</span>
        </button>

        <div className="flex items-center justify-between" style={{ paddingTop: '0.5rem' }}>
          <div className="flex items-center gap-2" style={{ minWidth: 0 }}>
            <div className="avatar">
              <UserIcon size={16} />
            </div>
            <div style={{ minWidth: 0 }}>
              <div className="text-sm font-semibold text-main truncate">
                {user?.name || 'Recruiter'}
              </div>
              <div className="text-xs text-subtle truncate">
                {user?.email}
              </div>
            </div>
          </div>

          <button onClick={logout} title="Logout" className="icon-btn">
            <LogOut size={16} />
          </button>
        </div>
      </div>
    </aside>
  );
}
