import React, { useEffect, useState } from 'react';
import { apiPost } from '../api.js';
import { getCurrentRole } from '../roleAccess.js';
import { toast } from './EnterpriseFeedback.jsx';
import '../styles/hiring_process.css';

const EVENTS = [
  ['assessment_passed', 'Assessment passed'],
  ['scheduled', 'Scheduled'],
  ['rescheduled', 'Rescheduled'],
  ['selected_after_interview', 'Selected after interview'],
  ['rejected_after_interview', 'Rejected after interview'],
  ['cancelled', 'Cancelled'],
];
const UNMAPPED = '__unmapped__';

function JdHiringProcessEditor({ jdId, hiringProcess }) {
  const canEdit = ['recruiter', 'admin'].includes(getCurrentRole());
  const [steps, setSteps] = useState(hiringProcess?.steps || []);
  const [mappings, setMappings] = useState(hiringProcess?.event_mappings || {});
  const [stepInput, setStepInput] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    setSteps(hiringProcess?.steps || []);
    setMappings(hiringProcess?.event_mappings || {});
  }, [hiringProcess]);

  const addStep = () => {
    const name = stepInput.trim();
    if (!name) return;
    setSteps(prev => [...prev, { id: '', name }]);
    setStepInput('');
  };
  const renameStep = (index, name) => setSteps(prev => prev.map((s, i) => (i === index ? { ...s, name } : s)));
  const removeStep = (index) => {
    const removedId = steps[index]?.id;
    setSteps(prev => prev.filter((_, i) => i !== index));
    if (removedId) {
      setMappings(prev => {
        const next = { ...prev };
        Object.keys(next).forEach(key => { if (next[key] === removedId) next[key] = null; });
        return next;
      });
    }
  };
  const moveStep = (index, dir) => {
    setSteps(prev => {
      const next = [...prev];
      const target = index + dir;
      if (target < 0 || target >= next.length) return prev;
      [next[index], next[target]] = [next[target], next[index]];
      return next;
    });
  };

  const save = async () => {
    setSaving(true); setError('');
    try {
      const { ok, data } = await apiPost(`/api/jds/${jdId}/hiring-process`, { steps, event_mappings: mappings });
      if (ok) {
        setSteps(data.steps || steps);
        setMappings(data.event_mappings || mappings);
        toast({ type: 'success', message: 'Hiring process saved.' });
      } else {
        setError(data.error || 'Could not save the hiring process.');
      }
    } catch {
      setError('Could not save the hiring process.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="white-card jd-hiring-process-card">
      <div className="jd-details-topbar">
        <h2 className="white-card-title"><i className="fas fa-list-check"></i> Hiring Process</h2>
      </div>
      {!steps.length && !canEdit && <p className="jd-empty-text">No hiring process configured for this job yet.</p>}

      <div className="hiring-process-steps">
        {steps.map((step, index) => (
          <div key={step.id || `new-${index}`} className="hiring-process-step-row">
            <span className="hiring-process-step-index">{index + 1}</span>
            {canEdit ? (
              <input type="text" value={step.name} onChange={(e) => renameStep(index, e.target.value)} />
            ) : (
              <span className="hiring-process-step-name">{step.name}</span>
            )}
            {canEdit && (
              <span className="hiring-process-step-actions">
                <button type="button" onClick={() => moveStep(index, -1)} disabled={index === 0} aria-label="Move up"><i className="fas fa-arrow-up"></i></button>
                <button type="button" onClick={() => moveStep(index, 1)} disabled={index === steps.length - 1} aria-label="Move down"><i className="fas fa-arrow-down"></i></button>
                <button type="button" onClick={() => removeStep(index)} aria-label={`Remove ${step.name}`}><i className="fas fa-times"></i></button>
              </span>
            )}
          </div>
        ))}
      </div>

      {canEdit && (
        <>
          <div className="stage-builder-row">
            <input type="text" value={stepInput} onChange={(e) => setStepInput(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); addStep(); } }}
              placeholder="e.g. Technical Round 1" />
            <button type="button" className="stage-builder-add" onClick={addStep}><i className="fas fa-plus"></i> Add Step</button>
          </div>

          <h3 className="hiring-process-mappings-title">Interview event → stage</h3>
          <div className="hiring-process-mappings">
            {EVENTS.map(([key, label]) => (
              <div key={key} className="hiring-process-mapping-row">
                <label htmlFor={`mapping-${key}`}>{label}</label>
                <select id={`mapping-${key}`} value={mappings[key] || UNMAPPED}
                  onChange={(e) => setMappings(prev => ({ ...prev, [key]: e.target.value === UNMAPPED ? null : e.target.value }))}>
                  <option value={UNMAPPED}>— unmapped —</option>
                  {steps.filter(s => s.id).map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </div>
            ))}
          </div>

          {error && <div className="jd-create-error">{error}</div>}
          <button type="button" className="btn btn-success jd-table-btn hiring-process-save" disabled={saving} onClick={save}>
            {saving ? 'Saving...' : 'Save Hiring Process'}
          </button>
        </>
      )}
    </div>
  );
}

export default JdHiringProcessEditor;
