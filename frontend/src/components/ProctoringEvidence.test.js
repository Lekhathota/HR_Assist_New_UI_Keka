import { fixLiveRecordingDuration } from './ProctoringEvidence.jsx';

function fakeVideo(duration) {
  const video = new EventTarget();
  video.duration = duration;
  video.currentTime = 0;
  return video;
}

beforeEach(() => jest.useFakeTimers());
afterEach(() => jest.useRealTimers());

test('a live recording with unknown length is scanned, then rewound to the start', () => {
  const video = fakeVideo(Infinity);
  const ready = jest.fn();
  fixLiveRecordingDuration(video, ready);
  expect(video.currentTime).toBe(1e101);
  expect(ready).not.toHaveBeenCalled();
  video.duration = 70.4;
  video.dispatchEvent(new Event('durationchange'));
  expect(video.currentTime).toBe(0);
  expect(ready).toHaveBeenCalledTimes(1);
  jest.advanceTimersByTime(10000);
  expect(ready).toHaveBeenCalledTimes(1);
});

test('a recording with a known length is ready immediately', () => {
  const video = fakeVideo(42);
  const ready = jest.fn();
  fixLiveRecordingDuration(video, ready);
  expect(ready).toHaveBeenCalledTimes(1);
  expect(video.currentTime).toBe(0);
});

test('the player is shown even if the browser never reports a length', () => {
  const video = fakeVideo(Infinity);
  const ready = jest.fn();
  fixLiveRecordingDuration(video, ready);
  jest.advanceTimersByTime(5000);
  expect(ready).toHaveBeenCalledTimes(1);
  expect(video.currentTime).toBe(0);
});
