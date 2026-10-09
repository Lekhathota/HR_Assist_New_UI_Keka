import { dedupeCandidates, candidateMatchesSelection } from './candidateGrouping';

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
