import React from 'react';

// Small, safe Markdown for assistant replies: headings, bullet / numbered lists, tables, code, bold, italic,
// inline code and links. It builds React elements (never HTML strings), so model text cannot inject markup.

const INLINE = /(\*\*[^*]+\*\*|__[^_]+__|`[^`]+`|\[[^\]]+\]\([^)\s]+\)|\*[^*\s][^*]*\*|_[^_\s][^_]*_)/g;
const SAFE_URL = /^(https?:\/\/|\/|mailto:)/i;

function inline(text, keyBase) {
  return String(text).split(INLINE).map((part, i) => {
    const key = `${keyBase}-${i}`;
    if (!part) return null;
    if (/^(\*\*|__)[^*_]+(\*\*|__)$/.test(part)) return <strong key={key}>{inline(part.slice(2, -2), key)}</strong>;
    if (/^`[^`]+`$/.test(part)) return <code key={key}>{part.slice(1, -1)}</code>;
    const link = part.match(/^\[([^\]]+)\]\(([^)\s]+)\)$/);
    if (link) return SAFE_URL.test(link[2]) ? <a key={key} href={link[2]} target="_blank" rel="noreferrer noopener">{link[1]}</a> : link[1];
    if (/^(\*|_)[^*_]+(\*|_)$/.test(part)) return <em key={key}>{part.slice(1, -1)}</em>;
    return part;
  });
}

const BULLET = /^\s*(?:[-*•]\s+|[-*•](?=\*\*))(.*)$/;   // "- item", "* item", and the malformed "-**Label:** item"
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/;
const HEADING = /^\s*(#{1,4})\s+(.*)$/;
const ROW = /^\s*\|(.+)\|\s*$/;

export default function Markdown({ text }) {
  const lines = String(text || '').replace(/\r\n/g, '\n').split('\n');
  const blocks = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const key = `b${blocks.length}`;
    if (!line.trim()) { i += 1; continue; }
    if (line.trim().startsWith('```')) {
      const code = [];
      for (i += 1; i < lines.length && !lines[i].trim().startsWith('```'); i += 1) code.push(lines[i]);
      i += 1;
      blocks.push(<pre key={key}><code>{code.join('\n')}</code></pre>);
      continue;
    }
    const heading = line.match(HEADING);
    if (heading) { blocks.push(<p key={key} className="md-heading">{inline(heading[2], key)}</p>); i += 1; continue; }
    if (ROW.test(line) && ROW.test(lines[i + 1] || '') && /^[\s|:-]+$/.test(lines[i + 1])) {
      const cells = (row) => row.trim().slice(1, -1).split('|').map((c) => c.trim());
      const head = cells(line);
      const body = [];
      for (i += 2; i < lines.length && ROW.test(lines[i]); i += 1) body.push(cells(lines[i]));
      blocks.push(
        <div key={key} className="md-table"><table>
          <thead><tr>{head.map((c, n) => <th key={n}>{inline(c, `${key}h${n}`)}</th>)}</tr></thead>
          <tbody>{body.map((r, n) => <tr key={n}>{r.map((c, m) => <td key={m}>{inline(c, `${key}r${n}c${m}`)}</td>)}</tr>)}</tbody>
        </table></div>,
      );
      continue;
    }
    const kind = BULLET.test(line) ? 'ul' : NUMBERED.test(line) ? 'ol' : null;
    if (kind) {
      const pattern = kind === 'ul' ? BULLET : NUMBERED;
      const items = [];
      for (; i < lines.length && pattern.test(lines[i]); i += 1) items.push(lines[i].match(pattern)[1]);
      const List = kind;
      blocks.push(<List key={key}>{items.map((item, n) => <li key={n}>{inline(item, `${key}i${n}`)}</li>)}</List>);
      continue;
    }
    const paragraph = [];
    for (; i < lines.length && lines[i].trim() && !BULLET.test(lines[i]) && !NUMBERED.test(lines[i]) && !HEADING.test(lines[i]) && !lines[i].trim().startsWith('```'); i += 1) paragraph.push(lines[i]);
    blocks.push(<p key={key}>{paragraph.map((l, n) => <React.Fragment key={n}>{n > 0 && <br />}{inline(l, `${key}p${n}`)}</React.Fragment>)}</p>);
  }
  return <div className="md">{blocks}</div>;
}
