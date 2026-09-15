const STATUS_LABELS = {
  NOT_CREATED: 'Not Created',
  DRAFT: 'Draft',
  SENT: 'Sent',
  IN_PROGRESS: 'In Progress',
  COMPLETED: 'Completed',
  PASSED: 'Passed',
  FAILED: 'Failed',
};

export function formatAssessmentStatus(status) {
  return STATUS_LABELS[status] || status || 'Not Created';
}

export function assessmentBadgeClass(status) {
  if (status === 'PASSED') return 'badge-success';
  if (status === 'FAILED') return 'badge-danger';
  if (status === 'SENT' || status === 'IN_PROGRESS') return 'badge-warning';
  if (status === 'DRAFT') return 'badge-primary';
  if (status === 'COMPLETED') return 'badge-primary';
  return 'badge-secondary';
}

export function isAssessmentScoreVisible(status) {
  return ['COMPLETED', 'PASSED', 'FAILED'].includes(status);
}

export function formatAssessmentDate(value) {
  if (!value) return '—';
  const raw = String(value).trim();
  const parsed = new Date(raw.includes('T') ? raw : raw.replace(' ', 'T'));
  if (Number.isNaN(parsed.getTime())) return raw.slice(0, 10) || '—';
  const day = String(parsed.getDate()).padStart(2, '0');
  const month = String(parsed.getMonth() + 1).padStart(2, '0');
  const year = parsed.getFullYear();
  return `${day}/${month}/${year}`;
}

export function formatAssessmentDuration(minutes) {
  if (minutes == null || minutes === '') return '—';
  const value = Number(minutes);
  if (Number.isNaN(value) || value < 0) return '—';
  if (value < 60) return `${value} min`;
  const hours = Math.floor(value / 60);
  const mins = value % 60;
  return mins ? `${hours}h ${mins}m` : `${hours}h`;
}

export function resolveAssessmentRow(candidate, assessmentMap) {
  const mapped = assessmentMap?.[candidate.id];
  const assessment = mapped?.assessment || null;
  const status = candidate.assessment_status || mapped?.status || assessment?.status || 'NOT_CREATED';
  return {
    status,
    score: candidate.assessment_score ?? mapped?.score ?? mapped?.result?.score ?? null,
    percentage: candidate.assessment_percentage ?? mapped?.percentage ?? mapped?.result?.percentage ?? null,
    result: candidate.assessment_result ?? mapped?.assessment_result ?? mapped?.result?.status ?? null,
    assessmentId: candidate.assessment_id ?? assessment?.id ?? null,
    sentAt: candidate.sent_at ?? mapped?.sent_at ?? assessment?.sent_at ?? null,
    startedAt: candidate.started_at ?? mapped?.started_at ?? assessment?.started_at ?? null,
    completedAt: candidate.completed_at ?? mapped?.completed_at ?? assessment?.completed_at ?? null,
    durationMinutes: candidate.assessment_duration_minutes ?? mapped?.assessment_duration_minutes ?? null,
    linkStatus: candidate.link_status ?? mapped?.link_status ?? 'Not Sent',
    eligibleForInterview: Boolean(
      candidate.eligible_for_interview ?? mapped?.eligible_for_interview ?? status === 'PASSED',
    ),
  };
}
