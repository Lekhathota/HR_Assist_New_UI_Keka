import React, { useState } from 'react';
import { apiGet, apiPost, apiPut } from '../api.js';
import '../styles/reference_solution.css';

const STATUS = {
  verified: { label: 'Verified', tone: 'ok' },
  failed: { label: 'Failed', tone: 'bad' },
  unavailable: { label: 'Execution unavailable', tone: 'warn' },
  not_verified: { label: 'Not verified', tone: 'muted' },
};

function statusOf(verification) {
  return STATUS[verification?.status] || STATUS.not_verified;
}

function newCase(isSql) {
  return isSql
    ? { name: '', description: '', setup_sql: '', hidden: true, enabled: true }
    : { name: '', description: '', input: '', expected_output: '', hidden: true, enabled: true };
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

function CaseResult({ result, isSql }) {
  if (!result) return null;
  return (
    <div className={`rs-case-result ${result.passed ? 'ok' : 'bad'}`}>
      <strong>{result.passed ? 'Passed' : result.status.replace(/_/g, ' ')}</strong>
      {result.time != null && <span className="rs-muted"> · {result.time}s</span>}
      {result.error && <pre className="rs-pre rs-error">{result.error}</pre>}
      {!isSql && result.actual != null && (<><span className="rs-label">Actual output</span><pre className="rs-pre">{result.actual || '(no output)'}</pre></>)}
      {isSql && result.actual && (<><span className="rs-label">Reference result (expected)</span><ResultRows data={result.actual} /></>)}
    </div>
  );
}

/**
 * Admin editor for a coding / SQL question's reference solution and test cases.
 * Saving always re-verifies, so the status reflects actual execution of the saved version.
 */
function ReferenceSolutionPanel({ question, onChange }) {
  const isSql = question.question_type === 'sql';
  const [open, setOpen] = useState(false);
  const [config, setConfig] = useState(null);
  const [draft, setDraft] = useState(null);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState('');
  const [error, setError] = useState('');

  const cases = (draft || config)?.test_cases || question.test_cases || [];
  const enabledCases = cases.filter(c => c.enabled !== false);
  const hiddenCount = enabledCases.filter(c => c.hidden).length;
  const verification = config?.verification || question.verification;
  const status = statusOf(dirty ? { status: 'not_verified' } : verification);
  const editable = config?.editable;
  const resultsById = new Map((dirty ? [] : verification?.results || []).map(r => [r.id, r]));
  const codingAvailable = config?.execution?.coding?.available;

  const applyConfig = (data) => {
    setConfig(data);
    setDraft({
      reference_solution: data.reference_solution,
      reference_language: data.reference_language,
      sql_schema: data.sql_schema,
      order_matters: data.order_matters,
      test_cases: data.test_cases.map(c => ({ ...c })),
    });
    setDirty(false);
    onChange?.({
      correct_answer: data.reference_solution, reference_language: data.reference_language,
      test_cases: data.test_cases, verification: data.verification, sql_schema: data.sql_schema,
    });
  };

  const toggle = async (event) => {
    const nextOpen = event.currentTarget.open;
    setOpen(nextOpen);
    if (nextOpen && !config) {
      setBusy('load');
      setError('');
      try {
        applyConfig(await apiGet(`/api/assessment/question/${question.id}/reference`));
      } catch (err) {
        setError(err.message || 'Could not load the reference solution.');
      } finally {
        setBusy('');
      }
    }
  };

  const update = (patch) => { setDraft(prev => ({ ...prev, ...patch })); setDirty(true); };
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

  const save = async () => {
    setBusy('save');
    setError('');
    try {
      const { ok, data } = await apiPut(`/api/assessment/question/${question.id}/reference`, { ...draft, verify: true });
      if (!ok) throw new Error(data.error || 'Could not save the reference solution.');
      applyConfig(data);
    } catch (err) {
      setError(err.message || 'Could not save the reference solution.');
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

  return (
    <details className="rs-panel" open={open} onToggle={toggle}>
      <summary>
        <span className="rs-title">
          Reference solution &amp; test cases ({enabledCases.length - hiddenCount} visible, {hiddenCount} hidden)
        </span>
        <span className={`rs-status rs-status-${status.tone}`}>{status.label}</span>
        {dirty && <span className="rs-status rs-status-warn">Unsaved changes</span>}
      </summary>

      {busy === 'load' && <p className="rs-muted">Loading…</p>}
      {error && <div className="rs-alert" role="alert">{error}</div>}

      {draft && (
        <div className="rs-body">
          {verification?.message && !dirty && (
            <p className={`rs-message rs-message-${statusOf(verification).tone}`}>
              {verification.message}
              {verification.verified_at && <span className="rs-muted"> · {new Date(verification.verified_at).toLocaleString()}</span>}
            </p>
          )}
          {!isSql && config && !codingAvailable && (
            <p className="rs-message rs-message-warn">
              Code execution is not configured on the server, so coding solutions cannot be verified yet (set <code>JUDGE0_URL</code>).
              You can still save the solution and test cases.
            </p>
          )}
          {!editable && <p className="rs-muted">The assessment has been sent, so the solution and tests are read-only. You can still re-run verification.</p>}

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
                <CaseResult result={resultsById.get(c.id)} isSql={isSql} />
              </li>
            ))}
          </ol>

          <div className="rs-actions">
            {editable && (
              <button type="button" className="btn btn-secondary" onClick={() => update({ test_cases: [...draft.test_cases, newCase(isSql)] })} disabled={!!busy}>
                <i className="fas fa-plus" /> Add test case
              </button>
            )}
            <span className="rs-spacer" />
            {dirty && <button type="button" className="btn btn-secondary" onClick={discard} disabled={!!busy}>Discard</button>}
            <button type="button" className="btn btn-secondary" onClick={verify} disabled={!!busy || dirty}
              title={dirty ? 'Save your changes first' : 'Run the saved reference solution against the enabled test cases'}>
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
