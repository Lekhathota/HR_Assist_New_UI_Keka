import React, { useEffect, useMemo, useState } from 'react';

const ROLE_LEVELS = ['Junior', 'Mid', 'Senior', 'Lead'];

function RoleEditor({ role = null, pipelines = [], saving = false, onSave, onCancel }) {
  const activePipelines = useMemo(
    () => (Array.isArray(pipelines) ? pipelines.filter((pipeline) => pipeline && !pipeline.is_archived) : []),
    [pipelines]
  );
  const [title, setTitle] = useState(role?.title || '');
  const [level, setLevel] = useState(role?.level || ROLE_LEVELS[0]);
  const [pipelineId, setPipelineId] = useState(role?.pipeline_id || activePipelines[0]?.id || '');

  useEffect(() => {
    setTitle(role?.title || '');
    setLevel(role?.level || ROLE_LEVELS[0]);
    setPipelineId(role?.pipeline_id || activePipelines[0]?.id || '');
  }, [role, activePipelines]);

  const handleSubmit = (event) => {
    event.preventDefault();
    onSave({ title: title.trim(), level, pipeline_id: pipelineId });
  };

  return (
    <form className="client-config-editor client-role-editor" onSubmit={handleSubmit}>
      <label className="jd-create-label-color">
        <span>Role title</span>
        <input value={title} onChange={(event) => setTitle(event.target.value)} required />
      </label>
      <label className="jd-create-label-color">
        <span>Level</span>
        <select value={level} onChange={(event) => setLevel(event.target.value)} required>
          {ROLE_LEVELS.map((option) => <option key={option} value={option}>{option}</option>)}
        </select>
      </label>
      <label className="jd-create-label-color">
        <span>Hiring pipeline</span>
        <select
          value={pipelineId}
          onChange={(event) => setPipelineId(event.target.value)}
          required
          disabled={activePipelines.length === 0}
        >
          {activePipelines.map((pipeline) => (
            <option key={pipeline.id} value={pipeline.id}>{pipeline.name}</option>
          ))}
        </select>
      </label>
      <div className="client-editor-footer">
        <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={saving}>Cancel</button>
        <button type="submit" className="btn btn-primary" disabled={saving || activePipelines.length === 0}>
          {saving ? 'Saving...' : 'Save'}
        </button>
      </div>
    </form>
  );
}

export default RoleEditor;
