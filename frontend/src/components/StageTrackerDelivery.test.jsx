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

test('without a hiring process it shows real screening and interview progress', () => {
  expect(buildStages({ screeningStatus: null }).items.map(i => i.state)).toEqual(['current', 'none']);
  const scheduled = buildStages({ screeningStatus: 'accepted', hiringStage: 'Interview Scheduled' });
  expect(scheduled.items.map(i => i.state)).toEqual(['ok', 'current']);
  expect(scheduled.label).toBe('Interview Scheduled');
  expect(buildStages({ screeningStatus: 'accepted', hiringStage: 'Interview Completed' }).items[1].state).toBe('ok');
  expect(buildStages({ screeningStatus: 'waitlisted' }).label).toBe('Waitlisted');
});
