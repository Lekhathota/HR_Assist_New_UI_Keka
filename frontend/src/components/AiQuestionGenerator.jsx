import React, { useEffect, useRef, useState } from 'react';
import { apiDelete, apiGet, apiPost } from '../api.js';
import { draftProblem } from './CodingQuestionsPanel.jsx';
import { mcqProblem } from '../utils/assessmentValidation.js';

const LETTERS = ['A', 'B', 'C', 'D'];
const DIFFICULTIES = ['Easy', 'Medium', 'Hard'];
const VERIFY = {
  verified: ['Reference verified', 'ok'], failed: ['Reference fails tests', 'bad'],
  unavailable: ['Execution unavailable', 'warn'], not_verified: ['Not validated', 'muted'],
};
const STALE = { status: 'not_verified', results: [], message: 'Edited since the last validation. Validate the reference solution again.' };
// Draft fields the backend accepts as review edits (coding_question_service.DRAFT_EDIT_KEYS).
const CODING_EDIT_KEYS = ['question_text', 'input_format', 'output_format', 'constraints', 'explanation', 'correct_answer',
  'test_cases', 'title', 'edge_cases', 'scoring', 'reference_solutions'];
const newRequestId = () => `mcq-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;

function VerifyBadge({ verification }) {
  const [label, tone] = VERIFY[verification?.status] || VERIFY.not_verified;
  return <span className={`pv-chip pv-verify-${tone}`}>{label}</span>;
}

function McqReview({ draft, editing, onChange }) {
  if (!editing) {
    return (
      <div className="pv-card">
        <p className="pv-text">{draft.question_text}</p>
        <div className="pv-options">
          {draft.options.map((option, i) => (
            <div key={i} className={`pv-option${option === draft.correct_answer ? ' pv-correct' : ''}`}>
              <span className="pv-letter">{LETTERS[i]}</span><span>{option}</span>
              {option === draft.correct_answer && <span className="pv-sr">(correct answer)</span>}
            </div>
          ))}
        </div>
        <div className="pv-explanation"><strong>Explanation</strong><p>{draft.explanation}</p></div>
      </div>
    );
  }
  const setOption = (index, value) => {
    const options = [0, 1, 2, 3].map(i => draft.options[i] ?? '');
    const wasCorrect = options[index] === draft.correct_answer && String(options[index]).trim();
    options[index] = value;
    onChange({ options, correct_answer: wasCorrect ? value : draft.correct_answer });
  };
  return (
    <div className="pv-card pv-editing">
      <label className="pv-label" htmlFor="ag-mcq-text">Question</label>
      <textarea id="ag-mcq-text" rows={3} value={draft.question_text} onChange={e => onChange({ question_text: e.target.value })} />
      <span className="pv-label">Options — select the correct answer</span>
      <div className="pv-options">
        {[0, 1, 2, 3].map(i => {
          const value = draft.options[i] ?? '';
          const correct = String(value).trim() && value === draft.correct_answer;
          return (
            <div key={i} className={`pv-option pv-option-edit${correct ? ' pv-correct' : ''}`}>
              <input type="radio" name="ag-mcq-correct" checked={Boolean(correct)} disabled={!String(value).trim()}
                aria-label={`Option ${LETTERS[i]} is correct`} onChange={() => onChange({ correct_answer: value })} />
              <span className="pv-letter">{LETTERS[i]}</span>
              <input type="text" value={value} aria-label={`Option ${LETTERS[i]}`} onChange={e => setOption(i, e.target.value)} />
            </div>
          );
        })}
      </div>
      <label className="pv-label" htmlFor="ag-mcq-expl">Explanation</label>
      <textarea id="ag-mcq-expl" rows={2} value={draft.explanation} onChange={e => onChange({ explanation: e.target.value })} />
    </div>
  );
}

function CodingReview({ draft, editing, language, onChange }) {
  const tests = draft.test_cases || [];
  const visible = tests.filter(t => !t.hidden);
  const scoring = { min_tests_passed: 0, min_score_percent: 50, partial_credit: true, ...(draft.scoring || {}) };
  const extraLanguage = language && language !== 'python' ? language : '';
  const failed = (draft.verification?.results || []).filter(r => !r.passed);
  const verification = (
    <div className="ag-verify">
      <VerifyBadge verification={draft.verification} />
      <span className={`pv-muted${draft.verification?.status === 'failed' ? ' pv-verify-text-bad' : ''}`}>{draft.verification?.message}</span>
      {failed.length > 0 && (
        <ul className="ag-failures">
          {failed.slice(0, 6).map((r, i) => (
            <li key={`${r.id}-${r.language || ''}-${i}`}>
              Test {r.id}{r.language ? ` (${r.language})` : ''}: {r.status.replace(/_/g, ' ')}
              {!r.hidden && r.actual != null && <> — got <code>{String(r.actual).slice(0, 80)}</code></>}
              {r.error && <> — {r.error.slice(0, 160)}</>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
  if (!editing) {
    return (
      <div className="pv-card">
        {draft.title && <h4 className="pv-title">{draft.title}</h4>}
        <p className="pv-text">{draft.question_text}</p>
        <dl className="pv-facts">
          {draft.input_format && <div><dt>Input</dt><dd>{draft.input_format}</dd></div>}
          {draft.output_format && <div><dt>Output</dt><dd>{draft.output_format}</dd></div>}
          {draft.constraints && <div><dt>Constraints</dt><dd>{draft.constraints}</dd></div>}
          {draft.edge_cases && <div><dt>Edge cases</dt><dd className="ag-pre">{draft.edge_cases}</dd></div>}
        </dl>
        {visible.length > 0 && (
          <div className="pv-samples">
            {visible.map((t, i) => (
              <div key={t.id || i} className="pv-sample"><strong>Sample {i + 1}</strong>
                <div className="pv-io"><div><span>Input</span><pre>{t.input}</pre></div><div><span>Expected output</span><pre>{t.expected_output}</pre></div></div>
              </div>
            ))}
          </div>
        )}
        <p className="pv-muted">
          Tests: {visible.length} public, {tests.length - visible.length} hidden
          {tests.some(t => Number(t.weight ?? 1) !== 1) && ' · weighted'}
          {tests.some(t => t.mandatory) && ` · ${tests.filter(t => t.mandatory).length} mandatory`}.
          {' '}Qualifies with at least {scoring.min_tests_passed} test(s) and {scoring.min_score_percent}% of the marks.
        </p>
        {draft.explanation && <div className="pv-explanation"><strong>Expected approach</strong><p>{draft.explanation}</p></div>}
        <details className="pv-reference"><summary>Reference solution (Python 3)</summary><pre>{draft.correct_answer}</pre></details>
        {Object.entries(draft.reference_solutions || {}).map(([lang, code]) => (
          <details key={lang} className="pv-reference"><summary>Reference solution ({lang})</summary><pre>{code}</pre></details>
        ))}
        {verification}
      </div>
    );
  }
  const field = (key, label, rows = 2, code = false) => (
    <div>
      <label className="pv-label" htmlFor={`ag-${key}`}>{label}</label>
      <textarea id={`ag-${key}`} rows={rows} className={code ? 'ag-code' : undefined} value={draft[key] || ''}
        onChange={e => onChange({ [key]: e.target.value })} />
    </div>
  );
  const setTest = (index, patch) => onChange({ test_cases: tests.map((t, i) => (i === index ? { ...t, ...patch } : t)) });
  const setScoring = patch => onChange({ scoring: { ...scoring, ...patch } });
  return (
    <div className="pv-card pv-editing">
      <label className="pv-label" htmlFor="ag-title">Title</label>
      <input id="ag-title" type="text" className="ag-input" value={draft.title || ''} onChange={e => onChange({ title: e.target.value })} />
      {field('question_text', 'Problem statement (with samples)', 6)}
      <div className="ag-grid">{field('input_format', 'Input format')}{field('output_format', 'Output format')}</div>
      <div className="ag-grid">{field('constraints', 'Constraints')}{field('edge_cases', 'Edge cases')}</div>
      {field('explanation', 'Expected approach / explanation', 3)}
      {field('correct_answer', 'Reference solution (Python 3)', 8, true)}
      {extraLanguage && (
        <div>
          <label className="pv-label" htmlFor="ag-ref-extra">Reference solution ({extraLanguage})</label>
          <textarea id="ag-ref-extra" rows={8} className="ag-code" value={draft.reference_solutions?.[extraLanguage] || ''}
            onChange={e => onChange({ reference_solutions: { ...(draft.reference_solutions || {}), [extraLanguage]: e.target.value } })} />
        </div>
      )}
      <span className="pv-label">Test cases ({visible.length} public, {tests.length - visible.length} hidden)</span>
      <div className="ag-tests">
        {tests.map((t, i) => (
          <div className="ag-test" key={t.id || i}>
            <span className="pv-qnum">#{i + 1}</span>
            <textarea rows={2} className="ag-code" aria-label={`Test ${i + 1} input`} value={t.input ?? ''} onChange={e => setTest(i, { input: e.target.value })} />
            <textarea rows={2} className="ag-code" aria-label={`Test ${i + 1} expected output`} value={t.expected_output ?? ''}
              onChange={e => setTest(i, { expected_output: e.target.value })} />
            <div className="ag-test-flags">
              <label className="pv-inline"><input type="checkbox" checked={Boolean(t.hidden)} onChange={e => setTest(i, { hidden: e.target.checked })} /> Hidden</label>
              <label className="pv-inline"><input type="checkbox" checked={Boolean(t.mandatory)} onChange={e => setTest(i, { mandatory: e.target.checked })} /> Mandatory</label>
              <label className="pv-inline">Weight
                <input type="number" min={0.01} max={100} step={0.5} aria-label={`Test ${i + 1} weight`} value={t.weight ?? 1}
                  onChange={e => setTest(i, { weight: Number(e.target.value) })} />
              </label>
              <button type="button" className="pv-link" aria-label={`Remove test ${i + 1}`}
                onClick={() => onChange({ test_cases: tests.filter((_, n) => n !== i) })}>Remove</button>
            </div>
          </div>
        ))}
        <button type="button" className="pv-link" onClick={() => onChange({ test_cases: [...tests, { input: '', expected_output: '', hidden: true, weight: 1 }] })}>
          + Add test case
        </button>
      </div>
      <div className="pv-row">
        <label className="pv-inline">Min. tests passed
          <input type="number" min={0} max={tests.length} value={scoring.min_tests_passed} onChange={e => setScoring({ min_tests_passed: Number(e.target.value) })} />
        </label>
        <label className="pv-inline">Qualifying score %
          <input type="number" min={0} max={100} value={scoring.min_score_percent} onChange={e => setScoring({ min_score_percent: Number(e.target.value) })} />
        </label>
        <label className="pv-inline"><input type="checkbox" checked={scoring.partial_credit !== false}
          onChange={e => setScoring({ partial_credit: e.target.checked })} /> Partial credit</label>
      </div>
      {verification}
    </div>
  );
}

/**
 * "Generate Question with AI" (Preview Assessment → + Add MCQ / + Add Coding Question).
 * Generates one question from the assessment's JD (+ the client coding prompt for coding questions) and the
 * recruiter's settings, lets the recruiter review, edit, regenerate and (coding) validate it, then saves it to
 * the draft. Nothing is sent to the candidate. Backend: services/mcq_question_service.py and
 * services/coding_question_service.py.
 */
function AiQuestionGenerator({ assessment, initialType, defaultPoints, onClose, onSaved, onDirtyChange }) {
  const [type, setType] = useState(initialType);
  const [context, setContext] = useState(null);
  const [contextError, setContextError] = useState('');
  const [settings, setSettings] = useState({ prompt: '', topic: '', difficulty: 'Medium', points: defaultPoints[initialType],
    time_limit_minutes: '', language: '', extend_duration: true });
  const [draft, setDraft] = useState(null);
  const [edited, setEdited] = useState(false);
  const [editing, setEditing] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const specId = useRef(null);       // coding entry created for this dialog (deleted on Cancel unless saved)
  const requestId = useRef(newRequestId()); // MCQ save token: retries of one save store one question
  const isCoding = type === 'coding';

  useEffect(() => {
    apiGet(`/api/assessment/${assessment.id}/coding`).then(setContext)
      .catch(err => setContextError(err.message || 'Could not load the job description details.'));
  }, [assessment.id]);
  useEffect(() => { onDirtyChange?.(Boolean(draft)); }, [draft]); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => () => onDirtyChange?.(false), []); // eslint-disable-line react-hooks/exhaustive-deps

  const set = patch => setSettings(prev => ({ ...prev, ...patch }));
  const changeDraft = patch => {
    setEdited(true);
    setDraft(prev => {
      const next = { ...prev, ...patch };
      // Execution results only describe the code and tests they ran on.
      if (isCoding && ['correct_answer', 'test_cases', 'reference_solutions'].some(k => k in patch)) next.verification = STALE;
      return next;
    });
  };
  const timeLimit = settings.time_limit_minutes === '' ? null : Number(settings.time_limit_minutes);
  const specFields = () => ({ prompt: settings.prompt, topic: settings.topic, difficulty: settings.difficulty,
    points: Number(settings.points), time_limit_minutes: timeLimit, language: settings.language });

  const changeType = next => {
    if (next === type) return;
    if (draft && !window.confirm('Discard the generated question and switch the question type?')) return;
    setDraft(null);
    setEdited(false);
    setEditing(false);
    setError('');
    setType(next);
    set({ points: defaultPoints[next] });
  };

  const settingsProblem = () => {
    if (isCoding && !settings.prompt.trim()) return 'Describe the coding question in the custom prompt.';
    if (!isCoding && !settings.prompt.trim() && !settings.topic.trim()) return 'Enter a custom prompt or a topic.';
    const points = Number(settings.points);
    if (!Number.isInteger(points) || points < 1 || points > 100) return 'Maximum marks must be a whole number from 1 to 100.';
    if (timeLimit !== null && (!Number.isInteger(timeLimit) || timeLimit < 1 || timeLimit > 240)) return 'Time limit must be 1–240 minutes, or empty.';
    return '';
  };

  const generate = async () => {
    const problem = settingsProblem();
    if (problem) { setError(problem); return; }
    if (draft && edited && !window.confirm('Regenerate? Your edits to this question will be replaced.')) return;
    setBusy('generate');
    setError('');
    try {
      if (isCoding && !specId.current) {
        const created = await apiPost(`/api/assessment/${assessment.id}/coding/specs`, specFields());
        if (!created.ok) throw new Error(created.data.error || 'Could not start the coding question.');
        specId.current = created.data.spec.id;
      }
      const res = await apiPost(isCoding ? `/api/assessment/${assessment.id}/coding/specs/${specId.current}/generate`
        : `/api/assessment/${assessment.id}/mcq/generate`, specFields());
      if (!res.ok) throw new Error(res.data.error || 'AI generation failed.');
      requestId.current = newRequestId(); // a new question gets a new save token
      setDraft(res.data.draft);
      setEdited(false);
      setEditing(false);
    } catch (err) {
      setError(err.message || 'AI generation failed. Please retry.');
    } finally {
      setBusy('');
    }
  };

  const codingEdits = () => Object.fromEntries(CODING_EDIT_KEYS.filter(k => draft[k] !== undefined).map(k => [k, draft[k]]));

  const validateReference = async () => {
    const problem = draftProblem(draft);
    if (problem) { setError(problem); return; }
    setBusy('verify');
    setError('');
    try {
      const { ok, data } = await apiPost(`/api/assessment/${assessment.id}/coding/specs/${specId.current}/draft/verify`,
        { ...specFields(), question: codingEdits() });
      if (!ok) throw new Error(data.error || 'Could not validate the reference solution.');
      setDraft(data.draft);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy('');
    }
  };

  const save = async () => {
    const problem = isCoding ? draftProblem(draft) : mcqProblem({ ...draft, question_type: 'mcq' });
    if (problem) { setError(problem); setEditing(true); return; }
    setBusy('save');
    setError('');
    try {
      const common = { prompt: settings.prompt, topic: settings.topic, time_limit_minutes: timeLimit,
        extend_duration: Boolean(timeLimit) && settings.extend_duration };
      const res = isCoding
        ? await apiPost(`/api/assessment/${assessment.id}/coding/specs/${specId.current}/save`,
          { ...specFields(), ...common, question: codingEdits() })
        : await apiPost(`/api/assessment/${assessment.id}/mcq/save`, {
          ...common, request_id: requestId.current, draft_meta: draft,
          question: { question_text: draft.question_text, options: draft.options, correct_answer: draft.correct_answer,
            explanation: draft.explanation, difficulty: settings.difficulty, points: Number(settings.points) },
        });
      if (!res.ok) throw new Error(res.data.error || 'Could not save the question.');
      specId.current = null; // saved: Cancel must no longer delete the entry
      setDraft(null);
      onSaved({ ...res.data, type });
    } catch (err) {
      setError(err.message || 'Could not save the question. Retrying is safe.');
    } finally {
      setBusy('');
    }
  };

  const cancel = async () => {
    if (draft && !window.confirm('Discard this generated question? It has not been added to the assessment.')) return;
    if (specId.current) {
      setBusy('cancel');
      await apiDelete(`/api/assessment/${assessment.id}/coding/specs/${specId.current}`).catch(() => null);
      specId.current = null;
    }
    onClose();
  };

  const working = Boolean(busy);
  const languages = context?.languages || [];
  const executionOff = isCoding && context?.execution && !context.execution.available;
  return (
    <div className="pv-confirm-overlay" role="presentation">
      <div className="ag-dialog" role="dialog" aria-modal="true" aria-labelledby="ag-title-h">
        <header className="ag-head">
          <h3 id="ag-title-h"><i className="fas fa-wand-magic-sparkles" aria-hidden="true" /> Generate Question with AI</h3>
          <button type="button" className="pv-close" aria-label="Close question generator" onClick={cancel} disabled={working}><i className="fas fa-times" /></button>
        </header>
        <div className="ag-body">
          <div className="ag-grid">
            <label className="ag-field">Question type
              <select value={type} disabled={working} onChange={e => changeType(e.target.value)}>
                <option value="mcq">MCQ</option><option value="coding">Coding</option>
              </select>
            </label>
            <div className="ag-field">Job description · client
              <strong className="ag-context">{context ? `${context.jd?.title || assessment.job_role || '—'}${context.client ? ` · ${context.client.name}` : ''}` : contextError ? '—' : 'Loading…'}</strong>
            </div>
          </div>
          {contextError && <p className="pv-muted">{contextError}</p>}
          {isCoding && context?.client_prompt && (
            <details className="ag-client-prompt"><summary>Client coding instructions (applied automatically)</summary><p>{context.client_prompt}</p></details>
          )}
          <label className="ag-field" htmlFor="ag-prompt">Custom prompt
            <textarea id="ag-prompt" rows={3} value={settings.prompt} disabled={working} maxLength={4000}
              placeholder={isCoding ? 'Problem to solve, expected behaviour, input/output, edge cases…' : 'What the question should assess, scenario or angle…'}
              onChange={e => set({ prompt: e.target.value })} />
          </label>
          <div className="ag-grid ag-grid-4">
            <label className="ag-field">Topic / skill
              <input type="text" value={settings.topic} disabled={working} maxLength={200} onChange={e => set({ topic: e.target.value })} />
            </label>
            <label className="ag-field">Difficulty
              <select value={settings.difficulty} disabled={working} onChange={e => set({ difficulty: e.target.value })}>
                {DIFFICULTIES.map(d => <option key={d} value={d}>{d}</option>)}
              </select>
            </label>
            <label className="ag-field">Maximum marks
              <input type="number" min={1} max={100} value={settings.points} disabled={working} onChange={e => set({ points: e.target.value })} />
            </label>
            <label className="ag-field">Time limit (min, optional)
              <input type="number" min={1} max={240} value={settings.time_limit_minutes} disabled={working} onChange={e => set({ time_limit_minutes: e.target.value })} />
            </label>
            {isCoding && (
              <label className="ag-field">Programming language
                <select value={settings.language} disabled={working} onChange={e => set({ language: e.target.value })}>
                  <option value="">Candidate's choice</option>
                  {languages.map(l => <option key={l.key} value={l.key}>{l.label}</option>)}
                </select>
              </label>
            )}
          </div>
          {timeLimit ? (
            <label className="pv-inline ag-extend">
              <input type="checkbox" checked={settings.extend_duration} disabled={working} onChange={e => set({ extend_duration: e.target.checked })} />
              Add {timeLimit} min to the assessment duration ({assessment.time_limit_minutes} → {Math.min(480, assessment.time_limit_minutes + timeLimit)} min)
            </label>
          ) : null}
          {executionOff && <p className="pv-muted ag-warn"><i className="fas fa-triangle-exclamation" aria-hidden="true" /> Code execution is not configured, so reference solutions cannot be validated here. Generated coding questions stay unvalidated and block sending.</p>}
          {busy === 'generate' && <div className="pv-notice" role="status"><i className="fas fa-spinner fa-spin" aria-hidden="true" /> Generating the question from the job description…</div>}
          {draft && busy !== 'generate' && (
            <section className="ag-review" aria-label="Generated question">
              <div className="ag-review-head">
                <strong>Review the generated question</strong>
                <span className="pv-chip pv-chip-type">{isCoding ? 'Coding' : 'MCQ'}</span>
                <span className={`pv-chip pv-diff-${settings.difficulty.toLowerCase()}`}>{settings.difficulty}</span>
                <span className="pv-marks">{settings.points} mark{Number(settings.points) === 1 ? '' : 's'}</span>
              </div>
              {isCoding
                ? <CodingReview draft={draft} editing={editing} language={settings.language} onChange={changeDraft} />
                : <McqReview draft={draft} editing={editing} onChange={changeDraft} />}
              <p className="pv-muted">Not added yet: review it, then <strong>Save to Draft</strong>. Nothing is sent to the candidate.</p>
            </section>
          )}
          {error && <div className="pv-error" role="alert">{error}</div>}
        </div>
        <footer className="ag-foot">
          <button type="button" className="btn btn-secondary" onClick={cancel} disabled={working}>Cancel</button>
          <span className="pv-spacer" />
          {draft && (
            <>
              <button type="button" className="btn btn-secondary" onClick={() => setEditing(v => !v)} disabled={working}>
                <i className="fas fa-pen" /> {editing ? 'Done Editing' : 'Edit Question'}
              </button>
              {isCoding && (
                <button type="button" className="btn btn-secondary" onClick={validateReference} disabled={working}>
                  {busy === 'verify' ? <><i className="fas fa-spinner fa-spin" /> Validating…</> : <><i className="fas fa-vial" /> Validate Reference Solution</>}
                </button>
              )}
            </>
          )}
          <button type="button" className="btn btn-secondary" onClick={generate} disabled={working}>
            {busy === 'generate' ? <><i className="fas fa-spinner fa-spin" /> Generating…</>
              : draft ? <><i className="fas fa-rotate" /> Regenerate Question</> : <><i className="fas fa-wand-magic-sparkles" /> Generate Question</>}
          </button>
          <button type="button" className="btn pv-send" onClick={save} disabled={working || !draft}
            title={draft ? undefined : 'Generate a question first'}>
            {busy === 'save' ? <><i className="fas fa-spinner fa-spin" /> Saving…</> : <><i className="fas fa-floppy-disk" /> Save to Draft</>}
          </button>
        </footer>
      </div>
    </div>
  );
}

export default AiQuestionGenerator;
