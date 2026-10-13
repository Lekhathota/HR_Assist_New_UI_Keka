import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import useMediaProctoring from './useMediaProctoring.js';
import { publicApiPostForm } from '../api.js';
import { captureAndCheck, loadFaceDetector } from '../utils/faceCheck.js';

jest.mock('../api.js', () => ({ publicApiPostForm: jest.fn() }));
jest.mock('../utils/faceCheck.js', () => ({ captureAndCheck: jest.fn(), loadFaceDetector: jest.fn() }));

class FakeTrack extends EventTarget {
  constructor(kind, settings = {}) { super(); this.kind = kind; this.settings = settings; this.stop = jest.fn(); }
  getSettings() { return this.settings; }
}
class FakeStream {
  constructor(tracks) { this.tracks = tracks; }
  getTracks() { return this.tracks; }
  getVideoTracks() { return this.tracks.filter(track => track.kind === 'video'); }
  getAudioTracks() { return this.tracks.filter(track => track.kind === 'audio'); }
}
let recorders;
class FakeRecorder extends EventTarget {
  static isTypeSupported() { return true; }
  constructor(stream, options) { super(); this.stream = stream; this.options = options; this.state = 'inactive'; recorders.push(this); }
  start(timeslice) { this.timeslice = timeslice; this.state = 'recording'; }
  emit(data) { this.ondataavailable?.({ data }); }
  stop() {
    this.state = 'inactive';
    this.emit(new Blob(['final'], { type: 'video/webm' }));
    this.dispatchEvent(new Event('stop'));
  }
}

let hook, root, container, options;
function Harness(props) {
  hook = useMediaProctoring('test-token', props);
  return null;
}
const render = props => act(async () => root.render(<Harness {...options} {...props} />));
const uploads = kind => publicApiPostForm.mock.calls.filter(([, form]) => (kind ? form.get('kind') === kind : true));
const face = (faceOk, issue = faceOk ? '' : 'no_face') => ({ faceOk, faceCount: faceOk ? 1 : 0, issue, image: new Blob(['jpg'], { type: 'image/jpeg' }) });
let screenSurface;

async function setUpDevices() {
  await act(async () => { await hook.requestCamera(); });
  await act(async () => { await hook.captureReference(); });
  await act(async () => { await hook.requestMicrophone(); });
  await act(async () => { await hook.requestScreen(); });
}

beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  jest.useFakeTimers();
  recorders = [];
  screenSurface = 'monitor';
  window.MediaRecorder = FakeRecorder;
  window.MediaStream = FakeStream;
  global.MediaStream = FakeStream;
  global.URL.createObjectURL = jest.fn(() => 'blob:photo');
  global.URL.revokeObjectURL = jest.fn();
  jest.spyOn(HTMLMediaElement.prototype, 'play').mockResolvedValue(undefined);
  Object.defineProperty(HTMLVideoElement.prototype, 'videoWidth', { configurable: true, get: () => 640 });
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: {
    getUserMedia: jest.fn(async constraints => new FakeStream([new FakeTrack(constraints.video ? 'video' : 'audio')])),
    getDisplayMedia: jest.fn(async () => new FakeStream([new FakeTrack('video', { displaySurface: screenSurface })])),
  } });
  loadFaceDetector.mockResolvedValue({});
  captureAndCheck.mockResolvedValue(face(true));
  publicApiPostForm.mockImplementation(async (path, form) => (path.endsWith('/snapshot')
    ? { face_ok: form.get('face_ok') === 'true', face_violation_count: 0, terminated: false } : { stored: true }));
  options = { active: false, onViolation: jest.fn(), onTerminated: jest.fn() };
  container = document.createElement('div');
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  jest.clearAllTimers();
  jest.useRealTimers();
  jest.restoreAllMocks();
  jest.clearAllMocks();
});

test('setup verifies the face photo and becomes ready only with camera, microphone and screen', async () => {
  await render();
  await act(async () => { await hook.requestCamera(); });
  expect(hook.ready).toBe(false);
  await act(async () => { await hook.captureReference(); });
  const [path, form] = uploads('reference')[0];
  expect(path).toBe('/api/assessment/proctoring/snapshot');
  expect(form.get('token')).toBe('test-token');
  expect(form.get('face_ok')).toBe('true');
  expect(form.get('image')).toBeInstanceOf(Blob);
  expect(hook.reference.status).toBe('ok');
  await act(async () => { await hook.requestMicrophone(); });
  expect(hook.ready).toBe(false);
  await act(async () => { await hook.requestScreen(); });
  expect(hook.ready).toBe(true);
});

test('a reference photo without a face is rejected and not uploaded', async () => {
  captureAndCheck.mockResolvedValue(face(false));
  await render();
  await act(async () => { await hook.requestCamera(); });
  await act(async () => { await hook.captureReference(); });
  expect(hook.reference.status).toBe('failed');
  expect(hook.reference.message).toContain('could not see your face');
  expect(uploads()).toHaveLength(0);
});

test('sharing a window instead of the entire screen is refused', async () => {
  screenSurface = 'window';
  await render();
  await act(async () => { await hook.requestScreen(); });
  expect(hook.streams.screen).toBeNull();
  expect(hook.error).toContain('Share your entire screen');
});

