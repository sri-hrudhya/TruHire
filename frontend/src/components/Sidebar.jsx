import React from 'react';
import { NavLink } from 'react-router-dom';
import { UploadCloud, FileText, Search, BarChart3, Mail, PanelLeftClose, PanelLeftOpen } from 'lucide-react';

// Ingestion History lives inside the Ingestion section (/ingestion/history), so "Ingestion"
// matches its sub-routes (end: false) and stays highlighted there.
const NAV_ITEMS = [
  { name: 'Ingestion', path: '/ingestion', icon: UploadCloud, end: false },
  { name: 'Requirements', path: '/requirements', icon: FileText, end: true },
  { name: 'Search', path: '/search', icon: Search, end: true },
  { name: 'Email', path: '/email', icon: Mail, end: true },
  { name: 'Analytics', path: '/analytics', icon: BarChart3, end: true },
];

export default function Sidebar({ collapsed = false, onToggle }) {
  return (
    <aside
      id="app-sidebar"
      className={`sidebar${collapsed ? ' collapsed' : ''}`}
      aria-label="Main navigation"
    >
      <div className="sidebar-head">
        <button
          type="button"
          onClick={onToggle}
          className="icon-btn sidebar-collapse-btn"
          aria-label={collapsed ? 'Expand navigation' : 'Collapse navigation'}
          aria-controls="app-sidebar"
          aria-expanded={!collapsed}
          title={collapsed ? 'Expand navigation' : 'Collapse navigation'}
        >
          {collapsed ? <PanelLeftOpen size={20} /> : <PanelLeftClose size={20} />}
        </button>
      </div>
      <nav className="sidebar-nav">
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
    </aside>
  );
}
