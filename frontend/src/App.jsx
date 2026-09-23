import React, { useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { AuthProvider, useAuth } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';

import Sidebar from './components/Sidebar';
import Navbar from './components/Navbar';
import AIChatWindow from './components/AIChatWindow';

import AuthPage from './pages/AuthPage';
import IngestionPage from './pages/IngestionPage';
import JobDescriptionsPage from './pages/JobDescriptionsPage';
import SearchPage from './pages/SearchPage';
import CandidateDetailPage from './pages/CandidateDetailPage';
import AnalyticsPage from './pages/AnalyticsPage';

// Protected layout wrapper
function ProtectedLayout() {
  const { isAuthenticated, loading } = useAuth();
  const [isCopilotOpen, setIsCopilotOpen] = useState(false);

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ fontSize: '1rem', fontWeight: 600 }}>Loading TruHire...</div>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="app-container">
      <Sidebar />
      <div className="main-content">
        <Navbar
          title="TruHire"
          subtitle="AI-Powered Recruitment & Candidate Search"
          onOpenChat={() => setIsCopilotOpen(true)}
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
              <Route path="/" element={<Navigate to="/ingestion" replace />} />
              <Route path="/ingestion" element={<IngestionPage />} />
              <Route path="/job-descriptions" element={<JobDescriptionsPage />} />
              <Route path="/positions" element={<Navigate to="/job-descriptions" replace />} />
              <Route path="/search" element={<SearchPage />} />
              <Route path="/candidates/:id" element={<CandidateDetailPage />} />
              <Route path="/analytics" element={<AnalyticsPage />} />
            </Route>

            <Route path="*" element={<Navigate to="/ingestion" replace />} />
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </ThemeProvider>
  );
}
