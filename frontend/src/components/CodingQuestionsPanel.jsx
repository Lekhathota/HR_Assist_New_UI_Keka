import React, { useCallback, useEffect, useRef, useState } from 'react';
import { apiDelete, apiGet, apiPost, apiPut } from '../api.js';

const PROMPT_HINT = [
  'Describe the client requirement for this question, for example:',
  '• Topic / concepts (e.g. graphs, sliding window, REST payload parsing)',
  '• Problem statement and expected behaviour',
  '• Input and output format, constraints and edge cases',
  '• Sample input/output, expected approach or evaluation criteria',
].join('\n');
const STATUS_LABELS = { pending: 'Not generated', review: 'Review & save', generated: 'Saved', failed: 'Generation failed' };
const MIN_VISIBLE_TESTS = 2;
const MIN_HIDDEN_TESTS = 3;

function summaryOf(text) {
  const line = String(text || '').trim().split('\n')[0];
  return line.length > 80 ? `${line.slice(0, 77)}…` : line;
}

// Mirrors the server checks in coding_question_service._validated_draft so problems show before saving.
export function draftProblem(draft) {
  if (String(draft.question_text || '').trim().split(/\s+/).filter(Boolean).length < 12) {
    return 'The problem statement must describe the task, behaviour, constraints and samples (at least 12 words).';
  }
  if (!String(draft.correct_answer || '').trim()) return 'Add a reference solution (a complete Python 3 program).';
  if (!String(draft.explanation || '').trim()) return 'Add an explanation of the expected solution approach.';
  const tests = draft.test_cases || [];
  if (!tests.length) return '';
  const blank = tests.findIndex(t => !String(t.expected_output || '').trim());
  if (blank >= 0) return `Test ${blank + 1} needs an expected output.`;
  if (new Set(tests.map(t => t.input)).size !== tests.length) return 'Two test cases have the same input. Make each test different.';
  const visible = tests.filter(t => !t.hidden).length;
  if (visible < MIN_VISIBLE_TESTS || tests.length - visible < MIN_HIDDEN_TESTS) {
    return `Keep at least ${MIN_VISIBLE_TESTS} visible sample tests and ${MIN_HIDDEN_TESTS} hidden tests.`;
  }
  return '';
}

