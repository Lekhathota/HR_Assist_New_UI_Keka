export function candidateMatchesSelection(candidate, category) {
  if (category === 'all') return true;
  const statuses = [candidate.status, ...(candidate.submission_statuses || []), ...(candidate.job_applications || []).map(job => job.status)]
    .map(status => String(status || '').trim().toLowerCase());
  return statuses.includes(category);
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
    const selected = String(candidate.status || '').toLowerCase() === 'selected';
    const wasSelected = String(existing?.status || '').toLowerCase() === 'selected';
    const representative = !existing || (selected && !wasSelected) ? candidate : existing;
    groups.set(key, {
      ...representative,
      submission_statuses: [...new Set([...(existing?.submission_statuses || []), ...(candidate.submission_statuses || []), candidate.status].filter(Boolean))],
      applied_roles: [...new Set([...(existing?.applied_roles || []), ...(candidate.applied_roles || [])])],
      job_applications: [...jobs.values()],
    });
  }
  return [...groups.values()];
}
