import React, { useEffect, useRef, useState } from 'react';
import { Bot, Paperclip, Send, Sparkles, Trash2, X } from 'lucide-react';
import { assistantApi } from '../lib/api';
import { streamAssistantMessage } from '../lib/assistantStream';
import { errorText } from '../lib/errors';
import DemandSessionCard from './assistant/DemandSessionCard';
import './truhire-assistant.css';

const GREETING = 'Hello! I’m your TruHire Assistant. I can help you create demands, find candidates and manage recruitment workflows. What would you like to do?';
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
            <div className="truhire-assistant-title"><span className="truhire-assistant-avatar"><Sparkles size={16} /></span><span><strong>TruHire Assistant</strong><small>Demands, candidate search, email drafts</small></span></div>
            <span className="cluster cluster-tight">
              <button type="button" className="icon-btn" onClick={clearChat} disabled={loading} aria-label="Clear chat" title="Clear chat"><Trash2 size={16} /></button>
              <button type="button" className="icon-btn" onClick={closePanel} aria-label="Close assistant"><X size={18} /></button>
            </span>
          </header>
          <div className="truhire-assistant-messages" role="log" aria-live="polite" aria-label="Conversation" aria-busy={loading || sessionBusy}>
            {messages.map((message, index) => (
              <div key={`${index}-${message.role}`} className={`truhire-assistant-row ${message.role}`}>
                {message.role === 'assistant' && <span className="truhire-assistant-avatar small"><Bot size={13} /></span>}
                <div className={`truhire-assistant-bubble${message.data?.action === 'error' ? ' error' : ''}`} role={message.data?.action === 'error' ? 'alert' : undefined}>{message.content}
                  {message.data?.action === 'error' && message.data.retryText && <button type="button" className="btn btn-secondary assistant-action" onClick={() => retry(index, message.data.retryText)} disabled={loading}>Try again</button>}
                  {message.data?.action === 'matches' && (
                    <div className="truhire-assistant-results">{message.data.results.slice(0, message.data.position.no_of_positions).map((row, i) => <div key={row.candidate?.id || i}><b>{i + 1}. {row.candidate?.candidate_name || row.candidate_name}</b> <span>{typeof row.match_score === 'number' ? `${row.match_score.toFixed(1)}%` : ''}</span></div>)}</div>
                  )}
                  {message.data?.action === 'client_candidate_matches' && (message.data.client_groups || []).map((group) => (
                    <section className="truhire-assistant-client-requirements" key={group.position.id}>
                      <strong>{group.position.title}</strong><small>{group.position.client_name} · {group.total_matches} matches</small>
                      {group.results.map((row) => <a key={row.candidate.id} href={`/candidates/${row.candidate.id}`}>
                        <b>{row.candidate.candidate_name}</b><small>{typeof row.match_score === 'number' ? `${row.match_score.toFixed(1)}% match` : 'Open candidate profile'}</small>
                      </a>)}
                      {!group.results.length && <span>No candidates matched this requirement.</span>}
                    </section>
                  ))}
                  {message.data?.action === 'candidate_history' && <div className="truhire-assistant-results">
                    {message.data.items.map((event, i) => <div key={`${event.timestamp}-${i}`}><b>{event.summary}</b><small>{[new Date(event.timestamp).toLocaleString(), event.position_title, event.client_name].filter(Boolean).join(' · ')}</small></div>)}
                  </div>}
                  {message.data?.action === 'candidate_comparison' && <div className="truhire-assistant-results">
                    {message.data.candidates.map((candidate) => <a key={candidate.id} href={`/candidates/${candidate.id}`}>
                      <b>{candidate.display_id} · {candidate.name}</b>
                      <small>{candidate.years_experience ?? 'Experience not recorded'} years · {candidate.status}</small>
                      <small>Skills: {candidate.skills.join(', ') || 'Not recorded'}</small>
                    </a>)}
                  </div>}
                  {message.data?.action === 'candidate_lookup' && <div className="truhire-assistant-results">
                    {message.data.results.map((candidate) => <a key={candidate.id} href={`/candidates/${candidate.id}`}>
                      <b>{candidate.display_id} · {candidate.candidate_name}</b>
                      <small>{[candidate.current_company, candidate.email, candidate.phone, candidate.status].filter(Boolean).join(' · ')}</small>
                    </a>)}
                  </div>}
                  {message.data?.action === 'email' && <button type="button" className="btn btn-secondary assistant-action" onClick={() => { window.location.href = `/email?position=${message.data.position_id}`; }}>Open Email drafts</button>}
                  {message.data?.action === 'created' && message.data.position?.id && <button type="button" className="btn btn-secondary assistant-action" onClick={() => { window.location.href = `/requirements?id=${message.data.position.id}`; }}>Open this demand</button>}
                  {message.data?.action === 'choose_position' && message.data.positions?.length > 0 && (
                    <div className="truhire-assistant-results">
                      {message.data.positions.slice(0, 8).map((position) => (
                        <button key={position.id} type="button" className="btn btn-secondary assistant-action" onClick={() => setInput(`What JD fields are present or missing for ${position.display_id}?`)}>
                          {position.display_id} · {position.title}
                        </button>
                      ))}
                    </div>
                  )}
                  {(message.data?.action === 'client_groups' || message.data?.action === 'client_demands') && (
                    <div className="truhire-assistant-client-groups">
                      {(message.data.clients || [{ name: message.data.client_name, requirements: message.data.requirements || [], count: (message.data.requirements || []).length }]).map((client) => {
                        const expanded = message.data.action === 'client_demands' || expandedClients[`${index}:${client.name}`];
                        return (
                          <section key={client.name} className="truhire-assistant-client-group">
                            <button type="button" className="truhire-assistant-client-toggle" onClick={() => setExpandedClients((current) => ({ ...current, [`${index}:${client.name}`]: !expanded }))} aria-expanded={expanded}>
                              <strong>{client.name}</strong><span>{client.count ?? client.requirements.length} {(client.count ?? client.requirements.length) === 1 ? 'demand' : 'demands'}</span>
                            </button>
                            {expanded && <div className="truhire-assistant-client-requirements">
                              {client.requirements.map((requirement) => {
                                const clientParam = requirement.client_name?.trim() ? requirement.client_name : '__unassigned__';
                                const query = new URLSearchParams();
                                if (requirement.demand_id) query.set('demand', requirement.demand_id);
                                query.set('client', clientParam);
                                return <a key={requirement.id} href={`/requirements?${query}`}><b>{requirement.display_id || 'JD'}</b> · {requirement.title}<small>{requirement.demand_name || 'No practice assigned'}</small></a>;
                              })}
                              {!client.requirements.length && <span>No demands found for this client.</span>}
                            </div>}
                          </section>
                        );
                      })}
                    </div>
                  )}
                  {message.data?.field_report && (
                    <div className="truhire-assistant-results truhire-assistant-field-report">
                      <strong>Here’s what I could read from the document</strong>
                      {message.data.field_report.present.length
                        ? message.data.field_report.present.map((field) => <div key={field.name}><b>{field.name}:</b> {field.value}</div>)
                        : <div>No structured fields could be confirmed from the document.</div>}
                      <div><b>Not stated in the document:</b> {message.data.field_report.missing.join(', ') || 'None'}</div>
                    </div>
                  )}
                </div>
              </div>
            ))}
            {session && <DemandSessionCard session={session} busy={sessionBusy} error={sessionError} onAct={actOnSession} onCancel={() => actOnSession('cancel')} />}
            {loading && !streaming && <div className="truhire-assistant-thinking" role="status"><Sparkles size={14} aria-hidden="true" /> Working…</div>}
            <div ref={endRef} />
          </div>
          <form className="truhire-assistant-composer" onSubmit={send}>
            <label className="truhire-assistant-upload" title="Upload demand or resume"><Paperclip size={17} aria-hidden="true" /><span className="sr-only">Upload a demand or resume</span><input type="file" onChange={upload} disabled={loading || sessionBusy} accept=".pdf,.doc,.docx,.rtf,.md,.txt,.csv,.jpg,.jpeg,.png,.webp" /></label>
            <input ref={inputRef} value={input} onChange={(event) => setInput(event.target.value)} placeholder={placeholder} aria-label="Message TruHire Assistant" />
            <button type="submit" className="btn btn-primary" disabled={!input.trim() || loading || sessionBusy} aria-label="Send message"><Send size={15} /></button>
          </form>
        </section>
      )}
      <button type="button" ref={launcherRef} className="truhire-assistant-bubble-button" onClick={() => (open ? closePanel() : setOpen(true))} aria-expanded={open} aria-label={open ? 'Close TruHire AI Assistant' : 'Open TruHire AI Assistant'} title="TruHire AI Assistant"><Bot size={23} /></button>
    </>
  );
}
