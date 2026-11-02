import React, { useEffect, useRef, useState } from 'react';
import { Bot, Check, FileText, Paperclip, Send, Sparkles, Trash2, Upload, X } from 'lucide-react';
import { assistantApi } from '../lib/api';
import { streamAssistantMessage } from '../lib/assistantStream';
import { OTHER_CLIENT } from '../lib/requirements';
import { useMeta } from '../context/MetaContext';
import './truhire-assistant.css';

const GREETING = 'Hi! Upload a JD and I’ll summarize what I found, help fill in missing details, and create the demand when you’re ready. I can also help find candidates or draft emails.';
const JD_QUESTION_DEFS = [
  { field: 'client_name', reportLabel: 'Client', label: 'client', prompt: 'Which client should I assign to this demand?' },
  { field: 'role', reportLabel: 'Job title', label: 'role', prompt: 'What role is this demand hiring for?' },
  { field: 'location', reportLabel: 'Location', label: 'locations', prompt: 'Which work locations should I add? You can give more than one, separated by commas.' },
  { field: 'experience_years', reportLabel: 'Experience', label: 'minimum experience', prompt: 'What minimum experience should I use? You can answer with a range, like 5–8 years.' },
  { field: 'experience_max_years', reportLabel: 'Maximum experience', label: 'maximum experience', prompt: 'What maximum experience should I use? You can say a number of years or say “skip”.' },
  { field: 'position_count', reportLabel: 'Number of positions', label: 'number of positions', prompt: 'How many people are you hiring for this demand?' },
  { field: 'work_mode', reportLabel: 'Work mode', label: 'work mode', prompt: 'Is this role remote, hybrid, or onsite?' },
  { field: 'start_date', reportLabel: 'Start date', label: 'start date', prompt: 'What should the start date be? Please enter a date, for example 2026-11-15.' },
  { field: 'end_date', reportLabel: 'End date', label: 'tentative end date', prompt: 'What should the tentative end date be? Please enter a date, for example 2027-05-15.' },
];

function readAnswer(field, text) {
  const value = text.trim();
  if (/^(skip|unknown|not stated|not sure|leave blank)$/i.test(value)) return {};
  if (field === 'experience_years') {
    const range = value.match(/(\d+(?:\.\d+)?)\s*(?:-|to|–)\s*(\d+(?:\.\d+)?)/i);
    if (range) return { experience_years: Number(range[1]), experience_max_years: Number(range[2]) };
    const years = value.match(/\d+(?:\.\d+)?/);
    return years ? { experience_years: Number(years[0]) } : {};
  }
  if (field === 'experience_max_years') {
    const years = value.match(/\d+(?:\.\d+)?/);
    return years ? { experience_max_years: Number(years[0]) } : {};
  }
  if (field === 'position_count') {
    const count = value.match(/\d{1,4}/);
    return count ? { position_count: Number(count[0]) } : {};
  }
  if (field === 'work_mode') {
    const mode = value.match(/remote|hybrid|onsite/i);
    return mode ? { work_mode: mode[0].toLowerCase() } : {};
  }
  if (field === 'location') {
    const locations = value.split(/[,;]+/).map((location) => location.trim()).filter(Boolean);
    return locations.length ? { location: locations.join('; '), locations } : {};
  }
  if (field === 'start_date' || field === 'end_date') {
    const iso = value.match(/\b(\d{4})-(\d{1,2})-(\d{1,2})\b/);
    if (iso) return { [field]: `${iso[1]}-${iso[2].padStart(2, '0')}-${iso[3].padStart(2, '0')}` };
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) return { [field]: `${parsed.getFullYear()}-${String(parsed.getMonth() + 1).padStart(2, '0')}-${String(parsed.getDate()).padStart(2, '0')}` };
    return {};
  }
  return value ? { [field]: value } : {};
}

