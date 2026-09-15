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
    mcq: 'Multiple Choice',
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

  const saveTimersRef = useRef({});
  const answersRef = useRef(answers);
  const submitRef = useRef(null);
  answersRef.current = answers;

  const sortedQuestions = useMemo(
    () => [...questions].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0)),
    [questions],
  );

  const currentQuestion = sortedQuestions[currentIndex] || null;

  const answeredCount = useMemo(
    () => sortedQuestions.filter(q => String(answers[q.id] || '').trim()).length,
    [sortedQuestions, answers],
  );

  const loadAssessment = useCallback(async () => {
    setLoading(true);
    setError('');
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
      (data.questions || []).forEach(q => {
        if (initial[q.id] == null && q.starter_code && isCodeQuestion(q.question_type)) {
          initial[q.id] = q.starter_code;
        }
      });
      setAnswers(initial);
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
      <div className="ca-page">
        <div className="ca-card ca-center">
          <div className="ca-spinner" aria-hidden="true" />
          <p>Loading your assessment…</p>
        </div>
      </div>
    );
  }

  if (error && !assessment) {
    return (
      <div className="ca-page">
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
      <div className="ca-page">
        <div className="ca-card ca-center ca-success-card">
          <i className="fas fa-check-circle" />
          <h1>Assessment Submitted</h1>
          <p>{submitMessage}</p>
        </div>
      </div>
    );
  }

  return (
    <div className="ca-page">
      <header className="ca-header">
        <div className="ca-header-main">
          <div className="ca-brand">
            <i className="fas fa-clipboard-check" />
            <span>Recruitment Assessment</span>
          </div>
          <div className="ca-header-meta">
            <div className="ca-meta-block">
              <span className="ca-meta-label">Candidate</span>
              <strong>{assessment?.candidate_name || 'Candidate'}</strong>
            </div>
            <div className="ca-meta-block">
              <span className="ca-meta-label">Assessment</span>
              <strong>{assessment?.title || assessment?.job_role || 'Technical Assessment'}</strong>
            </div>
          </div>
        </div>
        <div className="ca-header-actions">
          {remainingSeconds != null && (
            <div className={`ca-timer ${remainingSeconds <= 300 ? 'ca-timer-warning' : ''}`}>
              <i className="fas fa-clock" />
              <span>{formatTimer(remainingSeconds)}</span>
            </div>
          )}
          <div className="ca-progress-pill">
            {answeredCount} / {sortedQuestions.length} answered
          </div>
          <div className={`ca-save-indicator ca-save-${saveState}`}>
            {saveState === 'saving' && <><i className="fas fa-sync fa-spin" /> Saving…</>}
            {saveState === 'saved' && <><i className="fas fa-check" /> Saved</>}
            {saveState === 'error' && <><i className="fas fa-exclamation-triangle" /> Save failed</>}
          </div>
        </div>
      </header>

      {error && <div className="ca-inline-error">{error}</div>}

      <div className="ca-layout">
        <aside className="ca-nav">
          <h2>Questions</h2>
          <ul className="ca-nav-list">
            {sortedQuestions.map((q, index) => {
              const answered = Boolean(String(answers[q.id] || '').trim());
              const active = index === currentIndex;
              return (
                <li key={q.id}>
                  <button
                    type="button"
                    className={`ca-nav-item ${active ? 'active' : ''} ${answered ? 'answered' : ''}`}
                    onClick={() => setCurrentIndex(index)}
                  >
                    <span className="ca-nav-num">{index + 1}</span>
                    <span className="ca-nav-type">{questionLabel(q.question_type)}</span>
                  </button>
                </li>
              );
            })}
          </ul>
        </aside>

        <main className="ca-main">
          {currentQuestion ? (
            <div className="ca-question-card">
              <div className="ca-question-head">
                <span className="ca-question-badge">{questionLabel(currentQuestion.question_type)}</span>
                {currentQuestion.skill_tag && (
                  <span className="ca-skill-tag">{currentQuestion.skill_tag}</span>
                )}
                <span className="ca-points">{currentQuestion.points} pts</span>
              </div>
              <h2 className="ca-question-title">
                Question {currentIndex + 1} of {sortedQuestions.length}
              </h2>
              <p className="ca-question-text">{currentQuestion.question_text}</p>

              {isChoiceQuestion(currentQuestion.question_type) && (
                <div className="ca-options">
                  {(currentQuestion.options || []).map(option => (
                    <label key={option} className="ca-option">
                      <input
                        type="radio"
                        name={`question-${currentQuestion.id}`}
                        value={option}
                        checked={(answers[currentQuestion.id] || '') === option}
                        onChange={() => handleAnswerChange(currentQuestion.id, option)}
                      />
                      <span>{option}</span>
                    </label>
                  ))}
                </div>
              )}

              {currentQuestion.question_type === 'short_answer' && (
                <textarea
                  className="ca-text-input"
                  rows={4}
                  value={answers[currentQuestion.id] || ''}
                  onChange={e => handleAnswerChange(currentQuestion.id, e.target.value)}
                  placeholder="Type your answer here…"
                />
              )}

              {currentQuestion.question_type === 'coding' && (
                <div className="ca-code-block">
                  <label className="ca-code-label" htmlFor={`code-${currentQuestion.id}`}>
                    Your solution
                  </label>
                  <textarea
                    id={`code-${currentQuestion.id}`}
                    className="ca-code-input"
                    rows={16}
                    spellCheck={false}
                    value={answers[currentQuestion.id] ?? currentQuestion.starter_code ?? ''}
                    onChange={e => handleAnswerChange(currentQuestion.id, e.target.value)}
                    placeholder="// Write your code here"
                  />
                </div>
              )}

              {currentQuestion.question_type === 'sql' && (
                <div className="ca-code-block">
                  <label className="ca-code-label" htmlFor={`sql-${currentQuestion.id}`}>
                    Your SQL query
                  </label>
                  <textarea
                    id={`sql-${currentQuestion.id}`}
                    className="ca-code-input ca-sql-input"
                    rows={12}
                    spellCheck={false}
                    value={answers[currentQuestion.id] || ''}
                    onChange={e => handleAnswerChange(currentQuestion.id, e.target.value)}
                    placeholder="-- Write your SQL here"
                  />
                </div>
              )}

              <div className="ca-question-footer">
                <button
                  type="button"
                  className="ca-btn ca-btn-secondary"
                  disabled={currentIndex === 0}
                  onClick={() => setCurrentIndex(i => Math.max(0, i - 1))}
                >
                  <i className="fas fa-arrow-left" /> Previous
                </button>
                {currentIndex < sortedQuestions.length - 1 ? (
                  <button
                    type="button"
                    className="ca-btn ca-btn-primary"
                    onClick={() => setCurrentIndex(i => Math.min(sortedQuestions.length - 1, i + 1))}
                  >
                    Next <i className="fas fa-arrow-right" />
                  </button>
                ) : (
                  <button
                    type="button"
                    className="ca-btn ca-btn-success"
                    disabled={submitting}
                    onClick={() => handleSubmit(false)}
                  >
                    {submitting ? 'Submitting…' : 'Submit Assessment'}
                  </button>
                )}
              </div>
            </div>
          ) : (
            <div className="ca-card ca-center">
              <p>No questions found for this assessment.</p>
            </div>
          )}
        </main>
      </div>

      <footer className="ca-footer">
        <button
          type="button"
          className="ca-btn ca-btn-success ca-submit-footer"
          disabled={submitting}
          onClick={() => handleSubmit(false)}
        >
          {submitting ? 'Submitting…' : 'Submit Assessment'}
        </button>
      </footer>
    </div>
  );
}

export default CandidateAssessment;
