import React, { useState, useEffect, useCallback } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Outlet, useLocation } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { MetaProvider } from './context/MetaContext';

import Sidebar from './components/Sidebar';
import Navbar from './components/Navbar';

import AuthPage from './pages/AuthPage';
import IngestionPage from './pages/IngestionPage';
import IngestionHistoryPage from './pages/IngestionHistoryPage';
import JobDescriptionsPage from './pages/JobDescriptionsPage';
import SearchPage from './pages/SearchPage';
import CandidateDetailPage from './pages/CandidateDetailPage';
import AnalyticsPage from './pages/AnalyticsPage';
import EmailPage from './pages/EmailPage';
import { DEFAULT_ROUTE } from './lib/navigation';
import { STORAGE_KEYS } from './config/env';

const SIDEBAR_PREF_KEY = STORAGE_KEYS.sidebarCollapsed;

const isMobile = () => window.matchMedia('(max-width: 768px)').matches;

function readSidebarPref() {
  try {
    const stored = localStorage.getItem(SIDEBAR_PREF_KEY);
    return stored === null ? isMobile() : stored === '1';  // phones start with the narrow icon rail
  } catch {
    return isMobile();
  }
}

// Protected layout wrapper
function ProtectedLayout() {
  const { isAuthenticated, loading } = useAuth();
  const location = useLocation();
  // Collapsed (icons only) vs expanded; remembered across navigation and reloads. The arrow under the logo is the only control.
  const [sidebarCollapsed, setSidebarCollapsed] = useState(readSidebarPref);

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_PREF_KEY, sidebarCollapsed ? '1' : '0');
    } catch {
      // Storage unavailable (private mode): the preference just lasts for this session.
    }
  }, [sidebarCollapsed]);

  const toggleSidebar = useCallback(() => setSidebarCollapsed((c) => !c), []);

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
      <Navbar />
      <div className="app-body">
        <Sidebar collapsed={sidebarCollapsed} onToggle={toggleSidebar} />
        <div className="main-content">
          <Outlet />
        </div>
      </div>
    </div>
  );
}

export default function App() {
  return (
    <ThemeProvider>
      <AuthProvider>
        <MetaProvider>
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
        </MetaProvider>
      </AuthProvider>
    </ThemeProvider>
  );
}
