import React from 'react';
import './StageTrackerDelivery.css';

const SCREENING = {
  accepted: { label: 'Resume Accepted', tone: 'ok' },
  waitlisted: { label: 'Waitlisted', tone: 'warn' },
  rejected: { label: 'Rejected', tone: 'bad' },
};
const NOT_SCREENED = { label: 'Not screened', tone: 'none' };
// Latest assessment for the candidate (candidate.assessment_status from the backend).
const ASSESSMENT = {
  SENT: { label: 'Assessment Sent', state: 'current' },
  IN_PROGRESS: { label: 'Assessment In Progress', state: 'current' },
  COMPLETED: { label: 'Assessment Submitted', state: 'current' },
  PASSED: { label: 'Assessment Passed', state: 'ok' },
  FAILED: { label: 'Assessment Failed', state: 'bad' },
  TERMINATED: { label: 'Assessment Terminated', state: 'bad' },
};
const isAssessmentStep = step => {
  const name = String(step?.name || '').toLowerCase();
  return name.includes('assessment') || name === 'test';
};

const ICON_PATHS = {
  ok: 'M3.5 8.5l3 3 6-7',
  bad: 'M4.5 4.5l7 7M11.5 4.5l-7 7',
  warn: 'M4 8h8',
};

function StatusIcon({ tone }) {
  const d = ICON_PATHS[tone];
  if (!d) return null;
  return (
    <svg viewBox="0 0 16 16" width="12" height="12" fill="none" stroke="currentColor" strokeWidth="2"
      strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d={d} />
    </svg>
  );
}

// Interview progress as reported by the backend (candidate.hiring_stage).
function interviewState(hiringStage) {
  const stage = String(hiringStage || '').toLowerCase();
  if (stage === 'interview completed') return 'ok';
  if (stage === 'rejected after interview') return 'bad';
  if (stage === 'interview cancelled') return 'warn';
  if (stage.startsWith('interview') || stage === 'client interview pending') return 'current';
  return 'none';
}

/**
 * Builds the steps to show from real candidate data:
 * - the JD's configured hiring process (step names + the candidate's current step), or
 * - when no process is configured, Screening (screening result) and Interview (interview status).
 */
export function buildStages({ screeningStatus, steps, stageId, hiringStage, interviewStage, onHold, assessmentStatus }) {
  const screening = SCREENING[screeningStatus] || NOT_SCREENED;
  const rejected = screeningStatus === 'rejected';
  const assessment = ASSESSMENT[assessmentStatus];

  if (Array.isArray(steps) && steps.length) {
    // A configured pipeline replaces hiringStage with its step name, so the
    // interview outcome arrives separately as interviewStage.
    const interviewRejected = String(interviewStage || '').toLowerCase() === 'rejected after interview';
    let current = steps.findIndex(step => step.id === stageId);
    // A rejection with no recorded step still shows on the first step.
    if (current < 0 && (rejected || interviewRejected)) current = 0;
    const assessmentIndex = steps.findIndex(isAssessmentStep);
    // The assessment outcome is authoritative until the candidate moves past that step.
    const onAssessment = assessment && assessmentIndex >= 0 && current <= assessmentIndex && !rejected && !interviewRejected;
    if (onAssessment) current = assessmentIndex;
    const items = steps.map((step, i) => {
      let state = 'none';
      if (i < current) state = 'ok';
      else if (i === current) state = rejected || interviewRejected ? 'bad' : onAssessment ? assessment.state : onHold ? 'warn' : 'current';
      return { name: step.name, state };
    });
    const failed = onAssessment && assessment.state === 'bad';
    const stageName = onAssessment ? assessment.label : current >= 0 ? steps[current].name : 'Not started';
    const label = rejected ? 'Rejected' : interviewRejected ? 'Rejected After Interview'
      : onHold ? `${stageName} · On hold` : stageName;
    const tone = rejected || interviewRejected || failed ? 'bad' : onHold ? 'warn' : current >= 0 ? 'ok' : 'none';
    return { items, label, tone };
  }

  const interview = rejected ? 'none' : interviewState(hiringStage);
  const assessmentState = rejected || !assessment ? 'none' : assessment.state;
  const items = [
    { name: 'Screening', state: screening.tone === 'none' ? 'current' : screening.tone },
    { name: 'Assessment', state: assessmentState },
    { name: 'Interview', state: interview },
  ];
  const label = interview !== 'none' ? hiringStage : assessmentState !== 'none' ? assessment.label : screening.label;
  const latest = interview !== 'none' ? interview : assessmentState;
  const tone = latest === 'bad' || rejected ? 'bad' : latest === 'warn' || (latest === 'none' && screening.tone === 'warn') ? 'warn'
    : latest !== 'none' || screening.tone === 'ok' ? 'ok' : 'none';
  return { items, label: onHold && !rejected ? `${label} · On hold` : label, tone };
}

export default function StageTrackerDelivery({ screeningStatus, steps, stageId, hiringStage, interviewStage, onHold, assessmentStatus }) {
  const { items, label, tone } = buildStages({ screeningStatus, steps, stageId, hiringStage, interviewStage, onHold, assessmentStatus });
  return (
    <div className={`stx stx--${tone}`} role="group" aria-label={`Stage: ${label}`} title={label}
      style={{ '--stx-cols': items.length }}>
      <ol className="stx__steps" aria-hidden="true">
        {items.map((item, i) => (
          <li key={`${i}-${item.name}`} className={`stx__step stx__step--${item.state}`}>
            <span className="stx__dot"><StatusIcon tone={item.state} /></span>
            <span className="stx__label">{item.name}</span>
          </li>
        ))}
      </ol>
      <div className="stx__status">{label}</div>
    </div>
  );
}
