import { buildStages } from './StageTrackerDelivery.jsx';

const steps = [{ id: 's1', name: 'Screening' }, { id: 's2', name: 'Technical' }, { id: 's3', name: 'HR Round' }];

test('uses the JD hiring process and marks the current step', () => {
  const { items, label, tone } = buildStages({ screeningStatus: 'accepted', steps, stageId: 's2' });
  expect(items.map(i => `${i.name}:${i.state}`)).toEqual(['Screening:ok', 'Technical:current', 'HR Round:none']);
  expect(label).toBe('Technical');
  expect(tone).toBe('ok');
});

test('flags hold and rejection on the current step', () => {
  expect(buildStages({ steps, stageId: 's1', onHold: true }).label).toBe('Screening · On hold');
  const rejected = buildStages({ screeningStatus: 'rejected', steps, stageId: 's1' });
  expect(rejected.items[0].state).toBe('bad');
  expect(rejected.label).toBe('Rejected');
  expect(buildStages({ steps, stageId: null }).label).toBe('Not started');
});

test('without a hiring process it shows real screening, assessment and interview progress', () => {
  expect(buildStages({ screeningStatus: null }).items.map(i => i.state)).toEqual(['current', 'none', 'none']);
  const scheduled = buildStages({ screeningStatus: 'accepted', hiringStage: 'Interview Scheduled', assessmentStatus: 'PASSED' });
  expect(scheduled.items.map(i => i.state)).toEqual(['ok', 'ok', 'current']);
  expect(scheduled.label).toBe('Interview Scheduled');
  expect(buildStages({ screeningStatus: 'accepted', hiringStage: 'Interview Completed' }).items[2].state).toBe('ok');
  expect(buildStages({ screeningStatus: 'waitlisted' }).label).toBe('Waitlisted');
});

test('assessment outcomes show on the tracker without a hiring process', () => {
  const cases = [
    ['SENT', 'current', 'Assessment Sent', 'ok'], ['IN_PROGRESS', 'current', 'Assessment In Progress', 'ok'],
    ['PASSED', 'ok', 'Assessment Passed', 'ok'], ['FAILED', 'bad', 'Assessment Failed', 'bad'],
    ['TERMINATED', 'bad', 'Assessment Terminated', 'bad'],
  ];
  cases.forEach(([assessmentStatus, state, label, tone]) => {
    const result = buildStages({ screeningStatus: 'accepted', assessmentStatus });
    expect(result.items.map(i => i.name)).toEqual(['Screening', 'Assessment', 'Interview']);
    expect(result.items[1].state).toBe(state);
    expect(result.label).toBe(label);
    expect(result.tone).toBe(tone);
  });
});

test('a configured assessment step reflects a failed or terminated attempt', () => {
  const process = [{ id: 's1', name: 'Screening' }, { id: 's2', name: 'Online Assessment' }, { id: 's3', name: 'Interview' }];
  const terminated = buildStages({ screeningStatus: 'accepted', steps: process, stageId: 's1', assessmentStatus: 'TERMINATED' });
  expect(terminated.items.map(i => i.state)).toEqual(['ok', 'bad', 'none']);
  expect(terminated.label).toBe('Assessment Terminated');
  expect(terminated.tone).toBe('bad');
  const advanced = buildStages({ screeningStatus: 'accepted', steps: process, stageId: 's3', assessmentStatus: 'PASSED' });
  expect(advanced.items.map(i => i.state)).toEqual(['ok', 'ok', 'current']);
  expect(advanced.label).toBe('Interview');
});
