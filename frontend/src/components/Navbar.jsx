import React from 'react';
import { Moon, Sun } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';
import Logo from './Logo';
import AccountMenu from './AccountMenu';

// Fixed top bar shown on every page: logo on the left (the collapse arrow sits under it in the sidebar), theme switch and account on the right.
export default function Navbar() {
  const { theme, toggleTheme } = useTheme();
  const next = theme === 'dark' ? 'light' : 'dark';

  return (
    <header className="navbar">
      <div className="navbar-left">
        <Logo />
      </div>
      <div className="navbar-right">
        <button
          type="button"
          onClick={toggleTheme}
          className="icon-btn theme-btn"
          aria-label={`Switch to ${next} mode`}
          title={`Switch to ${next} mode`}
        >
          {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
        </button>
        <AccountMenu />
      </div>
    </header>
  );
}
