// Splits plain JD text into display blocks: heading, paragraph, bullet list, numbered list.
// Pure and conservative: anything not recognised stays a paragraph, and no line is dropped.

const BULLET = /^\s*(?:[-*•·▪◦●■]|–|—)\s+(.*\S)\s*$/;
const NUMBERED = /^\s*(?:\d{1,3}[.)]|\(\d{1,3}\))\s+(.*\S)\s*$/;

// A short line that ends in a colon, or is written in capitals, reads as a section heading.
export function isHeading(line) {
  const t = line.trim();
  if (!t || t.length > 80 || BULLET.test(t) || NUMBERED.test(t)) return false;
  if (/:$/.test(t)) return t.length > 1;
  const letters = t.replace(/[^A-Za-z]/g, '');
  return letters.length >= 3 && t === t.toUpperCase() && !/[.!?]$/.test(t);
}

export function parseJd(text) {
  const blocks = [];
  let para = [];
  let list = null;

  const flushPara = () => {
    if (para.length) blocks.push({ type: 'p', text: para.join(' ') });
    para = [];
  };
  const flushList = () => {
    if (list) blocks.push(list);
    list = null;
  };
  const addItem = (type, item) => {
    flushPara();
    if (!list || list.type !== type) { flushList(); list = { type, items: [] }; }
    list.items.push(item);
  };

  for (const raw of String(text || '').replace(/\r\n?/g, '\n').split('\n')) {
    const line = raw.trimEnd();
    if (!line.trim()) { flushPara(); flushList(); continue; }
    const bullet = BULLET.exec(line);
    const numbered = bullet ? null : NUMBERED.exec(line);
    if (bullet) addItem('ul', bullet[1]);
    else if (numbered) addItem('ol', numbered[1]);
    else if (isHeading(line)) { flushPara(); flushList(); blocks.push({ type: 'h', text: line.trim().replace(/:$/, '') }); }
    else if (list && /^\s{2,}\S/.test(line)) list.items[list.items.length - 1] += ` ${line.trim()}`; // wrapped list item
    else { flushList(); para.push(line.trim()); }
  }
  flushPara();
  flushList();
  return blocks;
}
