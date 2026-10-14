// The backend's `outcome` is the screening result overridden by any later
// rejection (interview, failed assessment); older payloads only carry `status`.
const resultOf = candidate => candidate.outcome ?? candidate.status;

export function candidateMatchesSelection(candidate, category) {
  if (category === 'all') return true;
  const statuses = [resultOf(candidate), ...(candidate.submission_statuses || []), ...(candidate.job_applications || []).map(job => job.status)]
    .map(status => String(status || '').trim().toLowerCase());
  return statuses.includes(category);
}

// The hiring progress of one submission, so a merged row can show every job's stage.
function stageRecord(candidate) {
  const ownJob = (candidate.job_applications || []).find(job => job.jd_id != null && job.jd_id === candidate.jd_id);
  return {
    id: candidate.id,
    jd_id: candidate.jd_id ?? null,
    jd_title: ownJob?.jd_title || candidate.jd_title || '',
    screening_status: candidate.screening_status ?? null,
    hiring_process_steps: candidate.hiring_process_steps,
    stage_id: candidate.stage_id,
    hiring_stage: candidate.hiring_stage,
    interview_stage: candidate.interview_stage,
    on_hold: Boolean(candidate.on_hold),
    assessment_status: candidate.assessment_status,
  };
}

export function dedupeCandidates(rows) {
  const groups = new Map();
  for (const candidate of rows) {
    const email = String(candidate.email || candidate.structured_data?.email || '').trim().toLowerCase();
    const phone = String(candidate.phone || '').trim();
    const key = email ? `email:${email}` : phone ? `phone:${phone}` : `id:${candidate.id}`;
    const existing = groups.get(key);
    const applications = [...(existing?.job_applications || []), ...(candidate.job_applications || [])];
    const jobs = new Map();
    applications.forEach(application => {
      const jobKey = application.jd_id ?? application.jd_title;
      if (!jobs.has(jobKey)) jobs.set(jobKey, application);
    });
    const records = new Map();
    [...(existing?.stage_records || []), ...(candidate.stage_records || [stageRecord(candidate)])]
      .forEach(record => { if (!records.has(record.id)) records.set(record.id, record); });
    const selected = String(resultOf(candidate) || '').toLowerCase() === 'selected';
    const wasSelected = String(resultOf(existing || {}) || '').toLowerCase() === 'selected';
    const representative = !existing || (selected && !wasSelected) ? candidate : existing;
    groups.set(key, {
      ...representative,
      submission_statuses: [...new Set([...(existing?.submission_statuses || []), ...(candidate.submission_statuses || []), resultOf(candidate)].filter(Boolean))],
      applied_roles: [...new Set([...(existing?.applied_roles || []), ...(candidate.applied_roles || [])])],
      job_applications: [...jobs.values()],
      // Every underlying submission, so deleting the merged row removes the whole person.
      member_ids: [...new Set([...(existing?.member_ids || []), ...(candidate.member_ids || [candidate.id])])],
      stage_records: [...records.values()],
    });
  }
  return [...groups.values()];
}

// How far one submission got: rejected submissions rank below any live one.
function progressOf(record) {
  const rejected = record.screening_status === 'rejected'
    || String(record.interview_stage || '').toLowerCase() === 'rejected after interview';
  if (rejected) return -1;
  return (record.hiring_process_steps || []).findIndex(step => step.id === record.stage_id);
}

// One stage record per job (repeat submissions to the same job collapse to the
// furthest-along one), with the row's own job first.
export function stageRecordsByJob(candidate) {
  const records = candidate.stage_records?.length ? candidate.stage_records : [{ ...candidate, jd_title: '' }];
  const byJob = new Map();
  records.forEach(record => {
    const key = record.jd_id ?? record.jd_title ?? record.id;
    const current = byJob.get(key);
    if (!current || progressOf(record) > progressOf(current)) byJob.set(key, record);
  });
  const ownKey = records.find(record => record.id === candidate.id)?.jd_id;
  return [...byJob.values()].sort((a, b) => (b.jd_id === ownKey) - (a.jd_id === ownKey));
}
