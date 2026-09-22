import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import Layout from '../components/Layout.jsx';
import { apiGet, apiPostForm } from '../api.js';
import '../styles/comparison.css';
import '../styles/comparison_extra.css';

const listify = (value) => Array.isArray(value) ? value.filter(Boolean) : String(value || '').split(/\n|,|;/).map(item => item.trim()).filter(Boolean);
const RESUME_EXT = /\.(pdf|docx)$/i;

function Comparison() {
  const [jds, setJds] = useState([]);
  const [selectedJdId, setSelectedJdId] = useState('');
  const [resumeFiles, setResumeFiles] = useState([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const [previewUrl, setPreviewUrl] = useState('');
  const [previewType, setPreviewType] = useState('');
  const [mode, setMode] = useState('');
  const [stats, setStats] = useState([]);
  const [selected, setSelected] = useState([]);
  const [waitlisted, setWaitlisted] = useState([]);
  const [rejected, setRejected] = useState([]);
  const [hasRun, setHasRun] = useState(false);
  const [activeTab, setActiveTab] = useState('selected');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const inputRef = useRef(null);

  useEffect(() => {
    apiGet('/api/jds').then(data => setJds(Array.isArray(data) ? data : [])).catch(() => setError('Could not load job descriptions.'));
  }, []);

  useEffect(() => {
    const pdf = resumeFiles.find(file => file.type === 'application/pdf' || /\.pdf$/i.test(file.name));
    if (pdf) {
      const url = URL.createObjectURL(pdf);
      setPreviewUrl(url);
      setPreviewType('pdf');
      return () => URL.revokeObjectURL(url);
    }
    setPreviewUrl('');
    setPreviewType(resumeFiles.length ? 'other' : '');
    return undefined;
  }, [resumeFiles]);

  const selectedJd = useMemo(() => jds.find(jd => String(jd.id) === String(selectedJdId)), [jds, selectedJdId]);

  const addFiles = (fileList) => {
    const incoming = Array.from(fileList || []).filter(file => RESUME_EXT.test(file.name));
    if (!incoming.length) return;
    setResumeFiles(prev => [...prev, ...incoming]);
  };
  const removeFile = (idx) => setResumeFiles(prev => prev.filter((_, i) => i !== idx));
  const clearFiles = () => { setResumeFiles([]); if (inputRef.current) inputRef.current.value = ''; };
  const handleDrop = (event) => { event.preventDefault(); setIsDragOver(false); addFiles(event.dataTransfer.files); };

  const runWorkflow = async (event) => {
    event.preventDefault();
    if (!selectedJdId) { setError('Select a job description before starting analysis.'); return; }
    setLoading(true); setError('');
    const form = new FormData();
    form.append('jd_id', selectedJdId);
    resumeFiles.forEach(file => form.append('resumes', file));
    try {
      const { ok, data } = await apiPostForm('/api/compare', form);
      if (!ok) { setError(data.error || 'Workflow could not be completed.'); return; }
      setSelected(data.selected_results || []);
      setWaitlisted(data.waitlisted_results || []);
      setRejected(data.rejected_results || []);
      setStats(Array.isArray(data.stats) ? data.stats : []);
      setMode(data.mode || 'bench');
      setHasRun(true);
    } catch { setError('Workflow failed. Check that the API server is running.'); }
    finally { setLoading(false); }
  };
  const visible = activeTab === 'selected' ? selected : activeTab === 'waitlisted' ? waitlisted : rejected;

  return <Layout><div className="comparison-container">
    <h1><i className="fas fa-chart-line"></i> Automated Bench Analysis</h1>
    <p className="comparison-subtitle">Analyze eligible internal bench candidates for a JD, or upload resumes to match them directly against a saved JD, and track fulfilment.</p>
    <form onSubmit={runWorkflow}>
      <div className="step-card step-card-blue">
        <div className="step-card-header"><div className="step-badge step-badge-blue">1</div><h2><i className="fas fa-file-alt"></i> Select Job Description</h2></div>
        <select name="jd_id" id="jd_id" required className="step-jd-select" value={selectedJdId} onChange={event => setSelectedJdId(event.target.value)}>
          <option value="">-- Select a JD --</option>{jds.map(jd => <option key={jd.id} value={jd.id}>{jd.title} ({jd.department})</option>)}
        </select>
        {selectedJd && <div className="analyze-jd-context" aria-live="polite"><div className="analyze-jd-context-head"><i className="fas fa-clipboard-list"></i><span><strong>{selectedJd.title}</strong><small>{selectedJd.job_category || 'Category review required'}</small></span></div><div className="analyze-jd-context-grid"><div><span>Required</span><strong>{selectedJd.required_candidate_count || 'Not set'}</strong></div><div><span>Bench matched</span><strong>{selectedJd.bench_matched_count || 0}</strong></div><div><span>Workflow</span><strong>{selectedJd.workflow_status || 'ACTIVE'}</strong></div><div><span>Location</span><strong>{selectedJd.location || 'Not specified'}</strong></div></div><div className="analyze-skill-row">{listify(selectedJd.skills).slice(0, 6).map(skill => <span key={skill}>{skill}</span>)}</div></div>}
      </div>

      <div className="step-card step-card-blue">
        <div className="step-card-header"><div className="step-badge step-badge-blue">2</div><h2><i className="fas fa-file-upload"></i> Upload Resumes (optional)</h2></div>
        <p className="step3-desc">Add one or more resumes (PDF or DOCX) to send straight to the matching agent against the selected JD. Leave empty to run the automated bench workflow instead.</p>
        <div
          className={`upload-zone${isDragOver ? ' drop-zone--over' : ''}`}
          onClick={() => inputRef.current && inputRef.current.click()}
          onDragOver={event => { event.preventDefault(); setIsDragOver(true); }}
          onDragLeave={() => setIsDragOver(false)}
          onDrop={handleDrop}
        >
          <i className="fas fa-cloud-upload-alt upload-zone-icon"></i>
          <div className="upload-zone-title">Drop resumes here or click to upload</div>
          <div className="upload-zone-subtitle">PDF or DOCX &middot; multiple files supported</div>
          <input type="file" multiple accept=".pdf,.docx" ref={inputRef} className="upload-zone-input"
            onChange={event => { addFiles(event.target.files); event.target.value = ''; }} />
        </div>
        {resumeFiles.length > 0 && <div className="upload-file-list">
          {resumeFiles.map((file, idx) => <div className="upload-file-item" key={`${file.name}-${idx}`}>
            <i className="fas fa-file-alt"></i>
            <span>{file.name}</span>
            <button type="button" onClick={() => removeFile(idx)} aria-label={`Remove ${file.name}`}><i className="fas fa-times"></i></button>
          </div>)}
          <button type="button" className="upload-clear-btn" onClick={clearFiles}><i className="fas fa-trash"></i> Clear all</button>
        </div>}
        {previewUrl && previewType === 'pdf' && <div className="resume-preview-wrap">
          <div className="resume-preview-label"><i className="fas fa-eye"></i> Resume preview</div>
          <iframe title="Resume preview" src={previewUrl} className="resume-preview-frame" />
        </div>}
        {!previewUrl && previewType === 'other' && <div className="upload-remembered-note"><i className="fas fa-info-circle"></i> Inline preview is only available for PDF resumes. DOCX files will still be parsed and matched by the agent.</div>}
      </div>

      <div className="step-card step-card-green"><div className="step-card-header"><div className="step-badge step-badge-green">3</div><h2><i className="fas fa-robot"></i> Run {resumeFiles.length ? 'Resume Matching' : 'Automated Workflow'}</h2></div><p className="step3-desc">{resumeFiles.length ? 'Uploaded resumes are parsed and compared against the selected JD by the matching agent.' : 'The system discovers exact-category, available internal bench candidates and analyzes them automatically.'}</p>{error && <div className="analyze-submit-error"><i className="fas fa-triangle-exclamation"></i>{error}</div>}<button type="submit" className="btn btn-success step3-submit-btn" disabled={loading}>{loading ? <><i className="fas fa-spinner fa-spin"></i> Analysis in progress...</> : <><i className="fas fa-rocket"></i> {resumeFiles.length ? 'Match Resumes' : 'Analyze Bench'}</>}</button></div>
    </form>
    {hasRun ? <div className="results-section"><h2 className="results-section-title"><i className="fas fa-check"></i> {mode === 'resume_upload' ? 'Resume Match Summary' : 'Fulfilment Summary'}</h2><div className="screening-batch-summary">{stats.map(stat => <div key={stat.label}><strong>{stat.value}</strong><span>{stat.label}</span></div>)}</div><div className="results-tabs"><button type="button" className={`comparison-tab${activeTab === 'selected' ? ' active-green' : ''}`} onClick={() => setActiveTab('selected')}>Selected ({selected.length})</button><button type="button" className={`comparison-tab${activeTab === 'waitlisted' ? ' active-blue' : ''}`} onClick={() => setActiveTab('waitlisted')}>Waitlisted ({waitlisted.length})</button><button type="button" className={`comparison-tab${activeTab === 'rejected' ? ' active-red' : ''}`} onClick={() => setActiveTab('rejected')}>Rejected ({rejected.length})</button></div><div className="analyze-result-grid">{visible.map(row => <ResultCard key={row.id || row.name} result={row} tone={activeTab === 'selected' ? 'selected' : 'rejected'} />)}{visible.length === 0 && <div className="analyze-results-empty">No candidates in this group.</div>}</div></div> : <div className="results-empty"><i className="fas fa-search results-empty-icon"></i><h3 className="results-empty-title">No Workflow Run Yet</h3><p className="results-empty-subtitle">Select a JD (and optionally upload resumes) to view its automated fulfilment or matching analysis.</p></div>}
  </div></Layout>;
}

function ResultCard({ result, tone }) {
  const selected = tone === 'selected';
  const strengths = listify(result.strengths || result.matched_skills).slice(0, 4);
  const gaps = listify(result.gaps || result.missing_skills || result.rejection_reason).slice(0, 4);
  return <article className={`analyze-result-card ${selected ? 'analyze-result-selected' : 'analyze-result-rejected'}`}><div className="analyze-result-head"><div><h3>{result.name || 'Candidate'}</h3><span className={`badge ${selected ? 'badge-success' : 'badge-danger'}`}>{result.selection_status || result.status || (selected ? 'Selected' : 'Review')}</span></div><strong className={selected ? 'result-score-selected' : 'result-score-rejected'}>{Number(result.match_score || 0)}%</strong></div><div className="progress result-progress-wrap"><div className={`progress-bar${selected ? '' : ' result-progress-bar-rejected'}`} style={{ width: `${Number(result.match_score || 0)}%` }}></div></div><p className="analyze-result-summary">{result.screening_summary || result.recommendation || result.rejection_reason || 'No screening explanation available.'}</p><div className="analyze-explain-grid"><div><strong>Strong matches</strong>{strengths.map(item => <span key={item}>{item}</span>)}</div><div><strong>Gaps / focus</strong>{gaps.map(item => <span key={item}>{item}</span>)}</div></div><div className="analyze-result-actions"><Link to={`/talent/${result.id}`} className="btn btn-primary result-btn-action"><i className="fas fa-eye"></i> View Profile</Link></div></article>;
}

export default Comparison;
