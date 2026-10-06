import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import Layout from '../components/Layout.jsx';
import { apiGet, apiPostForm } from '../api.js';
import { initials } from '../utils/userDisplay.js';
import '../styles/comparison.css';
import '../styles/comparison_extra.css';
import '../styles/analyze.css';

const listify = (value) => Array.isArray(value) ? value.filter(Boolean) : String(value || '').split(/\n|,|;/).map(item => item.trim()).filter(Boolean);
const RESUME_EXT = /\.(pdf|docx)$/i;
const isPdf = file => file.type === 'application/pdf' || /\.pdf$/i.test(file.name);
const fileSize = bytes => bytes >= 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
const score = row => Number(row.match_score || 0);

const GROUPS = [
  { key: 'selected', label: 'Selected', tone: 'selected' },
  { key: 'waitlisted', label: 'Waitlisted', tone: 'waitlisted' },
  { key: 'rejected', label: 'Rejected', tone: 'rejected' },
];
const SORTS = {
  'score-desc': (a, b) => score(b) - score(a),
  'score-asc': (a, b) => score(a) - score(b),
  name: (a, b) => String(a.name || '').localeCompare(String(b.name || '')),
};

function Comparison() {
  const [jds, setJds] = useState([]);
  const [selectedJdId, setSelectedJdId] = useState('');
  const [source, setSource] = useState('bench');
  const [resumeFiles, setResumeFiles] = useState([]);
  const [isDragOver, setIsDragOver] = useState(false);
  const [previewIndex, setPreviewIndex] = useState(-1);
  const [previewUrl, setPreviewUrl] = useState('');
  const [mode, setMode] = useState('');
  const [stats, setStats] = useState([]);
  const [results, setResults] = useState({ selected: [], waitlisted: [], rejected: [] });
  const [hasRun, setHasRun] = useState(false);
  const [activeTab, setActiveTab] = useState('selected');
  const [query, setQuery] = useState('');
  const [sort, setSort] = useState('score-desc');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const inputRef = useRef(null);
  const resultsRef = useRef(null);

  useEffect(() => {
    apiGet('/api/jds').then(data => setJds(Array.isArray(data) ? data : [])).catch(() => setError('Could not load job descriptions.'));
  }, []);

  // Preview only the PDF the user chose; release the object URL when it changes.
  useEffect(() => {
    const file = resumeFiles[previewIndex];
    if (!file || !isPdf(file)) { setPreviewUrl(''); return undefined; }
    const url = URL.createObjectURL(file);
    setPreviewUrl(url);
    return () => URL.revokeObjectURL(url);
  }, [resumeFiles, previewIndex]);

  const selectedJd = useMemo(() => jds.find(jd => String(jd.id) === String(selectedJdId)), [jds, selectedJdId]);
  const uploading = source === 'upload';
  const ready = Boolean(selectedJdId) && (!uploading || resumeFiles.length > 0);
  const runLabel = !uploading ? 'Analyze bench'
    : resumeFiles.length ? `Match ${resumeFiles.length} ${resumeFiles.length === 1 ? 'resume' : 'resumes'}` : 'Match resumes';

  const addFiles = (fileList) => {
    const incoming = Array.from(fileList || []).filter(file => RESUME_EXT.test(file.name));
    if (!incoming.length) { setError('Only PDF or DOCX resumes can be uploaded.'); return; }
    setError('');
    setResumeFiles(prev => [...prev, ...incoming]);
  };
  const removeFile = (idx) => {
    setResumeFiles(prev => prev.filter((_, i) => i !== idx));
    setPreviewIndex(current => current === idx ? -1 : current > idx ? current - 1 : current);
  };
  const clearFiles = () => { setResumeFiles([]); setPreviewIndex(-1); if (inputRef.current) inputRef.current.value = ''; };
  const handleDrop = (event) => { event.preventDefault(); setIsDragOver(false); addFiles(event.dataTransfer.files); };

  const runWorkflow = async (event) => {
    event.preventDefault();
    if (!selectedJdId) { setError('Select a job description before starting analysis.'); return; }
    if (uploading && !resumeFiles.length) { setError('Add at least one resume, or switch the source to Internal bench.'); return; }
    setLoading(true); setError('');
    const form = new FormData();
    form.append('jd_id', selectedJdId);
    if (uploading) resumeFiles.forEach(file => form.append('resumes', file));
    try {
      const { ok, data } = await apiPostForm('/api/compare', form);
      if (!ok) { setError(data.error || 'Workflow could not be completed.'); return; }
      setResults({ selected: data.selected_results || [], waitlisted: data.waitlisted_results || [], rejected: data.rejected_results || [] });
      setStats(Array.isArray(data.stats) ? data.stats : []);
      setMode(data.mode || 'bench');
      setActiveTab('selected');
      setQuery('');
      setHasRun(true);
      // On stacked (narrow) layouts the results sit below the form; bring them into view.
      if (window.matchMedia?.('(max-width: 1100px)').matches) {
        requestAnimationFrame(() => resultsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }));
      }
    } catch { setError('Workflow failed. Check that the API server is running.'); }
    finally { setLoading(false); }
  };

  const groups = GROUPS.filter(group => group.key !== 'waitlisted' || mode !== 'resume_upload' || results.waitlisted.length);
  const activeGroup = GROUPS.find(group => group.key === activeTab);
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return results[activeTab]
      .filter(row => !needle || String(row.name || '').toLowerCase().includes(needle))
      .sort(SORTS[sort]);
  }, [results, activeTab, query, sort]);

  return <Layout><div className="analyze-page">
    <header className="analyze-header">
      <div>
        <h1>AI Analyze</h1>
        <p>Match internal bench candidates or uploaded resumes against a saved job, then review who fits and why.</p>
      </div>
    </header>

    <div className="analyze-layout">
      <form className="analyze-setup" onSubmit={runWorkflow} noValidate>
        <section className="az-card">
          <div className="az-card-head"><span className="az-step">1</span><div><h2>Job description</h2><p>The role candidates are matched against.</p></div></div>
          <label className="sr-only" htmlFor="jd_id">Job description</label>
          <select name="jd_id" id="jd_id" required className="az-select" value={selectedJdId} onChange={event => { setSelectedJdId(event.target.value); setError(''); }}>
            <option value="">Select a job…</option>
            {jds.map(jd => <option key={jd.id} value={jd.id}>{jd.title}{jd.department ? ` · ${jd.department}` : ''}</option>)}
          </select>
          {selectedJd && <div className="az-jd" aria-live="polite">
            <div className="az-jd-title"><strong>{selectedJd.title}</strong><span>{selectedJd.job_category || 'Category review required'}</span></div>
            <dl className="az-jd-facts">
              <div><dt>Required</dt><dd>{selectedJd.required_candidate_count || 'Not set'}</dd></div>
              <div><dt>Bench matched</dt><dd>{selectedJd.bench_matched_count || 0}</dd></div>
              <div><dt>Status</dt><dd>{selectedJd.workflow_status || 'ACTIVE'}</dd></div>
              <div><dt>Location</dt><dd>{selectedJd.location || 'Not specified'}</dd></div>
            </dl>
            {listify(selectedJd.skills).length > 0 && <div className="az-chips">{listify(selectedJd.skills).slice(0, 8).map(skill => <span key={skill}>{skill}</span>)}</div>}
          </div>}
        </section>

        <section className="az-card">
          <div className="az-card-head"><span className="az-step">2</span><div><h2>Candidate source</h2><p>Where the candidates come from.</p></div></div>
          <div className="az-segment" role="group" aria-label="Candidate source">
            <button type="button" aria-pressed={!uploading} className={!uploading ? 'active' : ''} onClick={() => { setSource('bench'); setError(''); }}>
              <i className="fas fa-people-group" aria-hidden="true" /><span><strong>Internal bench</strong><small>Auto-discover available people</small></span>
            </button>
            <button type="button" aria-pressed={uploading} className={uploading ? 'active' : ''} onClick={() => { setSource('upload'); setError(''); }}>
              <i className="fas fa-file-arrow-up" aria-hidden="true" /><span><strong>Upload resumes</strong><small>Match specific PDF or DOCX files</small></span>
            </button>
          </div>

          {uploading ? <>
            <div
              className={`az-drop${isDragOver ? ' over' : ''}`}
              role="button" tabIndex={0}
              onClick={() => inputRef.current && inputRef.current.click()}
              onKeyDown={event => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); inputRef.current && inputRef.current.click(); } }}
              onDragOver={event => { event.preventDefault(); setIsDragOver(true); }}
              onDragLeave={() => setIsDragOver(false)}
              onDrop={handleDrop}
            >
              <span className="az-drop-icon"><i className="fas fa-cloud-arrow-up" aria-hidden="true" /></span>
              <strong>Drop resumes or <u>browse</u></strong>
              <small>PDF or DOCX · multiple files</small>
              <input type="file" multiple accept=".pdf,.docx" ref={inputRef} hidden
                onChange={event => { addFiles(event.target.files); event.target.value = ''; }} />
            </div>
            {resumeFiles.length > 0 && <div className="az-files">
              <div className="az-files-head"><span>{resumeFiles.length} {resumeFiles.length === 1 ? 'file' : 'files'}</span><button type="button" onClick={clearFiles}>Clear all</button></div>
              <ul>
                {resumeFiles.map((file, idx) => <li key={`${file.name}-${idx}`} className={previewIndex === idx ? 'previewing' : ''}>
                  <i className={`fas ${isPdf(file) ? 'fa-file-pdf' : 'fa-file-word'}`} aria-hidden="true" />
                  <span className="az-file-name" title={file.name}>{file.name}<small>{fileSize(file.size)}</small></span>
                  {isPdf(file) && <button type="button" onClick={() => setPreviewIndex(current => current === idx ? -1 : idx)} aria-label={`${previewIndex === idx ? 'Hide' : 'Preview'} ${file.name}`} aria-pressed={previewIndex === idx}><i className={`fas ${previewIndex === idx ? 'fa-eye-slash' : 'fa-eye'}`} aria-hidden="true" /></button>}
                  <button type="button" onClick={() => removeFile(idx)} aria-label={`Remove ${file.name}`}><i className="fas fa-xmark" aria-hidden="true" /></button>
                </li>)}
              </ul>
              {previewUrl && <iframe title="Resume preview" src={previewUrl} className="az-preview" />}
            </div>}
          </> : <p className="az-note"><i className="fas fa-circle-info" aria-hidden="true" />Finds available bench candidates in the job's exact category and analyzes them automatically.</p>}
        </section>

        {error && <div className="az-error" role="alert"><i className="fas fa-triangle-exclamation" aria-hidden="true" />{error}</div>}
        <button type="submit" className="az-run" disabled={loading || !ready}>
          {loading ? <><i className="fas fa-spinner fa-spin" aria-hidden="true" /> Analyzing…</>
            : <><i className="fas fa-wand-magic-sparkles" aria-hidden="true" /> {runLabel}</>}
        </button>
        {!ready && !loading && <p className="az-hint">{!selectedJdId ? 'Select a job to continue.' : 'Add at least one resume to continue.'}</p>}
      </form>

      <section ref={resultsRef} className="analyze-results" aria-live="polite" aria-busy={loading}>
        {loading ? <ResultsLoading /> : hasRun ? <>
          <div className="az-results-head">
            <h2>{mode === 'resume_upload' ? 'Resume match results' : 'Fulfilment results'}</h2>
            {selectedJd && <span>{selectedJd.title}</span>}
          </div>
          {stats.length > 0 && <div className="az-stats">{stats.map(stat => <div key={stat.label}><span>{stat.label}</span><strong>{stat.value}</strong></div>)}</div>}
          <div className="az-toolbar">
            <div className="az-tabs" role="tablist" aria-label="Result groups">
              {groups.map(group => <button key={group.key} type="button" role="tab" aria-selected={activeTab === group.key} className={`tone-${group.tone}`} onClick={() => setActiveTab(group.key)}>
                {group.label}<span>{results[group.key].length}</span>
              </button>)}
            </div>
            <div className="az-filters">
              <label className="az-search"><i className="fas fa-magnifying-glass" aria-hidden="true" /><span className="sr-only">Search candidates</span><input type="search" placeholder="Search candidates" value={query} onChange={event => setQuery(event.target.value)} /></label>
              <label><span className="sr-only">Sort candidates</span><select value={sort} onChange={event => setSort(event.target.value)}><option value="score-desc">Highest score</option><option value="score-asc">Lowest score</option><option value="name">Name A–Z</option></select></label>
            </div>
          </div>
          <div className="az-list" role="tabpanel">
            {visible.map(row => <ResultCard key={row.id || row.name} result={row} tone={activeGroup.tone} />)}
            {visible.length === 0 && <div className="az-list-empty">{query ? `No ${activeGroup.label.toLowerCase()} candidates match “${query}”.` : `No ${activeGroup.label.toLowerCase()} candidates.`}</div>}
          </div>
        </> : <ResultsIntro />}
      </section>
    </div>
  </div></Layout>;
}

