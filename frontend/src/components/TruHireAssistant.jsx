import React, { useEffect, useRef, useState } from 'react';
import { Bot, Paperclip, Send, Sparkles, Trash2, X } from 'lucide-react';
import { assistantApi } from '../lib/api';
import { streamAssistantMessage } from '../lib/assistantStream';
import { errorText } from '../lib/errors';
import DemandSessionCard from './assistant/DemandSessionCard';
import ResultCards from './assistant/ResultCards';
import Markdown from './assistant/Markdown';
import './truhire-assistant.css';

const GREETING = 'Hello! I’m your TruHire Assistant. I can help you create demands, find candidates and manage recruitment workflows. What would you like to do?';
const QUICK_ACTIONS = [
  { title: 'Demand info', hint: 'Open positions, status, client', prompt: 'How many open positions does DM-0005 have?' },
  { title: 'Find candidates', hint: 'Best matches for a demand, with scores', prompt: 'Best candidates for DM-0005' },
  { title: 'Candidate history', hint: 'Where a candidate was submitted, and notes', prompt: 'Show history of ' },
  { title: 'Create demand', hint: 'Guided form, or upload a JD', prompt: 'Create a new demand' },
];
const OPEN_STATUSES = ['choose_mode', 'collecting', 'review', 'creating'];
const asMessage = (m) => ({ role: m.role, content: m.content, data: m.data || {} });

