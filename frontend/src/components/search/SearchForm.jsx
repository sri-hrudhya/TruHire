import { Link } from 'react-router-dom';
import { Search, X } from 'lucide-react';
import CategoryRow from '../CategoryRow';
import TagInput from '../ui/TagInput';
import { jdsInCategory, topNOptions } from '../../lib/categories';
import { TOP_N_PRESETS } from '../../config/env';
import { COPY } from '../../config/copy';
import { useMeta } from '../../context/MetaContext';
import './search.css';

// The search console: keywords, an optional category and requirement, then the narrowing filters.
export default function SearchForm({ s }) {
  const { search: limits } = useMeta();
  const category = s.demands.find((d) => d.id === s.categoryId);
  const choices = jdsInCategory(s.jds, s.categoryId);
  const suggested = s.jdFilterInfo?.locations?.length ? s.jdFilterInfo.locations : s.jdFilterInfo?.location ? [s.jdFilterInfo.location] : [];
  const sameAsSuggested = suggested.length > 0 && suggested.length === s.locations.length && suggested.every((p, i) => p === s.locations[i]);

  return (
    <form className="search-form" onSubmit={(e) => { e.preventDefault(); s.run(); }}>
      <div className="search-bar">
        <label className="search-input">
          <Search size={17} aria-hidden="true" />
          <span className="sr-only">Keywords</span>
          <input type="text" value={s.query} onChange={(e) => s.setQuery(e.target.value)}
            placeholder="Skills, role or a sentence, such as “Python and Docker, 5+ yrs”" />
        </label>
        <button type="submit" className="btn btn-primary" disabled={s.loading}>{s.loading ? 'Searching…' : 'Search'}</button>
      </div>

      <div className="search-scope">
        <CategoryRow demands={s.demands} activeId={s.categoryId || null} onSelect={s.selectCategory} label="Search within category" />
        <label className="search-field">
          <span className="input-label">Requirement</span>
          <select className="input-field" value={s.jdId} onChange={(e) => s.selectJd(e.target.value)}>
            <option value="">{s.categoryId ? `Any ${category?.name || 'category'} requirement (keywords only)` : 'No requirement (keywords only)'}</option>
            {choices.map((jd) => (
              <option key={jd.id} value={jd.id}>{jd.display_id ? `${jd.display_id} · ` : ''}{jd.title} (v{jd.jd_version})</option>
            ))}
          </select>
        </label>
        {s.categoryId && choices.length === 0 && (
          <p className="dek">
            {category?.name || 'This category'} has no requirements yet.{' '}
            <Link to={`/requirements?demand=${s.categoryId}`}>Open it in Requirements</Link>
          </p>
        )}
      </div>

      <div className="search-filters">
        <label className="search-field">
          <span className="input-label">Minimum years</span>
          <input className="input-field" type="number" min="0" step="0.5" value={s.minExp} onChange={(e) => s.setMinExp(e.target.value)} />
        </label>
        <label className="search-field">
          <span className="input-label">Show top</span>
          <select className="input-field" value={s.topN} onChange={(e) => s.setTopN(e.target.value)}>
            {topNOptions(limits, TOP_N_PRESETS).map((n) => <option key={n} value={n}>{n}{n === limits.max_top_n ? ' (max)' : ''}</option>)}
          </select>
        </label>
        <label className="search-field">
          <span className="input-label">
            Job title
            {s.jdFilterInfo?.role && s.role === s.jdFilterInfo.role && <span className="slug"> · from requirement</span>}
          </span>
          <input className="input-field" maxLength={100} value={s.role} onChange={(e) => s.setRole(e.target.value)} placeholder={COPY.searchPlaceholders.role} />
        </label>
        <label className="search-field">
          <span className="input-label">
            Locations <span className="slug">(any of)</span>
            {sameAsSuggested && <span className="slug"> · from requirement</span>}
            {s.jdFilterInfo?.work_mode && <span className="slug"> · {s.jdFilterInfo.work_mode}</span>}
          </span>
          <TagInput values={s.locations} onChange={s.setLocations} maxItems={10} maxLength={100} itemLabel="location"
            ariaLabel="Locations" placeholder={COPY.searchPlaceholders.location} />
        </label>
      </div>

      {s.jdFilterInfo && (s.jdFilterInfo.role || suggested.length > 0) && (
        <p className="dek search-suggest">
          Suggested:
          {s.jdFilterInfo.role && s.role !== s.jdFilterInfo.role && (
            <button type="button" className="link-btn" onClick={() => s.setRole(s.jdFilterInfo.role)}>Title: {s.jdFilterInfo.role}</button>
          )}
          {suggested.length > 0 && !sameAsSuggested && (
            <button type="button" className="link-btn" onClick={() => s.setLocations(suggested)}>Locations: {suggested.join(', ')}</button>
          )}
        </p>
      )}

      <div className="search-active cluster cluster-between">
        <span className="cluster cluster-tight" aria-label="Active filters">
          {s.chips.map((chip) => (
            <span key={chip} className="chip">
              {chip}
              <button type="button" className="chip-remove" onClick={() => s.removeChip(chip)} aria-label={`Remove ${chip}`}><X size={12} /></button>
            </span>
          ))}
          {s.role.trim() && <span className="chip" title="Only candidates with this job title">Title: {s.role.trim()}</span>}
          {s.locations.length > 0 && <span className="chip" title="Only candidates who state one of these locations">Locations: {s.locations.join(' or ')}</span>}
          
        </span>
        <span className="cluster cluster-tight">
          {(s.role.trim() || s.locations.length > 0) && <button type="button" className="link-btn" onClick={s.clearRoleLocation}>Clear title and location</button>}
          <button type="button" className="btn btn-secondary btn-compact" onClick={s.reset}>Reset</button>
        </span>
      </div>
    </form>
  );
}
