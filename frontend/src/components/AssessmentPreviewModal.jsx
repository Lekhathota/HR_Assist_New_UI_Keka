import React, { useEffect, useMemo, useRef, useState } from 'react';
import { apiGet, apiPost, apiPut } from '../api.js';
import ReferenceSolutionPanel from './ReferenceSolutionPanel.jsx';
import { isValidEmail, mcqProblem } from '../utils/assessmentValidation.js';
import '../styles/assessment_preview.css';

const LETTERS = ['A', 'B', 'C', 'D'];
const LANGUAGE_LABELS = { python: 'Python', javascript: 'JavaScript', java: 'Java', c: 'C', cpp: 'C++' };
const VERIFY_LABELS = {
  verified: { label: 'Reference verified', tone: 'ok' },
  failed: { label: 'Reference fails tests', tone: 'bad' },
  unavailable: { label: 'Execution unavailable', tone: 'warn' },
  not_verified: { label: 'Not validated', tone: 'muted' },
};
const STATUS_BADGES = {
  DRAFT: 'Draft — Not Sent', SENT: 'Sent — awaiting candidate', IN_PROGRESS: 'In progress',
  COMPLETED: 'Submitted', PASSED: 'Passed', FAILED: 'Failed', TERMINATED: 'Terminated',
};
const isCodingType = type => type === 'coding' || type === 'sql';
const marksLabel = points => `${points} mark${Number(points) === 1 ? '' : 's'}`;
const newRequestId = () => `preview-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;

function verifyState(question) {
  if (question.verification?.status) return question.verification.status;
  return question.tests_verified ? 'verified' : 'not_verified';
}

function DifficultyChip({ value }) {
  if (!value) return null;
  return <span className={`pv-chip pv-diff-${String(value).toLowerCase()}`}>{value}</span>;
}

function McqCard({ question, number, total, editable, form, busy, error, onEdit, onChange, onSave, onCancel, onRegenerate }) {
  const options = (form ? form.options : question.options) || [];
  if (form) {
    const setOption = (index, value) => {
      const next = [0, 1, 2, 3].map(i => form.options[i] ?? '');
      const wasCorrect = next[index] === form.correct_answer && String(next[index]).trim();
      next[index] = value;
      onChange({ ...form, options: next, correct_answer: wasCorrect ? value : form.correct_answer });
    };
    return (
      <article className="pv-card pv-editing" id={`pv-q-${question.id}`} aria-label={`Question ${number} (editing)`}>
        <div className="pv-card-head"><span className="pv-qnum">Question {number} of {total}</span><span className="pv-chip pv-chip-edit">Editing</span></div>
        <label className="pv-label" htmlFor={`pv-text-${question.id}`}>Question</label>
        <textarea id={`pv-text-${question.id}`} rows={3} value={form.question_text} onChange={e => onChange({ ...form, question_text: e.target.value })} />
        <span className="pv-label">Options — select the correct answer</span>
        <div className="pv-options">
          {[0, 1, 2, 3].map(i => {
            const value = form.options[i] ?? '';
            const correct = String(value).trim() && value === form.correct_answer;
            return (
              <div key={i} className={`pv-option pv-option-edit${correct ? ' pv-correct' : ''}`}>
                <input type="radio" name={`pv-correct-${question.id}`} checked={Boolean(correct)} disabled={!String(value).trim()}
                  aria-label={`Option ${LETTERS[i]} is correct`} onChange={() => onChange({ ...form, correct_answer: value })} />
                <span className="pv-letter">{LETTERS[i]}</span>
                <input type="text" value={value} aria-label={`Option ${LETTERS[i]}`} onChange={e => setOption(i, e.target.value)} />
              </div>
            );
          })}
        </div>
        <label className="pv-label" htmlFor={`pv-expl-${question.id}`}>Explanation</label>
        <textarea id={`pv-expl-${question.id}`} rows={2} value={form.explanation} onChange={e => onChange({ ...form, explanation: e.target.value })} />
        <div className="pv-row">
          <label className="pv-inline">Difficulty
            <select value={form.difficulty || 'Medium'} onChange={e => onChange({ ...form, difficulty: e.target.value })}>
              {['Easy', 'Medium', 'Hard'].map(d => <option key={d} value={d}>{d}</option>)}
            </select>
          </label>
          <label className="pv-inline">Marks
            <input type="number" min={1} max={100} value={form.points} onChange={e => onChange({ ...form, points: Number(e.target.value) })} />
          </label>
        </div>
        {error && <div className="pv-error" role="alert">{error}</div>}
        <div className="pv-card-actions">
          <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={busy}>Cancel Editing</button>
          <button type="button" className="btn btn-primary" onClick={onSave} disabled={busy}>{busy === 'save' ? 'Saving…' : 'Save Changes'}</button>
        </div>
      </article>
    );
  }
  return (
    <article className="pv-card" id={`pv-q-${question.id}`} aria-label={`Question ${number}`}>
      <div className="pv-card-head">
        <span className="pv-qnum">Question {number} of {total}</span>
        <DifficultyChip value={question.difficulty} />
        <span className="pv-marks">{marksLabel(question.points)}</span>
      </div>
      <p className="pv-text">{question.question_text}</p>
      <div className="pv-options">
        {options.map((option, i) => {
          const correct = option === question.correct_answer;
          return (
            <div key={i} className={`pv-option${correct ? ' pv-correct' : ''}`}>
              <span className="pv-letter">{LETTERS[i] || i + 1}</span>
              <span>{option}</span>
              {correct && <span className="pv-sr">(correct answer)</span>}
            </div>
          );
        })}
      </div>
      {question.explanation && (<div className="pv-explanation"><strong>Explanation</strong><p>{question.explanation}</p></div>)}
      {error && <div className="pv-error" role="alert">{error}</div>}
      {editable && (
        <div className="pv-card-actions">
          <button type="button" className="btn btn-secondary btn-sm" onClick={onRegenerate} disabled={Boolean(busy)}>
            {busy === 'regenerate' ? <><i className="fas fa-spinner fa-spin" /> Regenerating…</> : <><i className="fas fa-rotate" /> Regenerate</>}
          </button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onEdit} disabled={Boolean(busy)}><i className="fas fa-pen" /> Edit</button>
        </div>
      )}
    </article>
  );
}

function CodingCard({ question, number, total, editable, editing, busy, error, onEdit, onRegenerate, onValidate, onPanelChange, onDirtyChange }) {
  const isSql = question.question_type === 'sql';
  const cases = (question.test_cases || []).filter(c => c.enabled !== false);
  const samples = cases.filter(c => !c.hidden);
  const hidden = cases.filter(c => c.hidden);
  const scoring = { min_tests_passed: 0, min_score_percent: 50, require_mandatory: true, ...(question.scoring || {}) };
  const status = VERIFY_LABELS[verifyState(question)] || VERIFY_LABELS.not_verified;
  const languages = isSql ? 'SQL (SQLite)' : (question.allowed_languages || Object.keys(LANGUAGE_LABELS)).map(l => LANGUAGE_LABELS[l] || l).join(', ');
  return (
    <article className="pv-card" id={`pv-q-${question.id}`} aria-label={`Coding question ${number}`}>
      <div className="pv-card-head">
        <span className="pv-qnum">Question {number} of {total}</span>
        <span className="pv-chip pv-chip-type">{isSql ? 'SQL' : 'Coding'}</span>
        <DifficultyChip value={question.difficulty} />
        <span className={`pv-chip pv-verify-${status.tone}`}>{status.label}</span>
        <span className="pv-marks">{marksLabel(question.points)}</span>
      </div>
      {question.title && <h4 className="pv-title">{question.title}</h4>}
      <p className="pv-text">{question.question_text}</p>
      <dl className="pv-facts">
        <div><dt>Language</dt><dd>{languages}</dd></div>
        {!isSql && <div><dt>Limits</dt><dd>{question.time_limit_seconds || 2}s CPU · {question.memory_limit_mb || 128} MB per test</dd></div>}
        {question.input_format && <div><dt>Input</dt><dd>{question.input_format}</dd></div>}
        {question.output_format && <div><dt>Output</dt><dd>{question.output_format}</dd></div>}
        {question.constraints && <div><dt>Constraints</dt><dd>{question.constraints}</dd></div>}
        {question.sql_schema && <div><dt>Schema</dt><dd><pre>{question.sql_schema}</pre></dd></div>}
      </dl>
      {samples.length > 0 && (
        <div className="pv-samples">
          {samples.map((sample, i) => (
            <div key={sample.id || i} className="pv-sample">
              <strong>Sample {i + 1}</strong>
              {isSql ? <pre>{sample.setup_sql}</pre> : (
                <div className="pv-io"><div><span>Input</span><pre>{sample.input}</pre></div><div><span>Expected output</span><pre>{sample.expected_output}</pre></div></div>
              )}
            </div>
          ))}
        </div>
      )}
      <p className="pv-muted">
        Tests: {samples.length} public sample{samples.length === 1 ? '' : 's'}, {hidden.length} hidden (inputs and outputs are never shown to the candidate)
        {cases.some(c => Number(c.weight ?? 1) !== 1) && ' · weighted'}
        {cases.some(c => c.mandatory) && ` · ${cases.filter(c => c.mandatory).length} mandatory`}.
        {' '}Qualifies with at least {scoring.min_tests_passed} test(s) and {scoring.min_score_percent}% of the marks
        {scoring.partial_credit === false ? ' (all-or-nothing marks)' : ' (partial credit)'}.
      </p>
      {question.correct_answer && (
        <details className="pv-reference"><summary>Reference solution{question.reference_language ? ` (${LANGUAGE_LABELS[question.reference_language] || question.reference_language})` : ''}</summary><pre>{question.correct_answer}</pre></details>
      )}
      {question.verification?.message && <p className={`pv-muted pv-verify-text-${status.tone}`}>{question.verification.message}</p>}
      {error && <div className="pv-error" role="alert">{error}</div>}
      {editable && (
        <div className="pv-card-actions">
          <button type="button" className="btn btn-secondary btn-sm" onClick={onValidate} disabled={Boolean(busy)}>
            {busy === 'verify' ? <><i className="fas fa-spinner fa-spin" /> Validating…</> : <><i className="fas fa-vial" /> Validate Code</>}
          </button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onRegenerate} disabled={Boolean(busy)}>
            {busy === 'regenerate' ? <><i className="fas fa-spinner fa-spin" /> Regenerating…</> : <><i className="fas fa-rotate" /> Regenerate</>}
          </button>
          <button type="button" className="btn btn-secondary btn-sm" onClick={onEdit} disabled={Boolean(busy)}>
            <i className="fas fa-pen" /> {editing ? 'Close editor' : 'Edit Question'}
          </button>
        </div>
      )}
      {editing && (
        <ReferenceSolutionPanel key={`${question.id}-${question.updated_at || ''}`} question={question} defaultOpen
          onChange={onPanelChange} onDirtyChange={onDirtyChange} />
      )}
    </article>
  );
}

/**
 * Preview & Send: review every saved question as the recruiter will publish it, edit, regenerate and
 * validate, then send the exact validated version after an explicit confirmation.
 */
function AssessmentPreviewModal({ assessment, questions, onQuestionsChange, onSaveDraft, onClose, onSent, autoValidate = false }) {
  const editable = assessment?.status === 'DRAFT';
  const sorted = useMemo(() => [...questions].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.id - b.id), [questions]);
  const mcqs = sorted.filter(q => !isCodingType(q.question_type));
  const coding = sorted.filter(q => isCodingType(q.question_type));
  const sqlCount = coding.filter(q => q.question_type === 'sql').length;
  const totalMarks = sorted.reduce((sum, q) => sum + Number(q.points || 0), 0);
  const [tab, setTab] = useState(mcqs.length ? 'mcq' : 'coding');
  const [forms, setForms] = useState({});        // MCQ id -> edit form
  const [openPanels, setOpenPanels] = useState(() => new Set()); // coding ids with the configuration editor open
  const [dirtyPanels, setDirtyPanels] = useState(() => new Set());
  const [busy, setBusy] = useState({});
  const [errors, setErrors] = useState({});
  const [check, setCheck] = useState(null);
  const [checking, setChecking] = useState(false);
  const [notice, setNotice] = useState('');
  const [confirming, setConfirming] = useState(false);
  const [email, setEmail] = useState(assessment?.candidate_email || '');
  const [sending, setSending] = useState(false);
  const [sendError, setSendError] = useState('');
  const [sent, setSent] = useState(null);
  const requestId = useRef(newRequestId());

  const original = id => sorted.find(q => q.id === id);
  const formDirty = id => {
    const form = forms[id];
    const q = original(id);
    if (!form || !q) return false;
    return ['question_text', 'correct_answer', 'explanation', 'difficulty', 'points'].some(k => String(form[k] ?? '') !== String(q[k] ?? ''))
      || JSON.stringify(form.options) !== JSON.stringify([0, 1, 2, 3].map(i => q.options?.[i] ?? ''));
  };
  const unsaved = Object.keys(forms).some(id => formDirty(Number(id))) || dirtyPanels.size > 0;
  const setQBusy = (id, value) => setBusy(prev => ({ ...prev, [id]: value }));
  const setQError = (id, value) => setErrors(prev => ({ ...prev, [id]: value }));
  const invalidate = () => setCheck(null); // any change needs a new validation before sending
  const replaceQuestion = (updated) => { onQuestionsChange(prev => prev.map(q => (q.id === updated.id ? { ...q, ...updated } : q))); invalidate(); };

  useEffect(() => {
    const onKey = event => { if (event.key === 'Escape' && !confirming && !sending) requestClose(); };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  });
  useEffect(() => { if (autoValidate && editable) validate(); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const requestClose = () => {
    if (unsaved && !window.confirm('You have unsaved changes in the preview. Close and discard them?')) return;
    onClose();
  };

  const startEdit = q => setForms(prev => ({ ...prev, [q.id]: {
    question_text: q.question_text || '', options: [0, 1, 2, 3].map(i => q.options?.[i] ?? ''), correct_answer: q.correct_answer || '',
    explanation: q.explanation || '', difficulty: q.difficulty || 'Medium', points: q.points ?? 1, question_type: 'mcq',
  } }));
  const cancelEdit = id => { setForms(prev => { const next = { ...prev }; delete next[id]; return next; }); setQError(id, ''); };

  const saveMcq = async (id) => {
    const form = forms[id];
    const problem = mcqProblem(form);
    if (problem) { setQError(id, problem); return false; }
    setQBusy(id, 'save');
    setQError(id, '');
    try {
      const { question_type: _type, ...body } = form;
      const { ok, data } = await apiPut(`/api/assessment/question/${id}`, body);
      if (!ok) throw new Error(data.error || 'Could not save the question.');
      replaceQuestion(data.question);
      cancelEdit(id);
      return true;
    } catch (err) {
      setQError(id, err.message);
      return false;
    } finally {
      setQBusy(id, null);
    }
  };

  const regenerate = async (q) => {
    if (!window.confirm(`Regenerate question ${sorted.indexOf(q) + 1}? It is replaced by a new AI-generated question (same position and marks).`)) return;
    setQBusy(q.id, 'regenerate');
    setQError(q.id, '');
    try {
      const { ok, data } = await apiPost(`/api/assessment/question/${q.id}/regenerate`, {});
      if (!ok) throw new Error(data.error || 'Could not regenerate the question.');
      replaceQuestion(data.question);
      cancelEdit(q.id);
    } catch (err) {
      setQError(q.id, err.message);
    } finally {
      setQBusy(q.id, null);
    }
  };

  const validateCode = async (q) => {
    setQBusy(q.id, 'verify');
    setQError(q.id, '');
    try {
      const { ok, data } = await apiPost(`/api/assessment/question/${q.id}/verify`, {});
      if (!ok) throw new Error(data.error || 'Could not validate the code.');
      replaceQuestion({ id: q.id, verification: data.verification, test_cases: data.test_cases });
    } catch (err) {
      setQError(q.id, err.message);
    } finally {
      setQBusy(q.id, null);
    }
  };

  const togglePanel = id => setOpenPanels(prev => {
    const next = new Set(prev);
    if (next.has(id)) {
      if (dirtyPanels.has(id) && !window.confirm('Close the editor and discard its unsaved changes?')) return prev;
      next.delete(id);
      setDirtyPanels(d => { const n = new Set(d); n.delete(id); return n; });
    } else next.add(id);
    return next;
  });
  const panelDirty = (id, dirty) => setDirtyPanels(prev => {
    if (dirty === prev.has(id)) return prev;
    const next = new Set(prev);
    if (dirty) next.add(id); else next.delete(id);
    return next;
  });

  async function validate() {
    setChecking(true);
    setNotice('');
    try {
      const data = await apiGet(`/api/assessment/${assessment.id}/publish-check`);
      setCheck(isValidEmail(email) ? data
        : { ...data, ready: false, problems: [...(data.problems || []), 'Enter a valid candidate email address.'] });
    } catch (err) {
      setCheck({ ready: false, problems: [err.message || 'Could not validate the assessment.'], questions: [] });
    } finally {
      setChecking(false);
    }
  }

  const saveDraft = async () => {
    for (const id of Object.keys(forms).map(Number).filter(formDirty)) {
      if (!(await saveMcq(id))) { setNotice(''); return; }
    }
    if (dirtyPanels.size) {
      setNotice('Save or discard the open coding configuration (Save & verify) before saving the draft.');
      return;
    }
    const saved = await onSaveDraft();
    if (saved !== false) setNotice('Draft saved. Nothing has been sent.');
  };

  const goTo = (questionId) => {
    const q = original(questionId);
    if (!q) return;
    setTab(isCodingType(q.question_type) ? 'coding' : 'mcq');
    window.setTimeout(() => document.getElementById(`pv-q-${questionId}`)?.scrollIntoView?.({ behavior: 'smooth', block: 'center' }), 0);
  };

  const openConfirm = () => {
    requestId.current = newRequestId(); // one id per confirmation: retries of this send are never emailed twice
    setSendError('');
    setConfirming(true);
  };

  const send = async () => {
    if (!isValidEmail(email)) { setSendError('Enter a valid candidate email address.'); return; }
    setSending(true);
    setSendError('');
    try {
      const { ok, data } = await apiPost(`/api/assessment/${assessment.id}/send`, {
        to_email: email.trim(), confirm: true, reviewed_fingerprint: check.fingerprint, request_id: requestId.current,
      });
      if (!ok) throw new Error(data.error || 'Could not send the assessment.');
      setSent(data);
      setConfirming(false);
      onSent?.(data);
    } catch (err) {
      setSendError(err.message || 'Could not send the assessment. Retrying is safe: the candidate is not emailed twice.');
    } finally {
      setSending(false);
    }
  };

  const canSend = editable && !sent && check?.ready && !unsaved && !checking;
  const list = tab === 'mcq' ? mcqs : coding;

  return (
    <div className="pv-overlay" role="presentation">
      <div className="pv-dialog" role="dialog" aria-modal="true" aria-labelledby="pv-title">
        <header className="pv-header">
          <h2 id="pv-title"><i className="fas fa-eye" aria-hidden="true" /> Preview Assessment</h2>
          <span className={`pv-status pv-status-${String(assessment.status || '').toLowerCase()}`}>{STATUS_BADGES[assessment.status] || assessment.status}</span>
          <button type="button" className="pv-close" aria-label="Close preview" onClick={requestClose}><i className="fas fa-times" /></button>
        </header>
        <div className="pv-summary">
          <div className="pv-stat"><i className="fas fa-briefcase" aria-hidden="true" /><div><span>Job role</span><strong>{assessment.job_role || assessment.title}</strong><small>{assessment.title}</small></div></div>
          <div className="pv-stat"><i className="fas fa-user" aria-hidden="true" /><div><span>Candidate</span><strong>{assessment.candidate_name || '—'}</strong><small>{assessment.candidate_email || 'No email'}</small></div></div>
          <div className="pv-stat"><i className="fas fa-list-ol" aria-hidden="true" /><div><span>Total questions</span><strong>{sorted.length} ({mcqs.length} MCQ + {coding.length} Coding)</strong><small>{sqlCount ? `${coding.length - sqlCount} coding · ${sqlCount} SQL` : ' '}</small></div></div>
          <div className="pv-stat"><i className="fas fa-trophy" aria-hidden="true" /><div><span>Total marks</span><strong>{totalMarks}</strong><small>{assessment.time_limit_minutes} min · pass {assessment.passing_score}%</small></div></div>
        </div>

        <div className="pv-tabs" role="tablist">
          <button type="button" role="tab" aria-selected={tab === 'mcq'} className={tab === 'mcq' ? 'active' : ''} onClick={() => setTab('mcq')}>MCQ Questions ({mcqs.length})</button>
          <button type="button" role="tab" aria-selected={tab === 'coding'} className={tab === 'coding' ? 'active' : ''} onClick={() => setTab('coding')}>Coding Questions ({coding.length})</button>
        </div>

        <div className="pv-body">
          {sent && (
            <div className="pv-success" role="status">
              <i className="fas fa-circle-check" aria-hidden="true" />
              <div>
                <strong>{sent.replayed ? 'This assessment was already sent.' : `Assessment sent to ${sent.email?.to_email}.`}</strong>
                <p>Version {sent.published_version} published{sent.sent_at ? ` · ${new Date(sent.sent_at).toLocaleString()}` : ''}.
                  {sent.delivery_unknown && ' The mail server did not confirm delivery; check with the candidate before resending.'}</p>
                {sent.assessment_link && <input readOnly value={sent.assessment_link} aria-label="Candidate test link" onFocus={e => e.target.select()} />}
              </div>
            </div>
          )}
          {notice && <div className="pv-notice" role="status">{notice}</div>}
          {check && (
            check.ready ? (
              <div className="pv-valid" role="status"><i className="fas fa-circle-check" aria-hidden="true" /> All {sorted.length} questions, coding reference solutions and scoring rules are valid. Ready to send.</div>
            ) : (
              <div className="pv-invalid" role="alert">
                <strong>Fix these before sending:</strong>
                <ul>
                  {(check.problems || []).map(p => <li key={p}>{p}</li>)}
                  {(check.questions || []).map(q => (
                    <li key={q.question_id}>
                      <button type="button" className="pv-link" onClick={() => goTo(q.question_id)}>Question {q.number}</button> ({q.question_type}): {q.problems.join(' ')}
                    </li>
                  ))}
                </ul>
              </div>
            )
          )}
          {tab === 'coding' && sqlCount > 0 && <p className="pv-muted">Includes {sqlCount} SQL question{sqlCount === 1 ? '' : 's'}, executed in an SQLite sandbox.</p>}
          {list.length === 0 && <p className="pv-empty">No {tab === 'mcq' ? 'MCQ' : 'coding'} questions in this assessment.</p>}
          {list.map((q, index) => (tab === 'mcq' ? (
            <McqCard key={q.id} question={q} number={index + 1} total={list.length} editable={editable} form={forms[q.id]}
              busy={busy[q.id]} error={errors[q.id]} onEdit={() => startEdit(q)} onCancel={() => cancelEdit(q.id)}
              onChange={form => setForms(prev => ({ ...prev, [q.id]: form }))} onSave={() => saveMcq(q.id)} onRegenerate={() => regenerate(q)} />
          ) : (
            <CodingCard key={q.id} question={q} number={index + 1} total={list.length} editable={editable} editing={openPanels.has(q.id)}
              busy={busy[q.id]} error={errors[q.id]} onEdit={() => togglePanel(q.id)} onRegenerate={() => regenerate(q)}
              onValidate={() => validateCode(q)} onPanelChange={patch => replaceQuestion({ id: q.id, ...patch })}
              onDirtyChange={dirty => panelDirty(q.id, dirty)} />
          )))}
        </div>

        <footer className="pv-footer">
          <button type="button" className="btn btn-secondary" onClick={requestClose}>Close Preview</button>
          <span className="pv-spacer" />
          {unsaved && <span className="pv-unsaved"><i className="fas fa-circle-exclamation" aria-hidden="true" /> Unsaved changes</span>}
          {editable && !sent && (
            <>
              <button type="button" className="btn btn-secondary" onClick={saveDraft}>Save as Draft</button>
              <button type="button" className="btn btn-secondary" onClick={validate} disabled={checking}>
                {checking ? <><i className="fas fa-spinner fa-spin" /> Validating…</> : <><i className="fas fa-clipboard-check" /> Validate Assessment</>}
              </button>
              <button type="button" className="btn pv-send" onClick={openConfirm} disabled={!canSend}
                title={canSend ? undefined : unsaved ? 'Save your changes, then validate' : 'Validate the assessment first'}>
                <i className="fas fa-paper-plane" /> Send Assessment
              </button>
            </>
          )}
        </footer>

        {confirming && (
          <div className="pv-confirm-overlay" role="presentation">
            <div className="pv-confirm" role="alertdialog" aria-modal="true" aria-labelledby="pv-confirm-title">
              <h3 id="pv-confirm-title">Send this assessment?</h3>
              <p>The candidate receives a personal test link by email. After sending, this exact version is published and its questions can no longer change once the candidate starts.</p>
              <label className="pv-label" htmlFor="pv-confirm-email">Candidate email</label>
              <input id="pv-confirm-email" type="email" value={email} disabled={sending} onChange={e => { setEmail(e.target.value); setSendError(''); }} />
              <dl className="pv-facts">
                <div><dt>Job</dt><dd>{assessment.job_role || assessment.title}</dd></div>
                <div><dt>Questions</dt><dd>{sorted.length} ({mcqs.length} MCQ + {coding.length} Coding)</dd></div>
                <div><dt>Total marks</dt><dd>{totalMarks}</dd></div>
                <div><dt>Duration</dt><dd>{assessment.time_limit_minutes} minutes</dd></div>
              </dl>
              {sendError && <div className="pv-error" role="alert">{sendError}</div>}
              <div className="pv-card-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setConfirming(false)} disabled={sending}>Cancel</button>
                <button type="button" className="btn pv-send" onClick={send} disabled={sending}>
                  {sending ? <><i className="fas fa-spinner fa-spin" /> Sending…</> : <><i className="fas fa-paper-plane" /> Confirm &amp; Send</>}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

export default AssessmentPreviewModal;
