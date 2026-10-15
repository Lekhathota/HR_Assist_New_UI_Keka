// Display helpers for the Talent table (one row per person; see candidateGrouping.js).
import { buildStages } from '../components/StageTrackerDelivery.jsx';
import { stageRecordsByJob } from './candidateGrouping.js';

// The row's primary job: its own submission first, then the furthest-along other job.
export function primaryRecord(candidate) {
  return stageRecordsByJob(candidate)[0] || candidate;
}

// Stage pill: the same label the stage tracker computes, coloured by kind of stage.
export function stageOf(candidate) {
  const record = primaryRecord(candidate);
  const { label, tone } = buildStages({
    screeningStatus: record.screening_status ?? null,
    steps: record.hiring_process_steps,
    stageId: record.stage_id,
    hiringStage: record.hiring_stage,
    interviewStage: record.interview_stage,
    onHold: Boolean(record.on_hold),
    assessmentStatus: record.assessment_status,
  });
  const text = String(label || '').toLowerCase();
  let kind = 'muted';
  if (tone === 'bad' || text.includes('reject')) kind = 'rejected';
  else if (record.on_hold) kind = 'hold';
  else if (/hired|joined|onboard|placed/.test(text)) kind = 'hired';
  else if (/offer|selected|pending client/.test(text)) kind = 'offer';
  else if (text.includes('interview')) kind = 'interview';
  else if (/screen|assessment|resume|waitlist|shortlist/.test(text)) kind = 'screening';
  else if (tone === 'ok') kind = 'progress';
  const display = record.on_hold && kind === 'hold' ? 'On Hold' : label || 'Not started';
  return { label: display, title: label || 'Not started', kind, record };
}

export function roleOf(candidate) {
  const record = primaryRecord(candidate);
  const titles = [...new Set((candidate.job_applications || []).map(job => job.jd_title).filter(Boolean))];
  const primary = record.jd_title || candidate.jd_title || titles[0] || candidate.primary_category || '';
  return { primary, others: titles.filter(title => title !== primary) };
}

export function locationOf(candidate) {
  const sd = candidate.structured_data || {};
  const value = sd.location || sd.current_location || candidate.location || '';
  return typeof value === 'string' ? value.trim() : [value.city, value.state, value.country].filter(Boolean).join(', ');
}

export function scoreOf(candidate) {
  const value = Number(candidate.match_score);
  return Number.isFinite(value) && candidate.match_score !== null && candidate.match_score !== '' ? Math.round(value) : null;
}

export function scoreTone(score) {
  if (score === null) return 'muted';
  return score >= 70 ? 'good' : score >= 50 ? 'mid' : 'low';
}

export function appliedTime(candidate) {
  const parsed = new Date(String(candidate.uploaded_at || candidate.created_at || ''));
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

// "10 Jul, 02:00 PM"; the year is added when it is not the current one.
export function formatApplied(date) {
  if (!date) return '—';
  const day = date.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', ...(date.getFullYear() !== new Date().getFullYear() ? { year: 'numeric' } : {}) });
  const time = date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
  return `${day}, ${time}`;
}

export function initialsOf(name) {
  return String(name || '?').trim().split(/\s+/).slice(0, 2).map(part => part[0] || '').join('').toUpperCase() || '?';
}

// Page numbers around the current page, at most `span` of them.
export function pageWindow(page, pageCount, span = 5) {
  const start = Math.max(1, Math.min(page - Math.floor(span / 2), pageCount - span + 1));
  return Array.from({ length: Math.min(span, pageCount) }, (_, i) => start + i);
}
