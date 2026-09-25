import React, { useState, useRef, useEffect } from 'react';
import { Sparkles, X, Send, Bot } from 'lucide-react';
import { chatApi } from '../lib/api';

const GREETING = 'Hello! I am your TruHire AI recruitment assistant. Ask me questions about candidate suitability, skills evaluation, or job requirements.';

export default function AIChatWindow({ isOpen, onClose, candidateId = null, positionId = null, title = "TruHire AI Copilot" }) {
  const [messages, setMessages] = useState([{ role: 'assistant', content: GREETING }]);
  const [conversationId, setConversationId] = useState(null);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const messagesEndRef = useRef(null);

  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    const loadConversation = async () => {
      try {
        const res = await chatApi.listConversations();
        const rows = res.data?.conversations || [];
        const matching = rows.find(c => (c.candidate_id || null) === (candidateId || null) && (c.position_id || null) === (positionId || null));
        if (matching) {
          const detail = await chatApi.getConversation(matching.id);
          if (!cancelled) {
            setConversationId(matching.id);
            const stored = detail.data?.messages || [];
            setMessages(stored.length ? stored.map(({ role, content }) => ({ role, content })) : [{ role: 'assistant', content: GREETING }]);
          }
        } else if (!cancelled) {
          setConversationId(null);
          setMessages([{ role: 'assistant', content: GREETING }]);
        }
      } catch (err) {
        console.error('Failed to restore chat conversation:', err);
      }
    };
    loadConversation();
    return () => { cancelled = true; };
  }, [isOpen, candidateId, positionId]);

  useEffect(() => {
    if (isOpen) messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isOpen]);

  if (!isOpen) return null;

  const handleSend = async (e) => {
    e.preventDefault();
    if (!input.trim() || loading) return;
    const userMsg = { role: 'user', content: input.trim() };
    const updatedMessages = [...messages, userMsg];
    setMessages(updatedMessages);
    setInput('');
    setLoading(true);
    try {
      // Only send the new user message. The backend loads the complete persisted
      // conversation history, preventing duplicate messages and preserving memory.
      const res = await chatApi.sendMessage({
        messages: [userMsg],
        candidate_id: candidateId,
        position_id: positionId,
        conversation_id: conversationId
      });
      setConversationId(res.data.conversation_id);
      setMessages([...updatedMessages, { role: 'assistant', content: res.data.reply }]);
    } catch (err) {
      console.error('Chat error:', err);
      setMessages([...updatedMessages, { role: 'assistant', content: 'Apologies, I encountered an error answering your question. Please try again.' }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ position: 'fixed', bottom: '1.5rem', right: '1.5rem', width: '420px', height: '560px', backgroundColor: 'var(--bg-card)', border: '1px solid var(--border-color)', borderRadius: 'var(--radius-lg)', boxShadow: 'var(--shadow-lg)', display: 'flex', flexDirection: 'column', zIndex: 50, overflow: 'hidden' }} className="animate-fade-in">
      <div style={{ padding: '1rem 1.25rem', borderBottom: '1px solid var(--border-color)', display: 'flex', alignItems: 'center', justifyContent: 'space-between', backgroundColor: 'var(--bg-surface)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.625rem' }}>
          <div style={{ width: '28px', height: '28px', borderRadius: '6px', backgroundColor: 'var(--primary-light)', color: 'var(--primary)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}><Sparkles size={16} /></div>
          <div>
            <div style={{ fontSize: '0.875rem', fontWeight: 700, color: 'var(--text-main)' }}>{title}</div>
            <div style={{ fontSize: '0.7rem', color: 'var(--text-subtle)' }}>Persistent, RAG-grounded conversation</div>
          </div>
        </div>
        <button onClick={onClose} style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', padding: '0.25rem', borderRadius: '4px' }}><X size={18} /></button>
      </div>
      <div style={{ flex: 1, padding: '1.25rem', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '1rem' }}>
        {messages.map((msg, i) => {
          const isUser = msg.role === 'user';
          return <div key={i} style={{ display: 'flex', gap: '0.625rem', alignSelf: isUser ? 'flex-end' : 'flex-start', maxWidth: '85%' }}>
            {!isUser && <div style={{ width: '24px', height: '24px', borderRadius: '50%', backgroundColor: 'var(--primary-light)', color: 'var(--primary)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginTop: '2px' }}><Bot size={14} /></div>}
            <div style={{ padding: '0.75rem 1rem', borderRadius: '12px', fontSize: '0.875rem', lineHeight: 1.45, backgroundColor: isUser ? 'var(--primary)' : 'var(--bg-subtle)', color: isUser ? '#ffffff' : 'var(--text-main)', border: isUser ? 'none' : '1px solid var(--border-color)', whiteSpace: 'pre-wrap' }}>{msg.content}</div>
          </div>;
        })}
        {loading && <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'center', color: 'var(--text-muted)', fontSize: '0.8125rem' }}><Sparkles size={14} className="animate-spin" /> Thinking...</div>}
        <div ref={messagesEndRef} />
      </div>
      <form onSubmit={handleSend} style={{ padding: '0.875rem 1rem', borderTop: '1px solid var(--border-color)', backgroundColor: 'var(--bg-surface)', display: 'flex', gap: '0.5rem' }}>
        <input type="text" value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask a question..." className="input-field" style={{ flex: 1, padding: '0.5rem 0.75rem', fontSize: '0.8125rem' }} />
        <button type="submit" disabled={!input.trim() || loading} className="btn btn-primary" style={{ padding: '0.5rem 0.875rem' }}><Send size={15} /></button>
      </form>
    </div>
  );
}