function ResultsIntro() {
  const steps = [
    ['fa-briefcase', 'Pick a job', 'Choose the saved JD you are hiring for.'],
    ['fa-users', 'Choose candidates', 'Use the internal bench or upload resumes.'],
    ['fa-wand-magic-sparkles', 'Review the match', 'See scores, strengths and gaps for each person.'],
  ];
  return <div className="az-intro">
    <span className="az-intro-icon"><i className="fas fa-chart-simple" aria-hidden="true" /></span>
    <h2>No analysis yet</h2>
    <p>Results appear here once you run an analysis.</p>
    <ol>{steps.map(([icon, title, text], i) => <li key={title}><span><i className={`fas ${icon}`} aria-hidden="true" /></span><div><strong>{i + 1}. {title}</strong><small>{text}</small></div></li>)}</ol>
  </div>;
}

function ResultsLoading() {
  return <div className="az-loading">
    <p><i className="fas fa-spinner fa-spin" aria-hidden="true" /> Matching candidates against the job. This can take a minute…</p>
    {[0, 1, 2].map(i => <div key={i} className="az-skeleton"><span /><div><span /><span /><span /></div></div>)}
  </div>;
}

function ResultCard({ result, tone }) {
  const value = Math.max(0, Math.min(100, score(result)));
  const strengths = listify(result.strengths || result.matched_skills).slice(0, 5);
  const gaps = listify(result.gaps || result.missing_skills || result.rejection_reason).slice(0, 5);
  const status = result.selection_status || result.status || { selected: 'Selected', waitlisted: 'Waitlisted', rejected: 'Review' }[tone];
  return <article className={`az-result tone-${tone}`}>
    <div className="az-result-main">
      <span className="az-avatar" aria-hidden="true">{initials(result.name || 'Candidate')}</span>
      <div className="az-result-who">
        <h3>{result.name || 'Candidate'}</h3>
        <span className="az-status">{status}</span>
      </div>
      <div className="az-ring" style={{ '--score': value }} role="img" aria-label={`Match score ${value}%`}><span>{value}<small>%</small></span></div>
    </div>
    <p className="az-summary">{result.screening_summary || result.recommendation || result.rejection_reason || 'No screening explanation available.'}</p>
    {(strengths.length > 0 || gaps.length > 0) && <div className="az-explain">
      {strengths.length > 0 && <div><strong><i className="fas fa-circle-check" aria-hidden="true" /> Strong matches</strong><div className="az-chips good">{strengths.map(item => <span key={item}>{item}</span>)}</div></div>}
      {gaps.length > 0 && <div><strong><i className="fas fa-circle-exclamation" aria-hidden="true" /> Gaps to probe</strong><div className="az-chips gap">{gaps.map(item => <span key={item}>{item}</span>)}</div></div>}
    </div>}
    {result.id != null && <div className="az-result-actions"><Link to={`/talent/${result.id}`}>View profile <i className="fas fa-arrow-right" aria-hidden="true" /></Link></div>}
  </article>;
}

export default Comparison;
