import React, { useEffect, useRef, useState } from 'react';
import { Bot, Check, FileText, Paperclip, Send, Sparkles, Upload, X } from 'lucide-react';
import { assistantApi } from '../lib/api';
import './truhire-assistant.css';

const GREETING = 'Hi! I can ingest resumes or a demand document, create a requirement after you choose its demand, find the strict top candidates, and prepare email drafts.';

export default function TruHireAssistant() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([{ role: 'assistant', content: GREETING }]);
  const [conversationId, setConversationId] = useState(null);
  const [input, setInput] = useState('');
  const [pending, setPending] = useState(null);
  const [kind, setKind] = useState('auto');
  const [loading, setLoading] = useState(false);
  const endRef = useRef(null);

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
        if (restored.length) {
          setMessages(restored.map((message) => ({
            role: message.role,
            content: message.content,
            data: message.data || {},
          })));
        }
      } catch (error) {
        console.error('Failed to restore assistant conversation:', error);
      }
    };
    restore();
    return () => { cancelled = true; };
  }, [open]);

  useEffect(() => {
    if (open) endRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, open]);

  const append = (message) => setMessages((current) => [...current, message]);

  const handleResponse = (data) => {
    if (data.reply) append({ role: 'assistant', content: data.reply, data });
    if (data.action === 'confirm_jd') setPending(data);
    if (data.action === 'created') setPending(null);
  };

  const send = async (event) => {
    event?.preventDefault();
    const text = input.trim();
    if (!text || loading) return;
    append({ role: 'user', content: text });
    setInput('');
    setLoading(true);
    try {
      const { data } = await assistantApi.send({ message: text, conversation_id: conversationId });
      setConversationId(data.conversation_id);
      handleResponse(data);
    } catch (error) {
      append({ role: 'assistant', content: error?.response?.data?.detail || 'I could not complete that request.' });
    } finally {
      setLoading(false);
    }
  };

  const upload = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file || loading) return;
    const form = new FormData();
    form.append('file', file);
    form.append('kind', kind);
    if (conversationId) form.append('conversation_id', conversationId);
    append({ role: 'user', content: `Uploading “${file.name}”…` });
    setLoading(true);
    try {
      const { data } = await assistantApi.upload(form);
      setConversationId(data.conversation_id);
      handleResponse(data);
    } catch (error) {
      append({ role: 'assistant', content: error?.response?.data?.detail || 'The document could not be processed.' });
    } finally {
      setLoading(false);
    }
  };

  const chooseDemand = async (demandId) => {
    if (!pending?.draft || loading) return;
    setLoading(true);
    try {
      const { data } = await assistantApi.confirmJd({ ...pending.draft, demand_id: demandId });
      handleResponse(data);
    } catch (error) {
      append({ role: 'assistant', content: error?.response?.data?.detail || 'The requirement could not be created.' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {open && (
        <section className="truhire-assistant-panel" aria-label="TruHire AI Assistant">
          <header className="truhire-assistant-header">
            <div className="truhire-assistant-title"><span className="truhire-assistant-avatar"><Sparkles size={16} /></span><span><strong>TruHire Assistant</strong><small>Demand-grounded recruitment actions</small></span></div>
            <button type="button" className="icon-btn" onClick={() => setOpen(false)} aria-label="Close assistant"><X size={18} /></button>
          </header>
          <div className="truhire-assistant-messages">
            {messages.map((message, index) => (
              <div key={`${index}-${message.role}`} className={`truhire-assistant-row ${message.role}`}>
                {message.role === 'assistant' && <span className="truhire-assistant-avatar small"><Bot size={13} /></span>}
                <div className="truhire-assistant-bubble">{message.content}
                  {message.data?.action === 'matches' && (
                    <div className="truhire-assistant-results">{message.data.results.slice(0, message.data.position.no_of_positions).map((row, i) => <div key={row.candidate?.id || i}><b>{i + 1}. {row.candidate?.candidate_name || row.candidate_name}</b> <span>{typeof row.match_score === 'number' ? `${row.match_score.toFixed(1)}%` : ''}</span></div>)}</div>
                  )}
                  {message.data?.action === 'email' && <button type="button" className="btn btn-secondary assistant-action" onClick={() => { window.location.href = `/email?position=${message.data.position_id}`; }}>Open Email drafts</button>}
                </div>
              </div>
            ))}
            {pending?.demands && (
              <div className="truhire-assistant-demand-picker">
                <strong>Choose the demand for “{pending.draft.title}”</strong>
                <div>{pending.demands.map((demand) => <button key={demand.id} type="button" onClick={() => chooseDemand(demand.id)} disabled={loading}><Check size={13} />{demand.name}</button>)}</div>
              </div>
            )}
            {loading && <div className="truhire-assistant-thinking"><Sparkles size={14} /> Working…</div>}
            <div ref={endRef} />
          </div>
          <form className="truhire-assistant-composer" onSubmit={send}>
            <select value={kind} onChange={(event) => setKind(event.target.value)} aria-label="Upload type"><option value="auto">Auto</option><option value="jd">Demand</option><option value="resume">Resume</option></select>
            <label className="truhire-assistant-upload" title="Upload demand or resume"><Paperclip size={17} /><input type="file" onChange={upload} accept=".pdf,.doc,.docx,.rtf,.md,.txt,.csv,.jpg,.jpeg,.png,.webp" /></label>
            <input value={input} onChange={(event) => setInput(event.target.value)} placeholder="Ask about TruHire…" aria-label="Message TruHire Assistant" />
            <button type="submit" className="btn btn-primary" disabled={!input.trim() || loading} aria-label="Send message"><Send size={15} /></button>
          </form>
        </section>
      )}
      <button type="button" className="truhire-assistant-bubble-button" onClick={() => setOpen((value) => !value)} aria-label="Open TruHire AI Assistant" title="TruHire AI Assistant"><Bot size={23} /></button>
    </>
  );
}