export default function TruHireAssistant() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([{ role: 'assistant', content: GREETING }]);
  const [conversationId, setConversationId] = useState(null);
  const [input, setInput] = useState('');
  const [session, setSession] = useState(null);  // the open guided demand session, as the server reports it
  const [sessionBusy, setSessionBusy] = useState(false);
  const [sessionError, setSessionError] = useState(null);
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [expandedClients, setExpandedClients] = useState({});
  const [deciding, setDeciding] = useState(false);
  const endRef = useRef(null);
  const inputRef = useRef(null);
  const launcherRef = useRef(null);

  const append = (message) => setMessages((current) => [...current, message]);
  const adoptSession = (next) => setSession(next && OPEN_STATUSES.includes(next.status) ? next : null);

  useEffect(() => {
    if (!open) return undefined;
    let cancelled = false;
    const restore = async () => {
      try {
        const { data } = await assistantApi.listConversations();
        const latest = data.conversations?.[0];
        if (!latest) return;
        const detail = await assistantApi.getConversation(latest.id);
        if (cancelled) return;
        setConversationId(latest.id);
        const restored = detail.data?.messages || [];
        if (restored.length) setMessages(restored.map(asMessage));
        adoptSession(detail.data?.demand_session);
      } catch (error) {
        console.error('Failed to restore assistant conversation:', error);
      }
    };
    restore();
    return () => { cancelled = true; };
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    endRef.current?.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth' });
  }, [messages, session, open]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  // Grow the message box with its text (up to a cap), and shrink it again after sending.
  useEffect(() => {
    const box = inputRef.current;
    if (!box) return;
    box.style.height = 'auto';
    box.style.height = `${Math.min(box.scrollHeight, 140)}px`;
  }, [input, open]);

  const closePanel = () => { setOpen(false); launcherRef.current?.focus(); };

  // Every guided-workflow step goes to the server, which validates it and decides what comes next.
  const actOnSession = async (action, body) => {
    if (!session || sessionBusy) return null;
    setSessionBusy(true);
    setSessionError(null);
    try {
      const { data } = await assistantApi.demandSession.act(session.id, action, body);
      const added = (data.messages || []).map(asMessage);
      setMessages((current) => [...current, ...added]);
      adoptSession(data.session);
      return added;
    } catch (error) {
      if ([404, 409].includes(error?.response?.status)) {
        // Out of step with the server (another tab, or the demand ended): show where it really is.
        try { adoptSession((await assistantApi.demandSession.get(session.id)).data.session); } catch { setSession(null); }
      }
      setSessionError(errorText(error, 'I couldn’t reach the server. Your answers are saved; please try again.'));
      return null;
    } finally {
      setSessionBusy(false);
    }
  };

  const handleResponse = (data) => {
    const content = data.reply || data.message;
    if (content) append({ role: 'assistant', content, data });
    if (data.action === 'demand_session') { setSessionError(null); adoptSession(data.session); }
  };

  const askModel = async (text) => {
    setLoading(true);
    let started = false;
    const onToken = (piece) => {
      if (!started) {
        started = true;
        setStreaming(true);
        append({ role: 'assistant', content: piece });
        return;
      }
      setMessages((current) => {
        const last = current[current.length - 1];
        return [...current.slice(0, -1), { ...last, content: last.content + piece }];
      });
    };
    try {
      const data = await streamAssistantMessage({ message: text, conversation_id: conversationId }, onToken);
      setConversationId(data.conversation_id);
      if (started) {
        // The streamed text is already on screen; attach the final payload (actions, results) to it.
        setMessages((current) => [...current.slice(0, -1), { role: 'assistant', content: data.reply, data }]);
      } else {
        handleResponse(data);
      }
    } catch (error) {
      append({ role: 'assistant', content: error?.response?.data?.detail || error?.message || 'I could not complete that request.', data: { action: 'error', retryText: text } });
    } finally {
      setStreaming(false);
      setLoading(false);
    }
  };

  const send = async (event) => {
    event?.preventDefault?.();
    const text = input.trim();
    if (!text || loading || sessionBusy) return;
    setInput('');
    // While a demand is open, typed text is an answer or a command (cancel, back, skip, edit …) handled by the server.
    // A question goes to the assistant as usual and the demand stays open.
    if (session && !text.endsWith('?')) {
      const added = await actOnSession('message', { text });
      if (added && !added.some((m) => m.role === 'user')) {
        setMessages((current) => [...current.slice(0, current.length - added.length), { role: 'user', content: text }, ...current.slice(current.length - added.length)]);
      }
      return;
    }
    append({ role: 'user', content: text });
    await askModel(text);
  };

  // A write the agent proposed runs only when the user confirms it here.
  const decide = async (index, pending, approve) => {
    if (deciding) return;
    setDeciding(true);
    try {
      const { data } = await assistantApi.confirm({ conversation_id: conversationId, pending_id: pending.id, approve });
      setMessages((current) => current.map((m, i) => (i === index ? { ...m, data: { ...m.data, pending: { ...m.data.pending, decision: approve ? 'approve' : 'reject' } } } : m)));
      const content = data.reply || data.message;
      if (content) append({ role: 'assistant', content, data });
    } catch (error) {
      append({ role: 'assistant', content: errorText(error, 'I could not complete that action.'), data: { action: 'error' } });
    } finally {
      setDeciding(false);
    }
  };

  const retry = (index, text) => {
    if (loading) return;
    setMessages((current) => current.filter((_, i) => i !== index));
    askModel(text);
  };

  const upload = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file || loading || sessionBusy) return;
    append({ role: 'user', content: `Uploading “${file.name}”…` });
    setLoading(true);
    const form = new FormData();
    form.append('file', file);
    try {
      if (session && session.status !== 'creating') {
        // A demand is open: the document fills in what it states, and the user reviews it.
        const { data } = await assistantApi.demandSession.attach(session.id, form);
        setMessages((current) => [...current, ...(data.messages || []).map(asMessage)]);
        adoptSession(data.session);
      } else {
        if (conversationId) form.append('conversation_id', conversationId);
        const { data } = await assistantApi.upload(form);
        setConversationId(data.conversation_id);
        handleResponse(data);
      }
    } catch (error) {
      append({ role: 'assistant', content: errorText(error, 'The document could not be processed.') });
    } finally {
      setLoading(false);
    }
  };

  const clearChat = async () => {
    if (loading || !window.confirm('Clear all TruHire Assistant chat history? This cannot be undone.')) return;
    setLoading(true);
    try {
      await assistantApi.clearConversations();
      setConversationId(null);
      setMessages([{ role: 'assistant', content: GREETING }]);
      setSession(null);
      setSessionError(null);
      setExpandedClients({});
    } catch (error) {
      append({ role: 'assistant', content: error?.response?.data?.detail || 'I could not clear the chat history. Please try again.' });
    } finally {
      setLoading(false);
    }
  };

  const step = session?.status === 'collecting' && session.input_mode === 'step_by_step' ? session.fields.find((f) => f.key === session.current_field) : null;
  const placeholder = !session ? 'Ask about TruHire…'
    : step ? `${step.label}${step.required ? '' : ' (or say skip)'}`
      : 'Use the options above, or type “cancel”';

  return (
    <>
      {open && (
        <section className="truhire-assistant-panel" aria-label="TruHire AI Assistant" onKeyDown={(event) => { if (event.key === 'Escape') closePanel(); }}>
          <header className="truhire-assistant-header">
            <div className="truhire-assistant-title"><span className="truhire-assistant-avatar"><Sparkles size={16} /></span><span><strong>TruHire Assistant</strong><small>Ask or act: demands, candidates, history, emails</small></span></div>
            <span className="cluster cluster-tight">
              <button type="button" className="icon-btn" onClick={clearChat} disabled={loading} aria-label="Clear chat" title="Clear chat"><Trash2 size={16} /></button>
              <button type="button" className="icon-btn" onClick={closePanel} aria-label="Close assistant"><X size={18} /></button>
            </span>
          </header>
          <div className="truhire-assistant-messages" role="log" aria-live="polite" aria-label="Conversation" aria-busy={loading || sessionBusy}>
            {messages.map((message, index) => (
              <div key={`${index}-${message.role}`} className={`truhire-assistant-row ${message.role}`}>
                {message.role === 'assistant' && <span className="truhire-assistant-avatar small"><Bot size={13} /></span>}
                <div className={`truhire-assistant-bubble${message.data?.action === 'error' ? ' error' : ''}`} role={message.data?.action === 'error' ? 'alert' : undefined}>{message.role === 'assistant' ? <Markdown text={message.content} /> : message.content}
                  {message.data?.action === 'error' && message.data.retryText && <button type="button" className="btn btn-secondary assistant-action" onClick={() => retry(index, message.data.retryText)} disabled={loading}>Try again</button>}
                  <ResultCards data={message.data} index={index} expanded={expandedClients}
                    onToggle={(key) => setExpandedClients((current) => ({ ...current, [key]: !current[key] }))}
                    onPrefill={setInput} onDecide={decide} deciding={deciding} />
                </div>
              </div>
            ))}
            {messages.length === 1 && !session && <div className="assistant-quick" aria-label="What I can do">
              {QUICK_ACTIONS.map((a) => <button key={a.title} type="button" onClick={() => { setInput(a.prompt); inputRef.current?.focus(); }}>
                <strong>{a.title}</strong><span>{a.hint}</span>
              </button>)}
            </div>}
            {session && <DemandSessionCard session={session} busy={sessionBusy} error={sessionError} onAct={actOnSession} onCancel={() => actOnSession('cancel')} />}
            {loading && !streaming && <div className="truhire-assistant-thinking" role="status"><Sparkles size={14} aria-hidden="true" /> Working…</div>}
            <div ref={endRef} />
          </div>
          <form className="truhire-assistant-composer" onSubmit={send}>
            <label className="truhire-assistant-upload" title="Upload demand or resume"><Paperclip size={17} aria-hidden="true" /><span className="sr-only">Upload a demand or resume</span><input type="file" onChange={upload} disabled={loading || sessionBusy} accept=".pdf,.doc,.docx,.rtf,.md,.txt,.csv,.jpg,.jpeg,.png,.webp" /></label>
            <textarea ref={inputRef} rows={1} value={input} onChange={(event) => setInput(event.target.value)} placeholder={placeholder} aria-label="Message TruHire Assistant"
              onKeyDown={(event) => { if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) { event.preventDefault(); send(); } }} />
            <button type="submit" className="btn btn-primary" disabled={!input.trim() || loading || sessionBusy} aria-label="Send message"><Send size={15} /></button>
          </form>
        </section>
      )}
      <button type="button" ref={launcherRef} className="truhire-assistant-bubble-button" onClick={() => (open ? closePanel() : setOpen(true))} aria-expanded={open} aria-label={open ? 'Close TruHire AI Assistant' : 'Open TruHire AI Assistant'} title="TruHire AI Assistant"><Bot size={23} /></button>
    </>
  );
}
