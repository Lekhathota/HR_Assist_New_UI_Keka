import React, { useEffect, useState } from 'react';
import { apiGet, apiPost } from '../api.js';
import { toast } from './EnterpriseFeedback.jsx';
import '../styles/recruiter_select.css';

// Recruiters who can own a JD. The list lives in the backend (/api/recruiters) so new
// names are shared; these are shown only if it cannot be loaded.
export const RECRUITERS = ['Prajwal P', 'Rajeswari L', 'Mamatha M', 'Soumen S', 'Afritha P'];
const ADD_RECRUITER = '__add_recruiter__';

/** Recruiter dropdown with a "+ Add new recruiter" option (Create JD and Edit JD). */
export default function RecruiterSelect({ id = 'recruiter', name, value, onChange, required = false, className = '' }) {
  const [recruiters, setRecruiters] = useState(RECRUITERS);
  const [adding, setAdding] = useState(false);
  const [newName, setNewName] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    let active = true;
    apiGet('/api/recruiters')
      .then((data) => { if (active && Array.isArray(data.recruiters) && data.recruiters.length) setRecruiters(data.recruiters); })
      .catch(() => {});
    return () => { active = false; };
  }, []);

  // A JD may hold a recruiter that is not in the list (e.g. set before the list existed).
  const options = value && !recruiters.includes(value) ? [...recruiters, value] : recruiters;

  const cancel = () => {
    setAdding(false);
    setNewName('');
  };

  const save = async () => {
    const clean = newName.replace(/\s+/g, ' ').trim();
    if (!clean) {
      toast({ type: 'error', message: 'Enter the recruiter\'s name.' });
      return;
    }
    setSaving(true);
    try {
      const { ok, data } = await apiPost('/api/recruiters', { name: clean });
      if (!ok) throw new Error(data.error || 'Could not add recruiter.');
      setRecruiters(Array.isArray(data.recruiters) ? data.recruiters : [...recruiters, data.name]);
      onChange(data.name);
      cancel();
      toast({ type: 'success', message: data.created ? `${data.name} added as a recruiter.` : `${data.name} is already in the list - selected.` });
    } catch (err) {
      toast({ type: 'error', message: err.message || 'Could not add recruiter.' });
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <select
        id={id}
        name={name}
        className={className}
        value={value}
        required={required}
        onChange={(event) => (event.target.value === ADD_RECRUITER ? setAdding(true) : onChange(event.target.value))}
      >
        <option value="">Select recruiter</option>
        {options.map((recruiter) => <option key={recruiter} value={recruiter}>{recruiter}</option>)}
        <option value={ADD_RECRUITER}>+ Add new recruiter</option>
      </select>
      {adding && (
        <div className="recruiter-add">
          <input
            type="text"
            value={newName}
            maxLength={80}
            autoFocus
            aria-label="New recruiter name"
            placeholder="New recruiter's name"
            onChange={(event) => setNewName(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') { event.preventDefault(); save(); }
              if (event.key === 'Escape') { event.stopPropagation(); cancel(); }
            }}
          />
          <button type="button" className="recruiter-add-btn" disabled={saving} onClick={save}>
            <i className={`fas ${saving ? 'fa-spinner fa-spin' : 'fa-plus'}`} aria-hidden="true"></i> Add
          </button>
          <button type="button" className="recruiter-cancel-btn" onClick={cancel}>Cancel</button>
        </div>
      )}
    </>
  );
}
