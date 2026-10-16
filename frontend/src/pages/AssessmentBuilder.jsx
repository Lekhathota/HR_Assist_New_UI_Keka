import React, { useState, useEffect, useCallback } from 'react';
import { Link, useParams, useNavigate } from 'react-router-dom';
import Layout from '../components/Layout.jsx';
import ReferenceSolutionPanel from '../components/ReferenceSolutionPanel.jsx';
import CodingQuestionsPanel from '../components/CodingQuestionsPanel.jsx';
import { apiGet, apiPost, apiPut, apiDelete } from '../api.js';
import ProctoringEvidence from '../components/ProctoringEvidence.jsx';
import { downloadAssessmentPdf } from '../utils/assessmentPdf.js';
import '../styles/assessment_builder.css';

const TYPE_LABELS = {
  mcq: 'MCQ',
  coding: 'Coding',
  sql: 'SQL',
  short_answer: 'Short Answer',
  true_false: 'True / False',
};

const EMPTY_QUESTION = {
  question_text: '',
  question_type: 'mcq',
  options: ['', '', '', ''],
  correct_answer: '',
  starter_code: '',
  explanation: '',
  points: 10,
  skill_tag: '',
};

// Questions change only in DRAFT; a sent assessment is a published version (return it to draft to edit).
const QUESTION_EDIT_STATES = ['DRAFT'];
const DEFAULT_POLICY = {
  section_weights: null, min_mcq_score: 0, min_coding_score: 0, coding_section_mandatory: false, require_coding_qualification: false,
};

// Same rules as the server's validate_mcq: four distinct options, exactly one correct, an explanation.
export function mcqProblem(form) {
  if (form.question_type !== 'mcq') return '';
  if (!String(form.question_text || '').trim()) return 'Enter the question text.';
  const options = form.options || [];
  if (options.length !== 4 || options.some(o => !String(o).trim())) return 'An MCQ needs exactly four non-empty options.';
  if (new Set(options.map(o => String(o).trim().toLowerCase().replace(/\s+/g, ' '))).size !== 4) return 'The four MCQ options must be different from each other.';
  if (options.filter(o => o === form.correct_answer).length !== 1) return 'Select exactly one of the four options as the correct answer.';
  if (!String(form.explanation || '').trim()) return 'Add an explanation of why the correct answer is right.';
  return '';
}

const METHOD_LABELS = {
  executed: 'Executed in sandbox',
  sql_executed: 'Executed (SQLite)',
  ai_estimated: 'AI-estimated (not executed)',
  pending_ai: 'Not graded',
};
const RESULT_LABELS = {
  passed: 'Passed', partially_passed: 'Partially passed', not_passed: 'Not passed',
  execution_error: 'Execution error', not_answered: 'Not answered',
};
const QUALIFICATION_LABELS = { qualified: 'Qualified', not_qualified: 'Not qualified', pending: 'Pending re-grade' };

// Section scores and the pass/qualification rules that were applied.
function ScoreSummary({ result }) {
  const sections = result?.evaluation_breakdown?.sections || {};
  const checks = result?.qualification_checks || [];
  const weights = result?.applied_section_weights;
  return (
    <div className="ab-score-summary">
      <div className="ab-score-tiles">
        {sections.mcq?.count > 0 && <div className="ab-score-tile"><span>MCQ</span><strong>{sections.mcq.percentage}%</strong><small>{sections.mcq.earned}/{sections.mcq.possible} pts{weights?.mcq != null ? ` · weight ${Math.round(weights.mcq)}%` : ''}</small></div>}
        {sections.coding?.count > 0 && <div className="ab-score-tile"><span>Coding &amp; SQL</span><strong>{sections.coding.percentage}%</strong><small>{sections.coding.earned}/{sections.coding.possible} pts{weights?.coding != null ? ` · weight ${Math.round(weights.coding)}%` : ''}</small></div>}
        <div className="ab-score-tile"><span>Overall</span><strong>{result.percentage ?? result.score_percentage}%</strong><small>{result.pass_basis === 'weighted' ? 'weighted by section' : 'by points'}</small></div>
      </div>
      {result.needs_retry && (
        <p className="ab-error" role="status">Some coding answers could not be executed because of an infrastructure problem. No pass/fail decision was made: use Re-grade once code execution is available.</p>
      )}
      {checks.length > 0 && (
        <ul className="ab-criteria" aria-label="Qualification criteria">
          {checks.map(c => <li key={c.rule} className={c.met ? 'ok' : 'bad'}><i className={`fas fa-${c.met ? 'check' : 'times'}`} aria-hidden="true" /> {c.label} <span className="ab-muted">(actual {typeof c.actual === 'number' ? c.actual : String(c.actual)})</span></li>)}
        </ul>
      )}
    </div>
  );
}

