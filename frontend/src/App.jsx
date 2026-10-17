import React, { useState, useEffect, useCallback } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Outlet, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';

import Sidebar from './components/Sidebar';
import Navbar from './components/Navbar';
import AIChatWindow from './components/AIChatWindow';

import AuthPage from './pages/AuthPage';
import IngestionPage from './pages/IngestionPage';
import IngestionHistoryPage from './pages/IngestionHistoryPage';
import JobDescriptionsPage from './pages/JobDescriptionsPage';
import SearchPage from './pages/SearchPage';
import CandidateDetailPage from './pages/CandidateDetailPage';
import AnalyticsPage from './pages/AnalyticsPage';
import EmailPage from './pages/EmailPage';
import { DEFAULT_ROUTE } from './lib/navigation';

const SIDEBAR_PREF_KEY = 'truhire_sidebar_collapsed';

function readSidebarPref() {
  try {
    return localStorage.getItem(SIDEBAR_PREF_KEY) === '1';
  } catch {
    return false;
  }
}

// Protected layout wrapper
function ProtectedLayout() {
  const { isAuthenticated, loading } = useAuth();
  const location = useLocation();
  const [isCopilotOpen, setIsCopilotOpen] = useState(false);
  // Desktop: collapsed (icons only) vs expanded; remembered across navigation and reloads.
  const [sidebarCollapsed, setSidebarCollapsed] = useState(readSidebarPref);
  // Small screens: the sidebar is an off-canvas drawer.
  const [mobileNavOpen, setMobileNavOpen] = useState(false);

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_PREF_KEY, sidebarCollapsed ? '1' : '0');
    } catch {
      // Storage unavailable (private mode): the preference just lasts for this session.
    }
  }, [sidebarCollapsed]);

  // Close the mobile drawer after any navigation (link click, browser Back/Forward).
  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    if (!mobileNavOpen) return;
    const onKey = (e) => { if (e.key === 'Escape') setMobileNavOpen(false); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [mobileNavOpen]);

  const toggleSidebar = useCallback(() => setSidebarCollapsed((c) => !c), []);
  const closeMobileNav = useCallback(() => setMobileNavOpen(false), []);

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ fontSize: '1rem', fontWeight: 600 }}>Loading TruHire...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    // Remember where the user was headed so login can return them there.
    return <Navigate to="/login" replace state={{ from: { path: `${location.pathname}${location.search}` } }} />;
  }

  return (
    <div className="app-container">
      <Sidebar
        collapsed={sidebarCollapsed}
        onToggleCollapse={toggleSidebar}
        mobileOpen={mobileNavOpen}
        onCloseMobile={closeMobileNav}
      />
      {mobileNavOpen && <div className="sidebar-backdrop" onClick={closeMobileNav} aria-hidden="true" />}
      <div className="main-content">
        <Navbar
          title="TruHire"
          subtitle="AI-Powered Recruitment & Candidate Search"
          onOpenChat={() => setIsCopilotOpen(true)}
          onOpenMenu={() => setMobileNavOpen(true)}
          menuOpen={mobileNavOpen}
        />
        <Outlet />
        <AIChatWindow
          isOpen={isCopilotOpen}
          onClose={() => setIsCopilotOpen(false)}
          title="TruHire AI Copilot"
        />
      </div>
    </div>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<AuthPage />} />

            <Route element={<ProtectedLayout />}>
              <Route path="/" element={<Navigate to={DEFAULT_ROUTE} replace />} />
              <Route path="/ingestion" element={<IngestionPage />} />
              <Route path="/ingestion/history" element={<IngestionHistoryPage />} />
              <Route path="/requirements" element={<JobDescriptionsPage />} />
              <Route path="/job-descriptions" element={<Navigate to="/requirements" replace />} />
              <Route path="/positions" element={<Navigate to="/requirements" replace />} />
              <Route path="/search" element={<SearchPage />} />
              <Route path="/email" element={<EmailPage />} />
              <Route path="/candidates/:id" element={<CandidateDetailPage />} />
              <Route path="/analytics" element={<AnalyticsPage />} />
            </Route>

            <Route path="*" element={<Navigate to={DEFAULT_ROUTE} replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  );
}
