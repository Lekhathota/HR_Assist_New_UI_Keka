import React, { useEffect, useState } from 'react';
import { apiGet, apiPost, apiPut } from '../api.js';
import '../styles/reference_solution.css';

const STATUS = {
  verified: { label: 'Verified', tone: 'ok' },
  failed: { label: 'Failed', tone: 'bad' },
  unavailable: { label: 'Execution unavailable', tone: 'warn' },
  not_verified: { label: 'Not verified', tone: 'muted' },
};
const DIFFICULTIES = ['Easy', 'Medium', 'Hard'];

function statusOf(verification) {
  return STATUS[verification?.status] || STATUS.not_verified;
}

function newCase(isSql) {
  return isSql
    ? { name: '', description: '', setup_sql: '', hidden: true, enabled: true, weight: 1, mandatory: false }
    : { name: '', description: '', input: '', expected_output: '', hidden: true, enabled: true, weight: 1, mandatory: false };
}

// Marks for each number of passed tests, for the recruiter to check the scoring rules (equal weights only).
export function marksTable(points, cases, scoring) {
  const enabled = cases.filter(c => c.enabled !== false);
  const total = enabled.length;
  if (!total) return [];
  const equal = enabled.every(c => Number(c.weight ?? 1) === Number(enabled[0].weight ?? 1));
  if (!equal) return null;
  return Array.from({ length: total + 1 }, (_, passed) => {
    const fraction = scoring.partial_credit ? passed / total : passed === total ? 1 : 0;
    const marks = Math.round(points * fraction * 100) / 100;
    const qualified = passed >= Number(scoring.min_tests_passed || 0) && fraction * 100 >= Number(scoring.min_score_percent || 0);
    return { passed, total, marks, qualified };
  });
}

function ResultRows({ data }) {
  const columns = data?.columns || [];
  const rows = data?.rows || [];
  if (!columns.length && !rows.length) return <p className="rs-muted">No rows</p>;
  return (
    <div className="rs-table-wrap">
      <table className="rs-table">
        {columns.length > 0 && <thead><tr>{columns.map((c, i) => <th key={i}>{c}</th>)}</tr></thead>}
        <tbody>{rows.map((row, r) => <tr key={r}>{row.map((v, c) => <td key={c}>{v === null ? 'NULL' : String(v)}</td>)}</tr>)}</tbody>
      </table>
    </div>
  );
}

function CaseResult({ result, isSql, showLanguage }) {
  if (!result) return null;
  return (
    <div className={`rs-case-result ${result.passed ? 'ok' : 'bad'}`}>
      {showLanguage && result.language && <span className="rs-lang">{result.language}</span>}{' '}
      <strong>{result.passed ? 'Passed' : result.status.replace(/_/g, ' ')}</strong>
      {result.time != null && <span className="rs-muted"> · {result.time}s</span>}
      {result.memory != null && <span className="rs-muted"> · {Math.round(result.memory / 1024)} MB</span>}
      {result.error && <pre className="rs-pre rs-error">{result.error}</pre>}
      {!isSql && result.actual != null && (<><span className="rs-label">Actual output</span><pre className="rs-pre">{result.actual || '(no output)'}</pre></>)}
      {isSql && result.actual && (<><span className="rs-label">Reference result (expected)</span><ResultRows data={result.actual} /></>)}
    </div>
  );
}

/**
 * Coding Configuration for a coding / SQL question: problem details, execution limits, reference
 * solutions per language, public and hidden test cases with weights, and scoring / qualification rules.
 * Saving always re-verifies, so the status reflects actual execution of the saved version.
 */
