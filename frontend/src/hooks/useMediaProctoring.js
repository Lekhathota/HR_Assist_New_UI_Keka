import { useCallback, useEffect, useRef, useState } from 'react';
import { publicApiPostForm } from '../api.js';
import { captureAndCheck, loadFaceDetector } from '../utils/faceCheck.js';

export const FACE_LIMIT = 2;
// One photo at a random moment in each ~10 second window, so the timing is not predictable.
const SNAPSHOT_MIN_MS = 7000;
const SNAPSHOT_MAX_MS = 13000;
// Recorder timeslice: each chunk is uploaded as it arrives (well under the 4.5 MB request cap).
const TIMESLICE_MS = 10000;
const CAMERA_BITS = 250000;
const SCREEN_BITS = 400000;
const RETRY_MS = 3000;
const DEVICE_LABEL = { camera: 'camera', mic: 'microphone', screen: 'screen sharing' };

const newId = () => window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`;
const pickMime = types => types.find(type => window.MediaRecorder?.isTypeSupported?.(type)) || '';

function mediaErrorText(err, kind) {
  const label = DEVICE_LABEL[kind];
  if (err?.name === 'NotAllowedError') return `Access to your ${label} was blocked. Allow it in the browser prompt or the address bar's site settings, then try again.`;
  if (err?.name === 'NotFoundError') return `No ${label === 'screen sharing' ? 'screen' : label} was found on this device.`;
  if (err?.name === 'NotReadableError') return `Your ${label} is being used by another application. Close it and try again.`;
  return err?.message || `Could not start your ${label}.`;
}

