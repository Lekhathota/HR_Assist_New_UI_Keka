export function defaultFilters() {
  const end = new Date();
  const start = new Date(end.getFullYear(), end.getMonth(), end.getDate() - 29);
  const localDate = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
  return { start: localDate(start), end: localDate(end), job: '', jobs: [], status: '', source: '', allTime: true };
}

export function analyticsReport(data, filters) {
  const a = data.analytics || {};
  const value = v => v == null ? 'Not available' : String(v);
  return [
    'RECRUITMENT ANALYTICS REPORT',
    filters.allTime ? 'Dates: All time' : `Dates: ${filters.start} through ${filters.end} (local dates, inclusive)`,
    `Job: ${(filters.jobs?.length ? filters.jobs : filters.job ? [filters.job] : []).map(id => a.jobs?.find(j => String(j.id) === String(id))?.title || `Job #${id}`).join(', ') || 'All jobs'}`,
    `Status: ${filters.status || 'All statuses'}`, `Source: ${filters.source || 'All sources'}`,
    '\nOVERALL METRICS', ...Object.entries(data.metrics || {}).map(([k, v]) => `${k.replaceAll('_', ' ')}: ${value(v)}`),
    '\nJOB PERFORMANCE', ...(data.jd_reports || []).map(j => `${j.title}: ${j.total_screened} candidates; ${j.selected} selected; ${j.rejected} rejected; average match ${j.avg_match}%`),
    '\nPIPELINE', ...(a.pipeline || []).map(r => `${r.name}: ${value(r.count)}${r.reason ? ` - ${r.reason}` : ''}`),
    '\nCANDIDATE SOURCES', ...(a.sources || []).map(r => `${r.name}: ${r.count}`),
    '\nUPLOAD TREND', ...(a.trend || []).map(r => `${r.name}: ${r.count}`),
    '\nSKILL GAPS (ALL TIME)', ...(data.skill_gaps || []).map(r => `${r.name}: ${r.jd_count} jobs; ${r.candidate_count} candidates; gap ${r.jd_count - r.candidate_count}`),
    '\nMATCH SCORE DISTRIBUTION', ...(a.score_bands || []).map(r => `${r.name}: ${r.count}`),
    '\nCANDIDATE STATUS', ...(a.status_breakdown || []).map(r => `${r.name}: ${r.count}`),
    '\nCONVERSION', ...(a.pipeline || []).map(r => `${r.name}: ${r.count == null || !data.metrics?.total_candidates ? 'Not available' : `${(r.count / data.metrics.total_candidates * 100).toFixed(1)}%`} of uploaded cohort`),
    '\nDATA COVERAGE', ...(a.notes || []),
  ].join('\n');
}