// Editable review of a generated question before it is added to the assessment.
function DraftReview({ specId, draft, onChange, disabled }) {
  const field = (key, label, { rows = 3, code = false } = {}) => (
    <div className="ab-draft-field">
      <label className="ab-label" htmlFor={`ab-draft-${key}-${specId}`}>{label}</label>
      <textarea id={`ab-draft-${key}-${specId}`} rows={rows} className={code ? 'ab-code' : undefined} value={draft[key] || ''}
        disabled={disabled} onChange={e => onChange(key, e.target.value)} />
    </div>
  );
  const tests = draft.test_cases || [];
  const setTest = (index, patch) => onChange('test_cases', tests.map((t, i) => (i === index ? { ...t, ...patch } : t)));
  return (
    <div className="ab-draft-review" aria-label="Review generated question">
      <div className="ab-draft-review-head">
        <strong><i className="fas fa-clipboard-check" aria-hidden="true" /> Review the generated question</strong>
        <span className="ab-muted">Edit anything below, then <strong>Save Question</strong> to add it to the assessment.</span>
      </div>
      {field('question_text', 'Problem statement (with samples)', { rows: 7 })}
      <div className="ab-form-row">
        {field('input_format', 'Input format', { rows: 2 })}
        {field('output_format', 'Output format', { rows: 2 })}
      </div>
      {field('constraints', 'Constraints', { rows: 2 })}
      {field('explanation', 'Expected approach / explanation', { rows: 3 })}
      {field('correct_answer', 'Reference solution (Python 3)', { rows: 8, code: true })}
      <div className="ab-draft-tests">
        <div className="ab-draft-tests-head">
          <span className="ab-label">Test cases ({tests.filter(t => !t.hidden).length} visible samples, {tests.filter(t => t.hidden).length} hidden)</span>
          {draft.tests_verified && <span className="ab-coding-status ab-coding-status-generated">Verified</span>}
        </div>
        {tests.length === 0 && <p className="ab-muted">No automatic tests: the answer is graded by AI against the reference solution.</p>}
        {tests.map((test, index) => (
          <div className="ab-draft-test" key={test.id || index}>
            <span className="ab-q-num">#{index + 1}</span>
            <label className="ab-draft-test-io">
              <span className="ab-label">Input</span>
              <textarea rows={2} className="ab-code" value={test.input ?? ''} disabled={disabled}
                aria-label={`Test ${index + 1} input`} onChange={e => setTest(index, { input: e.target.value })} />
            </label>
            <label className="ab-draft-test-io">
              <span className="ab-label">Expected output</span>
              <textarea rows={2} className="ab-code" value={test.expected_output ?? ''} disabled={disabled}
                aria-label={`Test ${index + 1} expected output`} onChange={e => setTest(index, { expected_output: e.target.value })} />
            </label>
            <label className="ab-checkbox">
              <input type="checkbox" checked={Boolean(test.hidden)} disabled={disabled}
                onChange={e => setTest(index, { hidden: e.target.checked })} /> Hidden
            </label>
            <button type="button" className="ab-icon-btn ab-danger" title="Remove test" aria-label={`Remove test ${index + 1}`}
              disabled={disabled} onClick={() => onChange('test_cases', tests.filter((_, i) => i !== index))}>
              <i className="fas fa-times" />
            </button>
          </div>
        ))}
        <button type="button" className="ab-link-btn" disabled={disabled}
          onClick={() => onChange('test_cases', [...tests, { input: '', expected_output: '', hidden: true }])}>
          + Add test case
        </button>
      </div>
    </div>
  );
}

