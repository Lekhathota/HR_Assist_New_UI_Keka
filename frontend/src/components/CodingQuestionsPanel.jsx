import React, { useCallback, useEffect, useRef, useState } from 'react';
import { apiDelete, apiGet, apiPost, apiPut } from '../api.js';

const PROMPT_HINT = [
  'Describe the client requirement for this question, for example:',
  '• Topic / concepts (e.g. graphs, sliding window, REST payload parsing)',
  '• Problem statement and expected behaviour',
  '• Input and output format, constraints and edge cases',
  '• Sample input/output, expected approach or evaluation criteria',
].join('\n');
const STATUS_LABELS = { pending: 'Not generated', generated: 'Generated', failed: 'Generation failed' };

function summaryOf(text) {
  const line = String(text || '').trim().split('\n')[0];
  return line.length > 80 ? `${line.slice(0, 77)}…` : line;
}

// Recruiter-defined coding questions for a draft assessment: any number of entries, each generated
// by AI from the JD + client instructions + the entry's own prompt. Persists through
// /api/assessment/:id/coding (see backend/services/coding_question_service.py).
function CodingQuestionsPanel({ assessmentId, onQuestionsChanged, onConfigChange }) {
  const [config, setConfig] = useState(null);
  const [loadError, setLoadError] = useState('');
  const [drafts, setDrafts] = useState({});         // unsaved edits per entry id
  const [busy, setBusy] = useState({});             // entry id -> 'save' | 'generate' | 'remove'
  const [errors, setErrors] = useState({});         // entry id -> message
  const [open, setOpen] = useState(() => new Set());
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
  const generatedCount = specs.filter(spec => spec.status === 'generated').length;
  const questionCount = config.coding_question_count + specs.length - generatedCount;
  const atLimit = specs.length >= limits.max_coding_questions;
  const valueOf = (spec, key) => (drafts[spec.id] && key in drafts[spec.id] ? drafts[spec.id][key] : spec[key]);
  const dirty = spec => Boolean(drafts[spec.id]) && Object.keys(drafts[spec.id]).some(key => drafts[spec.id][key] !== spec[key]);
  const edit = (spec, key, value) => {
    setDrafts(prev => ({ ...prev, [spec.id]: { ...prev[spec.id], [key]: value } }));
    setErrors(prev => ({ ...prev, [spec.id]: '' }));
  };
  const toggle = id => setOpen(prev => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id); else next.add(id);
    return next;
  });
  const setSpecBusy = (id, value) => setBusy(prev => ({ ...prev, [id]: value }));
  const clearDraft = id => setDrafts(prev => { const next = { ...prev }; delete next[id]; return next; });

  const addEntry = async () => {
    setAdding(true);
    setPanelError('');
    try {
      const { ok, data } = await apiPost(`/api/assessment/${assessmentId}/coding/specs`,
        { prompt: '', language: '', difficulty: 'Medium', points: 15 });
      if (!ok) throw new Error(data.error || 'Could not add a coding question.');
      focusPrompt.current = data.spec.id;
      apply(data.config);
      setOpen(prev => new Set(prev).add(data.spec.id));
    } catch (err) {
      setPanelError(err.message);
    } finally {
      setAdding(false);
    }
  };

  const saveEntry = async (spec) => {
    setSpecBusy(spec.id, 'save');
    try {
      const { ok, data } = await apiPut(`/api/assessment/${assessmentId}/coding/specs/${spec.id}`, drafts[spec.id] || {});
      if (!ok) throw new Error(data.error || 'Could not save.');
      apply(data.config);
      clearDraft(spec.id);
    } catch (err) {
      setErrors(prev => ({ ...prev, [spec.id]: err.message }));
    } finally {
      setSpecBusy(spec.id, null);
    }
  };

  const generateEntry = async (spec) => {
    if (!String(valueOf(spec, 'prompt') || '').trim()) {
      setErrors(prev => ({ ...prev, [spec.id]: 'Enter the client\'s requirements for this question before generating it.' }));
      return;
    }
    if (spec.status === 'generated' && !window.confirm('Regenerate this coding question? The current version, including any edits to it, will be replaced.')) return;
    setSpecBusy(spec.id, 'generate');
    setErrors(prev => ({ ...prev, [spec.id]: '' }));
    try {
      // The generation API reads the persisted shared prompt. Save current instructions first.
      if (clientDirty || saveAsDefault) await persistClientPrompt();
      const { ok, data } = await apiPost(`/api/assessment/${assessmentId}/coding/specs/${spec.id}/generate`, drafts[spec.id] || {});
      if (!ok) throw new Error(data.error || 'Generation failed.');
      apply(data.config);
      clearDraft(spec.id);
      onQuestionsChanged?.();
    } catch (err) {
      setErrors(prev => ({ ...prev, [spec.id]: err.message }));
      // Refresh server failure state without discarding unsaved question or shared prompts.
      try { apply(await apiGet(`/api/assessment/${assessmentId}/coding`)); } catch { /* keep the original error */ }
    } finally {
      setSpecBusy(spec.id, null);
    }
  };

  const removeEntry = async (spec) => {
    const message = spec.status === 'generated'
      ? 'Remove this coding question? Its generated question is removed from the assessment too.'
      : 'Remove this coding question entry?';
    if (!window.confirm(message)) return;
    setSpecBusy(spec.id, 'remove');
    try {
      const { ok, data } = await apiDelete(`/api/assessment/${assessmentId}/coding/specs/${spec.id}`);
      if (!ok) throw new Error(data.error || 'Could not remove.');
      apply(data);
      clearDraft(spec.id);
      if (spec.status === 'generated') onQuestionsChanged?.();
    } catch (err) {
      setErrors(prev => ({ ...prev, [spec.id]: err.message }));
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

  return (
    <section className="white-card ab-coding-panel" aria-labelledby="ab-coding-title">
      <div className="ab-coding-head">
        <div>
          <h2 id="ab-coding-title"><i className="fas fa-code" aria-hidden="true" /> Coding Questions ({questionCount})</h2>
          <p className="ab-muted">
            {specs.length} custom {specs.length === 1 ? 'entry' : 'entries'} · {generatedCount} generated · limit {limits.max_coding_questions}.
            {' '}Each question is generated from the JD{config.jd?.title ? ` (${config.jd.title})` : ''}, the client instructions and its own prompt.
          </p>
        </div>
        <div className="ab-coding-head-actions">
          {specs.length > 3 && (
            <button type="button" className="btn btn-secondary btn-sm" onClick={() => setOpen(open.size ? new Set() : new Set(specs.map(s => s.id)))}>
              {open.size ? 'Collapse all' : 'Expand all'}
            </button>
          )}
          <button type="button" className="btn btn-primary" onClick={addEntry} disabled={adding || atLimit}
            title={atLimit ? `Limit of ${limits.max_coding_questions} reached` : undefined}>
            {adding ? <><i className="fas fa-spinner fa-spin" /> Adding…</> : <>+ Add Coding Question</>}
          </button>
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
            return (
              <li key={spec.id} className={`ab-coding-card ab-coding-${spec.status}`}>
                <div className="ab-coding-card-head">
                <button type="button" className="ab-coding-summary" aria-controls={`ab-coding-body-${spec.id}`} aria-expanded={isOpen} onClick={() => toggle(spec.id)}>
                  <span className="ab-q-num">#{index + 1}</span>
                  <span className="ab-coding-title">{summaryOf(prompt) || 'New coding question'}</span>
                  <span className={`ab-coding-status ab-coding-status-${spec.status}`}>{STATUS_LABELS[spec.status] || spec.status}</span>
                  <span className="ab-badge">{valueOf(spec, 'difficulty')}</span>
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
                  <div className="ab-coding-body" id={`ab-coding-body-${spec.id}`}>
                    <label className="ab-label" htmlFor={`ab-coding-prompt-${spec.id}`}>Question prompt (client requirements)</label>
                    <textarea id={`ab-coding-prompt-${spec.id}`} rows={6} value={prompt} placeholder={PROMPT_HINT}
                      maxLength={limits.max_prompt_chars} disabled={Boolean(working)}
                      onChange={e => edit(spec, 'prompt', e.target.value)} />
                    <div className="ab-form-row ab-coding-fields">
                      <div>
                        <label className="ab-label" htmlFor={`ab-coding-lang-${spec.id}`}>Language</label>
                        <select id={`ab-coding-lang-${spec.id}`} value={valueOf(spec, 'language')} disabled={Boolean(working)}
                          onChange={e => edit(spec, 'language', e.target.value)}>
                          <option value="">Any (candidate chooses)</option>
                          {languages.map(l => <option key={l.key} value={l.key}>{l.label}</option>)}
                        </select>
                      </div>
                      <div>
                        <label className="ab-label" htmlFor={`ab-coding-diff-${spec.id}`}>Difficulty</label>
                        <select id={`ab-coding-diff-${spec.id}`} value={valueOf(spec, 'difficulty')} disabled={Boolean(working)}
                          onChange={e => edit(spec, 'difficulty', e.target.value)}>
                          {difficulties.map(d => <option key={d} value={d}>{d}</option>)}
                        </select>
                      </div>
                      <div>
                        <label className="ab-label" htmlFor={`ab-coding-points-${spec.id}`}>Points</label>
                        <input id={`ab-coding-points-${spec.id}`} type="number" min={1} max={100} value={valueOf(spec, 'points')}
                          disabled={Boolean(working)} onChange={e => edit(spec, 'points', Number(e.target.value))} />
                      </div>
                    </div>

                    {working === 'generate' && (
                      <p className="ab-muted" role="status"><i className="fas fa-spinner fa-spin" /> Generating and validating the question with its test cases. This can take up to a minute…</p>
                    )}
                    {error && <div className="ab-error" role="alert">{error}</div>}

                    {question && (
                      <div className="ab-coding-preview">
                        <p className="ab-question-text">{question.question_text}</p>
                        <p className="ab-muted">
                          {(question.test_cases || []).length} test cases
                          {' '}({(question.test_cases || []).filter(t => t.hidden).length} hidden)
                          {question.tests_verified ? ' · verified against the reference solution' : (question.test_cases || []).length ? ' · not yet verified' : ' · graded by AI (no automatic tests)'}
                          {' '}· {question.points} pts
                        </p>
                        <a href={`#ab-q-${question.id}`} className="ab-link-btn">Edit this question in the list below</a>
                      </div>
                    )}

                    <div className="ab-form-actions">
                      <button type="button" className="btn btn-secondary ab-danger-btn" onClick={() => removeEntry(spec)} disabled={Boolean(working)}>
                        <i className="fas fa-trash" /> Remove
                      </button>
                      {dirty(spec) && (
                        <button type="button" className="btn btn-secondary" onClick={() => saveEntry(spec)} disabled={Boolean(working)}>
                          {working === 'save' ? 'Saving…' : 'Save changes'}
                        </button>
                      )}
                      <button type="button" className="btn btn-primary" onClick={() => generateEntry(spec)} disabled={Boolean(working) || clientBusy}>
                        {working === 'generate' ? <><i className="fas fa-spinner fa-spin" /> Generating…</>
                          : spec.status === 'generated' ? <><i className="fas fa-rotate" /> Regenerate</>
                            : <><i className="fas fa-magic" /> Generate Question</>}
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
        <button type="button" className="btn btn-primary" onClick={addEntry} disabled={adding || atLimit}
          title={atLimit ? `Limit of ${limits.max_coding_questions} reached` : undefined}>
          {adding ? 'Adding...' : '+ Add Coding Question'}
        </button>
        {atLimit && <p className="ab-muted" role="status">Limit of {limits.max_coding_questions} custom coding questions reached.</p>}
      </div>
    </section>
  );
}

export default CodingQuestionsPanel;
