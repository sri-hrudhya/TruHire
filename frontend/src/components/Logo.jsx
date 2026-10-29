import React from 'react';

// TruHire mark (three people over a shirt and tie). Colours come from the --logo-* tokens, so the mark
// and the name follow the active theme.
export function LogoMark({ size = 34 }) {
  return (
    <svg className="logo-mark" viewBox="0 0 252 224" height={size} width={(size * 252) / 224} aria-hidden="true" focusable="false">
      <circle cx="53" cy="55" r="20" fill="var(--logo-ink)" />
      <circle cx="126" cy="40" r="35" fill="var(--logo-ink)" />
      <circle cx="199" cy="55" r="20" fill="var(--logo-ink)" />
      <path d="M30 88h192l18 44-38 36-76 44-76-44-38-36z" fill="var(--logo-soft)" strokeLinejoin="round" />
      <path d="M76 88l39 8 13 96-76-42z" fill="var(--logo-mid)" />
      <path d="M176 88l-39 8-13 96 76-42z" fill="var(--logo-mid)" />
    </svg>
  );
}

export default function Logo() {
  return (
    <span className="logo" role="img" aria-label="TruHire">
      <LogoMark />
      <span className="logo-name" aria-hidden="true">TruHire</span>
    </span>
  );
}
