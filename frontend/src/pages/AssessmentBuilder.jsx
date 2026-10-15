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
  points: 10,
  skill_tag: '',
};

const METHOD_LABELS = {
  executed: 'Executed in sandbox',
  sql_executed: 'Executed (SQLite)',
  ai_estimated: 'AI-estimated (not executed)',
  pending_ai: 'Not graded',
};

// Per-question coding / SQL grading from the stored assessment result.
function CodingResultBreakdown({ result, questions }) {
  const rows = (result?.question_results || []).filter(r => r.question_type === 'coding' || r.question_type === 'sql');
  if (!rows.length) return null;
  const position = new Map(questions.map((q, i) => [q.id, i + 1]));
  return (
    <div className="ab-coding-results">
      <h3>Coding &amp; SQL grading</h3>
      {rows.map(r => {
        const meta = r.metadata || {};
        return (
          <details key={r.question_id} className="ab-coding-result">
            <summary>
              <span>Q{position.get(r.question_id) || '?'} · {r.question_type === 'sql' ? 'SQL' : 'Coding'}{meta.language && r.question_type === 'coding' ? ` (${meta.language})` : ''}</span>
              <span>{r.points_earned}/{r.points_possible} pts</span>
              {meta.tests_total > 0 && <span>{meta.tests_passed}/{meta.tests_total} tests · hidden {meta.hidden_passed}/{meta.hidden_total}</span>}
              <span className={`ab-method ab-method-${r.evaluation_method}`}>{METHOD_LABELS[r.evaluation_method] || r.evaluation_method}</span>
            </summary>
            {r.feedback && <p>{r.feedback}</p>}
            {r.review_notes && <p className="ab-muted">{r.review_notes}</p>}
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
          </details>
        );
      })}
    </div>
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
  const [draft, setDraft] = useState({ title: '', passing_score: 70, time_limit_minutes: 90 });
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

  const isDraft = assessment?.status === 'DRAFT';
  const isReviewable = ['PASSED', 'FAILED', 'COMPLETED'].includes(assessment?.status);
  // Answers exist once the candidate starts, including attempts that were terminated.
  const showAnswers = ['IN_PROGRESS', 'COMPLETED', 'PASSED', 'FAILED', 'TERMINATED'].includes(assessment?.status);
  const resultByQuestion = new Map((assessmentResult?.question_results || []).map(r => [r.question_id, r]));
  const answeredCount = Object.values(candidateAnswers).filter(a => String(a?.answer ?? '').trim()).length;
  const sortedQuestions = [...questions].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));

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
      });
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

  // Refresh just the question list (after a coding question is generated or removed) without a full reload.
  const refreshQuestions = useCallback(async () => {
    try {
      const data = await apiGet(`/api/assessment/${assessmentId}`);
      setQuestions(data.questions || []);
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
    if (!window.confirm('Replace the JD-based questions with a fresh set of 14 (10 MCQs, 2 moderate coding and 2 moderate SQL)? '
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
      points: q.points ?? 10,
      skill_tag: q.skill_tag || '',
    });
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditForm(null);
  };

  const handleUpdateQuestion = async () => {
    if (!editForm) return;
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
  };

  const handleAddQuestion = async () => {
    setBusy(true);
    try {
      const payload = {
        assessment_id: Number(assessmentId),
        ...addForm,
        options: addForm.options.filter(o => String(o).trim()),
        sort_order: questions.length,
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

  const openSendModal = async () => {
    const ungenerated = (codingConfig?.specs || []).filter(spec => spec.status !== 'generated').length;
    if (ungenerated && !window.confirm(`${ungenerated} coding question ${ungenerated === 1 ? 'entry has' : 'entries have'} no generated question and will not be in the assessment. Send anyway?`)) return;
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

  const renderOptionEditor = (form, setForm) => (
    <div className="ab-options-editor">
      <label className="ab-label">Options</label>
      {(form.options || []).map((opt, idx) => (
        <div key={idx} className="ab-option-row">
          <input
            type="text"
            value={opt}
            onChange={e => {
              const next = [...form.options];
              next[idx] = e.target.value;
              setForm({ ...form, options: next });
            }}
            placeholder={`Option ${idx + 1}`}
          />
          <button
            type="button"
            className="ab-icon-btn"
            onClick={() => setForm({ ...form, options: form.options.filter((_, i) => i !== idx) })}
            title="Remove option"
          >
            <i className="fas fa-times" />
          </button>
        </div>
      ))}
      <button
        type="button"
        className="ab-link-btn"
        onClick={() => setForm({ ...form, options: [...(form.options || []), ''] })}
      >
        + Add option
      </button>
      <label className="ab-label">Correct answer</label>
      <select
        value={form.correct_answer}
        onChange={e => setForm({ ...form, correct_answer: e.target.value })}
      >
        <option value="">Select correct option</option>
        {(form.options || []).filter(Boolean).map(opt => (
          <option key={opt} value={opt}>{opt}</option>
        ))}
      </select>
    </div>
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
      <div className="ab-form-actions">
        <button type="button" className="btn btn-secondary" onClick={onCancel}>Cancel</button>
        <button type="button" className="btn btn-primary" disabled={busy} onClick={onSave}>Save</button>
      </div>
    </div>
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
            {isDraft && (
              <>
                <button type="button" className="btn btn-secondary" onClick={handleRegenerate} disabled={busy}>
                  <i className="fas fa-magic" /> {busy ? "Generating..." : "Regenerate from JD"}
                </button>
                <button type="button" className="btn btn-secondary" onClick={handleSaveDraft} disabled={busy}>
                  <i className="fas fa-save" /> Save Draft
                </button>
                <button type="button" className="btn btn-success" onClick={openSendModal} disabled={busy || !questions.length}>
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
            </p>
            <p><strong>Status:</strong> {assessmentResult.status}</p>
            {assessmentResult.summary && <p>{assessmentResult.summary}</p>}
            <CodingResultBreakdown result={assessmentResult} questions={questions} />
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
        </div>

        {isDraft && (
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

        {addType && renderQuestionForm(addForm, setAddForm, handleAddQuestion, () => setAddType(null))}

        {isDraft && (
          <CodingQuestionsPanel assessmentId={assessmentId} onQuestionsChanged={refreshQuestions} onConfigChange={setCodingConfig} />
        )}

        <div className="ab-questions">
          <h2>Questions ({sortedQuestions.length})</h2>
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
                  {isDraft && (
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
