import React from 'react';
import { Menu, Moon, Sun } from 'lucide-react';
import { useTheme } from '../context/ThemeContext';
import Logo from './Logo';
import AccountMenu from './AccountMenu';

// Fixed top bar shown on every page: menu button and logo on the left, theme switch and account on the right.
export default function Navbar({ onToggleMenu, menuOpen = false }) {
  const { theme, toggleTheme } = useTheme();
  const next = theme === 'dark' ? 'light' : 'dark';

  return (
    <header className="navbar">
      <div className="navbar-left">
        <button
          type="button"
          onClick={onToggleMenu}
          className="icon-btn menu-btn"
          aria-label="Toggle navigation"
          aria-controls="app-sidebar"
          aria-expanded={menuOpen}
        >
          <Menu size={22} />
        </button>
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
