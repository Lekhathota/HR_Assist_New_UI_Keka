import { dedupeCandidates, candidateMatchesSelection, stageRecordsByJob } from './candidateGrouping';

test('mixed job outcomes appear in both relevant categories', () => {
  const candidate = { status: 'Selected', job_applications: [{ status: 'Rejected' }] };
  expect(candidateMatchesSelection(candidate, 'selected')).toBe(true);
  expect(candidateMatchesSelection(candidate, 'rejected')).toBe(true);
  expect(candidateMatchesSelection({ status: 'Pending' }, 'rejected')).toBe(false);
});

test('grouping retains rejected submission status even without job metadata', () => {
  const [candidate] = dedupeCandidates([
    { id: 1, email: 'person@example.com', status: 'Rejected' },
    { id: 2, email: 'person@example.com', status: 'Selected' },
  ]);
  expect(candidateMatchesSelection(candidate, 'rejected')).toBe(true);
  expect(candidateMatchesSelection(candidate, 'selected')).toBe(true);
});

test('groups job submissions and prefers the selected candidate profile', () => {
  const rows = [
    { id: 1, email: 'Person@Example.com ', status: 'Rejected', job_applications: [{ jd_id: 10, jd_title: 'Developer', status: 'Rejected' }] },
    { id: 2, email: 'person@example.com', status: 'Selected', job_applications: [{ jd_id: 20, jd_title: 'Tester', status: 'Selected' }] },
  ];
  const grouped = dedupeCandidates(rows);
  expect(grouped).toHaveLength(1);
  expect(grouped[0].id).toBe(2);
  expect(grouped[0].job_applications.map(job => job.status)).toEqual(['Rejected', 'Selected']);
  expect(dedupeCandidates(grouped)).toEqual(grouped);
});

test('does not merge different people with the same name', () => {
  expect(dedupeCandidates([{ id: 1, name: 'Alex' }, { id: 2, name: 'Alex' }])).toHaveLength(2);
});

test('does not repeat the same JD when submissions repeat', () => {
  const job = { jd_id: 10, jd_title: 'Developer', status: 'Selected' };
  expect(dedupeCandidates([
    { id: 1, email: 'person@example.com', job_applications: [job] },
    { id: 2, email: 'person@example.com', job_applications: [job] },
  ])[0].job_applications).toHaveLength(1);
});

test('a later rejection outweighs the screening result for the categories', () => {
  const candidate = { status: 'Selected', outcome: 'Rejected', job_applications: [{ jd_id: 1, status: 'Rejected' }] };
  expect(candidateMatchesSelection(candidate, 'rejected')).toBe(true);
  expect(candidateMatchesSelection(candidate, 'selected')).toBe(false);
});

test('a merged row keeps every submission id and each job stage', () => {
  const [row] = dedupeCandidates([
    { id: 1, jd_id: 10, email: 'p@example.com', status: 'Selected', stage_id: 'a', job_applications: [{ jd_id: 10, jd_title: 'Developer', status: 'Selected' }] },
    { id: 2, jd_id: 20, email: 'p@example.com', status: 'Selected', stage_id: 'b', job_applications: [{ jd_id: 20, jd_title: 'Tester', status: 'Selected' }] },
  ]);
  expect(row.member_ids).toEqual([1, 2]);
  expect(row.stage_records.map(r => [r.id, r.jd_title, r.stage_id])).toEqual([[1, 'Developer', 'a'], [2, 'Tester', 'b']]);
  expect(dedupeCandidates([row])).toEqual([row]);
});

test('repeat submissions to one job collapse to the furthest-along one, own job first', () => {
  const steps = [{ id: 'a' }, { id: 'b' }, { id: 'c' }];
  const records = [
    { id: 1, jd_id: 20, jd_title: 'QA', screening_status: 'rejected', hiring_process_steps: steps, stage_id: null },
    { id: 2, jd_id: 10, jd_title: 'DevOps', hiring_process_steps: steps, stage_id: 'b' },
    { id: 3, jd_id: 10, jd_title: 'DevOps', hiring_process_steps: steps, stage_id: 'c' },
    { id: 4, jd_id: 20, jd_title: 'QA', screening_status: 'rejected', hiring_process_steps: steps, stage_id: null },
  ];
  expect(stageRecordsByJob({ id: 2, stage_records: records }).map(r => r.id)).toEqual([3, 1]);
});
