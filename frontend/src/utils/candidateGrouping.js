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
      applied_roles: [...new Set([...(existing?.applied_roles || []), ...(candidate.applied_roles || [])])],
      job_applications: [...jobs.values()],
    });
  }
  return [...groups.values()];
}