function ReferenceSolutionPanel({ question, onChange, onDirtyChange, defaultOpen = false }) {
  const isSql = question.question_type === 'sql';
  const [open, setOpen] = useState(defaultOpen);
  const [config, setConfig] = useState(null);
  const [draft, setDraft] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');
  const [extraLanguage, setExtraLanguage] = useState('');

  const cases = (draft || config)?.test_cases || question.test_cases || [];
  const enabledCases = cases.filter(c => c.enabled !== false);
  const hiddenCount = enabledCases.filter(c => c.hidden).length;
  const verification = config?.verification || question.verification;
  const status = statusOf(dirty ? { status: 'not_verified' } : verification);
  const editable = config?.editable;
  const results = dirty ? [] : verification?.results || [];
  const multiLanguage = new Set(results.map(r => r.language).filter(Boolean)).size > 1;
  const codingAvailable = config?.execution?.coding?.available;
  const problems = dirty ? [] : config?.problems || [];
  const settings = draft?.config;
  const runtimes = config?.runtimes || [];
  const labelOf = key => runtimes.find(r => r.key === key)?.label || key;

  const applyConfig = (data) => {
    setConfig(data);
    setDraft({
      reference_solution: data.reference_solution,
      reference_language: data.reference_language,
      sql_schema: data.sql_schema,
      order_matters: data.order_matters,
      test_cases: data.test_cases.map(c => ({ weight: 1, mandatory: false, ...c })),
      config: data.config ? { ...data.config, scoring: { ...data.config.scoring }, reference_solutions: { ...(data.config.reference_solutions || {}) } } : null,
    });
    setDirty(false);
    const c = data.config || {};
    onChange?.({
      correct_answer: data.reference_solution, reference_language: data.reference_language,
      test_cases: data.test_cases, verification: data.verification, sql_schema: data.sql_schema,
      ...(data.config ? {
        title: c.title, question_text: c.question_text, points: c.points, difficulty: c.difficulty, skill_tag: c.skill_tag,
        input_format: c.input_format, output_format: c.output_format, constraints: c.constraints, edge_cases: c.edge_cases,
        time_limit_seconds: c.time_limit_seconds, memory_limit_mb: c.memory_limit_mb, allowed_languages: c.allowed_languages,
      } : {}),
      config_problems: data.problems || [],
    });
  };

  const load = async () => {
    setBusy('load');
    setError('');
    try {
      applyConfig(await apiGet(`/api/assessment/question/${question.id}/reference`));
    } catch (err) {
      setError(err.message || 'Could not load the coding configuration.');
    } finally {
      setBusy('');
    }
  };

  const toggle = async (event) => {
    const nextOpen = event.currentTarget.open;
    setOpen(nextOpen);
    if (nextOpen && !config && busy !== 'load') await load();
  };

  useEffect(() => { if (defaultOpen) load(); }, []); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { onDirtyChange?.(dirty); }, [dirty]); // eslint-disable-line react-hooks/exhaustive-deps

  const update = (patch) => { setDraft(prev => ({ ...prev, ...patch })); setDirty(true); };
  const updateConfig = (patch) => update({ config: { ...draft.config, ...patch } });
  const updateScoring = (patch) => updateConfig({ scoring: { ...draft.config.scoring, ...patch } });
  const updateCase = (index, patch) => update({ test_cases: draft.test_cases.map((c, i) => (i === index ? { ...c, ...patch } : c)) });
  const moveCase = (index, delta) => {
    const next = [...draft.test_cases];
    const target = index + delta;
    if (target < 0 || target >= next.length) return;
    [next[index], next[target]] = [next[target], next[index]];
    update({ test_cases: next });
  };
  const removeCase = (index) => {
    if (!window.confirm('Delete this test case?')) return;
    update({ test_cases: draft.test_cases.filter((_, i) => i !== index) });
  };
  const toggleLanguage = (key, on) => {
    const current = settings.allowed_languages || [];
    updateConfig({ allowed_languages: on ? [...current, key] : current.filter(k => k !== key) });
  };
  const setExtraReference = (language, code) => updateConfig({ reference_solutions: { ...settings.reference_solutions, [language]: code } });
  const removeExtraReference = (language) => {
    const next = { ...settings.reference_solutions };
    delete next[language];
    updateConfig({ reference_solutions: next });
  };

  const save = async () => {
    setBusy('save');
    setError('');
    try {
      const body = { ...draft, verify: true };
      if (!draft.config) delete body.config;
      const { ok, data } = await apiPut(`/api/assessment/question/${question.id}/reference`, body);
      if (!ok) throw new Error(data.error || 'Could not save the coding configuration.');
      applyConfig(data);
    } catch (err) {
      setError(err.message || 'Could not save the coding configuration.');
    } finally {
      setBusy('');
    }
  };

  const verify = async () => {
    setBusy('verify');
    setError('');
    try {
      const { ok, data } = await apiPost(`/api/assessment/question/${question.id}/verify`, {});
      if (!ok) throw new Error(data.error || 'Could not verify the reference solution.');
      applyConfig(data);
    } catch (err) {
      setError(err.message || 'Could not verify the reference solution.');
    } finally {
      setBusy('');
    }
  };

  const discard = () => { if (config) applyConfig(config); };
  const field = (key, label, { rows = 2, type = 'textarea' } = {}) => (
    <label className="rs-field">
      <span className="rs-label">{label}</span>
      {type === 'textarea'
        ? <textarea className="rs-text" rows={rows} disabled={!editable} value={settings[key] ?? ''} onChange={e => updateConfig({ [key]: e.target.value })} />
        : <input className="rs-text" type="text" disabled={!editable} value={settings[key] ?? ''} onChange={e => updateConfig({ [key]: e.target.value })} />}
    </label>
  );
  const table = settings ? marksTable(Number(settings.points) || 0, draft.test_cases, settings.scoring) : [];
  const extraLanguages = settings ? Object.keys(settings.reference_solutions || {}) : [];
  const addableLanguages = runtimes.filter(r => r.key !== draft?.reference_language && !extraLanguages.includes(r.key));

  return (
    <details className="rs-panel" open={open} onToggle={toggle}>
      <summary>
        <span className="rs-title">
          <i className="fas fa-sliders-h" aria-hidden="true" /> Coding Configuration · reference solution &amp; test cases ({enabledCases.length - hiddenCount} visible, {hiddenCount} hidden)
        </span>
        <span className={`rs-status rs-status-${status.tone}`}>{status.label}</span>
        {config && !dirty && (
          <span className={`rs-status rs-status-${problems.length ? 'bad' : 'ok'}`}>{problems.length ? `Invalid · ${problems.length} issue${problems.length === 1 ? '' : 's'}` : 'Ready to publish'}</span>
        )}
        {dirty && <span className="rs-status rs-status-warn">Unsaved changes</span>}
      </summary>

      {busy === 'load' && <p className="rs-muted">Loading…</p>}
      {error && <div className="rs-alert" role="alert">{error}</div>}

      {draft && (
        <div className="rs-body">
          {problems.length > 0 && (
            <div className="rs-message rs-message-bad" role="status">
              <strong>This question cannot be published yet:</strong>
              <ul className="rs-problems">{problems.map(p => <li key={p}>{p}</li>)}</ul>
            </div>
          )}
          {verification?.message && !dirty && (
            <p className={`rs-message rs-message-${statusOf(verification).tone}`}>
              {verification.message}
              {verification.verified_at && <span className="rs-muted"> · {new Date(verification.verified_at).toLocaleString()}</span>}
            </p>
          )}
          {!isSql && config && !codingAvailable && (
            <p className="rs-message rs-message-warn">
              Code execution is not configured on the server, so coding solutions cannot be verified and the question cannot be
              published yet (set <code>JUDGE0_URL</code>). You can still save the configuration.
            </p>
          )}
          {!editable && <p className="rs-muted">The assessment has been sent, so its configuration is read-only. Return it to draft to edit it; you can still re-run verification.</p>}

          {settings && (
            <>
              <h4 className="rs-subhead">Question</h4>
              {(config.jd || config.client) && (
                <p className="rs-muted">For {config.jd?.title || 'this job'}{config.client?.name ? ` · client ${config.client.name}` : ''}</p>
              )}
              {settings.generation_prompt && <p className="rs-muted"><strong>Recruiter prompt:</strong> {settings.generation_prompt}</p>}
              <div className="rs-grid">
                {field('title', 'Question title', { type: 'input' })}
                {field('skill_tag', 'Skills / topics evaluated', { type: 'input' })}
                <label className="rs-field">
                  <span className="rs-label">Difficulty</span>
                  <select disabled={!editable} value={settings.difficulty} onChange={e => updateConfig({ difficulty: e.target.value })}>
                    {DIFFICULTIES.map(d => <option key={d} value={d}>{d}</option>)}
                  </select>
                </label>
                <label className="rs-field">
                  <span className="rs-label">Maximum marks</span>
                  <input type="number" min={1} max={100} disabled={!editable} value={settings.points}
                    onChange={e => updateConfig({ points: Number(e.target.value) })} />
                </label>
              </div>
              {field('question_text', 'Problem statement', { rows: 5 })}
              <div className="rs-grid rs-grid-2">
                {field('input_format', 'Input format')}
                {field('output_format', 'Output format')}
                {field('constraints', 'Constraints')}
                {field('edge_cases', 'Edge cases')}
              </div>

              {!isSql && (
                <>
                  <h4 className="rs-subhead">Execution</h4>
                  <fieldset className="rs-languages" disabled={!editable}>
                    <legend className="rs-label">Allowed programming languages</legend>
                    {runtimes.map(r => (
                      <label key={r.key} className="rs-check">
                        <input type="checkbox" checked={(settings.allowed_languages || []).includes(r.key)}
                          onChange={e => toggleLanguage(r.key, e.target.checked)} /> {r.label}
                      </label>
                    ))}
                  </fieldset>
                  <div className="rs-grid">
                    <label className="rs-field">
                      <span className="rs-label">Time limit per test (s)</span>
                      <input type="number" min={0.5} max={15} step={0.5} disabled={!editable} value={settings.time_limit_seconds}
                        onChange={e => updateConfig({ time_limit_seconds: Number(e.target.value) })} />
                    </label>
                    <label className="rs-field">
                      <span className="rs-label">Memory limit (MB)</span>
                      <input type="number" min={16} max={512} disabled={!editable} value={settings.memory_limit_mb}
                        onChange={e => updateConfig({ memory_limit_mb: Number(e.target.value) })} />
                    </label>
                    <label className="rs-field">
                      <span className="rs-label">Output comparison</span>
                      <select disabled={!editable} value={settings.comparison} onChange={e => updateConfig({ comparison: e.target.value })}>
                        {(config.comparison_modes || []).map(m => <option key={m.key} value={m.key}>{m.label}</option>)}
                      </select>
                    </label>
                  </div>
                  <details className="rs-runtimes">
                    <summary>Compiler, entry point and run conventions</summary>
                    <table className="rs-table">
                      <thead><tr><th>Language</th><th>Runtime</th><th>Entry point</th><th>How it runs</th></tr></thead>
                      <tbody>{runtimes.map(r => <tr key={r.key}><td>{r.label}</td><td>{r.runtime}</td><td>{r.entry_point}</td><td>{r.run}</td></tr>)}</tbody>
                    </table>
                    <p className="rs-muted">Programs read standard input and write standard output. Code runs only in the Judge0 sandbox with network access disabled.</p>
                  </details>
                </>
              )}
            </>
          )}

          <div className="rs-editor-head">
            <label htmlFor={`rs-ref-${question.id}`}>{isSql ? 'Reference query' : 'Reference solution'}</label>
            {isSql ? (
              <span className="rs-lang">SQL (SQLite)</span>
            ) : (
              <select aria-label="Reference language" value={draft.reference_language} disabled={!editable}
                onChange={e => update({ reference_language: e.target.value })}>
                {(config?.execution?.coding?.languages || []).map(l => <option key={l.key} value={l.key}>{l.label}</option>)}
              </select>
            )}
          </div>
          <textarea id={`rs-ref-${question.id}`} className="rs-code" rows={10} spellCheck={false} disabled={!editable}
            value={draft.reference_solution} onChange={e => update({ reference_solution: e.target.value })} />

          {!isSql && settings && (
            <div className="rs-extra-refs">
              {extraLanguages.map(language => (
                <div key={language} className="rs-extra-ref">
                  <div className="rs-editor-head">
                    <label htmlFor={`rs-ref-${question.id}-${language}`}>Reference solution · {labelOf(language)}</label>
                    {editable && <button type="button" className="rs-danger" aria-label={`Remove ${labelOf(language)} reference`}
                      onClick={() => removeExtraReference(language)}><i className="fas fa-trash" /></button>}
                  </div>
                  <textarea id={`rs-ref-${question.id}-${language}`} className="rs-code rs-code-small" rows={8} spellCheck={false}
                    disabled={!editable} value={settings.reference_solutions[language]} onChange={e => setExtraReference(language, e.target.value)} />
                </div>
              ))}
              {editable && addableLanguages.length > 0 && (
                <div className="rs-add-ref">
                  <select aria-label="Add a reference solution in" value={extraLanguage} onChange={e => setExtraLanguage(e.target.value)}>
                    <option value="">Add a reference solution in another language…</option>
                    {addableLanguages.map(r => <option key={r.key} value={r.key}>{r.label}</option>)}
                  </select>
                  <button type="button" className="btn btn-secondary btn-sm" disabled={!extraLanguage}
                    onClick={() => { setExtraReference(extraLanguage, ''); setExtraLanguage(''); }}>Add</button>
                  <span className="rs-muted">Every reference solution must pass all enabled tests.</span>
                </div>
              )}
            </div>
          )}

          {isSql && (
            <>
              <label className="rs-field-label" htmlFor={`rs-schema-${question.id}`}>Schema (CREATE TABLE)</label>
              <textarea id={`rs-schema-${question.id}`} className="rs-code rs-code-small" rows={4} spellCheck={false} disabled={!editable}
                value={draft.sql_schema} onChange={e => update({ sql_schema: e.target.value })} />
              <label className="rs-check">
                <input type="checkbox" checked={!!draft.order_matters} disabled={!editable} onChange={e => update({ order_matters: e.target.checked })} />
                Row order matters (task requires ORDER BY)
              </label>
            </>
          )}

          <h4 className="rs-subhead">Test cases</h4>
          <p className="rs-muted">Visible tests are the public samples a candidate can run. Hidden tests are only used for scoring and are never shown to the candidate.</p>
          <ol className="rs-cases">
            {draft.test_cases.map((c, index) => (
              <li key={c.id || `new-${index}`} className={`rs-case ${c.enabled === false ? 'rs-disabled' : ''}`}>
                <div className="rs-case-head">
                  <span className="rs-case-num">#{index + 1}</span>
                  <input className="rs-name" placeholder="Name (optional)" value={c.name || ''} disabled={!editable}
                    onChange={e => updateCase(index, { name: e.target.value })} aria-label="Test case name" />
                  <select aria-label="Visibility" value={c.hidden ? 'hidden' : 'visible'} disabled={!editable}
                    onChange={e => updateCase(index, { hidden: e.target.value === 'hidden' })}>
                    <option value="visible">Visible to candidate</option>
                    <option value="hidden">Hidden</option>
                  </select>
                  <label className="rs-weight">
                    Weight
                    <input type="number" min={0.01} max={100} step="any" aria-label="Test case weight" value={c.weight ?? 1} disabled={!editable}
                      onChange={e => updateCase(index, { weight: e.target.value === '' ? '' : Number(e.target.value) })} />
                  </label>
                  <label className="rs-check">
                    <input type="checkbox" checked={!!c.mandatory} disabled={!editable} aria-label="Mandatory test"
                      onChange={e => updateCase(index, { mandatory: e.target.checked })} /> Mandatory
                  </label>
                  <label className="rs-check">
                    <input type="checkbox" checked={c.enabled !== false} disabled={!editable}
                      onChange={e => updateCase(index, { enabled: e.target.checked })} /> Enabled
                  </label>
                  {editable && (
                    <span className="rs-case-actions">
                      <button type="button" aria-label="Move up" onClick={() => moveCase(index, -1)} disabled={index === 0}><i className="fas fa-arrow-up" /></button>
                      <button type="button" aria-label="Move down" onClick={() => moveCase(index, 1)} disabled={index === draft.test_cases.length - 1}><i className="fas fa-arrow-down" /></button>
                      <button type="button" aria-label="Delete test case" className="rs-danger" onClick={() => removeCase(index)}><i className="fas fa-trash" /></button>
                    </span>
                  )}
                </div>
                {isSql ? (
                  <>
                    <span className="rs-label">Dataset (INSERT statements; leave empty for an empty table)</span>
                    <textarea className="rs-code rs-code-small" rows={3} spellCheck={false} disabled={!editable}
                      value={c.setup_sql || ''} onChange={e => updateCase(index, { setup_sql: e.target.value })} />
                  </>
                ) : (
                  <div className="rs-io">
                    <div>
                      <span className="rs-label">Input (stdin)</span>
                      <textarea className="rs-code rs-code-small" rows={3} spellCheck={false} disabled={!editable}
                        value={c.input || ''} onChange={e => updateCase(index, { input: e.target.value })} />
                    </div>
                    <div>
                      <span className="rs-label">Expected output</span>
                      <textarea className="rs-code rs-code-small" rows={3} spellCheck={false} disabled={!editable}
                        value={c.expected_output || ''} onChange={e => updateCase(index, { expected_output: e.target.value })} />
                    </div>
                  </div>
                )}
                <input className="rs-desc" placeholder="Description (optional)" value={c.description || ''} disabled={!editable}
                  onChange={e => updateCase(index, { description: e.target.value })} aria-label="Test case description" />
                {results.filter(r => r.id === c.id).map(r => <CaseResult key={`${r.language}-${r.id}`} result={r} isSql={isSql} showLanguage={multiLanguage} />)}
              </li>
            ))}
          </ol>

          {settings && (
            <>
              <h4 className="rs-subhead">Scoring &amp; qualification</h4>
              <p className="rs-muted">Marks come only from the tests the candidate's program passes when it runs; the code is never compared with the reference solution.</p>
              <div className="rs-grid">
                <label className="rs-check">
                  <input type="checkbox" checked={!!settings.scoring.partial_credit} disabled={!editable}
                    onChange={e => updateScoring({ partial_credit: e.target.checked })} /> Partial credit (marks by weight of passed tests)
                </label>
                <label className="rs-field">
                  <span className="rs-label">Minimum tests passed to qualify</span>
                  <input type="number" min={0} max={30} disabled={!editable} value={settings.scoring.min_tests_passed}
                    onChange={e => updateScoring({ min_tests_passed: Number(e.target.value) })} />
                </label>
                <label className="rs-field">
                  <span className="rs-label">Minimum score to qualify (%)</span>
                  <input type="number" min={0} max={100} disabled={!editable} value={settings.scoring.min_score_percent}
                    onChange={e => updateScoring({ min_score_percent: Number(e.target.value) })} />
                </label>
                <label className="rs-check">
                  <input type="checkbox" checked={!!settings.scoring.require_mandatory} disabled={!editable}
                    onChange={e => updateScoring({ require_mandatory: e.target.checked })} /> All mandatory tests must pass
                </label>
              </div>
              {table === null && <p className="rs-muted">Tests have different weights: marks = maximum marks × (weight of passed tests ÷ total weight).</p>}
              {table && table.length > 0 && (
                <table className="rs-table rs-marks" aria-label="Marks by tests passed">
                  <thead><tr><th>Tests passed</th><th>Marks</th><th>Qualifies</th></tr></thead>
                  <tbody>{table.map(row => (
                    <tr key={row.passed}><td>{row.passed} of {row.total}</td><td>{row.marks}/{settings.points}</td><td>{row.qualified ? 'Yes' : 'No'}</td></tr>
                  ))}</tbody>
                </table>
              )}
            </>
          )}

          <div className="rs-actions">
            {editable && (
              <button type="button" className="btn btn-secondary" onClick={() => update({ test_cases: [...draft.test_cases, newCase(isSql)] })} disabled={!!busy}>
                <i className="fas fa-plus" /> Add test case
              </button>
            )}
            <span className="rs-spacer" />
            {dirty && <button type="button" className="btn btn-secondary" onClick={discard} disabled={!!busy}>Discard</button>}
            <button type="button" className="btn btn-secondary" onClick={verify} disabled={!!busy || dirty}
              title={dirty ? 'Save your changes first' : 'Run the saved reference solutions against the enabled test cases'}>
              {busy === 'verify' ? <><i className="fas fa-spinner fa-spin" /> Verifying…</> : <><i className="fas fa-vial" /> Verify solution</>}
            </button>
            {editable && (
              <button type="button" className="btn btn-primary" onClick={save} disabled={!!busy || !dirty}>
                {busy === 'save' ? <><i className="fas fa-spinner fa-spin" /> Saving…</> : <><i className="fas fa-save" /> Save &amp; verify</>}
              </button>
            )}
          </div>
        </div>
      )}
    </details>
  );
}

export default ReferenceSolutionPanel;
