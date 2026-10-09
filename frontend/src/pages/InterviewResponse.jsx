import React, { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { publicApiGet, publicApiPost } from '../api.js';
import '../styles/assessment_candidate.css';
import '../styles/interview_response.css';

function formatStart(value) {
  if (!value) return '';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString([], { weekday: 'short', day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function statusMessage(view) {
  const status = view?.case?.status;
  if (status === 'RESCHEDULED' || status === 'RECOVERED') return { tone: 'good', text: `You're booked for ${view.case.confirmed_slot?.label}. A confirmation email is on its way.` };
  if (status === 'SLOT_PROPOSED') return { tone: 'info', text: 'Choose the time that suits you best.' };
  if (status === 'AWAITING_RESPONSE') return { tone: 'info', text: 'We missed you at your interview. Would you like to choose a new time?' };
  if (status === 'PENDING' || status === 'PROCESSING' || status === 'RETRY_SCHEDULED') return { tone: 'info', text: "We're looking for new interview times and will email you as soon as options are available." };
  if (status === 'ESCALATED') return { tone: 'info', text: 'Our recruitment team will contact you shortly to agree a new time.' };
  if (status === 'CLOSED' && view.case.recovery_type) return { tone: 'muted', text: 'This request is closed. Contact the recruitment team if you need anything else.' };
  return null;
}

function InterviewResponse() {
  const { token } = useParams();
  const [view, setView] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [showRequest, setShowRequest] = useState(false);
  const [reason, setReason] = useState('');
  const [windows, setWindows] = useState([]);
  const [notice, setNotice] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      setView(await publicApiGet(`/api/interview-recovery/public/${encodeURIComponent(token)}`));
    } catch (err) {
      setError(err.message || 'This interview link is invalid or has expired.');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => { load(); }, [load]);

  const post = async (path, body, success) => {
    setBusy(true);
    setError('');
    setNotice('');
    try {
      const data = await publicApiPost(`/api/interview-recovery/public/${encodeURIComponent(token)}/${path}`, body);
      setView(data);
      if (success) setNotice(success(data));
      setShowRequest(false);
    } catch (err) {
      if (err.status === 409 && err.data?.slot_unavailable) {
        setView(err.data);
        setNotice('That time was just taken. Here are updated options.');
      } else {
        setError(err.message || 'Something went wrong. Please try again.');
        await load();
      }
    } finally {
      setBusy(false);
    }
  };

  const submitRequest = () => post('reschedule', {
    reason: reason.trim(),
    preferred_windows: windows.filter(w => w.date && w.start && w.end),
  }, () => 'Thanks, your request was received.');

  const updateWindow = (index, key, value) => setWindows(prev => prev.map((w, i) => (i === index ? { ...w, [key]: value } : w)));

  if (loading) {
    return <div className="ca-page"><div className="ca-card ca-center"><div className="ca-spinner" aria-hidden="true" /><p>Loading your interview…</p></div></div>;
  }
  if (!view) {
    return (
      <div className="ca-page">
        <div className="ca-card ca-center ca-error-card">
          <i className="fas fa-exclamation-circle" />
          <h1>Link unavailable</h1>
          <p>{error}</p>
        </div>
      </div>
    );
  }

  const message = statusMessage(view);
  const slots = view.case?.proposed_slots || [];
  const { actions } = view;

  return (
    <div className="ca-page" id="ca-root">
      <main className="ir-card">
        <img src="/ShimentoX-Logo-Dark.png" alt="ShimentoX" className="ir-logo" />
        <h1>{view.candidate_first_name ? `Hi ${view.candidate_first_name},` : 'Your interview'}</h1>
        <p className="ir-meta">
          <strong>{view.job_role || 'Interview'}</strong>
          {view.interview_start && <> · {formatStart(view.interview_start)}</>}
          {view.interview_mode && <> · {view.interview_mode}</>}
        </p>
        {view.timezone && <p className="ir-tz">Times are shown in {view.timezone}.</p>}

        {message && <div className={`ir-banner ir-banner-${message.tone}`} role="status">{message.text}</div>}
        {notice && <div className="ir-banner ir-banner-good" role="status">{notice}</div>}
        {error && <div className="ca-inline-error" role="alert">{error}</div>}

        {actions.can_respond_no_show && (
          <div className="ir-actions">
            <button type="button" className="ca-btn ca-btn-primary" disabled={busy}
              onClick={() => post('respond', { wants_reschedule: true }, () => 'Great, here are the next available times.')}>
              Yes, find me a new time
            </button>
            <button type="button" className="ca-btn ca-btn-secondary" disabled={busy}
              onClick={() => post('respond', { wants_reschedule: false }, () => 'Thanks for letting us know.')}>
              I'm no longer interested
            </button>
          </div>
        )}

        {actions.can_choose_slot && slots.length > 0 && (
          <fieldset className="ir-slots">
            <legend>Available times</legend>
            {slots.map(slot => (
              <button key={slot.id} type="button" className="ir-slot" disabled={busy}
                onClick={() => post('confirm', { slot_id: slot.id }, data => (data.booked ? 'Your new interview time is confirmed.' : 'That time was just taken. Here are updated options.'))}>
                <i className="far fa-calendar-check" aria-hidden="true" /> {slot.label}
              </button>
            ))}
          </fieldset>
        )}

        {actions.can_request_reschedule && !showRequest && (
          <button type="button" className="ca-btn ca-btn-secondary ir-wide" onClick={() => setShowRequest(true)} disabled={busy}>
            {actions.can_choose_slot ? 'None of these times work for me' : 'I need to reschedule'}
          </button>
        )}

        {showRequest && (
          <section className="ir-request" aria-label="Reschedule request">
            <label htmlFor="ir-reason">Reason (optional)</label>
            <textarea id="ir-reason" rows={3} value={reason} onChange={e => setReason(e.target.value)} maxLength={1000} />
            <p className="ir-help">Optionally tell us when you're free and we'll only offer times inside those windows.</p>
            {windows.map((w, index) => (
              <div className="ir-window" key={index}>
                <input type="date" aria-label="Date" value={w.date} onChange={e => updateWindow(index, 'date', e.target.value)} />
                <input type="time" aria-label="From" value={w.start} onChange={e => updateWindow(index, 'start', e.target.value)} />
                <input type="time" aria-label="To" value={w.end} onChange={e => updateWindow(index, 'end', e.target.value)} />
                <button type="button" className="ca-icon-button" aria-label="Remove window" onClick={() => setWindows(prev => prev.filter((_, i) => i !== index))}>
                  <i className="fas fa-times" aria-hidden="true" />
                </button>
              </div>
            ))}
            {windows.length < 7 && (
              <button type="button" className="ir-link" onClick={() => setWindows(prev => [...prev, { date: '', start: '09:00', end: '18:00' }])}>
                + Add a time I'm available
              </button>
            )}
            <div className="ir-actions">
              <button type="button" className="ca-btn ca-btn-primary" onClick={submitRequest} disabled={busy}>
                {busy ? 'Sending…' : 'Find new times'}
              </button>
              <button type="button" className="ca-btn ca-btn-secondary" onClick={() => setShowRequest(false)} disabled={busy}>Back</button>
            </div>
          </section>
        )}

        {actions.can_decline && !actions.can_respond_no_show && (
          <button type="button" className="ir-link ir-decline" disabled={busy}
            onClick={() => window.confirm('Withdraw from this interview?') && post('respond', { wants_reschedule: false }, () => 'Thanks for letting us know.')}>
            I'm no longer interested in this role
          </button>
        )}
      </main>
    </div>
  );
}

export default InterviewResponse;
