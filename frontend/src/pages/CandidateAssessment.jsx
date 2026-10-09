import React, { useState, useEffect, useCallback, useRef, useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { publicApiGet, publicApiPost } from '../api.js';
import '../styles/assessment_candidate.css';

const AUTOSAVE_DELAY_MS = 600;

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
  const editorGutterRef = useRef(null);
  const activeNavRef = useRef(null);

  const saveTimersRef = useRef({});
  const answersRef = useRef(answers);
  const submitRef = useRef(null);
  answersRef.current = answers;

  // Non-coding questions come first so each tab holds a contiguous number range.
  const sortedQuestions = useMemo(
    () => [...questions].sort((a, b) =>
      Number(isCodeQuestion(a.question_type)) - Number(isCodeQuestion(b.question_type))
      || (a.sort_order ?? 0) - (b.sort_order ?? 0)),
    [questions],
  );

  const currentQuestion = sortedQuestions[currentIndex] || null;
  const totalQuestions = sortedQuestions.length;
  const editorValue = currentQuestion
    ? answers[currentQuestion.id] ?? currentQuestion.starter_code ?? ''
    : '';
  const editorLanguage = currentQuestion?.language || currentQuestion?.programming_language;
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
      (data.saved_answers || []).forEach(row => {
        if (row.question_id != null) {
          initial[row.question_id] = row.answer || '';
        }
      });
      setAnswers(initial);
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
    if (remainingSeconds == null || submitted) return undefined;
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
  }, [remainingSeconds, submitted, submitting]);

  const persistAnswer = useCallback(async (questionId, answer) => {
    setSaveState('saving');
    try {
      await publicApiPost('/api/assessment/save-answer', {
        token,
        question_id: questionId,
        answer,
      });
      setSaveState('saved');
      window.setTimeout(() => setSaveState('idle'), 2000);
    } catch {
      setSaveState('error');
    }
  }, [token]);

  const scheduleAutosave = useCallback((questionId, answer) => {
    if (submitted) return;
    if (saveTimersRef.current[questionId]) {
      window.clearTimeout(saveTimersRef.current[questionId]);
    }
    saveTimersRef.current[questionId] = window.setTimeout(() => {
      persistAnswer(questionId, answer);
    }, AUTOSAVE_DELAY_MS);
  }, [persistAnswer, submitted]);

  const handleAnswerChange = (questionId, value) => {
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
        }).catch(() => null),
      ),
    );
  };

  const handleSubmit = async (autoSubmit = false) => {
    if (submitting || submitted) return;
    if (!autoSubmit && !window.confirm('Submit your assessment? You cannot change answers after submission.')) return;
    setSubmitting(true);
    setError('');
    try {
      await flushPendingSaves();
      const payload = {
        token,
        answers: sortedQuestions.map(q => ({
          question_id: q.id,
          answer: answersRef.current[q.id] || '',
        })),
      };
      const result = await publicApiPost('/api/assessment/submit', payload);
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

  if (error && !assessment) {
    return (
      <div className="ca-page" id="ca-root">
        <div className="ca-card ca-center ca-error-card">
          <i className="fas fa-exclamation-circle" />
          <h1>Assessment Unavailable</h1>
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
        </div>
      </div>
    );
  }

  return (
    <div className="ca-page" id="ca-root">
      <header className="ca-header">
        <div className="ca-brand">
          <img src="/ShimentoX-Logo-Dark.png" alt="ShimentoX" className="ca-logo" />
          <h1 className="ca-assessment-title" title={assessment?.title || assessment?.job_role}>
            {assessment?.title || assessment?.job_role}
          </h1>
        </div>
        <div className="ca-header-actions">
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
                <div className={`ca-code-block ${editorExpanded ? 'ca-editor-expanded' : ''}`}>
                  <div className="ca-editor-toolbar">
                    <label className="ca-code-label" htmlFor={`code-${currentQuestion.id}`}>Your solution</label>
                    <i className="far fa-question-circle ca-editor-info" aria-hidden="true" title="Responses are saved automatically as you type" />
                    <span className="ca-editor-language">{editorLanguage || questionLabel(currentQuestion.question_type)}</span>
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
  );
}

export default CandidateAssessment;