// Recruiter-defined coding questions: any number of entries, each generated by AI from the JD + client
// instructions + the entry's own prompt, reviewed and edited, then saved to the assessment. Persists through
// /api/assessment/:id/coding (see backend/services/coding_question_service.py).
function CodingQuestionsPanel({ assessmentId, onQuestionsChanged, onConfigChange }) {
  const [config, setConfig] = useState(null);
  const [loadError, setLoadError] = useState('');
  const [drafts, setDrafts] = useState({});         // unsaved entry-setting edits per entry id
  const [reviewEdits, setReviewEdits] = useState({}); // unsaved edits to the generated question per entry id
  const [busy, setBusy] = useState({});             // entry id -> 'save' | 'generate' | 'remove' | 'cancel'
  const [errors, setErrors] = useState({});         // entry id -> message
  const [messages, setMessages] = useState({});     // entry id -> success message
  const [open, setOpen] = useState(() => new Set());
  const [fresh, setFresh] = useState(() => new Set()); // entries added in this visit that Cancel should delete
  const [clientPrompt, setClientPrompt] = useState('');
  const [saveAsDefault, setSaveAsDefault] = useState(false);
  const [clientBusy, setClientBusy] = useState(false);
  const [clientMessage, setClientMessage] = useState('');
  const [adding, setAdding] = useState(false);
  const [panelError, setPanelError] = useState('');
  const focusPrompt = useRef(null);

  useEffect(() => {
    if (focusPrompt.current) {
      document.getElementById(`ab-coding-prompt-${focusPrompt.current}`)?.focus();
      focusPrompt.current = null;
    }
  }, [config, open]);

  const apply = useCallback((next) => {
    setConfig(next);
    onConfigChange?.(next);
  }, [onConfigChange]);

  const load = useCallback(async () => {
    setLoadError('');
    try {
      const data = await apiGet(`/api/assessment/${assessmentId}/coding`);
      apply(data);
      setClientPrompt(data.client_prompt || '');
      // A generated draft waiting for review stays open after a reload.
      setOpen(prev => new Set([...prev, ...(data.specs || []).filter(s => s.draft).map(s => s.id)]));
    } catch (err) {
      setLoadError(err.message || 'Could not load coding questions.');
    }
  }, [assessmentId, apply]);

  useEffect(() => { load(); }, [load]);

  if (loadError) {
    return (
      <section className="white-card ab-coding-panel">
        <div className="ab-error">{loadError} <button type="button" className="ab-link-btn" onClick={load}>Retry</button></div>
      </section>
    );
  }
  if (!config) {
    return <section className="white-card ab-coding-panel"><p className="ab-muted"><i className="fas fa-spinner fa-spin" /> Loading coding questions…</p></section>;
  }

  const { specs, limits, languages, difficulties, client } = config;

  if (config.editable === false) {
    return (
      <section className="white-card ab-coding-panel ab-coding-locked" aria-labelledby="ab-coding-title">
        <div className="ab-coding-head">
          <div>
            <h2 id="ab-coding-title"><i className="fas fa-code" aria-hidden="true" /> Coding Questions ({config.coding_question_count})</h2>
            <p className="ab-muted">Questions are locked because the candidate has started this assessment.</p>
          </div>
          <button type="button" className="btn btn-primary" disabled title="Questions are locked once the candidate starts">
            + Add Coding Question
          </button>
        </div>
      </section>
    );
  }

  const savedCount = specs.filter(spec => spec.question).length;
  const questionCount = config.coding_question_count + specs.length - savedCount;
  const atLimit = specs.length >= limits.max_coding_questions;
  const valueOf = (spec, key) => (drafts[spec.id] && key in drafts[spec.id] ? drafts[spec.id][key] : spec[key]);
  const changedFields = spec => Object.fromEntries(Object.entries(drafts[spec.id] || {}).filter(([key, value]) => value !== spec[key]));
  const dirty = spec => Object.keys(changedFields(spec)).length > 0;
  const reviewOf = spec => (spec.draft ? { ...spec.draft, ...(reviewEdits[spec.id] || {}) } : null);
  const setError = (id, message) => setErrors(prev => ({ ...prev, [id]: message }));
  const edit = (spec, key, value) => {
    setDrafts(prev => ({ ...prev, [spec.id]: { ...prev[spec.id], [key]: value } }));
    setError(spec.id, '');
  };
  const editReview = (spec, key, value) => {
    setReviewEdits(prev => ({ ...prev, [spec.id]: { ...prev[spec.id], [key]: value } }));
    setError(spec.id, '');
  };
  const toggle = id => setOpen(prev => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const close = id => setOpen(prev => { const next = new Set(prev); next.delete(id); return next; });
  const forget = (setter, id) => setter(prev => { const next = { ...prev }; delete next[id]; return next; });
  const unfresh = id => setFresh(prev => { const next = new Set(prev); next.delete(id); return next; });
  const setSpecBusy = (id, value) => setBusy(prev => ({ ...prev, [id]: value }));

  const addEntry = async () => {
    setAdding(true);
    setPanelError('');
    try {
      const { ok, data } = await apiPost(`/api/assessment/${assessmentId}/coding/specs`,
        { prompt: '', language: '', difficulty: 'Medium', points: 15, topic: '', time_limit_minutes: null });
      if (!ok) throw new Error(data.error || 'Could not add a coding question.');
      focusPrompt.current = data.spec.id;
      apply(data.config);
      setFresh(prev => new Set(prev).add(data.spec.id));
      setOpen(prev => new Set(prev).add(data.spec.id));
    } catch (err) {
      setPanelError(err.message);
    } finally {
      setAdding(false);
    }
  };

  // Saves entry settings only (prompt, language, …) for an entry with nothing to review yet.
  const saveEntry = async (spec) => {
    setSpecBusy(spec.id, 'save');
    try {
      const { ok, data } = await apiPut(`/api/assessment/${assessmentId}/coding/specs/${spec.id}`, changedFields(spec));
      if (!ok) throw new Error(data.error || 'Could not save.');
      apply(data.config);
      forget(setDrafts, spec.id);
      unfresh(spec.id);
    } catch (err) {
      setError(spec.id, err.message);
    } finally {
      setSpecBusy(spec.id, null);
    }
  };

  // Validates the reviewed question on the server and adds it to the assessment.
  const saveQuestion = async (spec) => {
    const problem = draftProblem(reviewOf(spec));
    if (problem) { setError(spec.id, problem); return; }
    setSpecBusy(spec.id, 'save');
    setError(spec.id, '');
    try {
      const { ok, data } = await apiPost(`/api/assessment/${assessmentId}/coding/specs/${spec.id}/save`,
        { ...changedFields(spec), question: reviewEdits[spec.id] || {} });
      if (!ok) throw new Error(data.error || 'Could not save the question.');
      apply(data.config);
      forget(setDrafts, spec.id);
      forget(setReviewEdits, spec.id);
      unfresh(spec.id);
      setMessages(prev => ({ ...prev, [spec.id]: 'Saved to the assessment.' }));
      onQuestionsChanged?.(data.question);
    } catch (err) {
      setError(spec.id, err.message);
    } finally {
      setSpecBusy(spec.id, null);
    }
  };

  const generateEntry = async (spec) => {
    if (!String(valueOf(spec, 'prompt') || '').trim()) {
      setError(spec.id, 'Enter the client\'s requirements for this question before generating it.');
      return;
    }
    if (spec.draft && reviewEdits[spec.id] && !window.confirm('Regenerate this question? Your edits to the generated draft will be replaced.')) return;
    if (!spec.draft && spec.question && !window.confirm('Regenerate this coding question? You can review the new version before it replaces the saved one.')) return;
    setSpecBusy(spec.id, 'generate');
    setError(spec.id, '');
    setMessages(prev => ({ ...prev, [spec.id]: '' }));
    try {
      // The generation API reads the persisted shared prompt. Save current instructions first.
      if (clientDirty || saveAsDefault) await persistClientPrompt();
      const { ok, data } = await apiPost(`/api/assessment/${assessmentId}/coding/specs/${spec.id}/generate`, changedFields(spec));
      if (!ok) throw new Error(data.error || 'Generation failed.');
      apply(data.config);
      forget(setDrafts, spec.id);
      forget(setReviewEdits, spec.id);
    } catch (err) {
      setError(spec.id, err.message);
      // Refresh server failure state without discarding unsaved question or shared prompts.
      try { apply(await apiGet(`/api/assessment/${assessmentId}/coding`)); } catch { /* keep the original error */ }
    } finally {
      setSpecBusy(spec.id, null);
    }
  };

  // Cancel throws away what has not been saved: a generated draft, unsaved edits, or an entry added just now.
  const cancelEntry = async (spec) => {
    setSpecBusy(spec.id, 'cancel');
    setError(spec.id, '');
    try {
      if (fresh.has(spec.id) && !spec.question) {
        const { ok, data } = await apiDelete(`/api/assessment/${assessmentId}/coding/specs/${spec.id}`);
        if (!ok) throw new Error(data.error || 'Could not cancel.');
        apply(data);
        unfresh(spec.id);
      } else if (spec.draft) {
        const { ok, data } = await apiDelete(`/api/assessment/${assessmentId}/coding/specs/${spec.id}/draft`);
        if (!ok) throw new Error(data.error || 'Could not discard the draft.');
        apply(data);
      }
      forget(setDrafts, spec.id);
      forget(setReviewEdits, spec.id);
      close(spec.id);
    } catch (err) {
      setError(spec.id, err.message);
    } finally {
      setSpecBusy(spec.id, null);
    }
  };

  const removeEntry = async (spec) => {
    const message = spec.question
      ? 'Remove this coding question? Its saved question is removed from the assessment too.'
      : 'Remove this coding question entry?';
    if (!window.confirm(message)) return;
    setSpecBusy(spec.id, 'remove');
    try {
      const { ok, data } = await apiDelete(`/api/assessment/${assessmentId}/coding/specs/${spec.id}`);
      if (!ok) throw new Error(data.error || 'Could not remove.');
      apply(data);
      forget(setDrafts, spec.id);
      forget(setReviewEdits, spec.id);
      if (spec.question) onQuestionsChanged?.();
    } catch (err) {
      setError(spec.id, err.message);
      setSpecBusy(spec.id, null);
    }
  };

  const persistClientPrompt = async () => {
    setClientBusy(true);
    setClientMessage('');
    try {
      const { ok, data } = await apiPut(`/api/assessment/${assessmentId}/coding/client-prompt`,
        { prompt: clientPrompt, save_as_client_default: saveAsDefault });
      if (!ok) throw new Error(data.error || 'Could not save the client instructions.');
      apply(data);
      setClientPrompt(data.client_prompt || '');
      setClientMessage(saveAsDefault && client ? `Saved, and set as ${client.name}'s default.` : 'Saved for this assessment.');
      setSaveAsDefault(false);
    } finally {
      setClientBusy(false);
    }
  };

  const saveClientPrompt = async () => {
    try { await persistClientPrompt(); } catch (err) { setClientMessage(err.message); }
  };

  const clientDirty = clientPrompt !== (config.client_prompt || '');
  const addButton = (
    <button type="button" className="btn btn-primary" onClick={addEntry} disabled={adding || atLimit}
      title={atLimit ? `Limit of ${limits.max_coding_questions} reached` : undefined}>
      {adding ? <><i className="fas fa-spinner fa-spin" /> Adding…</> : '+ Add Coding Question'}
    </button>
  );

  return (
    <section className="white-card ab-coding-panel" aria-labelledby="ab-coding-title">
      <div className="ab-coding-head">
        <div>
          <h2 id="ab-coding-title"><i className="fas fa-code" aria-hidden="true" /> Coding Questions ({questionCount})</h2>
          <p className="ab-muted">
            {specs.length} custom {specs.length === 1 ? 'entry' : 'entries'} · {savedCount} saved · limit {limits.max_coding_questions}.
            {' '}Each question is generated from the JD{config.jd?.title ? ` (${config.jd.title})` : ''}, the client instructions and its own prompt,
            {' '}and is added to the assessment only after you review and save it.
          </p>
        </div>
        <div className="ab-coding-head-actions">
          {specs.length > 3 && (
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setOpen(open.size ? new Set() : new Set(specs.map(s => s.id)))}>
              {open.size ? 'Collapse all' : 'Expand all'}
            </button>
          )}
          {addButton}
        </div>
      </div>
      {panelError && <div className="ab-error" role="alert">{panelError}</div>}

      <div className="ab-client-prompt">
        <label className="ab-label" htmlFor="ab-client-prompt">
          Client coding instructions{client ? ` · ${client.name}` : ''} <span className="ab-optional">(optional, applies to every coding question)</span>
        </label>
        <textarea id="ab-client-prompt" rows={3} value={clientPrompt} maxLength={limits.max_client_prompt_chars}
          placeholder="e.g. Use Java 17, focus on clean object-oriented design, include performance constraints for 10^5 inputs."
          onChange={e => { setClientPrompt(e.target.value); setClientMessage(''); }} />
        <div className="ab-client-prompt-actions">
          {client && (
            <label className="ab-checkbox">
              <input type="checkbox" checked={saveAsDefault} onChange={e => setSaveAsDefault(e.target.checked)} />
              Also save as {client.name}'s default for future assessments
            </label>
          )}
          <button type="button" className="btn btn-secondary btn-sm" onClick={saveClientPrompt}
            disabled={clientBusy || (!clientDirty && !saveAsDefault)}>
            {clientBusy ? 'Saving…' : 'Save instructions'}
          </button>
          {clientMessage && <span className="ab-muted" role="status">{clientMessage}</span>}
        </div>
      </div>

      {specs.length === 0 ? (
        <div className="ab-empty">No custom coding questions yet. Click <strong>+ Add Coding Question</strong> for each one the client needs.</div>
      ) : (
        <ol className="ab-coding-list">
          {specs.map((spec, index) => {
            const working = busy[spec.id];
            const isOpen = open.has(spec.id);
            const prompt = valueOf(spec, 'prompt') || '';
            const error = errors[spec.id] || (spec.status === 'failed' ? spec.last_error : '');
            const question = spec.question;
            const review = reviewOf(spec);
            const id = key => `ab-coding-${key}-${spec.id}`;
            return (
              <li key={spec.id} className={`ab-coding-card ab-coding-${spec.status}`}>
                <div className="ab-coding-card-head">
                <button type="button" className="ab-coding-summary" aria-controls={id('body')} aria-expanded={isOpen} onClick={() => toggle(spec.id)}>
                  <span className="ab-q-num">#{index + 1}</span>
                  <span className="ab-coding-title">{summaryOf(prompt) || 'New coding question'}</span>
                  <span className={`ab-coding-status ab-coding-status-${spec.status}`}>{STATUS_LABELS[spec.status] || spec.status}</span>
                  <span className="ab-badge">{valueOf(spec, 'difficulty')}</span>
                  {valueOf(spec, 'topic') && <span className="ab-skill">{valueOf(spec, 'topic')}</span>}
                  <span className="ab-skill">{languages.find(l => l.key === valueOf(spec, 'language'))?.label || 'Any language'}</span>
                  <i className={`fas fa-chevron-${isOpen ? 'up' : 'down'}`} aria-hidden="true" />
                </button>
                <button type="button" className="btn btn-secondary btn-sm ab-coding-edit" aria-label={`Edit coding question ${index + 1}`}
                  disabled={Boolean(working)} onClick={() => {
                    focusPrompt.current = spec.id;
                    setOpen(prev => new Set(prev).add(spec.id));
                  }}>Edit</button>
                </div>
                {isOpen && (
                  <div className="ab-coding-body" id={id('body')}>
                    <label className="ab-label" htmlFor={id('prompt')}>Question prompt (client requirements) <span className="ab-required">*</span></label>
                    <textarea id={id('prompt')} rows={6} value={prompt} placeholder={PROMPT_HINT} required
                      maxLength={limits.max_prompt_chars} disabled={Boolean(working)}
                      onChange={e => edit(spec, 'prompt', e.target.value)} />
                    <div className="ab-form-row ab-coding-fields">
                      <div>
                        <label className="ab-label" htmlFor={id('topic')}>Topic / skill assessed</label>
                        <input id={id('topic')} type="text" value={valueOf(spec, 'topic') || ''} maxLength={limits.max_topic_chars}
                          placeholder="e.g. Sliding window" disabled={Boolean(working)} onChange={e => edit(spec, 'topic', e.target.value)} />
                      </div>
                      <div>
                        <label className="ab-label" htmlFor={id('lang')}>Language</label>
                        <select id={id('lang')} value={valueOf(spec, 'language')} disabled={Boolean(working)}
                          onChange={e => edit(spec, 'language', e.target.value)}>
                          <option value="">Any (candidate chooses)</option>
                          {languages.map(l => <option key={l.key} value={l.key}>{l.label}</option>)}
                        </select>
                      </div>
                      <div>
                        <label className="ab-label" htmlFor={id('diff')}>Difficulty</label>
                        <select id={id('diff')} value={valueOf(spec, 'difficulty')} disabled={Boolean(working)}
                          onChange={e => edit(spec, 'difficulty', e.target.value)}>
                          {difficulties.map(d => <option key={d} value={d}>{d}</option>)}
                        </select>
                      </div>
                      <div>
                        <label className="ab-label" htmlFor={id('time')}>Time limit (min, optional)</label>
                        <input id={id('time')} type="number" min={1} max={limits.max_time_limit_minutes} placeholder="No limit"
                          value={valueOf(spec, 'time_limit_minutes') ?? ''} disabled={Boolean(working)}
                          onChange={e => edit(spec, 'time_limit_minutes', e.target.value === '' ? null : Number(e.target.value))} />
                      </div>
                      <div>
                        <label className="ab-label" htmlFor={id('points')}>Points</label>
                        <input id={id('points')} type="number" min={1} max={100} value={valueOf(spec, 'points')}
                          disabled={Boolean(working)} onChange={e => edit(spec, 'points', Number(e.target.value))} />
                      </div>
                    </div>

                    {working === 'generate' && (
                      <p className="ab-muted" role="status"><i className="fas fa-spinner fa-spin" /> Generating and validating the question with its test cases. This can take up to a minute…</p>
                    )}
                    {error && <div className="ab-error" role="alert">{error}</div>}
                    {messages[spec.id] && !review && <p className="ab-success-text" role="status"><i className="fas fa-check-circle" /> {messages[spec.id]}</p>}

                    {review && (
                      <DraftReview specId={spec.id} draft={review} disabled={Boolean(working)} onChange={(key, value) => editReview(spec, key, value)} />
                    )}

                    {!review && question && (
                      <div className="ab-coding-preview">
                        <p className="ab-question-text">{question.question_text}</p>
                        <p className="ab-muted">
                          {(question.test_cases || []).length} test cases
                          {' '}({(question.test_cases || []).filter(t => t.hidden).length} hidden)
                          {question.tests_verified ? ' · verified against the reference solution' : (question.test_cases || []).length ? ' · not yet verified' : ' · graded by AI (no automatic tests)'}
                          {' '}· {question.points} pts
                        </p>
                        <a href={`#ab-q-${question.id}`} className="ab-link-btn">View this question in the list</a>
                      </div>
                    )}

                    <div className="ab-form-actions">
                      {!fresh.has(spec.id) && (
                        <button type="button" className="btn btn-secondary ab-danger-btn" onClick={() => removeEntry(spec)} disabled={Boolean(working)}>
                          <i className="fas fa-trash" /> Remove
                        </button>
                      )}
                      <button type="button" className="btn btn-secondary" onClick={() => cancelEntry(spec)} disabled={Boolean(working)}>
                        {working === 'cancel' ? 'Cancelling…' : 'Cancel'}
                      </button>
                      {!review && dirty(spec) && (
                        <button type="button" className="btn btn-secondary" onClick={() => saveEntry(spec)} disabled={Boolean(working)}>
                          {working === 'save' ? 'Saving…' : 'Save changes'}
                        </button>
                      )}
                      <button type="button" className={review ? 'btn btn-secondary' : 'btn btn-primary'} onClick={() => generateEntry(spec)} disabled={Boolean(working) || clientBusy}>
                        {working === 'generate' ? <><i className="fas fa-spinner fa-spin" /> Generating…</>
                          : review || question ? <><i className="fas fa-rotate" /> Regenerate</>
                            : <><i className="fas fa-magic" /> Generate Question</>}
                      </button>
                      <button type="button" className="btn btn-success" onClick={() => saveQuestion(spec)} disabled={Boolean(working) || !review}
                        title={review ? undefined : 'Generate the question first, then review and save it'}>
                        {working === 'save' && review ? <><i className="fas fa-spinner fa-spin" /> Saving…</> : <><i className="fas fa-save" /> Save Question</>}
                      </button>
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ol>
      )}
      <div className="ab-coding-footer">
        {addButton}
        {atLimit && <p className="ab-muted" role="status">Limit of {limits.max_coding_questions} custom coding questions reached.</p>}
      </div>
    </section>
  );
}

export default CodingQuestionsPanel;