test('blocked camera permission explains how to allow it', async () => {
  navigator.mediaDevices.getUserMedia.mockRejectedValue(Object.assign(new Error('denied'), { name: 'NotAllowedError' }));
  await render();
  await act(async () => { await hook.requestCamera(); });
  expect(hook.error).toContain('Access to your camera was blocked');
});

test('exam photos are taken at random about every 10 seconds; the second missing face terminates', async () => {
  await render();
  await setUpDevices();
  captureAndCheck.mockResolvedValue(face(false));
  await render({ active: true });
  await act(async () => { jest.advanceTimersByTime(6999); });
  expect(captureAndCheck).toHaveBeenCalledTimes(1); // the reference photo only
  await act(async () => { jest.advanceTimersByTime(6001); });
  expect(hook.faceWarning).toEqual({ issue: 'no_face', count: 1 });
  expect(hook.terminated).toBe(false);
  const [, first] = uploads('periodic')[0];
  expect(first.get('face_ok')).toBe('false');
  expect(first.get('issue')).toBe('no_face');
  await act(async () => { jest.advanceTimersByTime(13000); });
  expect(hook.faceCount).toBe(2);
  expect(hook.terminated).toBe(true);
  expect(options.onTerminated).toHaveBeenCalledTimes(1);
  expect(uploads('periodic')).toHaveLength(2);
  await act(async () => { jest.advanceTimersByTime(30000); });
  expect(uploads('periodic')).toHaveLength(2);
});

test('a visible face raises no warning, and the server can terminate the attempt', async () => {
  await render();
  await setUpDevices();
  publicApiPostForm.mockImplementation(async path => (path.endsWith('/snapshot')
    ? { face_violation_count: 2, terminated: true } : { stored: true }));
  await render({ active: true });
  await act(async () => { jest.advanceTimersByTime(13000); });
  expect(hook.faceWarning).toBeNull();
  expect(hook.terminated).toBe(true);
  expect(options.onTerminated).toHaveBeenCalled();
});

test('camera with microphone and the screen are recorded and uploaded chunk by chunk', async () => {
  await render();
  await setUpDevices();
  await render({ active: true });
  expect(recorders).toHaveLength(2);
  const [camera, screen] = recorders;
  expect(camera.timeslice).toBe(10000);
  expect(camera.stream.getAudioTracks()).toHaveLength(1);
  expect(camera.stream.getVideoTracks()).toHaveLength(1);
  expect(screen.stream.getAudioTracks()).toHaveLength(0);
  await act(async () => {
    camera.emit(new Blob(['c0'], { type: 'video/webm' }));
    camera.emit(new Blob(['c1'], { type: 'video/webm' }));
    screen.emit(new Blob(['s0'], { type: 'video/webm' }));
  });
  const chunks = publicApiPostForm.mock.calls.filter(([path]) => path === '/api/assessment/proctoring/recording').map(([, form]) => form);
  expect(chunks.map(form => [form.get('stream'), form.get('sequence')])).toEqual([['camera', '0'], ['camera', '1'], ['screen', '0']]);
  expect(chunks[0].get('session_id')).toBe(chunks[1].get('session_id'));
  expect(chunks[0].get('chunk')).toBeInstanceOf(Blob);
  await act(async () => { await hook.finish(); });
  expect(recorders.every(recorder => recorder.state === 'inactive')).toBe(true);
  expect(publicApiPostForm.mock.calls.filter(([path]) => path.endsWith('/recording'))).toHaveLength(5);
});

test('failed uploads are retried until they reach the server', async () => {
  await render();
  await setUpDevices();
  await render({ active: true });
  publicApiPostForm.mockRejectedValueOnce(Object.assign(new Error('offline'), { status: 0 }));
  await act(async () => { recorders[0].emit(new Blob(['c0'], { type: 'video/webm' })); });
  expect(hook.pending).toBe(1);
  await act(async () => { jest.advanceTimersByTime(3000); });
  expect(hook.pending).toBe(0);
  const sent = publicApiPostForm.mock.calls.filter(([path]) => path.endsWith('/recording'));
  expect(sent).toHaveLength(2);
  expect(sent[1][1].get('sequence')).toBe('0');
});

test('turning off a device during the exam is a violation and can be restored', async () => {
  await render();
  await setUpDevices();
  await render({ active: true });
  const screenTrack = hook.streams.screen.getVideoTracks()[0];
  await act(async () => { screenTrack.dispatchEvent(new Event('ended')); });
  expect(hook.lost).toEqual(['screen']);
  expect(options.onViolation).toHaveBeenCalledWith('media_stopped');
  await act(async () => { await hook.restore(); });
  expect(navigator.mediaDevices.getDisplayMedia).toHaveBeenCalledTimes(2);
  expect(hook.lost).toEqual([]);
  expect(hook.streams.screen).not.toBeNull();
  expect(recorders.slice(-2).every(recorder => recorder.state === 'recording')).toBe(true);
});

test('stopping a device before the exam starts is not a violation', async () => {
  await render();
  await setUpDevices();
  await act(async () => { hook.streams.mic.getAudioTracks()[0].dispatchEvent(new Event('ended')); });
  expect(hook.streams.mic).toBeNull();
  expect(hook.lost).toEqual([]);
  expect(options.onViolation).not.toHaveBeenCalled();
  expect(hook.ready).toBe(false);
});
