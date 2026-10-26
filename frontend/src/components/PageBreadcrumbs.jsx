import React from 'react';
import { Link } from 'react-router-dom';
import { ArrowLeft, ChevronRight } from 'lucide-react';

// Back button + breadcrumb trail for subviews. `items` is [{ label, to? | onClick? }];
// the last item is the current page.
export default function PageBreadcrumbs({ onBack, backLabel, items = [] }) {
  return (
    <div className="page-breadcrumbs">
      {onBack && (
        <button type="button" onClick={onBack} className="back-link">
          <ArrowLeft size={16} /> Back to {backLabel}
        </button>
      )}
      {items.length > 0 && (
        <nav aria-label="Breadcrumb">
          <ol className="breadcrumb-list">
            {items.map((item, i) => {
              const isLast = i === items.length - 1;
              return (
                <li key={`${item.label}-${i}`} className="breadcrumb-item">
                  {isLast ? (
                    <span aria-current="page" className="breadcrumb-current truncate">{item.label}</span>
                  ) : item.to ? (
                    <Link to={item.to} className="breadcrumb-link">{item.label}</Link>
                  ) : (
                    <button type="button" onClick={item.onClick} className="breadcrumb-link">{item.label}</button>
                  )}
                  {!isLast && <ChevronRight size={14} className="breadcrumb-sep" aria-hidden="true" />}
                </li>
              );
            })}
          </ol>
        </nav>
      )}
    </div>
  );
}