export default function useMediaProctoring(token, { active, initialFaceCount = 0, onViolation, onTerminated } = {}) {
  const [streams, setStreams] = useState({ camera: null, mic: null, screen: null });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  const [reference, setReference] = useState({ status: 'idle', message: '', url: '' });
  const [faceCount, setFaceCount] = useState(0);
  const [faceWarning, setFaceWarning] = useState(null);
  const [terminated, setTerminated] = useState(false);
  const [lost, setLost] = useState([]);
  const [pending, setPending] = useState(0);

  const streamsRef = useRef({ camera: null, mic: null, screen: null });
  const videoRef = useRef(null);
  const recordersRef = useRef([]);
  const snapshotQueueRef = useRef([]);
  const chunkQueueRef = useRef([]);
  const pumpingRef = useRef(false);
  const faceCountRef = useRef(0);
  const terminatedRef = useRef(false);
  const mountedRef = useRef(true);
  const callbacksRef = useRef({ onViolation, onTerminated });
  callbacksRef.current = { onViolation, onTerminated };
  const activeRef = useRef(active);
  activeRef.current = active;

  const supported = typeof navigator !== 'undefined' && !!navigator.mediaDevices?.getUserMedia
    && !!navigator.mediaDevices?.getDisplayMedia && typeof window.MediaRecorder === 'function';

  useEffect(() => {
    faceCountRef.current = Math.max(faceCountRef.current, initialFaceCount);
    setFaceCount(faceCountRef.current);
  }, [initialFaceCount]);

  const syncPending = () => {
    if (mountedRef.current) setPending(snapshotQueueRef.current.length + chunkQueueRef.current.length);
  };

  const terminate = useCallback(() => {
    if (terminatedRef.current) return;
    terminatedRef.current = true;
    setTerminated(true);
    setFaceWarning(null);
    callbacksRef.current.onTerminated?.();
  }, []);

  const applyFaceResult = useCallback(result => {
    faceCountRef.current = Math.max(faceCountRef.current, Number(result.face_violation_count) || 0);
    if (mountedRef.current) setFaceCount(faceCountRef.current);
    if (result.terminated) terminate();
  }, [terminate]);

  // Uploads run one at a time: face photos first (they decide warnings), then video chunks.
  const pump = useCallback(async () => {
    if (pumpingRef.current) return;
    pumpingRef.current = true;
    try {
      while (mountedRef.current && (snapshotQueueRef.current.length || chunkQueueRef.current.length)) {
        const queue = snapshotQueueRef.current.length ? snapshotQueueRef.current : chunkQueueRef.current;
        const item = queue[0];
        const form = new FormData();
        form.append('token', token);
        Object.entries(item.fields).forEach(([key, value]) => form.append(key, String(value)));
        form.append(item.fileField, item.blob, item.filename);
        try {
          const result = await publicApiPostForm(item.path, form);
          queue.shift();
          if (item.fileField === 'image') applyFaceResult(result);
        } catch (err) {
          // 4xx means the server will never accept it (e.g. attempt closed); drop it.
          if (err.status && err.status < 500 && ![408, 429].includes(err.status)) queue.shift();
          else await new Promise(resolve => window.setTimeout(resolve, RETRY_MS));
        }
        syncPending();
      }
    } finally {
      pumpingRef.current = false;
      syncPending();
    }
  }, [token, applyFaceResult]);

  useEffect(() => {
    mountedRef.current = true;
    window.addEventListener('online', pump);
    return () => { mountedRef.current = false; window.removeEventListener('online', pump); };
  }, [pump]);

  const handleEnded = useCallback((kind, stream) => {
    if (streamsRef.current[kind] !== stream) return;
    streamsRef.current = { ...streamsRef.current, [kind]: null };
    setStreams(streamsRef.current);
    // Before the exam starts the setup steps simply ask for the device again.
    if (terminatedRef.current || !activeRef.current) return;
    setLost(prev => (prev.includes(kind) ? prev : [...prev, kind]));
    callbacksRef.current.onViolation?.('media_stopped');
  }, []);

  const attach = useCallback((kind, stream) => {
    streamsRef.current[kind]?.getTracks().forEach(track => track.stop());
    streamsRef.current = { ...streamsRef.current, [kind]: stream };
    setStreams(streamsRef.current);
    stream.getTracks().forEach(track => track.addEventListener('ended', () => handleEnded(kind, stream)));
    if (kind === 'camera') {
      if (!videoRef.current) {
        videoRef.current = document.createElement('video');
        videoRef.current.muted = true;
        videoRef.current.playsInline = true;
      }
      videoRef.current.srcObject = stream;
      videoRef.current.play?.()?.catch?.(() => {});
    }
  }, [handleEnded]);

  const acquire = useCallback(async kind => {
    if (kind === 'screen') {
      const stream = await navigator.mediaDevices.getDisplayMedia({
        video: { displaySurface: 'monitor', frameRate: { ideal: 5, max: 10 }, width: { max: 1920 } },
        audio: false, monitorTypeSurfaces: 'include', selfBrowserSurface: 'exclude', surfaceSwitching: 'exclude',
      });
      const surface = stream.getVideoTracks()[0]?.getSettings?.().displaySurface;
      if (surface && surface !== 'monitor') {
        stream.getTracks().forEach(track => track.stop());
        throw new Error('Share your entire screen. Sharing a single window or tab is not allowed.');
      }
      return stream;
    }
    return navigator.mediaDevices.getUserMedia(kind === 'camera'
      ? { video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: 'user' }, audio: false }
      : { audio: { echoCancellation: true, noiseSuppression: true }, video: false });
  }, []);

  const request = useCallback(async kind => {
    setError('');
    if (!supported) {
      setError('This browser cannot record the exam. Use the latest Chrome, Edge or Firefox on a desktop or laptop computer.');
      return false;
    }
    setBusy(kind);
    try {
      attach(kind, await acquire(kind));
      if (kind === 'camera') loadFaceDetector().catch(() => {});
      return true;
    } catch (err) {
      setError(mediaErrorText(err, kind));
      return false;
    } finally { setBusy(''); }
  }, [acquire, attach, supported]);

  const enqueueSnapshot = useCallback((kind, result) => {
    snapshotQueueRef.current.push({
      path: '/api/assessment/proctoring/snapshot',
      fields: { snapshot_id: newId(), kind, face_ok: result.faceOk, face_count: result.faceCount, issue: result.issue },
      fileField: 'image', blob: result.image, filename: `${kind}.jpg`,
    });
    syncPending();
    return pump();
  }, [pump]);

  const captureReference = useCallback(async () => {
    setError('');
    setReference({ status: 'checking', message: '', url: '' });
    try {
      const result = await captureAndCheck(videoRef.current);
      if (!result.faceOk) {
        setReference({ status: 'failed', message: result.issue === 'looking_away'
          ? 'Look straight at the camera and try again.'
          : 'We could not see your face. Improve the lighting, move closer and try again.', url: '' });
        return false;
      }
      const form = new FormData();
      form.append('token', token);
      form.append('snapshot_id', newId());
      form.append('kind', 'reference');
      form.append('face_ok', 'true');
      form.append('face_count', String(result.faceCount));
      form.append('issue', '');
      form.append('image', result.image, 'reference.jpg');
      await publicApiPostForm('/api/assessment/proctoring/snapshot', form);
      setReference({ status: 'ok', message: '', url: URL.createObjectURL(result.image) });
      return true;
    } catch (err) {
      setReference({ status: 'failed', message: err.message || 'Could not save your photo. Check your connection and try again.', url: '' });
      return false;
    }
  }, [token]);

  const recheckFace = useCallback(async () => {
    try {
      const result = await captureAndCheck(videoRef.current);
      if (result.faceOk) setFaceWarning(null);
      return result.faceOk;
    } catch { return false; }
  }, []);

  const stopRecorders = useCallback(async () => {
    const recorders = recordersRef.current;
    recordersRef.current = [];
    await Promise.all(recorders.map(recorder => (recorder.state === 'inactive' ? null : new Promise(resolve => {
      recorder.addEventListener('stop', resolve, { once: true });
      try { recorder.stop(); } catch { resolve(); }
    }))));
  }, []);

  const startRecorders = useCallback(async () => {
    await stopRecorders();
    const { camera, mic, screen } = streamsRef.current;
    const record = (name, tracks, videoBitsPerSecond, types) => {
      const mimeType = pickMime(types);
      const recorder = new MediaRecorder(new MediaStream(tracks), {
        ...(mimeType ? { mimeType } : {}), videoBitsPerSecond, audioBitsPerSecond: 32000,
      });
      const sessionId = newId();
      let sequence = 0;
      recorder.ondataavailable = event => {
        if (!event.data?.size) return;
        chunkQueueRef.current.push({
          path: '/api/assessment/proctoring/recording',
          fields: { stream: name, session_id: sessionId, sequence: sequence++ },
          fileField: 'chunk', blob: event.data, filename: `${name}.webm`,
        });
        syncPending();
        pump();
      };
      recorder.start(TIMESLICE_MS);
      recordersRef.current.push(recorder);
    };
    if (camera) {
      record('camera', [...camera.getVideoTracks(), ...(mic?.getAudioTracks() || [])], CAMERA_BITS,
        ['video/webm;codecs=vp8,opus', 'video/webm', 'video/mp4']);
    }
    if (screen) record('screen', screen.getVideoTracks(), SCREEN_BITS, ['video/webm;codecs=vp8', 'video/webm', 'video/mp4']);
  }, [pump, stopRecorders]);

  const stopTracks = useCallback(() => {
    Object.values(streamsRef.current).forEach(stream => stream?.getTracks().forEach(track => track.stop()));
    streamsRef.current = { camera: null, mic: null, screen: null };
    if (mountedRef.current) setStreams(streamsRef.current);
  }, []);

  /** Ends the session: flushes the final recording chunks, releases devices, keeps uploading. */
  const finish = useCallback(async () => {
    await stopRecorders();
    stopTracks();
    pump();
  }, [pump, stopRecorders, stopTracks]);

  /** Re-acquires devices the candidate turned off. Must be called from a click. */
  const restore = useCallback(async () => {
    setError('');
    // Screen first: the picker needs the click's user activation.
    const missing = ['screen', 'camera', 'mic'].filter(kind => !streamsRef.current[kind]);
    for (const kind of missing) {
      setBusy(kind);
      try { attach(kind, await acquire(kind)); } catch (err) {
        setError(mediaErrorText(err, kind));
        setBusy('');
        return false;
      }
    }
    setBusy('');
    setLost([]);
    await startRecorders();
    return true;
  }, [acquire, attach, startRecorders]);

  useEffect(() => {
    if (!active) return undefined;
    startRecorders();
    let timer;
    let cancelled = false;
    const tick = async () => {
      if (cancelled || terminatedRef.current) return;
      if (streamsRef.current.camera && videoRef.current?.videoWidth) {
        try {
          const result = await captureAndCheck(videoRef.current, { width: 320, quality: 0.7 });
          if (cancelled) return;
          if (!result.faceOk) {
            faceCountRef.current += 1;
            setFaceCount(faceCountRef.current);
            setFaceWarning({ issue: result.issue, count: faceCountRef.current });
          }
          enqueueSnapshot('periodic', result);
          if (faceCountRef.current >= FACE_LIMIT) terminate();
        } catch { /* A frame that cannot be read is not the candidate's fault. */ }
      }
      if (!cancelled && !terminatedRef.current) {
        timer = window.setTimeout(tick, SNAPSHOT_MIN_MS + Math.random() * (SNAPSHOT_MAX_MS - SNAPSHOT_MIN_MS));
      }
    };
    timer = window.setTimeout(tick, SNAPSHOT_MIN_MS + Math.random() * (SNAPSHOT_MAX_MS - SNAPSHOT_MIN_MS));
    return () => { cancelled = true; window.clearTimeout(timer); };
  }, [active, enqueueSnapshot, startRecorders, terminate]);

  useEffect(() => () => {
    recordersRef.current.forEach(recorder => { try { recorder.stop(); } catch { /* already stopped */ } });
    Object.values(streamsRef.current).forEach(stream => stream?.getTracks().forEach(track => track.stop()));
  }, []);

  useEffect(() => () => { if (reference.url) URL.revokeObjectURL(reference.url); }, [reference.url]);

  return {
    supported, streams, error, busy, reference, faceCount, faceWarning, terminated, lost, pending,
    ready: Boolean(streams.camera && streams.mic && streams.screen && reference.status === 'ok'),
    requestCamera: () => request('camera'),
    requestMicrophone: () => request('mic'),
    requestScreen: () => request('screen'),
    captureReference, recheckFace, restore, finish,
  };
}
