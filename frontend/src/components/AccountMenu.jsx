import React, { useEffect, useRef, useState } from 'react';
import { LogOut, User as UserIcon } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

// Account button in the top bar: shows who is signed in and holds the sign-out option.
export default function AccountMenu() {
  const { user, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);
  const name = user?.name || 'Recruiter';

  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => { if (ref.current && !ref.current.contains(e.target)) setOpen(false); };
    const onKey = (e) => { if (e.key === 'Escape') setOpen(false); };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div className="account-menu" ref={ref}>
      <button
        type="button"
        className="account-trigger"
        onClick={() => setOpen((o) => !o)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label={`Account: ${name}`}
      >
        <span className="avatar"><UserIcon size={16} /></span>
        <span className="account-name truncate">{name}</span>
      </button>
      {open && (
        <div className="account-popover" role="menu">
          <div className="account-details">
            <div className="text-sm font-semibold text-main truncate">{name}</div>
            {user?.email && <div className="text-xs text-subtle truncate">{user.email}</div>}
          </div>
          <button type="button" role="menuitem" className="account-item" onClick={logout}>
            <LogOut size={15} /> Log out
          </button>
        </div>
      )}
    </div>
  );
}
