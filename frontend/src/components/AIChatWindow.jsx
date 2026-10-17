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
    <div className="chat-window animate-fade-in">
      <div className="chat-header">
        <div className="flex items-center gap-2">
          <div className="chat-avatar"><Sparkles size={16} /></div>
          <div>
            <div className="text-sm font-bold text-main">{title}</div>
            <div className="text-xs text-subtle">Persistent, RAG-grounded conversation</div>
          </div>
        </div>
        <button onClick={onClose} className="icon-btn"><X size={18} /></button>
      </div>
      <div className="chat-body">
        {messages.map((msg, i) => {
          const isUser = msg.role === 'user';
          return (
            <div key={i} className={`chat-row ${isUser ? 'chat-row-user' : 'chat-row-assistant'}`}>
              {!isUser && <div className="chat-avatar chat-avatar-sm"><Bot size={14} /></div>}
              <div className={`chat-bubble ${isUser ? 'chat-bubble-user' : 'chat-bubble-assistant'}`}>{msg.content}</div>
            </div>
          );
        })}
        {loading && <div className="flex items-center gap-2 text-muted text-sm"><Sparkles size={14} className="animate-spin" /> Thinking...</div>}
        <div ref={messagesEndRef} />
      </div>
      <form onSubmit={handleSend} className="chat-footer">
        <input type="text" value={input} onChange={(e) => setInput(e.target.value)} placeholder="Ask a question..." className="input-field flex-1 text-sm" />
        <button type="submit" disabled={!input.trim() || loading} className="btn btn-primary"><Send size={15} /></button>
      </form>
    </div>
  );
}
