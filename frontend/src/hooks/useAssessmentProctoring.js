import { useCallback, useEffect, useRef, useState } from 'react';
import { publicApiPost } from '../api.js';

const LIMIT = 2;
const storageKey = token => `assessment_proctoring:${token}`;
const readStored = token => {
  try { return JSON.parse(sessionStorage.getItem(storageKey(token)) || '{}'); } catch { return {}; }
};

export default function useAssessmentProctoring(token, assessment) {
  const [active, setActive] = useState(false);
  const [starting, setStarting] = useState(false);
  const [count, setCount] = useState(0);
  const [warning, setWarning] = useState(false);
  const [terminated, setTerminated] = useState(false);
  const [error, setError] = useState('');
  const [syncing, setSyncing] = useState(false);
  const activeRef = useRef(false);
  const countRef = useRef(0);
  const queueRef = useRef([]);
  const syncRef = useRef(null);
  const departureRef = useRef(false);
  const rearmTimerRef = useRef(null);
  const mountedRef = useRef(true);
  const suppressRef = useRef(false);

  const store = useCallback(() => {
    try { sessionStorage.setItem(storageKey(token), JSON.stringify({ count: countRef.current, pending: queueRef.current })); } catch { /* Server remains authoritative. */ }
  }, [token]);

  const stop = useCallback(() => {
    activeRef.current = false;
    setActive(false);
    if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
  }, []);

  const sync = useCallback(() => {
    if (syncRef.current) return syncRef.current;
    const task = async () => {
      if (mountedRef.current) { setSyncing(true); setError(''); }
      try {
        while (queueRef.current.length) {
          const event = queueRef.current[0];
          const result = await publicApiPost('/api/assessment/proctoring-event', { token, ...event }, { keepalive: true });
          queueRef.current.shift();
          countRef.current = Math.min(LIMIT, Math.max(countRef.current, result.violation_count || 0));
          store();
          if (mountedRef.current) setCount(countRef.current);
          if (result.terminated) {
            queueRef.current = [];
            store();
            activeRef.current = false;
            if (mountedRef.current) { setTerminated(true); stop(); }
            break;
          }
        }
        return countRef.current < LIMIT;
      } catch {
        if (mountedRef.current) setError('Could not sync exam monitoring. Check your connection and retry before continuing.');
        return false;
      } finally {
        if (mountedRef.current) setSyncing(false);
      }
    };
    syncRef.current = task().finally(() => { syncRef.current = null; });
    return syncRef.current;
  }, [token, store, stop]);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; activeRef.current = false; };
  }, []);

  useEffect(() => {
    const stored = readStored(token);
    queueRef.current = Array.isArray(stored.pending) ? stored.pending.slice(0, LIMIT) : [];
    countRef.current = Math.min(LIMIT, stored.count || 0);
    setCount(countRef.current);
    if (countRef.current >= LIMIT) setTerminated(true);
    if (queueRef.current.length) sync();
  }, [token, sync]);

  useEffect(() => {
    if (!assessment) return;
    countRef.current = Math.min(LIMIT, Math.max(countRef.current, assessment.proctoring_violation_count || 0));
    setCount(countRef.current);
    if (countRef.current >= LIMIT) setTerminated(true);
  }, [assessment]);

  useEffect(() => {
    window.addEventListener('online', sync);
    const timer = window.setInterval(() => { if (queueRef.current.length) sync(); }, 5000);
    return () => { window.removeEventListener('online', sync); window.clearInterval(timer); };
  }, [sync]);

  const incident = useCallback(reason => {
    if (!activeRef.current || countRef.current >= LIMIT || departureRef.current || suppressRef.current) return;
    departureRef.current = true;
    window.clearTimeout(rearmTimerRef.current);
    countRef.current += 1;
    queueRef.current.push({ event_id: window.crypto?.randomUUID?.() || `${Date.now()}-${Math.random().toString(36).slice(2)}`, reason });
    store();
    setCount(countRef.current);
    setWarning(true);
    if (countRef.current >= LIMIT) {
      setTerminated(true);
      stop();
    }
    sync();
  }, [store, stop, sync]);

  const rearm = useCallback(() => {
    window.clearTimeout(rearmTimerRef.current);
    if (document.visibilityState !== 'hidden') {
      rearmTimerRef.current = window.setTimeout(() => {
        if (document.visibilityState !== 'hidden') departureRef.current = false;
      }, 300);
    }
  }, []);

  useEffect(() => {
    if (!active) return undefined;
    const examUrl = window.location.href;
    const examState = window.history.state;
    window.history.pushState(examState, '', examUrl);
    const hidden = () => {
      if (document.visibilityState === 'hidden') {
        window.clearTimeout(rearmTimerRef.current);
        incident('tab_hidden');
      } else rearm();
    };
    const blur = () => { window.clearTimeout(rearmTimerRef.current); incident('window_blur'); };
    const fullscreen = () => { if (!document.fullscreenElement) incident('fullscreen_exit'); else rearm(); };
    const back = () => {
      if (!activeRef.current) return;
      window.history.pushState(examState, '', examUrl);
      incident('back_navigation');
      rearm();
    };
    const unload = event => {
      if (!activeRef.current) return;
      incident('page_unload');
      event.preventDefault();
      event.returnValue = '';
      rearm();
    };
    const shortcut = event => {
      const key = event.key.toLowerCase();
      const restricted = ['f5', 'f11'].includes(key) || (event.altKey && ['arrowleft', 'arrowright'].includes(key))
        || ((event.ctrlKey || event.metaKey) && ['l', 't', 'n', 'w', 'r', 'tab', 'pageup', 'pagedown'].includes(key));
      if (!restricted || event.repeat || !activeRef.current) return;
      event.preventDefault();
      incident('browser_shortcut');
      rearm();
    };
    const link = event => {
      if (!activeRef.current || !event.target.closest?.('a[href]')) return;
      event.preventDefault();
      event.stopPropagation();
      incident('navigation_attempt');
      rearm();
    };
    document.addEventListener('visibilitychange', hidden);
    window.addEventListener('blur', blur);
    window.addEventListener('focus', rearm);
    document.addEventListener('fullscreenchange', fullscreen);
    window.addEventListener('popstate', back, true);
    window.addEventListener('beforeunload', unload);
    window.addEventListener('keydown', shortcut, true);
    document.addEventListener('click', link, true);
    if (document.visibilityState === 'hidden') incident('tab_hidden');
    else if (!document.fullscreenElement) incident('fullscreen_exit');
    return () => {
      window.clearTimeout(rearmTimerRef.current);
      document.removeEventListener('visibilitychange', hidden);
      window.removeEventListener('blur', blur);
      window.removeEventListener('focus', rearm);
      document.removeEventListener('fullscreenchange', fullscreen);
      window.removeEventListener('popstate', back, true);
      window.removeEventListener('beforeunload', unload);
      window.removeEventListener('keydown', shortcut, true);
      document.removeEventListener('click', link, true);
    };
  }, [active, incident, rearm, sync]);

  const enterFullscreen = async () => {
    if (!document.documentElement.requestFullscreen) throw new Error('This exam requires fullscreen. Use a desktop browser that supports fullscreen.');
    if (!document.fullscreenElement) await document.documentElement.requestFullscreen();
  };

  // Browser pickers (e.g. re-sharing the screen) blur the page; they are not departures.
  const withoutMonitoring = useCallback(async task => {
    suppressRef.current = true;
    try { return await task(); } finally {
      window.setTimeout(() => { suppressRef.current = false; }, 500);
    }
  }, []);

  const markTerminated = useCallback(() => {
    queueRef.current = [];
    store();
    setTerminated(true);
    stop();
  }, [store, stop]);

  const start = async (acceptedTerms, recordingConsent) => {
    if (!acceptedTerms || !recordingConsent || starting || countRef.current >= LIMIT) return null;
    setStarting(true); setError('');
    try {
      await enterFullscreen();
      if (queueRef.current.length && !await sync()) return null;
      const result = await publicApiPost('/api/assessment/start', { token, accepted_terms: true, recording_consent: true });
      countRef.current = Math.max(countRef.current, result.assessment?.proctoring_violation_count || 0);
      setCount(countRef.current);
      if (countRef.current >= LIMIT) { setTerminated(true); stop(); return null; }
      departureRef.current = false;
      activeRef.current = true;
      setActive(true);
      return result.assessment;
    } catch (err) {
      stop();
      if (err.status === 409 && err.message?.toLowerCase().includes('terminated')) setTerminated(true);
      setError(err.message || 'Allow fullscreen to start the assessment.');
      return null;
    } finally { setStarting(false); }
  };

  const resume = async () => {
    setError('');
    try {
      // Request fullscreen synchronously with the button's user gesture.
      await enterFullscreen();
      if (!await sync()) return;
      departureRef.current = false;
      setWarning(false);
    } catch (err) { setError(err.message || 'Return to fullscreen to continue.'); }
  };

  return {
    active, starting, count, warning, terminated, error, syncing,
    start, resume, stop, sync, report: incident, withoutMonitoring, markTerminated,
  };
}
