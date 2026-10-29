import { parseJd } from '../../lib/jdFormat';
import './requirements.css';

// Read-only JD text on a plain sheet; headings, paragraphs and lists are kept.
export default function JdBody({ text }) {
  const blocks = parseJd(text);
  if (!blocks.length) return <p className="jd-body jd-body-empty">No description.</p>;
  return (
    <article className="jd-body">
      {blocks.map((b, i) => {
        if (b.type === 'h') return <h4 key={i}>{b.text}</h4>;
        if (b.type === 'p') return <p key={i}>{b.text}</p>;
        const List = b.type === 'ol' ? 'ol' : 'ul';
        return <List key={i}>{b.items.map((it, j) => <li key={j}>{it}</li>)}</List>;
      })}
    </article>
  );
}