const isSkipAnswer = (text) => /^(skip|unknown|not stated|not sure|leave blank)$/i.test(String(text || '').trim());
const isTopicChange = (text) => /\b(change the topic|change topic|something else|different topic|forget (this|that)|talk about|tell me about|what is|who is|can you help me with)\b/i.test(text.trim());
const hasDraftValue = (draft, field) => {
  const value = draft?.[field];
  return value !== null && value !== undefined && value !== '' && (!Array.isArray(value) || value.length > 0);
};
const isDateQuestion = (question) => ['start_date', 'end_date'].includes(question?.field);
// Dates must always be confirmed in chat, even when they were extracted from the JD.
const isAnsweredForFlow = (draft, question) => !isDateQuestion(question) && hasDraftValue(draft, question.field);

function readCorrection(text) {
  const fieldPattern = '(client(?:\\s+name)?|job\\s+title|demand\\s+title|title|role|locations?|work\\s+location|max(?:imum)?\\s+experience|min(?:imum)?\\s+experience|experience|number\\s+of\\s+positions|positions?|work\\s+mode|start\\s+date|end\\s+date)';
  const match = text.match(new RegExp(`^\\s*(?:actually[, ]+)?(?:(?:please\\s+)?(?:change|update|set|correct)\\s+(?:the\\s+)?)?(?:the\\s+)?${fieldPattern}\\s*(?::|=|\\bshould\\s+be\\b|\\bis\\b|\\bto\\b|\\bas\\b)\\s*(.+?)\\s*$`, 'i'));
  if (!match) return null;
  const label = match[1].toLowerCase();
  const field = /client/.test(label) ? 'client_name'
    : /title|role/.test(label) ? 'role'
      : /location/.test(label) ? 'location'
        : /max/.test(label) ? 'experience_max_years'
          : /min|experience/.test(label) ? 'experience_years'
            : /positions?/.test(label) ? 'position_count'
              : /work mode/.test(label) ? 'work_mode'
                : /start/.test(label) ? 'start_date' : 'end_date';
  const value = match[2].trim();
  const edits = readAnswer(field, value);
  if (!Object.keys(edits).length) return null;
  if (field === 'role') edits.title = value;
  return edits;
}

