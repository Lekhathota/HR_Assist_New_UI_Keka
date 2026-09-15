import React, { useEffect, useMemo, useRef, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { apiPost } from '../api.js';
import { toast, useConfirm } from './EnterpriseFeedback.jsx';

function routeContext(pathname) {
  const jd = pathname.match(/^\/jobs\/(\d+)/);
  if (jd) return { jd_id: Number(jd[1]) };
  const candidate = pathname.match(/^\/talent\/(\d+)/);
  if (candidate) return { candidate_id: Number(candidate[1]) };
  return {};
}

function normalizeBotPayload(data) {
  return {
    role: 'assistant',
    answer: data.answer || data.message || 'I could not produce a response.',
    actions: Array.isArray(data.actions) ? data.actions : [],
    suggested_questions: Array.isArray(data.suggested_questions) ? data.suggested_questions : [],
    at: Date.now(),
  };
}

function FloatingRecruiterChat() {
  const location = useLocation();
  const navigate = useNavigate();
  const confirm = useConfirm();
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [minimized, setMinimized] = useState(false);
  const [position, setPosition] = useState(null);
  const scrollRef = useRef(null);
  const dragRef = useRef(null);
  const context = useMemo(() => routeContext(location.pathname), [location.pathname]);

  useEffect(() => {
    if (open && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [open, messages, loading]);

  useEffect(() => {
    if (!open) {
      setMessages([]);
      setInput('');
      setMinimized(false);
    }
  }, [open]);

  useEffect(() => {
    const onPointerMove = (event) => {
      if (!dragRef.current) return;
      const nextLeft = event.clientX - dragRef.current.offsetX;
      const nextTop = event.clientY - dragRef.current.offsetY;
      const maxLeft = window.innerWidth - 320;
      const maxTop = window.innerHeight - 120;
      setPosition({
        left: Math.max(12, Math.min(maxLeft, nextLeft)),
        top: Math.max(12, Math.min(maxTop, nextTop)),
      });
    };
    const onPointerUp = () => {
      dragRef.current = null;
    };
    window.addEventListener('pointermove', onPointerMove);
    window.addEventListener('pointerup', onPointerUp);
    return () => {
      window.removeEventListener('pointermove', onPointerMove);
      window.removeEventListener('pointerup', onPointerUp);
    };
  }, []);

  const appendAssistant = (data) => {
    setMessages(prev => [...prev, normalizeBotPayload(data)]);
  };

  const sendMessage = async (text = input) => {
    const message = String(text || '').trim();
    if (!message || loading) return;
    setInput('');
    setOpen(true);
    setMessages(prev => [...prev, { role: 'user', answer: message, at: Date.now() }]);
    setLoading(true);
    try {
      const { ok, data } = await apiPost('/api/agentic/run', {
        task_type: 'chat',
        message,
        ...context,
      });
      if (!ok) {
        throw new Error(data.error || 'Chat request failed.');
      }
      appendAssistant(data);
    } catch (err) {
      const messageText = err.message || 'Chat request failed.';
      toast({ type: 'error', message: messageText });
      appendAssistant({ answer: messageText, actions: [], suggested_questions: [] });
    } finally {
      setLoading(false);
    }
  };

  const runBackendAction = async (action, confirmed = false) => {
    setLoading(true);
    try {
      const { ok, data } = await apiPost('/api/agentic/run', {
        task_type: 'chat_action',
        action: action.type,
        params: action.params || {},
        confirmed,
        ...context,
      });
      if (!ok) {
        throw new Error(data.error || 'Action failed.');
      }
      appendAssistant(data);
      toast({ type: data.action === 'schedule_interview' ? 'success' : 'info', message: data.answer || 'Action completed.' });
    } catch (err) {
      const messageText = err.message || 'Action failed.';
      toast({ type: 'error', message: messageText });
      appendAssistant({ answer: messageText, actions: [], suggested_questions: [] });
    } finally {
      setLoading(false);
    }
  };

  const handleAction = async (action) => {
    const params = action.params || {};
    if (action.type === 'open_jd' && params.jd_id) {
      navigate(`/jobs/${params.jd_id}`);
      return;
    }
    if (action.type === 'open_candidate' && params.candidate_id) {
      navigate(`/talent/${params.candidate_id}`);
      return;
    }
    if (action.requires_confirmation) {
      const approved = await confirm({
        title: action.type === 'schedule_interview' ? 'Confirm scheduling' : 'Confirm assistant action',
        message: action.type === 'schedule_interview'
          ? 'Send this interview email and create the interview record?'
          : 'Run this assistant action now?',
        confirmLabel: action.type === 'schedule_interview' ? 'Send & Schedule' : 'Confirm',
        icon: action.type === 'schedule_interview' ? 'fas fa-paper-plane' : 'fas fa-robot',
        danger: false,
      });
      if (!approved) return;
      await runBackendAction(action, true);
      return;
    }
    await runBackendAction(action, false);
  };

  const starterQuestions = context.jd_id
    ? ['Who are the top candidates?', 'Explain the ranking', 'What are the main gaps?']
    : context.candidate_id
      ? ['Explain this candidate', 'Show applied roles', 'Can this candidate be scheduled?']
      : ['What can I ask here?', 'Show recent recruiting insights', 'How should I use screening results?'];

  return (
    <div
      className={`floating-chat${open ? ' floating-chat-open' : ''}${position ? ' floating-chat-moved' : ''}`}
      style={position ? { left: position.left, top: position.top, right: 'auto', bottom: 'auto' } : undefined}
    >
      {open && (
        <section className={`floating-chat-panel${minimized ? ' floating-chat-panel-minimized' : ''}`} aria-label="Recruiter assistant">
          <header
            className="floating-chat-header"
            onPointerDown={(event) => {
              if (event.target.closest('button')) return;
              const rect = event.currentTarget.closest('.floating-chat').getBoundingClientRect();
              dragRef.current = { offsetX: event.clientX - rect.left, offsetY: event.clientY - rect.top };
            }}
          >
            <div>
              <strong><i className="fas fa-robot"></i> Recruiter Assistant</strong>
              <span>{context.jd_id ? `JD #${context.jd_id}` : context.candidate_id ? `Candidate #${context.candidate_id}` : 'Ready'}</span>
            </div>
            <div className="floating-chat-window-actions">
              <button type="button" aria-label={minimized ? 'Expand recruiter assistant' : 'Minimize recruiter assistant'} onClick={() => setMinimized(prev => !prev)}>
                <i className={`fas ${minimized ? 'fa-up-right-and-down-left-from-center' : 'fa-minus'}`}></i>
              </button>
              <button type="button" aria-label="Close recruiter assistant" onClick={() => setOpen(false)}>
                <i className="fas fa-times"></i>
              </button>
            </div>
          </header>

          {!minimized && <div className="floating-chat-messages" ref={scrollRef}>
            {messages.length === 0 && (
              <div className="floating-chat-empty">
                <i className="fas fa-comments"></i>
                <strong>Ask about candidates, JDs, rankings, or interviews.</strong>
              </div>
            )}
            {messages.map((msg, index) => (
              <div key={`${msg.at}-${index}`} className={`floating-chat-message floating-chat-message-${msg.role}`}>
                <div className="floating-chat-bubble">{msg.answer}</div>
                {msg.actions?.length > 0 && (
                  <div className="floating-chat-actions">
                    {msg.actions.map((action, i) => (
                      <button key={`${action.type}-${i}`} type="button" onClick={() => handleAction(action)} disabled={loading}>
                        {action.label || action.type}
                      </button>
                    ))}
                  </div>
                )}
                {msg.suggested_questions?.length > 0 && (
                  <div className="floating-chat-suggestions">
                    {msg.suggested_questions.map(q => (
                      <button key={q} type="button" onClick={() => sendMessage(q)} disabled={loading}>{q}</button>
                    ))}
                  </div>
                )}
              </div>
            ))}
            {loading && (
              <div className="floating-chat-message floating-chat-message-assistant">
                <div className="floating-chat-bubble floating-chat-thinking">
                  <span></span><span></span><span></span>
                </div>
              </div>
            )}
          </div>}

          {!minimized && <div className="floating-chat-starters">
            {starterQuestions.map(q => (
              <button key={q} type="button" onClick={() => sendMessage(q)} disabled={loading}>{q}</button>
            ))}
          </div>}

          {!minimized && <form className="floating-chat-input" onSubmit={(e) => { e.preventDefault(); sendMessage(); }}>
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask the recruiter assistant..."
              disabled={loading}
            />
            <button type="submit" aria-label="Send message" disabled={loading || !input.trim()}>
              <i className="fas fa-paper-plane"></i>
            </button>
          </form>}
        </section>
      )}

      <button type="button" className="floating-chat-toggle" aria-label="Open recruiter assistant" onClick={() => setOpen(prev => !prev)}>
        <span className="floating-chat-logo-frame" aria-hidden="true">
          <img src="/ShimentoX-Logo.png" alt="" className="floating-chat-toggle-mark" />
        </span>
      </button>
    </div>
  );
}

export default FloatingRecruiterChat;