// Per-question coding / SQL grading from the stored assessment result.
function CodingResultBreakdown({ result, questions, attempts }) {
  const rows = (result?.question_results || []).filter(r => r.question_type === 'coding' || r.question_type === 'sql');
  if (!rows.length) return null;
  const position = new Map(questions.map((q, i) => [q.id, i + 1]));
  return (
    <div className="ab-coding-results">
      <h3>Coding &amp; SQL grading</h3>
      {rows.map(r => {
        const meta = r.metadata || {};
        const history = (attempts || []).filter(a => a.question_id === r.question_id);
        return (
          <details key={r.question_id} className="ab-coding-result">
            <summary>
              <span>Q{position.get(r.question_id) || '?'} · {r.question_type === 'sql' ? 'SQL' : 'Coding'}{meta.language && r.question_type === 'coding' ? ` (${meta.language})` : ''}</span>
              <span>{r.points_earned}/{r.points_possible} marks</span>
              {meta.tests_total > 0 && <span>{meta.tests_passed}/{meta.tests_total} tests · hidden {meta.hidden_passed}/{meta.hidden_total}</span>}
              {meta.result_status && <span className={`ab-result-chip ab-result-chip-${meta.result_status}`}>{RESULT_LABELS[meta.result_status] || meta.result_status}</span>}
              {meta.qualification && <span className={`ab-result-chip ab-qual-${meta.qualification}`}>{QUALIFICATION_LABELS[meta.qualification] || meta.qualification}</span>}
              <span className={`ab-method ab-method-${r.evaluation_method}`}>{METHOD_LABELS[r.evaluation_method] || r.evaluation_method}</span>
            </summary>
            {r.feedback && <p>{r.feedback}</p>}
            {r.review_notes && <p className="ab-muted">{r.review_notes}</p>}
            <p className="ab-muted">
              {meta.compile_status === 'compile_error' ? 'Compilation failed' : meta.compile_status === 'compiled' ? 'Compiled and ran' : ''}
              {meta.max_time != null && ` · slowest test ${meta.max_time}s`}
              {meta.max_memory_kb != null && ` · peak memory ${Math.round(meta.max_memory_kb / 1024)} MB`}
            </p>
            {(meta.qualification_checks || []).length > 0 && (
              <ul className="ab-criteria">
                {meta.qualification_checks.map(c => <li key={c.rule} className={c.met ? 'ok' : 'bad'}><i className={`fas fa-${c.met ? 'check' : 'times'}`} aria-hidden="true" /> {c.label}</li>)}
              </ul>
            )}
            {r.answer ? <pre className="ab-code-preview">{r.answer}</pre> : <p className="ab-muted">No answer submitted.</p>}
            {(meta.tests || []).length > 0 && (
              <ul className="ab-test-outcomes">
                {meta.tests.map((t, i) => (
                  <li key={t.id || i} className={t.passed ? 'ok' : 'bad'}>
                    Test {i + 1}{t.hidden ? ' (hidden)' : ''}: {t.passed ? 'passed' : t.status.replace(/_/g, ' ')}
                    {t.error && <pre className="ab-code-preview">{t.error}</pre>}
                  </li>
                ))}
              </ul>
            )}
            {history.length > 0 && (
              <details className="ab-attempts">
                <summary>Attempt history ({history.length})</summary>
                <ol>
                  {history.map((a, i) => (
                    <li key={i}>
                      <span>{a.kind === 'submit' ? 'Final submission' : 'Sample run'}</span>
                      <span>{a.language}</span>
                      <span>{a.passed ?? 0}/{a.total ?? 0} tests</span>
                      {a.marks != null && <span>{a.marks}/{a.max_marks} marks</span>}
                      <span className="ab-muted">{a.created_at ? new Date(a.created_at).toLocaleString() : ''}</span>
                      {a.code && <details><summary>Code</summary><pre className="ab-code-preview">{a.code}</pre></details>}
                    </li>
                  ))}
                </ol>
              </details>
            )}
          </details>
        );
      })}
    </div>
  );
}

// Validate → Approve → Send: what still blocks publishing, and the approval state.
function PublishChecklist({ check, busy, onValidate, onApprove }) {
  return (
    <section className="white-card ab-publish" aria-labelledby="ab-publish-title">
      <div className="ab-publish-head">
        <h2 id="ab-publish-title"><i className="fas fa-clipboard-check" aria-hidden="true" /> Review &amp; approve</h2>
        <div className="ab-publish-actions">
          <button type="button" className="btn btn-secondary" onClick={onValidate} disabled={busy}>Validate</button>
          <button type="button" className="btn btn-primary" onClick={onApprove} disabled={busy || !check?.ready || check?.approval?.current}>
            {check?.approval?.current ? 'Approved' : 'Approve for sending'}
          </button>
        </div>
      </div>
      {!check && <p className="ab-muted">Validate the assessment before approving it. Sending requires a current approval.</p>}
      {check && check.ready && (
        <p className={check.approval?.current ? 'ab-success-text' : 'ab-muted'}>
          {check.approval?.current
            ? `Approved${check.approval.by ? ` by ${check.approval.by}` : ''}. Any change to questions, tests or scoring needs a new approval.`
            : `All ${check.mcq_questions} MCQs and ${check.coding_questions} coding questions are valid. Approve to enable sending.`}
        </p>
      )}
      {check && !check.ready && (
        <div className="ab-error" role="alert">
          <strong>Fix these before the assessment can be approved:</strong>
          <ul>
            {check.problems.map(p => <li key={p}>{p}</li>)}
            {check.questions.map(q => <li key={q.question_id}><a href={`#ab-q-${q.question_id}`}>Q{q.number}</a> ({q.question_type}): {q.problems.join(' ')}</li>)}
          </ul>
        </div>
      )}
    </section>
  );
}

const isChoice = type => type === 'mcq' || type === 'true_false';

// What the candidate actually submitted for one question, with its grading when scored.
export function CandidateAnswer({ question, answer, result }) {
  const text = String(answer?.answer ?? '').trim();
  const choice = isChoice(question.question_type);
  // Terminated attempts are not scored, so choice answers are checked against the key here.
  const correct = result ? Boolean(result.is_correct)
    : choice && text && question.correct_answer ? text === String(question.correct_answer).trim() : null;
  const verdict = !text ? { label: 'Not answered', tone: 'muted' }
    : correct === true ? { label: 'Correct', tone: 'ok' }
      : correct === false ? { label: 'Incorrect', tone: 'bad' }
        : { label: 'Not graded', tone: 'muted' };
  return (
    <div className={`ab-candidate-answer ab-answer-${verdict.tone}`}>
      <div className="ab-candidate-answer-head">
        <strong><i className="fas fa-user-edit" aria-hidden="true" /> Candidate's answer</strong>
        <span className={`ab-answer-verdict ab-answer-verdict-${verdict.tone}`}>{verdict.label}</span>
        {result && <span className="ab-points">{result.points_earned}/{result.points_possible} pts</span>}
        {answer?.language && <span className="ab-skill">{answer.language}</span>}
      </div>
      {!text ? <p className="ab-muted">The candidate did not answer this question.</p>
        : choice ? <p className="ab-answer-choice">{text}</p>
          : question.question_type === 'short_answer' ? <p className="ab-answer-text">{text}</p>
            : <pre className="ab-code-preview">{answer.answer}</pre>}
      {choice && correct === false && question.correct_answer && <p className="ab-muted">Correct answer: {question.correct_answer}</p>}
    </div>
  );
}

function typeBadgeClass(type) {
  if (type === 'coding') return 'ab-badge-coding';
  if (type === 'sql') return 'ab-badge-sql';
  return 'ab-badge-mcq';
}