export default function TruHireAssistant() {
  const { client_names: clientNames } = useMeta();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([{ role: 'assistant', content: GREETING }]);
  const [conversationId, setConversationId] = useState(null);
  const [input, setInput] = useState('');
  const [pending, setPending] = useState(null);
  const [approvalPending, setApprovalPending] = useState(false);
  const [correctionMode, setCorrectionMode] = useState(false);
  const [jdQuestions, setJdQuestions] = useState([]);
  const [jdQuestionIndex, setJdQuestionIndex] = useState(0);
  const [awaitingCustomClient, setAwaitingCustomClient] = useState(false);
  const [loading, setLoading] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [expandedClients, setExpandedClients] = useState({});
  const endRef = useRef(null);
  const demandCreateInFlight = useRef(false);

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
          const latestJdAction = [...restored].reverse().find((message) => message.role === 'assistant' && ['confirm_jd', 'created'].includes(message.data?.action));
          if (latestJdAction?.data?.action === 'confirm_jd') startJdReview(latestJdAction.data, false);
          else setPending(null);
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

  const askJdQuestion = (question, draftOverride) => {
    const activeDraft = draftOverride || pending?.draft;
    const existingDate = activeDraft?.[question.field];
    const prompt = isDateQuestion(question) && existingDate
      ? `The JD lists ${existingDate} as the ${question.label}. Should I use that date? Reply “use it” or enter a different date.`
      : question.prompt;
    append({
      role: 'assistant', content: prompt,
      data: question.field === 'client_name' ? { action: 'jd_question', field: question.field, options: clientNames } : { action: 'jd_question', field: question.field },
    });
  };

  const startJdReview = (data, announce = true) => {
    setPending(data);
    setAwaitingCustomClient(false);
    const missing = new Set(data.field_report?.missing || []);
    const questions = JD_QUESTION_DEFS.filter((question) => {
      const blank = !hasDraftValue(data.draft, question.field);
      // Dates and the upper experience bound are requirement fields even when
      // older saved JD reports do not include them in their missing list.
      const alwaysCheck = ['start_date', 'end_date', 'experience_max_years'].includes(question.field);
      return isDateQuestion(question) || (blank && (alwaysCheck || missing.has(question.reportLabel)));
    });
    setJdQuestions(questions);
    setJdQuestionIndex(0);
    setCorrectionMode(false);
    const fields = (data.field_report?.present || []).filter((item) => [
      'Job title', 'Client', 'Location', 'Experience', 'Maximum experience', 'Work mode', 'Number of positions', 'Start date', 'End date',
    ].includes(item.name));
    if (fields.length) {
      setApprovalPending(true);
      append({ role: 'assistant', content: 'I found these details in the JD. Should I use them as shown?', data: { action: 'jd_approval', fields } });
    } else {
      setApprovalPending(false);
      if (questions.length) askJdQuestion(questions[0]);
      else if (announce) append({ role: 'assistant', content: 'I’ve got the details I could read. Choose a demand category below when you’re ready to save it.' });
    }
  };

  const markApprovalAnswered = () => setMessages((current) => {
    let target = -1;
    for (let i = current.length - 1; i >= 0; i -= 1) {
      if (current[i].data?.action === 'jd_approval') { target = i; break; }
    }
    return target < 0 ? current : current.map((item, index) => index === target
      ? { ...item, data: { ...item.data, action: 'jd_approval_answered' } }
      : item);
  });

  const acceptExtractedFields = () => {
    setApprovalPending(false);
    markApprovalAnswered();
    append({ role: 'user', content: 'Use the extracted details' });
    append({ role: 'assistant', content: 'Okay, I’ll use those values. I’ll ask you about the fields the JD didn’t include.' });
    const firstUnfilled = jdQuestions.findIndex((question) => !isAnsweredForFlow(pending?.draft, question));
    if (firstUnfilled >= 0) { setJdQuestionIndex(firstUnfilled); askJdQuestion(jdQuestions[firstUnfilled]); }
    else append({ role: 'assistant', content: 'Everything I need is ready. Choose a demand practice to file this requirement.' });
  };

  const requestFieldCorrections = () => {
    setApprovalPending(false);
    setCorrectionMode(false);
    markApprovalAnswered();
    append({ role: 'user', content: 'I want to change a detail' });
    append({ role: 'assistant', content: 'I’ll ask about each missing requirement field one at a time. You can also correct another field naturally as we go.' });
    const firstUnfilled = jdQuestions.findIndex((question) => !isAnsweredForFlow(pending?.draft, question));
    if (firstUnfilled >= 0) {
      setJdQuestionIndex(firstUnfilled);
      askJdQuestion(jdQuestions[firstUnfilled]);
    } else {
      setJdQuestionIndex(jdQuestions.length);
      append({ role: 'assistant', content: 'All requirement fields are ready. Choose a demand practice to create it.' });
    }
  };

  const answerJdQuestion = (answer, userAlreadyAdded = false) => {
    const question = jdQuestions[jdQuestionIndex];
    if (!question || !pending) return;
    if (answer !== null && isTopicChange(String(answer))) {
      if (!userAlreadyAdded) append({ role: 'user', content: String(answer) });
      const currentDate = pending.draft?.[question.field];
      append({ role: 'assistant', content: `To finish this demand, I still need the ${question.label}. ${isDateQuestion(question) && currentDate ? `The JD lists ${currentDate}. Reply “use it” or enter a different date.` : question.prompt}` });
      return;
    }
    if (answer !== null && isDateQuestion(question) && isSkipAnswer(String(answer))) {
      if (!userAlreadyAdded) append({ role: 'user', content: String(answer) });
      append({ role: 'assistant', content: `I need the ${question.label} to create this requirement. Please enter a date.` });
      askJdQuestion(question, pending.draft);
      return;
    }
    const correction = answer === null ? null : readCorrection(String(answer));
    if (correction && correction[question.field] === undefined) {
      const correctedDraft = { ...pending.draft, ...correction };
      setPending((current) => current ? { ...current, draft: correctedDraft } : current);
      setMessages((current) => {
        let target = -1;
        for (let i = current.length - 1; i >= 0; i -= 1) {
          if (current[i].data?.action === 'jd_question') { target = i; break; }
        }
        return target < 0 ? current : current.map((item, index) => index === target
          ? { ...item, data: { ...item.data, action: 'jd_question_answered' } }
          : item);
      });
      append({ role: 'assistant', content: `Got it. I updated ${Object.keys(correction).join(', ')}. I still need the ${question.label}.` });
      askJdQuestion(question, correctedDraft);
      return;
    }
    const keepCurrentDate = isDateQuestion(question) && hasDraftValue(pending.draft, question.field)
      && /^(use it|keep it|yes|correct|skip)$/i.test(String(answer || '').trim());
    const edits = answer === null ? {} : keepCurrentDate ? { [question.field]: pending.draft[question.field] } : correction || readAnswer(question.field, String(answer));
    if (answer !== null && !keepCurrentDate && !Object.keys(edits).length && !isSkipAnswer(answer)) {
      if (!userAlreadyAdded) append({ role: 'user', content: String(answer) });
      append({ role: 'assistant', content: `I didn’t catch the ${question.label}. Please try again, or say “skip” to leave it blank.` });
      return;
    }
    const nextDraft = { ...pending.draft, ...edits };
    if (question.field === 'role' && pending.field_report?.missing?.includes('Job title') && edits.role) nextDraft.title = edits.role;
    setPending((current) => current ? { ...current, draft: nextDraft } : current);
    setMessages((current) => {
      let target = -1;
      for (let i = current.length - 1; i >= 0; i -= 1) {
        if (current[i].data?.action === 'jd_question') { target = i; break; }
      }
      return target < 0 ? current : current.map((item, index) => index === target
        ? { ...item, data: { ...item.data, action: 'jd_question_answered' } }
        : item);
    });
    if (!userAlreadyAdded) append({ role: 'user', content: answer === null ? 'Skip' : String(answer) });
    append({ role: 'assistant', content: Object.keys(edits).length
      ? `Got it. I’ll use that ${question.label}.`
      : `No problem. I’ll leave ${question.label} blank.` });

    let nextIndex = jdQuestionIndex + 1;
    while (nextIndex < jdQuestions.length) {
      const nextQuestion = jdQuestions[nextIndex];
      if (!isAnsweredForFlow(nextDraft, nextQuestion)) break;
      nextIndex += 1;
    }
    setJdQuestionIndex(nextIndex);
    if (nextIndex < jdQuestions.length) askJdQuestion(jdQuestions[nextIndex]);
    else append({ role: 'assistant', content: 'Thanks, I’ve got the details. Choose a demand category below to create the requirement.' });
  };

  const handleResponse = (data) => {
    const content = data.reply || data.message;
    if (content) append({ role: 'assistant', content, data });
    if (data.action === 'confirm_jd') startJdReview(data, false);
    if (data.action === 'created') { setPending(null); setJdQuestions([]); setApprovalPending(false); setCorrectionMode(false); }
  };

  const send = async (event) => {
    event?.preventDefault();
    const text = input.trim();
    if (!text || loading) return;
    append({ role: 'user', content: text });
    setInput('');
    if (pending && approvalPending) {
      if (/^(yes|use|use them|looks good|correct|approve|go ahead)$/i.test(text)) acceptExtractedFields();
      else if (/^(change|edit|correct them|i want to change|change a detail)$/i.test(text)) requestFieldCorrections();
      else append({ role: 'assistant', content: 'Please confirm the extracted JD details: say “use them” or “change a detail”.' });
      return;
    }
    if (pending && correctionMode) {
      if (/^(done|finished|continue|that’s all|thats all)$/i.test(text)) {
        setCorrectionMode(false);
        append({ role: 'assistant', content: 'Thanks. I’ll use the corrected values and ask about any details still missing.' });
        const firstUnfilled = jdQuestions.findIndex((question) => !isAnsweredForFlow(pending?.draft, question));
        if (firstUnfilled >= 0) { setJdQuestionIndex(firstUnfilled); askJdQuestion(jdQuestions[firstUnfilled]); }
        else append({ role: 'assistant', content: 'Everything is ready. Choose a demand practice to file this requirement.' });
      } else if (isTopicChange(text)) {
        append({ role: 'assistant', content: 'To finish this demand, tell me a field and its corrected value, or say “done”.' });
      } else {
        const edits = readCorrection(text);
        if (edits) {
          const nextDraft = { ...pending.draft, ...edits };
          const nextIndex = jdQuestions.findIndex((question) => !isAnsweredForFlow(nextDraft, question));
          setPending((current) => current ? { ...current, draft: nextDraft } : current);
          setCorrectionMode(false);
          append({ role: 'assistant', content: `Got it. I updated ${Object.keys(edits).join(', ')}. I’ll continue with the remaining requirement details.` });
          if (nextIndex >= 0) {
            setJdQuestionIndex(nextIndex);
            askJdQuestion(jdQuestions[nextIndex], nextDraft);
          } else {
            setJdQuestionIndex(jdQuestions.length);
            append({ role: 'assistant', content: 'All requirement details are ready. Choose a demand practice to create it.' });
          }
        } else append({ role: 'assistant', content: 'Tell me what to change, for example: “change the job title to .NET Full Stack”, or say “done”.' });
      }
      return;
    }
    if (pending && jdQuestionIndex < jdQuestions.length) {
      if (awaitingCustomClient) setAwaitingCustomClient(false);
      answerJdQuestion(text, true);
      return;
    }
    if (pending) {
      append({ role: 'assistant', content: 'To finish creating this demand, please choose one of the demand practices shown above.' });
      return;
    }
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
      append({ role: 'assistant', content: error?.response?.data?.detail || error?.message || 'I could not complete that request.' });
    } finally {
      setStreaming(false);
      setLoading(false);
    }
  };

  const upload = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if (!file || loading) return;
    const form = new FormData();
    form.append('file', file);
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
    if (!pending?.draft || loading || demandCreateInFlight.current) return;
    const nextDateIndex = jdQuestions.findIndex((question, index) => index >= jdQuestionIndex && isDateQuestion(question));
    if (nextDateIndex >= 0) {
      setJdQuestionIndex(nextDateIndex);
      append({ role: 'assistant', content: `I need to confirm the ${jdQuestions[nextDateIndex].label} before I create this demand.` });
      askJdQuestion(jdQuestions[nextDateIndex]);
      return;
    }
    demandCreateInFlight.current = true;
    setLoading(true);
    try {
      const draft = { ...pending.draft };
      for (const field of ['position_count', 'experience_years', 'experience_max_years']) {
        if (draft[field] === '' || draft[field] === undefined) draft[field] = null;
        else if (draft[field] !== null) draft[field] = Number(draft[field]);
      }
      const { data } = await assistantApi.confirmJd({ ...draft, demand_id: demandId, conversation_id: conversationId });
      handleResponse(data);
    } catch (error) {
      append({ role: 'assistant', content: error?.response?.data?.detail || 'The requirement could not be created.' });
    } finally {
      demandCreateInFlight.current = false;
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
      setPending(null);
      setApprovalPending(false);
      setCorrectionMode(false);
      setJdQuestions([]);
      setJdQuestionIndex(0);
      setAwaitingCustomClient(false);
      setExpandedClients({});
    } catch (error) {
      append({ role: 'assistant', content: error?.response?.data?.detail || 'I could not clear the chat history. Please try again.' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      {open && (
        <section className="truhire-assistant-panel" aria-label="TruHire AI Assistant">
          <header className="truhire-assistant-header">
            <div className="truhire-assistant-title"><span className="truhire-assistant-avatar"><Sparkles size={16} /></span><span><strong>TruHire Assistant</strong><small>JD help, candidate search, email drafts</small></span></div>
            <span className="cluster cluster-tight">
              <button type="button" className="icon-btn" onClick={clearChat} disabled={loading} aria-label="Clear chat" title="Clear chat"><Trash2 size={16} /></button>
              <button type="button" className="icon-btn" onClick={() => setOpen(false)} aria-label="Close assistant"><X size={18} /></button>
            </span>
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
                  {message.data?.action === 'created' && message.data.position?.id && <button type="button" className="btn btn-secondary assistant-action" onClick={() => { window.location.href = `/requirements?id=${message.data.position.id}`; }}>Open this requirement</button>}
                  {message.data?.action === 'jd_question' && message.data.field === 'client_name' && (
                    <div className="truhire-assistant-question-controls">
                      <select aria-label="Choose client" defaultValue="" onChange={(event) => {
                        const client = event.target.value;
                        if (!client) return;
                        setMessages((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, data: { ...item.data, action: 'jd_question_answered' } } : item));
                        if (client === OTHER_CLIENT) {
                          setAwaitingCustomClient(true);
                          append({ role: 'assistant', content: 'What client name should I use? Type it in the chat.' });
                        } else answerJdQuestion(client);
                      }}>
                        <option value="" disabled>Select a client</option>
                        {message.data.options.map((client) => <option key={client} value={client}>{client}</option>)}
                        <option value={OTHER_CLIENT}>Others</option>
                      </select>
                      <button type="button" className="btn btn-secondary assistant-action" onClick={() => answerJdQuestion(null)}>Skip</button>
                    </div>
                  )}
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
                  {message.data?.action === 'jd_approval' && (
                    <div className="truhire-assistant-results truhire-assistant-approval">
                      {message.data.fields.map((field) => <div key={field.name}><b>{field.name}:</b> {field.value}</div>)}
                      <span>Should I use these values?</span>
                      <div className="truhire-assistant-approval-actions">
                        <button type="button" className="btn btn-primary" onClick={acceptExtractedFields}>Use these details</button>
                        <button type="button" className="btn btn-secondary" onClick={requestFieldCorrections}>Change a detail</button>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            ))}
            {pending?.demands && !approvalPending && !correctionMode && jdQuestionIndex >= jdQuestions.length && (
              <div className="truhire-assistant-demand-picker">
                <strong>Which demand should I file “{pending.draft.title}” under?</strong>
                <div>{pending.demands.map((demand) => <button key={demand.id} type="button" onClick={() => chooseDemand(demand.id)} disabled={loading}><Check size={13} />{demand.name}</button>)}</div>
              </div>
            )}
            {loading && !streaming && <div className="truhire-assistant-thinking"><Sparkles size={14} /> Working…</div>}
            <div ref={endRef} />
          </div>
          <form className="truhire-assistant-composer" onSubmit={send}>
            <label className="truhire-assistant-upload" title="Upload demand or resume"><Paperclip size={17} /><input type="file" onChange={upload} accept=".pdf,.doc,.docx,.rtf,.md,.txt,.csv,.jpg,.jpeg,.png,.webp" /></label>
            <input value={input} onChange={(event) => setInput(event.target.value)} placeholder={approvalPending ? 'Say “use them” or “change a detail”' : correctionMode ? 'Field: corrected value, or say done' : pending && jdQuestionIndex < jdQuestions.length ? (awaitingCustomClient ? 'Type the client name' : jdQuestions[jdQuestionIndex].field === 'client_name' ? 'Or type a client name' : `Your ${jdQuestions[jdQuestionIndex].label} (or say skip)`) : pending ? 'Choose a demand practice above' : 'Ask about TruHire…'} aria-label="Message TruHire Assistant" />
            <button type="submit" className="btn btn-primary" disabled={!input.trim() || loading} aria-label="Send message"><Send size={15} /></button>
          </form>
        </section>
      )}
      <button type="button" className="truhire-assistant-bubble-button" onClick={() => setOpen((value) => !value)} aria-label="Open TruHire AI Assistant" title="TruHire AI Assistant"><Bot size={23} /></button>
    </>
  );
}
