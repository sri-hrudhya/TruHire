import { useRef } from 'react';
import { nextCategoryId } from '../lib/categories';
import './category-row.css';

// Categories as one horizontal row of tabs (not boxes). "All" is first and selects nothing (null).
// Arrow keys / Home / End move the selection; the row scrolls sideways when names do not fit.
export default function CategoryRow({ demands, allCount = null, activeId = null, onSelect, label = 'Categories' }) {
  const rowRef = useRef(null);
  const tabs = [{ id: null, name: 'All', count: allCount }, ...demands.map((d) => ({ id: d.id, name: d.name, count: d.jd_count }))];
  const ids = tabs.map((t) => t.id);

  const onKeyDown = (e) => {
    const next = nextCategoryId(ids, activeId, e.key);
    if (next === activeId && !['Home', 'End'].includes(e.key)) return;
    if (!['ArrowRight', 'ArrowLeft', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(e.key)) return;
    e.preventDefault();
    onSelect(next);
    requestAnimationFrame(() => rowRef.current?.querySelector('[aria-selected="true"]')?.focus());
  };

  return (
    <div className="category-row" role="tablist" aria-label={label} ref={rowRef} onKeyDown={onKeyDown}>
      {tabs.map((t) => {
        const selected = t.id === activeId;
        return (
          <button
            key={t.id ?? 'all'}
            type="button"
            role="tab"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            className="category-tab"
            onClick={() => onSelect(t.id)}
          >
            <span>{t.name}</span>
            {t.count !== null && t.count !== undefined && <span className="category-count">{t.count}</span>}
          </button>
        );
      })}
    </div>
  );
}