function AssessmentBuilder() {
  const { jdId, assessmentId } = useParams();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [assessment, setAssessment] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [draft, setDraft] = useState({ title: '', passing_score: 70, time_limit_minutes: 90, scoring_policy: { ...DEFAULT_POLICY } });
  const [editingId, setEditingId] = useState(null);
  const [editForm, setEditForm] = useState(null);
  const [addType, setAddType] = useState(null);
  const [addForm, setAddForm] = useState({ ...EMPTY_QUESTION });
  const [previewOpen, setPreviewOpen] = useState(false);
  const [previewData, setPreviewData] = useState(null);
  const [sendOpen, setSendOpen] = useState(false);
  const [sendForm, setSendForm] = useState({ to_email: '', from_email: '', subject: '', body: '', assessment_link: '' });
  const [lastSent, setLastSent] = useState(null);
  const [busy, setBusy] = useState(false);
  const [generatingEmail, setGeneratingEmail] = useState(false);
  const [assessmentResult, setAssessmentResult] = useState(null);
  const [candidateAnswers, setCandidateAnswers] = useState({});
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [pdfProgress, setPdfProgress] = useState('');
  const [codingConfig, setCodingConfig] = useState(null);
  const [formError, setFormError] = useState('');
  const [publishCheck, setPublishCheck] = useState(null);
  const [attempts, setAttempts] = useState([]);

  const isDraft = assessment?.status === 'DRAFT';
  const canEditQuestions = QUESTION_EDIT_STATES.includes(assessment?.status);
  const isReviewable = ['PASSED', 'FAILED', 'COMPLETED'].includes(assessment?.status);
  // Answers exist once the candidate starts, including attempts that were terminated.
  const showAnswers = ['IN_PROGRESS', 'COMPLETED', 'PASSED', 'FAILED', 'TERMINATED'].includes(assessment?.status);
  const resultByQuestion = new Map((assessmentResult?.question_results || []).map(r => [r.question_id, r]));
  const answeredCount = Object.values(candidateAnswers).filter(a => String(a?.answer ?? '').trim()).length;
  const sortedQuestions = [...questions].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.id - b.id);
  const typeCounts = sortedQuestions.reduce((acc, q) => ({ ...acc, [q.question_type]: (acc[q.question_type] || 0) + 1 }), {});

  const loadAssessment = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const data = await apiGet(`/api/assessment/${assessmentId}`);
      setAssessment(data.assessment || null);
      setQuestions(data.questions || []);
      setCandidateAnswers(Object.fromEntries((data.answers || []).map(row => [row.question_id, row])));
      setDraft({
        title: data.assessment?.title || '',
        passing_score: data.assessment?.passing_score ?? 70,
        time_limit_minutes: data.assessment?.time_limit_minutes ?? 90,
        scoring_policy: { ...DEFAULT_POLICY, ...(data.assessment?.scoring_policy || {}) },
      });
      setPublishCheck(null);
      if (['IN_PROGRESS', 'COMPLETED', 'PASSED', 'FAILED', 'TERMINATED'].includes(data.assessment?.status)) {
        apiGet(`/api/assessment/${assessmentId}/code-attempts`).then(res => setAttempts(res.attempts || [])).catch(() => setAttempts([]));
      }
      const status = data.assessment?.status;
      if (['PASSED', 'FAILED', 'COMPLETED'].includes(status)) {
        try {
          const resultData = await apiGet(`/api/assessment/result/${assessmentId}`);
          setAssessmentResult(resultData.result || null);
        } catch {
          setAssessmentResult(null);
        }
      } else {
        setAssessmentResult(null);
      }
    } catch (err) {
      setError(err.message || 'Could not load assessment.');
    } finally {
      setLoading(false);
    }
  }, [assessmentId]);

  useEffect(() => { loadAssessment(); }, [loadAssessment]);

  // Refresh just the question list (after a coding question is saved or removed) without a full reload.
  const refreshQuestions = useCallback(async (saved) => {
    try {
      const data = await apiGet(`/api/assessment/${assessmentId}`);
      const list = data.questions || [];
      setQuestions(list);
      if (saved?.id) {
        const ordered = [...list].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0) || a.id - b.id);
        const number = ordered.findIndex(q => q.id === saved.id) + 1;
        if (number) setNotice(`Coding question saved as Q${number}.`);
      }
    } catch (err) {
      setError(err.message || 'Could not refresh questions.');
    }
  }, [assessmentId]);

  useEffect(() => {
    if (!notice) return undefined;
    const t = window.setTimeout(() => setNotice(''), 3500);
    return () => window.clearTimeout(t);
  }, [notice]);

  const showNotice = (msg) => setNotice(msg);

  const handleDownloadPdf = async () => {
    setDownloadingPdf(true);
    setPdfProgress('Preparing PDF...');
    setError('');
    try {
      await downloadAssessmentPdf(assessmentId, setPdfProgress);
      showNotice('Test details PDF downloaded.');
    } catch (err) {
      setError(`Could not download the complete test PDF. ${err.message || 'Please retry.'}`);
    } finally {
      setDownloadingPdf(false);
      setPdfProgress('');
    }
  };

  const handleRegrade = async () => {
    if (!window.confirm('Re-grade this assessment with the current automatic grading? The candidate answers are not changed; the score and pass/fail status may change.')) return;
    setBusy(true);
    setError('');
    try {
      const { ok, data } = await apiPost(`/api/assessment/${assessmentId}/regrade`, {});
      if (!ok) throw new Error(data.error || 'Could not re-grade assessment.');
      await loadAssessment();
      showNotice(`Re-graded: ${data.result?.status || data.status} (${data.percentage ?? data.result?.score_percentage}%).`);
    } catch (err) {
      setError(err.message || 'Could not re-grade assessment.');
    } finally {
      setBusy(false);
    }
  };

  const handleRegenerate = async () => {
    if (!window.confirm('Replace the JD-based questions with a fresh set of 34 (30 MCQs, 2 moderate coding and 2 moderate SQL)? '
      + 'Questions from the Coding Questions panel and the client instructions are kept; questions you added manually are replaced.')) return;
    setBusy(true);
    setError('');
    try {
      const { ok, data } = await apiPost('/api/assessment/generate', {
        candidate_id: assessment.candidate_id, jd_id: assessment.jd_id,
        passing_score: draft.passing_score, time_limit_minutes: draft.time_limit_minutes,
      });
      if (!ok) throw new Error(data.error || 'Generation failed.');
      navigate(`/hiring-pipeline/assessment/${data.assessment.id}`);
      showNotice('JD-based assessment generated.');
    } catch (err) {
      setError(err.message || 'Could not regenerate assessment.');
    } finally {
      setBusy(false);
    }
  };

  const handleSaveDraft = async () => {
    setBusy(true);
    setError('');
    try {
      const { ok, data } = await apiPut(`/api/assessment/${assessmentId}`, draft);
      if (!ok) throw new Error(data.error || 'Save failed.');
      setAssessment(data.assessment || assessment);
      showNotice('Draft saved.');
    } catch (err) {
      setError(err.message || 'Could not save draft.');
    } finally {
      setBusy(false);
    }
  };

  const startEdit = (q) => {
    setEditingId(q.id);
    setEditForm({
      question_text: q.question_text || '',
      question_type: q.question_type || 'mcq',
      options: [...(q.options?.length ? q.options : ['', '', '', ''])],
      correct_answer: q.correct_answer || '',
      starter_code: q.starter_code || '',
      explanation: q.explanation || '',
      points: q.points ?? 10,
      skill_tag: q.skill_tag || '',
    });
    setFormError('');
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditForm(null);
    setFormError('');
  };

  const handleUpdateQuestion = async () => {
    if (!editForm) return;
    const problem = mcqProblem(editForm);
    if (problem) { setFormError(problem); return; }
    setBusy(true);
    try {
      const { ok, data } = await apiPut(`/api/assessment/question/${editingId}`, editForm);
      if (!ok) throw new Error(data.error || 'Update failed.');
      setQuestions(prev => prev.map(q => (q.id === editingId ? data.question : q)));
      cancelEdit();
      showNotice('Question updated.');
    } catch (err) {
      setError(err.message || 'Could not update question.');
    } finally {
      setBusy(false);
    }
  };

  const handleDeleteQuestion = async (questionId) => {
    if (!window.confirm('Delete this question?')) return;
    setBusy(true);
    try {
      const { ok, data } = await apiDelete(`/api/assessment/question/${questionId}`);
      if (!ok) throw new Error(data.error || 'Delete failed.');
      setQuestions(prev => prev.filter(q => q.id !== questionId));
      if (editingId === questionId) cancelEdit();
      showNotice('Question deleted.');
    } catch (err) {
      setError(err.message || 'Could not delete question.');
    } finally {
      setBusy(false);
    }
  };

  const openAddForm = (type) => {
    setAddType(type);
    setAddForm({
      ...EMPTY_QUESTION,
      question_type: type,
      options: type === 'mcq' ? ['', '', '', ''] : [],
      starter_code: type === 'coding' ? 'def solution():\n    pass\n' : '',
      points: type === 'coding' ? 20 : type === 'sql' ? 15 : 10,
    });
    setFormError('');
  };

  const handleAddQuestion = async () => {
    const problem = mcqProblem(addForm);
    if (problem) { setFormError(problem); return; }
    setBusy(true);
    try {
      // The server appends the question after the existing ones.
      const payload = {
        assessment_id: Number(assessmentId),
        ...addForm,
        options: addForm.question_type === 'mcq' ? addForm.options : addForm.options.filter(o => String(o).trim()),
      };
      const { ok, data } = await apiPost('/api/assessment/question', payload);
      if (!ok) throw new Error(data.error || 'Could not add question.');
      setQuestions(prev => [...prev, data.question]);
      setAddType(null);
      showNotice('Question added.');
    } catch (err) {
      setError(err.message || 'Could not add question.');
    } finally {
      setBusy(false);
    }
  };

  const handlePreview = async () => {
    setBusy(true);
    try {
      const data = await apiGet(`/api/assessment/${assessmentId}/preview`);
      setPreviewData(data);
      setPreviewOpen(true);
    } catch (err) {
      setError(err.message || 'Could not load preview.');
    } finally {
      setBusy(false);
    }
  };

  const loadEmailForSend = async (toEmail = '') => {
    setGeneratingEmail(true);
    setError('');
    try {
      const { ok, data } = await apiPost(`/api/assessment/${assessmentId}/generate-email`, {
        to_email: toEmail || assessment?.candidate_email || '',
      });
      if (!ok) throw new Error(data.error || 'Could not generate email.');
      setSendForm({
        to_email: data.to_email || toEmail || assessment?.candidate_email || '',
        from_email: data.from_email || '',
        subject: data.subject || '',
        body: data.body || '',
        assessment_link: data.candidate_test_link || data.assessment_link || '',
      });
    } catch (err) {
      setError(err.message || 'Could not generate email.');
    } finally {
      setGeneratingEmail(false);
    }
  };

  const handleValidate = async () => {
    setBusy(true);
    setError('');
    try {
      const data = await apiGet(`/api/assessment/${assessmentId}/publish-check`);
      setPublishCheck(data);
      return data;
    } catch (err) {
      setError(err.message || 'Could not validate the assessment.');
      return null;
    } finally {
      setBusy(false);
    }
  };

  const handleApprove = async () => {
    setBusy(true);
    setError('');
    try {
      const { ok, data } = await apiPost(`/api/assessment/${assessmentId}/approve`, {});
      if (!ok) throw new Error(data.error || 'Could not approve the assessment.');
      setPublishCheck(data);
      showNotice('Assessment approved. You can now send it.');
    } catch (err) {
      setError(err.message || 'Could not approve the assessment.');
      handleValidate();
    } finally {
      setBusy(false);
    }
  };

  const handleReturnToDraft = async () => {
    if (!window.confirm('Return this assessment to draft to edit it? The candidate link stops working until you approve and send it again (as a new version).')) return;
    setBusy(true);
    setError('');
    try {
      const { ok, data } = await apiPost(`/api/assessment/${assessmentId}/return-to-draft`, {});
      if (!ok) throw new Error(data.error || 'Could not return the assessment to draft.');
      await loadAssessment();
      showNotice('Assessment returned to draft.');
    } catch (err) {
      setError(err.message || 'Could not return the assessment to draft.');
    } finally {
      setBusy(false);
    }
  };

  const openSendModal = async () => {
    const check = await handleValidate();
    if (!check) return;
    if (!check.ready || !check.approval?.current) {
      setError(check.ready ? 'Approve the assessment before sending it.' : 'Fix the problems listed under Review & approve before sending.');
      document.getElementById('ab-publish-title')?.scrollIntoView?.({ behavior: 'smooth', block: 'center' });
      return;
    }
    const unsaved = (codingConfig?.specs || []).filter(spec => !spec.question || spec.draft).length;
    if (unsaved && !window.confirm(`${unsaved} coding question ${unsaved === 1 ? 'entry has' : 'entries have'} an unsaved or ungenerated question that will not be in the assessment. Send anyway?`)) return;
    setSendForm({
      to_email: assessment?.candidate_email || '',
      from_email: '',
      subject: '',
      body: '',
      assessment_link: '',
    });
    setSendOpen(true);
    await loadEmailForSend(assessment?.candidate_email || '');
  };

  const handleRegenerateEmail = async () => {
    await loadEmailForSend(sendForm.to_email);
  };

  const handleSend = async () => {
    setBusy(true);
    setError('');
    try {
      const { ok, data } = await apiPost(`/api/assessment/${assessmentId}/send`, {
        to_email: sendForm.to_email,
        regenerate_email: true,
      });
      if (!ok) throw new Error(data.error || 'Send failed.');
      setSendOpen(false);
      const toEmail = data.email?.to_email || sendForm.to_email;
      const link = data.assessment_link || '';
      setAssessment(prev => ({ ...prev, status: 'SENT', candidate_email: toEmail }));
      setLastSent({ toEmail, link });
      showNotice(
        link
          ? `Assessment email sent to ${toEmail}. Check inbox and spam folder.`
          : `Assessment email sent to ${toEmail}.`,
      );
    } catch (err) {
      setError(err.message || 'Could not send assessment.');
    } finally {
      setBusy(false);
    }
  };

  const copySendLink = async () => {
    if (!sendForm.assessment_link) return;
    try {
      await navigator.clipboard.writeText(sendForm.assessment_link);
      showNotice('Assessment link copied.');
    } catch {
      showNotice('Could not copy link — select and copy it manually.');
    }
  };

  const copyAssessmentLink = async () => {
    if (!lastSent?.link) return;
    try {
      await navigator.clipboard.writeText(lastSent.link);
      showNotice(`Link copied. Email was sent to ${lastSent.toEmail}.`);
    } catch {
      showNotice('Could not copy link — select and copy it manually.');
    }
  };

  // Exactly four options; the radio marks the one correct answer and follows its text when edited.
  const renderOptionEditor = (form, setForm) => (
    <fieldset className="ab-options-editor">
      <legend className="ab-label">Options (select the one correct answer)</legend>
      {[0, 1, 2, 3].map(idx => {
        const opt = form.options?.[idx] ?? '';
        const letter = String.fromCharCode(65 + idx);
        const isCorrect = Boolean(String(opt).trim()) && opt === form.correct_answer;
        return (
          <div key={idx} className={`ab-option-row${isCorrect ? ' ab-option-correct' : ''}`}>
            <input
              type="radio"
              name={`ab-correct-${editingId ?? 'new'}`}
              checked={isCorrect}
              disabled={!String(opt).trim()}
              onChange={() => setForm({ ...form, correct_answer: opt })}
              aria-label={`Option ${letter} is correct`}
            />
            <span className="ab-option-letter">{letter}</span>
            <input
              type="text"
              value={opt}
              onChange={e => {
                const next = [0, 1, 2, 3].map(i => form.options?.[i] ?? '');
                next[idx] = e.target.value;
                setForm({ ...form, options: next, correct_answer: isCorrect ? e.target.value : form.correct_answer });
              }}
              placeholder={`Option ${letter}`}
              aria-label={`Option ${letter}`}
            />
          </div>
        );
      })}
    </fieldset>
  );

  const renderQuestionForm = (form, setForm, onSave, onCancel) => (
    <div className="ab-edit-form">
      <label className="ab-label">Question</label>
      <textarea
        rows={4}
        value={form.question_text}
        onChange={e => setForm({ ...form, question_text: e.target.value })}
      />
      <div className="ab-form-row">
        <div>
          <label className="ab-label">Points</label>
          <input
            type="number"
            min={1}
            max={100}
            value={form.points}
            onChange={e => setForm({ ...form, points: Number(e.target.value) })}
          />
        </div>
        <div>
          <label className="ab-label">Skill tag</label>
          <input
            type="text"
            value={form.skill_tag}
            onChange={e => setForm({ ...form, skill_tag: e.target.value })}
          />
        </div>
      </div>
      {form.question_type === 'mcq' && renderOptionEditor(form, setForm)}
      <label className="ab-label">Explanation{form.question_type === 'mcq' ? ' (why the correct answer is right)' : ''}</label>
      <textarea
        rows={3}
        value={form.explanation || ''}
        onChange={e => setForm({ ...form, explanation: e.target.value })}
      />
      {form.question_type === 'coding' && (
        <>
          <label className="ab-label">Starter code</label>
          <textarea
            className="ab-code"
            rows={8}
            value={form.starter_code}
            onChange={e => setForm({ ...form, starter_code: e.target.value })}
          />
          <label className="ab-label">Sample solution / rubric</label>
          <textarea
            className="ab-code"
            rows={4}
            value={form.correct_answer}
            onChange={e => setForm({ ...form, correct_answer: e.target.value })}
          />
        </>
      )}
      {form.question_type === 'sql' && (
        <>
          <label className="ab-label">Expected SQL answer</label>
          <textarea
            className="ab-code"
            rows={5}
            value={form.correct_answer}
            onChange={e => setForm({ ...form, correct_answer: e.target.value })}
          />
        </>
      )}
      {formError && <div className="ab-error" role="alert">{formError}</div>}
      <div className="ab-form-actions">
        <button type="button" className="btn btn-secondary" onClick={onCancel}>Cancel</button>
        <button type="button" className="btn btn-primary" disabled={busy} onClick={onSave}>Save</button>
      </div>
    </div>
  );

  const policy = draft.scoring_policy || DEFAULT_POLICY;
  const setPolicy = patch => setDraft({ ...draft, scoring_policy: { ...policy, ...patch } });
  const renderScoringPolicy = () => (
    <fieldset className="ab-policy" disabled={!isDraft}>
      <legend>Scoring &amp; qualification</legend>
      <label className="ab-checkbox">
        <input type="checkbox" checked={Boolean(policy.section_weights)}
          onChange={e => setPolicy({ section_weights: e.target.checked ? { mcq: 40, coding: 60 } : null })} />
        Weight sections (otherwise the overall score is points earned ÷ points possible)
      </label>
      {policy.section_weights && (
        <div className="ab-settings-grid">
          <div>
            <label className="ab-label" htmlFor="ab-weight-mcq">MCQ weight (%)</label>
            <input id="ab-weight-mcq" type="number" min={0} max={100} value={policy.section_weights.mcq}
              onChange={e => { const mcq = Number(e.target.value); setPolicy({ section_weights: { mcq, coding: Math.max(0, 100 - mcq) } }); }} />
          </div>
          <div>
            <label className="ab-label" htmlFor="ab-weight-coding">Coding &amp; SQL weight (%)</label>
            <input id="ab-weight-coding" type="number" min={0} max={100} value={policy.section_weights.coding}
              onChange={e => { const coding = Number(e.target.value); setPolicy({ section_weights: { coding, mcq: Math.max(0, 100 - coding) } }); }} />
          </div>
        </div>
      )}
      <div className="ab-settings-grid">
        <div>
          <label className="ab-label" htmlFor="ab-min-mcq">Minimum MCQ score (%)</label>
          <input id="ab-min-mcq" type="number" min={0} max={100} value={policy.min_mcq_score}
            onChange={e => setPolicy({ min_mcq_score: Number(e.target.value) })} />
        </div>
        <div>
          <label className="ab-label" htmlFor="ab-min-coding">Minimum coding score (%)</label>
          <input id="ab-min-coding" type="number" min={0} max={100} value={policy.min_coding_score}
            onChange={e => setPolicy({ min_coding_score: Number(e.target.value) })} />
        </div>
      </div>
      <label className="ab-checkbox">
        <input type="checkbox" checked={Boolean(policy.coding_section_mandatory)}
          onChange={e => setPolicy({ coding_section_mandatory: e.target.checked })} />
        Coding qualification is independent of MCQs: the coding requirements must be met whatever the MCQ score
      </label>
      <label className="ab-checkbox">
        <input type="checkbox" checked={Boolean(policy.require_coding_qualification)} disabled={!policy.coding_section_mandatory}
          onChange={e => setPolicy({ require_coding_qualification: e.target.checked })} />
        Every coding question must meet its own qualification criteria (set in each question's Coding Configuration)
      </label>
    </fieldset>
  );

  if (loading) {
    return <Layout><div className="ab-loading">Loading assessment builder…</div></Layout>;
  }

  return (
    <Layout>
      <div className="ab-container">
        {notice && (
          <div className="ab-notice">
            <i className="fas fa-check-circle" /> {notice}
            {lastSent?.link && (
              <div className="ab-sent-link-row">
                <input type="text" readOnly value={lastSent.link} className="ab-sent-link-input" />
                <button type="button" className="btn btn-secondary btn-sm" onClick={copyAssessmentLink}>
                  Copy link
                </button>
              </div>
            )}
          </div>
        )}
        {error && <div className="ab-error">{error}</div>}

        <div className="ab-topbar">
          <div>
            <Link to={jdId ? `/jobs/${jdId}` : '/hiring-pipeline'} className="ab-back">
              <i className="fas fa-arrow-left" /> {jdId ? 'Back to Job' : 'Back to Hiring Pipeline'}
            </Link>
            <h1><i className="fas fa-tasks" /> Assessment Builder</h1>
            <p className="ab-subtitle">
              {assessment?.candidate_name} · {assessment?.job_role}
              <span className={`ab-status ab-status-${(assessment?.status || '').toLowerCase()}`}>
                {assessment?.status}
              </span>
            </p>
          </div>
          <div className="ab-topbar-actions">
            {showAnswers && (
              <button type="button" className="btn btn-secondary" onClick={handleDownloadPdf} disabled={downloadingPdf || busy}>
                <i className="fas fa-file-pdf" aria-hidden="true" /> {downloadingPdf ? pdfProgress : 'Download test PDF'}
              </button>
            )}
            <button type="button" className="btn btn-secondary" onClick={handlePreview} disabled={busy}>
              <i className="fas fa-eye" /> Preview
            </button>
            {assessment?.status === 'SENT' && !assessment?.started_at && (
              <button type="button" className="btn btn-secondary" onClick={handleReturnToDraft} disabled={busy}
                title="The candidate has not started: re-open the assessment to edit its questions">
                <i className="fas fa-edit" /> Edit questions (return to draft)
              </button>
            )}
            {isDraft && (
              <>
                <button type="button" className="btn btn-secondary" onClick={handleRegenerate} disabled={busy}>
                  <i className="fas fa-magic" /> {busy ? "Generating..." : "Regenerate from JD"}
                </button>
                <button type="button" className="btn btn-secondary" onClick={handleSaveDraft} disabled={busy}>
                  <i className="fas fa-save" /> Save Draft
                </button>
                <button type="button" className="btn btn-success" onClick={openSendModal} disabled={busy || !questions.length}
                  title={publishCheck?.approval?.current ? undefined : 'Validate and approve the assessment first'}>
                  <i className="fas fa-paper-plane" /> Send Assessment
                </button>
              </>
            )}
          </div>
        </div>

        {assessment?.status === 'TERMINATED' && <div className="ab-error" role="status">
          <strong>Assessment terminated.</strong> {assessment.termination_reason || 'Two exam navigation or focus violations'}.
          {' '}This attempt is closed. Saved answers are retained and no passing score is awarded.
        </div>}

        {isReviewable && assessmentResult && (
          <div className={`ab-result-banner ab-result-${(assessmentResult.status || '').toLowerCase()}`}>
            <div className="ab-result-head">
              <h2><i className="fas fa-chart-line" /> Assessment Result</h2>
              <button type="button" className="btn btn-secondary" onClick={handleRegrade} disabled={busy}
                title="Score the saved answers again with the current coding/SQL graders">
                <i className="fas fa-rotate" /> Re-grade
              </button>
            </div>
            <p>
              <strong>Score:</strong> {assessmentResult.percentage ?? assessmentResult.score_percentage}%
              {' '}({assessmentResult.score ?? assessmentResult.earned_points}/{assessmentResult.total_points} points)
              {assessmentResult.assessment_version && <span className="ab-muted"> · assessment version {assessmentResult.assessment_version}</span>}
            </p>
            <p><strong>Status:</strong> {assessmentResult.needs_retry ? 'Pending re-grade (execution error)' : assessmentResult.status}</p>
            {assessmentResult.summary && <p>{assessmentResult.summary}</p>}
            <ScoreSummary result={assessmentResult} />
            <CodingResultBreakdown result={assessmentResult} questions={questions} attempts={attempts} />
          </div>
        )}

        {['IN_PROGRESS', 'COMPLETED', 'PASSED', 'FAILED', 'TERMINATED'].includes(assessment?.status) && (
          <ProctoringEvidence assessmentId={assessmentId} live={assessment?.status === 'IN_PROGRESS'} />
        )}

        <div className="ab-settings white-card">
          <h2>Assessment Settings</h2>
          <div className="ab-settings-grid">
            <div>
              <label className="ab-label">Title</label>
              <input
                type="text"
                value={draft.title}
                disabled={!isDraft}
                onChange={e => setDraft({ ...draft, title: e.target.value })}
              />
            </div>
            <div>
              <label className="ab-label">Passing score (%)</label>
              <input
                type="number"
                min={1}
                max={100}
                value={draft.passing_score}
                disabled={!isDraft}
                onChange={e => setDraft({ ...draft, passing_score: Number(e.target.value) })}
              />
            </div>
            <div>
              <label className="ab-label">Time limit (minutes)</label>
              <input
                type="number"
                min={5}
                max={480}
                value={draft.time_limit_minutes}
                disabled={!isDraft}
                onChange={e => setDraft({ ...draft, time_limit_minutes: Number(e.target.value) })}
              />
            </div>
          </div>
          {renderScoringPolicy()}
        </div>

        {isDraft && <PublishChecklist check={publishCheck} busy={busy} onValidate={handleValidate} onApprove={handleApprove} />}

        {canEditQuestions && (
          <div className="ab-add-bar">
            <span>Add question:</span>
            <button type="button" className="btn btn-primary ab-add-btn" onClick={() => openAddForm('mcq')}>
              <i className="fas fa-list" /> MCQ
            </button>
            <button type="button" className="btn btn-primary ab-add-btn" onClick={() => openAddForm('coding')}>
              <i className="fas fa-code" /> Coding
            </button>
            <button type="button" className="btn btn-primary ab-add-btn" onClick={() => openAddForm('sql')}>
              <i className="fas fa-database" /> SQL
            </button>
          </div>
        )}

        {addType && renderQuestionForm(addForm, setAddForm, handleAddQuestion, () => { setAddType(null); setFormError(''); })}

        <div className="ab-questions">
          <h2>Questions ({sortedQuestions.length})</h2>
          {sortedQuestions.length > 0 && (
            <p className="ab-type-summary">
              {Object.entries(TYPE_LABELS).filter(([type]) => typeCounts[type]).map(([type, label]) => `${typeCounts[type]} ${label}`).join(' · ')}
            </p>
          )}
          {showAnswers && <p className="ab-answer-summary">
            <i className="fas fa-user-edit" aria-hidden="true" /> Candidate answered <strong>{answeredCount} of {sortedQuestions.length}</strong> questions.
            {assessment?.status === 'IN_PROGRESS' && ' The test is still in progress; reload to see the latest answers.'}
            {assessment?.status === 'TERMINATED' && ' The test was terminated, so these are the answers saved up to that point and they were not scored.'}
          </p>}
          {sortedQuestions.length === 0 ? (
            <div className="ab-empty">No questions yet. Generate or add questions to begin.</div>
          ) : (
            sortedQuestions.map((q, index) => (
              <div key={q.id} id={`ab-q-${q.id}`} className="ab-question-card white-card">
                <div className="ab-question-header">
                  <span className="ab-q-num">Q{index + 1}</span>
                  <span className={`ab-badge ${typeBadgeClass(q.question_type)}`}>
                    {TYPE_LABELS[q.question_type] || q.question_type}
                  </span>
                  {q.skill_tag && <span className="ab-skill">{q.skill_tag}</span>}
                  {q.difficulty && <span className="ab-badge">{q.difficulty}</span>}
                  {q.source === 'custom_coding' && <span className="ab-badge ab-badge-custom" title={q.generation_prompt}>Custom prompt</span>}
                  {q.scenario_type && <span className="ab-skill">{q.scenario_type}</span>}
                  <span className="ab-points">{q.points} pts</span>
                  {q.time_limit_minutes && <span className="ab-skill"><i className="far fa-clock" aria-hidden="true" /> {q.time_limit_minutes} min</span>}
                  {canEditQuestions && (
                    <div className="ab-question-actions">
                      <button type="button" className="ab-icon-btn" onClick={() => startEdit(q)} title="Edit">
                        <i className="fas fa-edit" />
                      </button>
                      <button type="button" className="ab-icon-btn ab-danger" onClick={() => handleDeleteQuestion(q.id)} title="Delete">
                        <i className="fas fa-trash" />
                      </button>
                    </div>
                  )}
                </div>

                {editingId === q.id && editForm
                  ? renderQuestionForm(editForm, setEditForm, handleUpdateQuestion, cancelEdit)
                  : (
                    <>
                      <p className="ab-question-text">{q.question_text}</p>
                      {q.source === 'custom_coding' && q.generation_prompt && (
                        <p className="ab-custom-prompt"><strong>Recruiter prompt:</strong> {q.generation_prompt}</p>
                      )}
                      {q.source === 'custom_coding' && q.input_format && <p><strong>Input:</strong> {q.input_format}</p>}
                      {q.source === 'custom_coding' && q.output_format && <p><strong>Output:</strong> {q.output_format}</p>}
                      {q.constraints && <p><strong>Constraints:</strong> {q.constraints}</p>}
                      {q.explanation && <p><strong>Explanation:</strong> {q.explanation}</p>}
                      {q.jd_requirement && <p><strong>JD requirement:</strong> {q.jd_requirement}</p>}
                      {q.evaluation_focus?.length > 0 && <p><strong>Evaluation focus:</strong> {q.evaluation_focus.join(", ")}</p>}
                      {q.question_type === 'mcq' && (
                        <ul className="ab-option-list">
                          {(q.options || []).map(opt => (
                            <li key={opt} className={opt === q.correct_answer ? 'ab-correct' : ''}>
                              {opt}{opt === q.correct_answer ? ' ✓' : ''}
                            </li>
                          ))}
                        </ul>
                      )}
                      {q.question_type === 'coding' && q.starter_code && (
                        <pre className="ab-code-preview">{q.starter_code}</pre>
                      )}
                      {q.question_type === 'sql' && q.correct_answer && !(q.test_cases || []).length && (
                        <pre className="ab-code-preview">{q.correct_answer}</pre>
                      )}
                      {showAnswers && <CandidateAnswer question={q} answer={candidateAnswers[q.id]} result={resultByQuestion.get(q.id)} />}
                      {(q.question_type === 'coding' || q.question_type === 'sql') && (
                        <ReferenceSolutionPanel question={q}
                          onChange={patch => setQuestions(prev => prev.map(item => (item.id === q.id ? { ...item, ...patch } : item)))} />
                      )}
                    </>
                  )}
              </div>
            ))
          )}
        </div>

        {/* Below the last question card, so it stays reachable however many questions there are. */}
        {assessment && (
          // Keyed by status: the panel reloads its editable state when the assessment is sent or returned to draft.
          <CodingQuestionsPanel key={assessment.status} assessmentId={assessmentId} onQuestionsChanged={refreshQuestions} onConfigChange={setCodingConfig} />
        )}

        {previewOpen && previewData && (
          <div className="ab-modal-overlay" onClick={() => setPreviewOpen(false)}>
            <div className="ab-modal" onClick={e => e.stopPropagation()}>
              <div className="ab-modal-head">
                <h2><i className="fas fa-eye" /> Preview (Candidate View)</h2>
                <button type="button" className="ab-icon-btn" onClick={() => setPreviewOpen(false)}>
                  <i className="fas fa-times" />
                </button>
              </div>
              <p className="ab-preview-meta">{previewData.assessment?.title} · {previewData.assessment?.time_limit_minutes} min</p>
              {(previewData.questions || []).map((q, i) => (
                <div key={q.id} className="ab-preview-q">
                  <div className="ab-preview-q-head">
                    <span>Q{i + 1}</span>
                    <span className={`ab-badge ${typeBadgeClass(q.question_type)}`}>{TYPE_LABELS[q.question_type]}</span>
                  </div>
                  <p>{q.question_text}</p>
                  {q.question_type === 'mcq' && (
                    <ul>{(q.options || []).map(o => <li key={o}>{o}</li>)}</ul>
                  )}
                  {q.question_type === 'coding' && q.starter_code && (
                    <pre className="ab-code-preview">{q.starter_code}</pre>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {sendOpen && (
          <div className="ab-modal-overlay" onClick={() => !busy && !generatingEmail && setSendOpen(false)}>
            <div className="ab-modal ab-modal-send" onClick={e => e.stopPropagation()}>
              <div className="ab-modal-head">
                <h2><i className="fas fa-paper-plane" /> Send Assessment</h2>
                <button type="button" className="ab-icon-btn" onClick={() => setSendOpen(false)} disabled={busy || generatingEmail}>
                  <i className="fas fa-times" />
                </button>
              </div>
              <p>Only the <strong>candidate test link</strong> below is emailed — not the recruiter login/app URL.</p>
              <label className="ab-label">Recipient email</label>
              <input
                type="email"
                value={sendForm.to_email}
                onChange={e => setSendForm({ ...sendForm, to_email: e.target.value })}
                placeholder="candidate@example.com"
                required
                disabled={generatingEmail}
              />
              <label className="ab-label">From</label>
              <input
                type="text"
                value={sendForm.from_email || 'Configured sender email'}
                readOnly
                disabled={generatingEmail}
              />
              <label className="ab-label">Candidate test link (sent in email)</label>
              <div className="ab-sent-link-row">
                <input
                  type="text"
                  readOnly
                  value={sendForm.assessment_link}
                  className="ab-sent-link-input"
                  placeholder={generatingEmail ? 'Generating link…' : 'Assessment link'}
                />
                <button
                  type="button"
                  className="btn btn-secondary btn-sm"
                  onClick={copySendLink}
                  disabled={!sendForm.assessment_link || generatingEmail}
                >
                  Copy
                </button>
              </div>
              <label className="ab-label">Subject (auto-generated)</label>
              <input
                type="text"
                value={sendForm.subject}
                readOnly
                disabled={generatingEmail}
              />
              <label className="ab-label">Email preview (auto-generated)</label>
              <textarea
                rows={10}
                value={sendForm.body}
                readOnly
                placeholder={generatingEmail ? 'Generating email body…' : 'Email body'}
                disabled={generatingEmail}
              />
              <div className="ab-form-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setSendOpen(false)} disabled={busy || generatingEmail}>Cancel</button>
                <button type="button" className="btn btn-primary" onClick={handleRegenerateEmail} disabled={busy || generatingEmail}>
                  {generatingEmail ? <><i className="fas fa-spinner fa-spin" /> Generating…</> : <><i className="fas fa-magic" /> Regenerate Email</>}
                </button>
                <button type="button" className="btn btn-success" onClick={handleSend} disabled={busy || generatingEmail || !sendForm.assessment_link}>
                  {busy ? 'Sending…' : 'Send Now'}
                </button>
              </div>
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
}

export default AssessmentBuilder;
