import React, { useState, useEffect } from 'react';
import { 
  BarChart3, 
  Users, 
  FileText, 
  UploadCloud, 
  TrendingUp, 
  CheckCircle2, 
  Clock, 
  Filter,
  Layers,
  Award,
  AlertTriangle
} from 'lucide-react';
import { analyticsApi, jdApi } from '../lib/api';

export default function AnalyticsPage() {
  const [data, setData] = useState(null);
  const [jds, setJds] = useState([]);
  const [selectedJdId, setSelectedJdId] = useState('');
  const [loading, setLoading] = useState(true);

  const loadAnalytics = async (jdId = '') => {
    try {
      const res = await analyticsApi.getOverview(jdId || null);
      setData(res.data);
    } catch (err) {
      console.error('Failed to load analytics:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const init = async () => {
      try {
        const jdsRes = await jdApi.list();
        setJds(jdsRes.data);
      } catch (err) {
        console.error('Failed to load JDs for analytics:', err);
      }
      loadAnalytics();
    };
    init();
  }, []);

  const handleJdFilterChange = (newJdId) => {
    setSelectedJdId(newJdId);
    loadAnalytics(newJdId);
  };

  if (loading) {
    return (
      <div className="page-body" style={{ textAlign: 'center', padding: '4rem' }}>
        <BarChart3 size={32} className="animate-spin" color="var(--primary)" style={{ margin: '0 auto 1rem' }} />
        <div style={{ fontSize: '1rem', fontWeight: 600 }}>Aggregating Talent Pool Metrics...</div>
      </div>
    );
  }

  const summary = data?.summary || {};
  const statusFunnel = data?.status_funnel || {};
  const expDist = data?.experience_distribution || {};
  const scoreDist = data?.match_score_distribution || {};
  const topSkills = data?.top_skills || [];
  const ingestionTimeline = data?.ingestion_timeline || [];

  // Find max skill count for percentage bar scaling
  const maxSkillCount = Math.max(...topSkills.map(s => s.count), 1);
  const totalInFunnel = Object.values(statusFunnel).reduce((a, b) => a + b, 0) || 1;
  const totalInExp = Object.values(expDist).reduce((a, b) => a + b, 0) || 1;
  const totalInScores = Object.values(scoreDist).reduce((a, b) => a + b, 0) || 1;

  return (
    <div className="page-body">
      {/* Header & JD Filter */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '2rem', flexWrap: 'wrap', gap: '1rem' }}>
        <div>
          <h1 style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--text-main)' }}>
            Talent Pool Analytics
          </h1>
          <p style={{ fontSize: '0.875rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
            High-level telemetry, skill distributions, match scores, and recruitment conversion funnel.
          </p>
        </div>

        {/* Filter by Job Description for Match Score Distribution */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-muted)' }}>
            Score Distribution for:
          </span>
          <select
            value={selectedJdId}
            onChange={(e) => handleJdFilterChange(e.target.value)}
            className="input-field"
            style={{ width: 'auto', fontSize: '0.8125rem', padding: '0.45rem 0.75rem' }}
          >
            <option value="">All Job Descriptions (Aggregate)</option>
            {jds.map(jd => (
              <option key={jd.id} value={jd.id}>
                {jd.title} (v{jd.jd_version})
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Top 4 KPI Metrics */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '1.25rem', marginBottom: '2rem' }}>
        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
            <span style={{ fontSize: '0.8125rem', fontWeight: 600 }}>Total Candidates</span>
            <Users size={18} color="var(--primary)" />
          </div>
          <div style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--text-main)' }}>
            {summary.total_candidates?.toLocaleString() || 0}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-subtle)', marginTop: '0.25rem' }}>
            In shared candidate pool
          </div>
        </div>

        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
            <span style={{ fontSize: '0.8125rem', fontWeight: 600 }}>Job Descriptions</span>
            <FileText size={18} color="var(--info)" />
          </div>
          <div style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--text-main)' }}>
            {summary.total_job_descriptions || 0}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-subtle)', marginTop: '0.25rem' }}>
            Active versioned specifications
          </div>
        </div>

        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
            <span style={{ fontSize: '0.8125rem', fontWeight: 600 }}>Avg. Match Score</span>
            <Award size={18} color="var(--success)" />
          </div>
          <div style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--success)' }}>
            {summary.average_match_score ? `${summary.average_match_score}%` : 'N/A'}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-subtle)', marginTop: '0.25rem' }}>
            Across {summary.evaluated_matches_count || 0} evaluated pairings
          </div>
        </div>

        <div className="card">
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
            <span style={{ fontSize: '0.8125rem', fontWeight: 600 }}>Ingestion Batches</span>
            <UploadCloud size={18} color="var(--warning)" />
          </div>
          <div style={{ fontSize: '1.75rem', fontWeight: 800, color: 'var(--text-main)' }}>
            {summary.total_batches || 0}
          </div>
          <div style={{ fontSize: '0.75rem', color: 'var(--text-subtle)', marginTop: '0.25rem' }}>
            {summary.total_duplicate_files || 0} duplicates skipped
          </div>
        </div>
      </div>

      {/* Row 2: Status Funnel & Match-Score Distribution */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '2rem', marginBottom: '2rem' }}>
        {/* Status Funnel */}
        <div className="card">
          <h3 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-main)', marginBottom: '0.25rem' }}>
            Recruitment Conversion Funnel
          </h3>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '1.5rem' }}>
            Candidate progression from initial ingest through interview stages.
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {[
              { label: 'New Ingests', key: 'New', color: 'var(--primary)', bg: 'var(--primary-light)' },
              { label: 'Shortlisted', key: 'Shortlisted', color: 'var(--info)', bg: 'var(--info-bg)' },
              { label: 'Interviewed', key: 'Interviewed', color: 'var(--warning)', bg: 'var(--warning-bg)' },
              { label: 'Rejected', key: 'Rejected', color: 'var(--danger)', bg: 'var(--danger-bg)' }
            ].map(stage => {
              const count = statusFunnel[stage.key] || 0;
              const pct = Math.round((count / totalInFunnel) * 100);
              return (
                <div key={stage.key}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8125rem', fontWeight: 600, marginBottom: '0.35rem' }}>
                    <span style={{ color: 'var(--text-main)' }}>{stage.label}</span>
                    <span style={{ color: 'var(--text-muted)' }}>{count} ({pct}%)</span>
                  </div>
                  <div className="progress-bar-bg" style={{ height: '10px' }}>
                    <div
                      className="progress-bar-fill"
                      style={{ width: `${pct}%`, backgroundColor: stage.color }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* Match-Score Distribution */}
        <div className="card">
          <h3 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-main)', marginBottom: '0.25rem' }}>
            Match Score Distribution
          </h3>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '1.5rem' }}>
            Tiered breakdown of candidate suitability ratings.
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
            {[
              { label: 'High Match (80%+)', key: '80%+', color: 'var(--success)', desc: 'Strong technical & cultural fit' },
              { label: 'Moderate Match (60–80%)', key: '60-80%', color: 'var(--warning)', desc: 'Partial match on skills or experience' },
              { label: 'Low Match (<60%)', key: '<60%', color: 'var(--text-subtle)', desc: 'Significant qualification gaps' }
            ].map(tier => {
              const count = scoreDist[tier.key] || 0;
              const pct = totalInScores > 0 ? Math.round((count / totalInScores) * 100) : 0;
              return (
                <div key={tier.key} style={{ padding: '0.875rem', backgroundColor: 'var(--bg-subtle)', borderRadius: '8px' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.35rem' }}>
                    <div>
                      <div style={{ fontSize: '0.875rem', fontWeight: 700, color: tier.color }}>{tier.label}</div>
                      <div style={{ fontSize: '0.7rem', color: 'var(--text-subtle)' }}>{tier.desc}</div>
                    </div>
                    <div style={{ fontSize: '1.125rem', fontWeight: 800, color: 'var(--text-main)' }}>
                      {count} <span style={{ fontSize: '0.75rem', fontWeight: 500, color: 'var(--text-muted)' }}>({pct}%)</span>
                    </div>
                  </div>
                  <div className="progress-bar-bg" style={{ height: '6px', marginTop: '0.5rem' }}>
                    <div
                      className="progress-bar-fill"
                      style={{ width: `${pct}%`, backgroundColor: tier.color }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Row 3: Top Skills & Experience Distribution */}
      <div style={{ display: 'grid', gridTemplateColumns: '1.5fr 1fr', gap: '2rem', marginBottom: '2rem' }}>
        {/* Top Skills Distribution */}
        <div className="card">
          <h3 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-main)', marginBottom: '0.25rem' }}>
            Top Skills in Candidate Pool
          </h3>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '1.25rem' }}>
            Frequency of technical proficiencies across all ingested resumes.
          </p>

          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem 1.5rem', maxHeight: '360px', overflowY: 'auto' }}>
            {topSkills.map((s, idx) => {
              const widthPct = Math.round((s.count / maxSkillCount) * 100);
              return (
                <div key={idx} style={{ display: 'flex', flexDirection: 'column', gap: '0.25rem' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.75rem', fontWeight: 600 }}>
                    <span style={{ color: 'var(--text-main)' }}>{s.skill}</span>
                    <span style={{ color: 'var(--text-muted)' }}>{s.count}</span>
                  </div>
                  <div className="progress-bar-bg" style={{ height: '6px' }}>
                    <div
                      className="progress-bar-fill"
                      style={{ width: `${widthPct}%` }}
                    />
                  </div>
                </div>
              );
            })}

            {topSkills.length === 0 && (
              <div style={{ colSpan: 2, textAlign: 'center', color: 'var(--text-subtle)', padding: '2rem' }}>
                No skill data available. Ingest resumes to populate skills.
              </div>
            )}
          </div>
        </div>

        {/* Experience Distribution */}
        <div className="card">
          <h3 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-main)', marginBottom: '0.25rem' }}>
            Experience Distribution
          </h3>
          <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '1.5rem' }}>
            Seniority tiers across candidate records.
          </p>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '1.25rem' }}>
            {[
              { label: '0–2 Years', sub: 'Junior / Associate', key: '0-2 years', color: 'var(--info)' },
              { label: '3–5 Years', sub: 'Mid-Level', key: '3-5 years', color: 'var(--primary)' },
              { label: '5+ Years', sub: 'Senior / Lead / Principal', key: '5+ years', color: 'var(--success)' }
            ].map(tier => {
              const count = expDist[tier.key] || 0;
              const pct = Math.round((count / totalInExp) * 100);
              return (
                <div key={tier.key}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: '0.35rem' }}>
                    <div>
                      <span style={{ fontSize: '0.875rem', fontWeight: 700, color: 'var(--text-main)' }}>{tier.label}</span>
                      <span style={{ fontSize: '0.75rem', color: 'var(--text-subtle)', marginLeft: '0.5rem' }}>({tier.sub})</span>
                    </div>
                    <span style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--text-muted)' }}>
                      {count} ({pct}%)
                    </span>
                  </div>
                  <div className="progress-bar-bg" style={{ height: '8px' }}>
                    <div
                      className="progress-bar-fill"
                      style={{ width: `${pct}%`, backgroundColor: tier.color }}
                    />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* Row 4: Ingestion Stats Over Time */}
      <div className="card">
        <h3 style={{ fontSize: '1rem', fontWeight: 700, color: 'var(--text-main)', marginBottom: '0.25rem' }}>
          Ingestion Velocity Over Time
        </h3>
        <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '1.5rem' }}>
          Daily volume of candidates parsed, PII-redacted, and indexed into OpenSearch.
        </p>

        {ingestionTimeline.length > 0 ? (
          <div style={{ display: 'flex', alignItems: 'flex-end', gap: '1.5rem', height: '140px', padding: '1rem 0' }}>
            {ingestionTimeline.map((item, idx) => {
              const maxVol = Math.max(...ingestionTimeline.map(i => i.resumes_added), 1);
              const heightPct = Math.max(15, Math.round((item.resumes_added / maxVol) * 100));
              return (
                <div key={idx} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', height: '100%', justifyContent: 'flex-end', gap: '0.5rem' }}>
                  <div style={{ fontSize: '0.75rem', fontWeight: 700, color: 'var(--primary)' }}>
                    {item.resumes_added}
                  </div>
                  <div style={{
                    width: '100%',
                    maxWidth: '42px',
                    height: `${heightPct}%`,
                    backgroundColor: 'var(--primary)',
                    borderRadius: '4px 4px 0 0',
                    transition: 'height 0.3s ease'
                  }} />
                  <div style={{ fontSize: '0.7rem', color: 'var(--text-subtle)', whiteSpace: 'nowrap' }}>
                    {item.date.slice(5)}
                  </div>
                </div>
              );
            })}
          </div>
        ) : (
          <div style={{ textAlign: 'center', padding: '2rem', color: 'var(--text-subtle)', fontSize: '0.875rem' }}>
            No timeline data yet.
          </div>
        )}
      </div>
    </div>
  );
}
