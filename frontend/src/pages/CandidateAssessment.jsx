import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { publicApiGet, publicApiPost } from '../api.js';
import useAssessmentProctoring from '../hooks/useAssessmentProctoring.js';
import useMediaProctoring, { FACE_LIMIT } from '../hooks/useMediaProctoring.js';
import ProctoringSetup from '../components/ProctoringSetup.jsx';
import { CameraPreview } from '../components/ProctoringMedia.jsx';
import { FACE_ISSUE_TEXT } from '../utils/faceCheck.js';
import '../styles/assessment_candidate.css';

const AUTOSAVE_DELAY_MS = 600;
const DEVICE_NAMES = { camera: 'camera', mic: 'microphone', screen: 'screen sharing' };

function formatTimer(totalSeconds) {
  const safe = Math.max(0, totalSeconds);
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const seconds = safe % 60;
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
  }
  return `${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

function questionLabel(type) {
  const map = {
    mcq: 'MCQ',
    true_false: 'True / False',
    coding: 'Coding',
    sql: 'SQL',
    short_answer: 'Short Answer',
  };
  return map[type] || 'Question';
}

function isChoiceQuestion(type) {
  return type === 'mcq' || type === 'true_false';
}

function isCodeQuestion(type) {
  return type === 'coding' || type === 'sql';
}

function ExamDialog({ title, children }) {
  const dialogRef = useRef(null);
  useEffect(() => { dialogRef.current?.querySelector('button')?.focus(); }, []);
  const trapFocus = event => {
    if (event.key !== 'Tab') return;
    const buttons = [...dialogRef.current.querySelectorAll('button:not(:disabled)')];
    const first = buttons[0];
    const last = buttons[buttons.length - 1];
    if (!first) { event.preventDefault(); return; }
    if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
    else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
  };
  return <div className="ca-dialog-overlay"><section className="ca-card ca-exam-dialog" role="alertdialog" aria-modal="true" aria-labelledby="ca-dialog-title" ref={dialogRef} onKeyDown={trapFocus}>
    <h2 id="ca-dialog-title">{title}</h2>{children}
  </section></div>;
}

function templateFor(question, language) {
  return (question?.language_options || []).find(option => option.key === language)?.template || '';
}

function ResultTable({ data }) {
  const columns = data?.columns || [];
  const rows = data?.rows || [];
  if (!columns.length && !rows.length) return <p className="ca-muted">No rows</p>;
  return (
    <div className="ca-table-wrap">
      <table className="ca-result-table">
        {columns.length > 0 && <thead><tr>{columns.map((c, i) => <th key={i}>{c}</th>)}</tr></thead>}
        <tbody>
          {rows.map((row, r) => <tr key={r}>{row.map((v, c) => <td key={c}>{v === null ? 'NULL' : String(v)}</td>)}</tr>)}
        </tbody>
      </table>
    </div>
  );
}

function SampleTests({ question }) {
  const samples = question.sample_tests || [];
  if (question.question_type === 'sql') {
    return (
      <div className="ca-samples">
        {question.sql_schema && (<><h3>Tables</h3><pre>{question.sql_schema}</pre></>)}
        {samples.map((sample, index) => (
          <div className="ca-sample" key={sample.id}>
            <h3>Example {index + 1}</h3>
            <span className="ca-sample-label">Data</span>
            <pre>{sample.setup_sql}</pre>
            <span className="ca-sample-label">Expected result</span>
            <ResultTable data={sample.expected} />
          </div>
        ))}
      </div>
    );
  }
  if (!samples.length && !question.input_format && !question.output_format && !question.constraints) return null;
  return (
    <div className="ca-samples">
      {question.input_format && <p><strong>Input:</strong> {question.input_format}</p>}
      {question.output_format && <p><strong>Output:</strong> {question.output_format}</p>}
      {question.constraints && <p><strong>Constraints:</strong> {question.constraints}</p>}
      {question.edge_cases && <p><strong>Edge cases to handle:</strong> {question.edge_cases}</p>}
      {(question.time_limit_seconds || question.memory_limit_mb) && (
        <p className="ca-muted">
          Limits per test: {question.time_limit_seconds || 2}s CPU time, {question.memory_limit_mb || 128} MB memory.
          {' '}Hidden tests are also used for scoring, so passing the examples alone does not guarantee full marks.
        </p>
      )}
      {samples.map((sample, index) => (
        <div className="ca-sample ca-sample-io" key={sample.id}>
          <h3>Example {index + 1}</h3>
          <div><span className="ca-sample-label">Input</span><pre>{sample.input}</pre></div>
          <div><span className="ca-sample-label">Expected output</span><pre>{sample.expected_output}</pre></div>
        </div>
      ))}
      <p className="ca-muted">Read from standard input and print to standard output. Java solutions must use <code>public class Main</code>.</p>
    </div>
  );
}

const RUN_STATUS = {
  failed: 'Wrong answer', compile_error: 'Compilation error', runtime_error: 'Runtime error',
  time_limit: 'Time limit exceeded', memory_limit: 'Memory limit exceeded', output_limit: 'Output limit exceeded',
};

function RunResults({ result, sql }) {
  if (result.error) return <div className="ca-run-results ca-run-error" role="alert">{result.error}</div>;
  const allPassed = result.total > 0 && result.passed === result.total;
  return (
    <div className="ca-run-results" role="status" aria-live="polite">
      <p className={`ca-run-summary ${allPassed ? 'ok' : 'bad'}`}>
        <i className={`fas ${allPassed ? 'fa-check-circle' : 'fa-times-circle'}`} aria-hidden="true" />
        {' '}Passed {result.passed} of {result.total} example test{result.total === 1 ? '' : 's'}
        {result.hidden_test_count > 0 && ` · ${result.hidden_test_count} hidden tests run on submit`}
      </p>
      {(result.tests || []).map((test, index) => (
        <details key={test.id} className={`ca-test ${test.passed ? 'ok' : 'bad'}`} open={!test.passed}>
          <summary>Example {index + 1}: {test.passed ? 'Passed' : RUN_STATUS[test.status] || test.status.replace(/_/g, ' ')}</summary>
          {test.error && <pre className="ca-test-error">{test.error}</pre>}
          {!sql && test.actual != null && (<><span className="ca-sample-label">Your output</span><pre>{test.actual || '(no output)'}</pre></>)}
          {!sql && !test.passed && test.expected != null && (<><span className="ca-sample-label">Expected output</span><pre>{test.expected}</pre></>)}
          {sql && test.actual && (<><span className="ca-sample-label">Your result</span><ResultTable data={test.actual} /></>)}
          {sql && !test.passed && test.expected && (<><span className="ca-sample-label">Expected result</span><ResultTable data={test.expected} /></>)}
        </details>
      ))}
    </div>
  );
}

function CandidateAssessment() {
  const { token } = useParams();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [assessment, setAssessment] = useState(null);
  const [questions, setQuestions] = useState([]);
  const [answers, setAnswers] = useState({});
  const [currentIndex, setCurrentIndex] = useState(0);
  const [remainingSeconds, setRemainingSeconds] = useState(null);
  const [saveState, setSaveState] = useState('idle');
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [submitMessage, setSubmitMessage] = useState('');
  const [editorExpanded, setEditorExpanded] = useState(false);
  const [confirmSubmit, setConfirmSubmit] = useState(false);
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [stage, setStage] = useState('terms');
  const [faceRecheck, setFaceRecheck] = useState('');
  const [languages, setLanguages] = useState({});
  const [runResults, setRunResults] = useState({});
  const [running, setRunning] = useState(false);
  const proctoring = useAssessmentProctoring(token, assessment);
  const media = useMediaProctoring(token, {
    active: proctoring.active,
    initialFaceCount: assessment?.face_violation_count || 0,
    onViolation: proctoring.report,
    onTerminated: proctoring.markTerminated,
  });
  const examPaused = Boolean(proctoring.warning || proctoring.error || media.faceWarning || media.lost.length);
  const terminated = proctoring.terminated || media.terminated;
  const editorGutterRef = useRef(null);
  const activeNavRef = useRef(null);

  const saveTimersRef = useRef({});
  const answersRef = useRef(answers);
  const languagesRef = useRef(languages);
  const submitRef = useRef(null);
  answersRef.current = answers;
  languagesRef.current = languages;

  // Non-coding questions come first so each tab holds a contiguous number range.
  const sortedQuestions = useMemo(
    () => [...questions].sort((a, b) =>
      Number(isCodeQuestion(a.question_type)) - Number(isCodeQuestion(b.question_type))
      || (a.sort_order ?? 0) - (b.sort_order ?? 0)),
    [questions],
  );

  const currentQuestion = sortedQuestions[currentIndex] || null;
  const totalQuestions = sortedQuestions.length;
  const languageOptions = currentQuestion?.language_options || [];
  const currentLanguage = currentQuestion
    ? languages[currentQuestion.id] || currentQuestion.default_language || languageOptions[0]?.key || ''
    : '';
  const editorValue = currentQuestion
    ? answers[currentQuestion.id] ?? (currentQuestion.starter_code || templateFor(currentQuestion, currentLanguage))
    : '';
  const editorLanguage = currentQuestion?.question_type === 'sql' ? 'SQL (SQLite)' : currentQuestion?.language || currentQuestion?.programming_language;
  const currentRun = currentQuestion ? runResults[currentQuestion.id] : null;
  const canGoBack = currentIndex > 0;
  const canGoForward = currentIndex < totalQuestions - 1;
  const activeSection = currentQuestion && isCodeQuestion(currentQuestion.question_type) ? 'coding' : 'general';
  const sections = useMemo(() => {
    const general = [];
    const coding = [];
    sortedQuestions.forEach((q, index) => (isCodeQuestion(q.question_type) ? coding : general).push({ q, index }));
    return [
      { key: 'general', label: 'Questions', items: general },
      { key: 'coding', label: 'Coding', items: coding },
    ].filter(section => section.items.length);
  }, [sortedQuestions]);
  const visibleItems = sections.find(section => section.key === activeSection)?.items || [];

  const answeredCount = useMemo(
    () => sortedQuestions.filter(q => String(answers[q.id] || '').trim()).length,
    [sortedQuestions, answers],
  );

  const progressPercent = totalQuestions ? (answeredCount / totalQuestions) * 100 : 0;

  useEffect(() => {
    setEditorExpanded(false);
    activeNavRef.current?.scrollIntoView?.({ block: 'nearest' });
  }, [currentIndex]);

  useEffect(() => () => {
    Object.values(saveTimersRef.current).forEach(timer => window.clearTimeout(timer));
  }, []);

  const loadAssessment = useCallback(async () => {
    setLoading(true);
    setTermsAccepted(false);
    setStage('terms');
    setError('');
    setRemainingSeconds(null);
    setSubmitted(false);
    setSubmitMessage('');
    setEditorExpanded(false);
    try {
      const data = await publicApiGet(`/api/assessment/token/${encodeURIComponent(token)}`);
      setAssessment(data.assessment || null);
      setQuestions(data.questions || []);
      const initial = {};
      const savedLanguages = {};
      (data.saved_answers || []).forEach(row => {
        if (row.question_id != null) {
          initial[row.question_id] = row.answer || '';
          if (row.language) savedLanguages[row.question_id] = row.language;
        }
      });
      setAnswers(initial);
      setLanguages(savedLanguages);
      setRunResults({});
      setCurrentIndex(0);
      setRemainingSeconds(null);
      if (typeof data.assessment?.remaining_seconds === 'number') {
        setRemainingSeconds(data.assessment.remaining_seconds);
      } else if (data.assessment?.time_limit_minutes) {
        setRemainingSeconds(data.assessment.time_limit_minutes * 60);
      }
    } catch (err) {
      setError(err.message || 'Could not load assessment.');
    } finally {
      setLoading(false);
    }
  }, [token]);

  useEffect(() => {
    loadAssessment();
  }, [loadAssessment]);

  useEffect(() => {
    if (remainingSeconds == null || submitted || !proctoring.active) return undefined;
    if (remainingSeconds <= 0) {
      if (!submitting && submitRef.current) {
        submitRef.current(true);
      }
      return undefined;
    }
    const timer = window.setInterval(() => {
      setRemainingSeconds(prev => (prev == null ? prev : Math.max(0, prev - 1)));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [remainingSeconds, submitted, submitting, proctoring.active]);

  const persistAnswer = useCallback(async (questionId, answer) => {
    setSaveState('saving');
    try {
      await publicApiPost('/api/assessment/save-answer', {
        token,
        question_id: questionId,
        answer,
        ...(languagesRef.current[questionId] ? { language: languagesRef.current[questionId] } : {}),
      });
      setSaveState('saved');
      window.setTimeout(() => setSaveState('idle'), 2000);
    } catch {
      setSaveState('error');
    }
  }, [token]);

  const scheduleAutosave = useCallback((questionId, answer) => {
    if (submitted || proctoring.terminated || !proctoring.active) return;
    if (saveTimersRef.current[questionId]) {
      window.clearTimeout(saveTimersRef.current[questionId]);
    }
    saveTimersRef.current[questionId] = window.setTimeout(() => {
      persistAnswer(questionId, answer);
    }, AUTOSAVE_DELAY_MS);
  }, [persistAnswer, submitted, proctoring.terminated, proctoring.active]);

  const handleAnswerChange = (questionId, value) => {
    if (examPaused || terminated || !proctoring.active) return;
    setAnswers(prev => ({ ...prev, [questionId]: value }));
    scheduleAutosave(questionId, value);
  };

  const flushPendingSaves = async () => {
    Object.values(saveTimersRef.current).forEach(t => window.clearTimeout(t));
    saveTimersRef.current = {};
    const pending = answersRef.current;
    await Promise.all(
      sortedQuestions.map(q =>
        publicApiPost('/api/assessment/save-answer', {
          token,
          question_id: q.id,
          answer: pending[q.id] || '',
          ...(languagesRef.current[q.id] ? { language: languagesRef.current[q.id] } : {}),
        }).catch(() => null),
      ),
    );
  };

  const handleSubmit = async (autoSubmit = false, confirmed = false) => {
    if (submitting || submitted || proctoring.terminated || !proctoring.active) return;
    if (!autoSubmit && !confirmed) { setConfirmSubmit(true); return; }
    setConfirmSubmit(false);
    setSubmitting(true);
    setError('');
    try {
      if (!await proctoring.sync()) throw new Error('Exam monitoring must sync before submission. Please retry.');
      await flushPendingSaves();
      const payload = {
        token,
        answers: sortedQuestions.map(q => ({
          question_id: q.id,
          answer: answersRef.current[q.id] || '',
          ...(q.question_type === 'coding' && (languagesRef.current[q.id] || q.default_language)
            ? { language: languagesRef.current[q.id] || q.default_language } : {}),
        })),
      };
      const result = await publicApiPost('/api/assessment/submit', payload);
      proctoring.stop();
      media.finish();
      setSubmitted(true);
      const status = result.result?.status || result.status || 'COMPLETED';
      setSubmitMessage(
        autoSubmit
          ? 'Time expired. Your assessment was submitted automatically.'
          : status === 'PASSED'
            ? 'Your assessment was submitted successfully. Thank you!'
            : status === 'FAILED'
              ? 'Your assessment was submitted. Our team will review your responses.'
              : 'Your assessment was submitted successfully. Thank you!',
      );
    } catch (err) {
      setError(err.message || 'Submission failed. Please try again.');
    } finally {
      setSubmitting(false);
    }
  };

  submitRef.current = handleSubmit;

  const finishMedia = media.finish;
  const examLocked = submitting || submitted || examPaused || terminated || !proctoring.active;

  const changeLanguage = (question, nextLanguage) => {
    if (examLocked) return;
    const previousTemplate = templateFor(question, languagesRef.current[question.id] || question.default_language);
    const code = answersRef.current[question.id];
    languagesRef.current = { ...languagesRef.current, [question.id]: nextLanguage };
    setLanguages(prev => ({ ...prev, [question.id]: nextLanguage }));
    setRunResults(prev => ({ ...prev, [question.id]: null }));
    if (code == null || code === previousTemplate) {
      // Untouched starter code follows the newly selected language.
      setAnswers(prev => {
        const next = { ...prev };
        delete next[question.id];
        return next;
      });
    } else {
      scheduleAutosave(question.id, code);
    }
  };

  const runCode = async () => {
    if (!currentQuestion || examLocked || running) return;
    const question = currentQuestion;
    setRunning(true);
    try {
      const result = await publicApiPost('/api/assessment/run-code', {
        token,
        question_id: question.id,
        code: editorValue,
        language: question.question_type === 'coding' ? currentLanguage : '',
      });
      setRunResults(prev => ({ ...prev, [question.id]: result }));
    } catch (err) {
      setRunResults(prev => ({ ...prev, [question.id]: { error: err.message || 'Could not run the code.' } }));
    } finally {
      setRunning(false);
    }
  };

  useEffect(() => {
    if (!terminated) return;
    Object.values(saveTimersRef.current).forEach(timer => window.clearTimeout(timer));
    saveTimersRef.current = {};
    setConfirmSubmit(false);
    finishMedia();
  }, [terminated, finishMedia]);

  useEffect(() => { setFaceRecheck(''); }, [media.faceWarning]);

  const recheckFace = async () => {
    setFaceRecheck('checking');
    setFaceRecheck(await media.recheckFace() ? '' : 'failed');
  };

  const uploadNotice = media.pending > 0 && <p className="ca-upload-note" role="status">
    <i className="fas fa-sync fa-spin" aria-hidden="true" /> Uploading your exam recording ({media.pending} part{media.pending === 1 ? '' : 's'} left). Keep this page open.
  </p>;

  if (loading) {
    return (
      <div className="ca-page" id="ca-root">
        <div className="ca-card ca-center">
          <div className="ca-spinner" aria-hidden="true" />
          <p>Loading your assessment…</p>
        </div>
      </div>
    );
  }

  if (error && !assessment && !proctoring.terminated) {
    return (
      <div className="ca-page" id="ca-root">
        <div className="ca-card ca-center ca-error-card">
          <i className="fas fa-exclamation-circle" />
          <h1>{error.toLowerCase().includes('terminated') ? 'Assessment Terminated' : 'Assessment Unavailable'}</h1>
          <p>{error}</p>
        </div>
      </div>
    );
  }

  if (submitted) {
    return (
      <div className="ca-page" id="ca-root">
        <div className="ca-card ca-center ca-success-card">
          <i className="fas fa-check-circle" />
          <h1>Assessment Submitted</h1>
          <p>{submitMessage}</p>
          {uploadNotice}
        </div>
      </div>
    );
  }

  if (terminated) {
    return <div className="ca-page" id="ca-root"><div className="ca-card ca-center ca-error-card">
      <i className="fas fa-exclamation-circle" aria-hidden="true" />
      <h1>Assessment Terminated</h1>
      <p>{media.terminated
        ? 'Your exam ended because your face was not detected on camera twice.'
        : 'Your exam ended after two navigation, focus or recording violations.'} This attempt cannot be resumed.</p>
      <p>Your previously saved answers are retained. Contact the recruiter if you need another attempt.</p>
      {proctoring.error && <div role="alert"><p>{proctoring.error}</p><button className="ca-btn ca-btn-primary" disabled={proctoring.syncing} onClick={proctoring.sync}>Retry sync</button></div>}
      {proctoring.syncing && <p role="status">Recording exam termination…</p>}
      {uploadNotice}
    </div></div>;
  }

  if (!proctoring.active && stage === 'setup') {
    return <ProctoringSetup media={media} proctoring={proctoring} resuming={Boolean(assessment?.started_at)}
      onBack={() => setStage('terms')}
      onStarted={started => { if (typeof started.remaining_seconds === 'number') setRemainingSeconds(started.remaining_seconds); }} />;
  }

  if (!proctoring.active) {
    return <div className="ca-page ca-welcome-page" id="ca-root"><section className="ca-exam-rules">
      <div className="ca-welcome-topbar">
        <img src="/ShimentoX-Logo-Dark.png" alt="ShimentoX" className="ca-welcome-logo" />
        <span className="ca-welcome-badge"><i className="fas fa-shield-alt" aria-hidden="true" /> Candidate assessment</span>
      </div>
      <header className="ca-welcome-heading">
        <span className="ca-welcome-eyebrow">LET’S GET YOU STARTED</span>
        <h1>Welcome{assessment?.candidate_name?.trim() ? `, ${assessment.candidate_name.trim()}` : ''}!</h1>
        <p>Take a moment to get comfortable and review the instructions.<br />When you’re ready, it’s your time to show what you can do.</p>
        <div className="ca-welcome-overview">
          <div className="ca-welcome-assessment"><span>Your assessment</span><strong>{assessment?.title || 'Your assessment'}</strong></div>
          <div><i className="far fa-clock" aria-hidden="true" /><strong>{assessment?.time_limit_minutes || (remainingSeconds != null ? Math.ceil(remainingSeconds / 60) : '—')}<small> min</small></strong><span>Time limit</span></div>
          <div><i className="far fa-file-alt" aria-hidden="true" /><strong>{totalQuestions}</strong><span>Questions</span></div>
          <div><i className="fas fa-video" aria-hidden="true" /><strong>Proctored</strong><span>Camera, mic &amp; screen</span></div>
        </div>
      </header>
      <div className="ca-welcome-columns">
      <section className="ca-instructions" aria-labelledby="ca-instructions-title">
      <span className="ca-section-eyebrow">01 · GET FAMILIAR</span>
      <h2 id="ca-instructions-title">A few things before you begin</h2>
      <p className="ca-section-intro">Follow these guidelines for a smooth assessment experience.</p>
      <ol className="ca-instruction-list">
        <li><span className="ca-instruction-icon"><i className="fas fa-user-check" aria-hidden="true" /></span><div><h3>Keep your face in view</h3><p>Your camera takes a photo at random about every 10 seconds. If your face is not visible or you look away from the screen, you get a warning. The second time, the exam ends automatically.</p></div></li>
        <li><span className="ca-instruction-icon"><i className="fas fa-video" aria-hidden="true" /></span><div><h3>Your whole session is recorded</h3><p>Your camera, microphone and entire screen are recorded until you submit. Do not turn them off or stop screen sharing.</p></div></li>
        <li><span className="ca-instruction-icon"><i className="fas fa-expand" aria-hidden="true" /></span><div><h3>Stay focused, stay in fullscreen</h3><p>Do not switch browser tabs, leave fullscreen, or move to another window.</p></div></li>
        <li><span className="ca-instruction-icon"><i className="fas fa-route" aria-hidden="true" /></span><div><h3>Use the exam’s navigation</h3><p>You can move between questions and the Questions / Coding sections inside this exam. Do not use browser Back, Forward, reload, or navigation shortcuts.</p></div></li>
        <li><span className="ca-instruction-icon"><i className="far fa-clock" aria-hidden="true" /></span><div><h3>Keep an eye on your time</h3><p>The timer begins when you start. For an attempt already in progress, the original timer continues.</p></div></li>
      </ol>
      </section>
      <div className="ca-welcome-start">
      <span className="ca-section-eyebrow">02 · CONFIRM & BEGIN</span>
      <h2>Ready when you are</h2>
      <p className="ca-section-intro">Read and accept the terms below to unlock your assessment.</p>
      <section className="ca-assessment-terms" aria-labelledby="ca-terms-title">
        <h2 id="ca-terms-title">Terms and conditions</h2>
        <p>This is a proctored exam. Complete it on your own, in a quiet and well-lit room. By accepting, you agree that:</p>
        <ul className="ca-terms-list">
          <li>Your camera, microphone and entire screen will be on and recorded for the whole exam.</li>
          <li>Photos of your face will be taken at random, about every 10 seconds.</li>
          <li>The recordings and photos will be stored with your name and reviewed by the hiring team.</li>
          <li>If your face is not detected or you look away from the screen, you will get a warning. The second time, the exam ends automatically.</li>
          <li>Leaving fullscreen, switching tabs or windows, or turning off your camera, microphone or screen sharing counts as a violation. Two violations end the exam.</li>
          <li>You cannot change your answers after you submit.</li>
        </ul>
        <label className="ca-terms-consent">
          <input type="checkbox" checked={termsAccepted} onChange={event => setTermsAccepted(event.target.checked)} />
          <span>I have read and agree to the proctored assessment terms and conditions.</span>
        </label>
      </section>
      {proctoring.count > 0 && <p className="ca-proctoring-warning">Warning already recorded: {proctoring.count} / 2. One more violation will end your exam.</p>}
      <button className="ca-btn ca-btn-primary" disabled={!termsAccepted} onClick={() => setStage('setup')}>
        Accept & set up proctoring <i className="fas fa-arrow-right" aria-hidden="true" /></button>
      <p className="ca-start-note"><i className="fas fa-video" aria-hidden="true" /> Next, you will allow camera, microphone and screen recording.</p>
      </div>
      </div>
      <footer className="ca-welcome-footer"><span>ShimentoX · Candidate experience</span><span>Take your time to prepare. Do your best.</span></footer>
    </section></div>;
  }

  return (
    <div className="ca-page" id="ca-root">
      <div inert={examPaused || confirmSubmit ? '' : undefined}>
      <header className="ca-header">
        <div className="ca-brand">
          <img src="/ShimentoX-Logo-Dark.png" alt="ShimentoX" className="ca-logo" />
          <h1 className="ca-assessment-title" title={assessment?.title || assessment?.job_role}>
            {assessment?.title || assessment?.job_role}
          </h1>
        </div>
        <div className="ca-header-actions">
          <span className="ca-proctoring-status"><span className="ca-rec-dot" aria-hidden="true" /> Recording · {proctoring.count} / 2 warnings · Face {media.faceCount} / {FACE_LIMIT}</span>
          {remainingSeconds != null && (
            <div className={`ca-timer ${remainingSeconds <= 300 ? 'ca-timer-warning' : ''}`} aria-label="Time remaining" role="timer">
              <i className="far fa-clock" aria-hidden="true" />
              <span>{formatTimer(remainingSeconds)}</span>
            </div>
          )}
          {assessment?.candidate_name && (
            <div className="ca-candidate" title={assessment.candidate_name}>
              <i className="far fa-user" aria-hidden="true" />
              <span>{assessment.candidate_name}</span>
            </div>
          )}
          <div className="ca-progress-summary">
            <span className="ca-progress-ring" style={{ '--ca-progress': `${progressPercent}%` }} aria-hidden="true" />
            <span className="ca-answered-count">{answeredCount} / {totalQuestions} answered</span>
          </div>
        </div>
      </header>

      {error && <div className="ca-inline-error" role="alert">{error}</div>}

      <div className="ca-layout">
        <aside className="ca-nav" aria-label="Question navigation">
          {sections.length > 1 ? (
            <div className="ca-tabs" role="tablist" aria-label="Question sections">
              {sections.map(section => {
                const done = section.items.filter(({ q }) => String(answers[q.id] || '').trim()).length;
                return (
                  <button key={section.key} type="button" role="tab" aria-selected={activeSection === section.key}
                    className={`ca-tab ${activeSection === section.key ? 'active' : ''}`} disabled={submitting}
                    onClick={() => { if (activeSection !== section.key) setCurrentIndex(section.items[0].index); }}>
                    <i className={`fas ${section.key === 'coding' ? 'fa-code' : 'fa-list-ul'}`} aria-hidden="true" />
                    {section.label}
                    <span className="ca-tab-count">{done}/{section.items.length}</span>
                  </button>
                );
              })}
            </div>
          ) : <h2 className="ca-nav-title">Questions</h2>}
          <ul className="ca-nav-list">
            {visibleItems.map(({ q, index }) => {
              const answered = Boolean(String(answers[q.id] || '').trim());
              const active = index === currentIndex;
              return (
                <li key={q.id}>
                  <button type="button" ref={active ? activeNavRef : null}
                    className={`ca-nav-item ${active ? 'active' : ''} ${answered ? 'answered' : ''}`}
                    onClick={() => setCurrentIndex(index)} disabled={submitting}
                    aria-current={active ? 'step' : undefined}
                    aria-label={`Question ${index + 1}, ${questionLabel(q.question_type)}, ${answered ? 'answered' : 'unanswered'}`}>
                    <span className="ca-nav-num">{index + 1}</span>
                    <span className="ca-nav-label">Question {index + 1}</span>
                    {answered && <span className="ca-nav-check" aria-hidden="true"><i className="fas fa-check" /></span>}
                  </button>
                </li>
              );
            })}
          </ul>
          <div className="ca-nav-progress">
            <p><strong>{answeredCount} / {totalQuestions}</strong> answered</p>
            <div className="ca-progress-track" role="progressbar" aria-label="Assessment completion"
              aria-valuemin={0} aria-valuemax={totalQuestions} aria-valuenow={answeredCount}
              aria-valuetext={`${answeredCount} of ${totalQuestions} questions answered`}>
              <span style={{ width: `${progressPercent}%` }} />
            </div>
          </div>
        </aside>

        <main className="ca-main">
          {currentQuestion ? (
            <section className="ca-question-card" aria-labelledby="ca-question-position">
              <div className="ca-question-head">
                <div className="ca-question-tags">
                  <span className="ca-question-badge">{questionLabel(currentQuestion.question_type)}</span>
                  {currentQuestion.skill_tag && <span className="ca-skill-tag">{currentQuestion.skill_tag}</span>}
                </div>
                <div className="ca-question-position">
                  <h2 id="ca-question-position">Question {currentIndex + 1} of {totalQuestions}</h2>
                  <div className="ca-step-actions">
                    <button type="button" className="ca-icon-button" aria-label="Previous question"
                      disabled={!canGoBack || submitting} onClick={() => setCurrentIndex(i => i - 1)}>
                      <i className="fas fa-chevron-left" aria-hidden="true" />
                    </button>
                    <button type="button" className="ca-icon-button" aria-label="Next question"
                      disabled={!canGoForward || submitting} onClick={() => setCurrentIndex(i => i + 1)}>
                      <i className="fas fa-chevron-right" aria-hidden="true" />
                    </button>
                  </div>
                </div>
              </div>
              <p className="ca-question-text">{currentQuestion.question_text}</p>

              {isChoiceQuestion(currentQuestion.question_type) && (
                <fieldset className="ca-options">
                  <legend className="ca-visually-hidden">Choose your answer</legend>
                  {(currentQuestion.options || []).map(option => (
                    <label key={option} className={`ca-option ${(answers[currentQuestion.id] || '') === option ? 'selected' : ''}`}>
                      <input type="radio" name={`question-${currentQuestion.id}`} value={option}
                        checked={(answers[currentQuestion.id] || '') === option} disabled={submitting}
                        onChange={() => handleAnswerChange(currentQuestion.id, option)} />
                      <span>{option}</span>
                    </label>
                  ))}
                </fieldset>
              )}

              {currentQuestion.question_type === 'short_answer' && (
                <div className="ca-answer-block">
                  <label className="ca-code-label" htmlFor={`answer-${currentQuestion.id}`}>Your answer</label>
                  <textarea id={`answer-${currentQuestion.id}`} className="ca-text-input" rows={6}
                    value={answers[currentQuestion.id] || ''} disabled={submitting}
                    onChange={e => handleAnswerChange(currentQuestion.id, e.target.value)} placeholder="Enter your answer" />
                </div>
              )}

              {isCodeQuestion(currentQuestion.question_type) && (
                <SampleTests question={currentQuestion} />
              )}

              {isCodeQuestion(currentQuestion.question_type) && (
                <div className={`ca-code-block ${editorExpanded ? 'ca-editor-expanded' : ''}`}>
                  <div className="ca-editor-toolbar">
                    <label className="ca-code-label" htmlFor={`code-${currentQuestion.id}`}>Your solution</label>
                    <i className="far fa-question-circle ca-editor-info" aria-hidden="true" title="Responses are saved automatically as you type" />
                    {currentQuestion.question_type === 'coding' && languageOptions.length > 0 ? (
                      <select className="ca-language-select" aria-label="Programming language" value={currentLanguage}
                        disabled={examLocked} onChange={e => changeLanguage(currentQuestion, e.target.value)}>
                        {languageOptions.map(option => <option key={option.key} value={option.key}>{option.label}</option>)}
                      </select>
                    ) : (
                      <span className="ca-editor-language">{editorLanguage || questionLabel(currentQuestion.question_type)}</span>
                    )}
                    <button type="button" className="ca-icon-button ca-expand-editor" aria-pressed={editorExpanded}
                      aria-label={editorExpanded ? 'Reduce editor' : 'Expand editor'} onClick={() => setEditorExpanded(value => !value)}>
                      <i className={`fas ${editorExpanded ? 'fa-compress-arrows-alt' : 'fa-expand-arrows-alt'}`} aria-hidden="true" />
                    </button>
                  </div>
                  <div className="ca-editor-surface">
                    <div className="ca-editor-lines" ref={editorGutterRef} aria-hidden="true">
                      {String(editorValue).split('\n').map((_, index) => <span key={index}>{index + 1}</span>)}
                    </div>
                    <textarea id={`code-${currentQuestion.id}`} className="ca-code-input" rows={10}
                      spellCheck={false} autoCapitalize="off" autoCorrect="off" disabled={submitting}
                      value={editorValue} onChange={e => handleAnswerChange(currentQuestion.id, e.target.value)}
                      onScroll={e => { if (editorGutterRef.current) editorGutterRef.current.scrollTop = e.currentTarget.scrollTop; }}
                      placeholder="Enter your solution" />
                  </div>
                  {currentQuestion.runnable && (
                    <div className="ca-run-row">
                      <button type="button" className="ca-btn ca-btn-run" onClick={runCode} disabled={examLocked || running || !String(editorValue).trim()}>
                        {running ? <><i className="fas fa-spinner fa-spin" aria-hidden="true" /> Running...</> : <><i className="fas fa-play" aria-hidden="true" /> Run</>}
                      </button>
                      <span className="ca-run-hint">
                        Runs the {(currentQuestion.sample_tests || []).length} example test{(currentQuestion.sample_tests || []).length === 1 ? '' : 's'} above.
                        {currentQuestion.hidden_test_count > 0 && ` ${currentQuestion.hidden_test_count} hidden tests are checked when you submit.`}
                      </span>
                    </div>
                  )}
                  {currentRun && <RunResults result={currentRun} sql={currentQuestion.question_type === 'sql'} />}
                </div>
              )}

              <div className="ca-question-footer">
                <button type="button" className="ca-btn ca-btn-secondary" disabled={!canGoBack || submitting}
                  onClick={() => setCurrentIndex(i => i - 1)}>
                  <i className="fas fa-arrow-left" aria-hidden="true" /> Previous
                </button>
                <div className={`ca-save-indicator ca-save-${saveState}`} role="status" aria-live="polite">
                  {saveState === 'saving' && <><i className="fas fa-sync fa-spin" aria-hidden="true" /> Saving...</>}
                  {saveState === 'saved' && <><i className="fas fa-check" aria-hidden="true" /> Saved</>}
                  {saveState === 'error' && <><i className="fas fa-exclamation-triangle" aria-hidden="true" /> Save failed</>}
                </div>
                {canGoForward ? (
                  <button type="button" className="ca-btn ca-btn-primary" disabled={submitting}
                    onClick={() => setCurrentIndex(i => i + 1)}>Next <i className="fas fa-arrow-right" aria-hidden="true" /></button>
                ) : (
                  <button type="button" className="ca-btn ca-btn-primary" disabled={submitting} onClick={() => handleSubmit(false)}>
                    {submitting ? 'Submitting...' : 'Submit Assessment'}
                  </button>
                )}
              </div>
            </section>
          ) : <div className="ca-card ca-center"><p>No questions found for this assessment.</p></div>}
        </main>
      </div>
      {currentQuestion && canGoForward && (
        <footer className="ca-footer">
          <button type="button" className="ca-submit-link" disabled={submitting} onClick={() => handleSubmit(false)}>
            {submitting ? 'Submitting...' : 'Submit Assessment'}
          </button>
        </footer>
      )}
      </div>
      <CameraPreview stream={media.streams.camera} className="ca-camera-pip" label="Your camera (recording)" />
      {media.lost.length > 0 && <ExamDialog title="Recording stopped">
        <p>Your {media.lost.map(kind => DEVICE_NAMES[kind]).join(' and ')} turned off. This has been recorded as a warning. Your exam will end if you do this again.</p>
        <p>Turn {media.lost.length > 1 ? 'them' : 'it'} back on to continue{media.lost.includes('screen') ? ', and choose Entire screen when sharing' : ''}.</p>
        {media.error && <p className="ca-inline-error" role="alert">{media.error}</p>}
        <button className="ca-btn ca-btn-primary" disabled={Boolean(media.busy)}
          onClick={() => proctoring.withoutMonitoring(media.restore)}>{media.busy ? 'Waiting for permission…' : 'Turn back on'}</button>
      </ExamDialog>}
      {!media.lost.length && (proctoring.warning || proctoring.error) && <ExamDialog title={proctoring.count ? 'Exam warning: 1 of 2' : 'Exam monitoring paused'}>
        {proctoring.count > 0 && <p>You left the exam, tried to navigate away, or stopped recording. Your exam will be ended if you do this again.</p>}
        <p>Return to fullscreen and stay in this tab to continue.</p>
        {proctoring.error && <p className="ca-inline-error" role="alert">{proctoring.error}</p>}
        <button className="ca-btn ca-btn-primary" disabled={proctoring.syncing} onClick={proctoring.resume}>Return to exam</button>
      </ExamDialog>}
      {!media.lost.length && !proctoring.warning && !proctoring.error && media.faceWarning && <ExamDialog title={`Face not detected: warning ${media.faceWarning.count} of ${FACE_LIMIT}`}>
        <p>{FACE_ISSUE_TEXT[media.faceWarning.issue] || FACE_ISSUE_TEXT.no_face}</p>
        <p>If your face is not detected again, your exam will end automatically.</p>
        <CameraPreview stream={media.streams.camera} className="ca-camera-dialog" />
        {faceRecheck === 'failed' && <p className="ca-inline-error" role="alert">We still cannot see your face. Face the camera directly and try again.</p>}
        <button className="ca-btn ca-btn-primary" disabled={faceRecheck === 'checking'} onClick={recheckFace}>
          {faceRecheck === 'checking' ? 'Checking…' : 'I am in view, continue'}</button>
      </ExamDialog>}
      {confirmSubmit && !examPaused && <ExamDialog title="Submit your assessment?">
        <p>You cannot change your answers after submission.</p>
        <div className="ca-dialog-actions">
          <button className="ca-btn ca-btn-secondary" onClick={() => setConfirmSubmit(false)}>Continue exam</button>
          <button className="ca-btn ca-btn-primary" onClick={() => handleSubmit(false, true)}>Confirm submission</button>
        </div>
      </ExamDialog>}
    </div>
  );
}

export default CandidateAssessment;
