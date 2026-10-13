import React, { useEffect, useState } from 'react';
import { apiGet, apiGetBlob } from '../api.js';

const PREVIEW_COUNT = 12;
const ISSUE_LABEL = { no_face: 'No face', looking_away: 'Looking away' };
const REASON_LABEL = {
  tab_hidden: 'Switched tab', window_blur: 'Left the window', fullscreen_exit: 'Exited fullscreen',
  back_navigation: 'Pressed Back', navigation_attempt: 'Clicked a link', browser_shortcut: 'Browser shortcut',
  page_unload: 'Reloaded or closed the page', media_stopped: 'Turned off camera, microphone or screen sharing',
  no_face: 'Face not detected', looking_away: 'Looked away from the screen',
};

const formatTime = value => (value ? new Date(value).toLocaleString() : '');
const formatSize = bytes => (bytes > 1048576 ? `${(bytes / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`);

function useObjectUrl(load, deps) {
  const [url, setUrl] = useState('');
  useEffect(() => {
    let cancelled = false;
    let created = '';
    load().then(blob => {
      if (cancelled || !blob) return;
      created = URL.createObjectURL(blob);
      setUrl(created);
    }).catch(() => {});
    return () => { cancelled = true; if (created) URL.revokeObjectURL(created); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return url;
}

function SnapshotThumb({ assessmentId, snapshot }) {
  const url = useObjectUrl(
    () => apiGetBlob(`/api/assessment/${assessmentId}/proctoring/snapshots/${encodeURIComponent(snapshot.snapshot_id)}`),
    [assessmentId, snapshot.snapshot_id]);
  const flagged = snapshot.kind === 'periodic' && !snapshot.face_ok;
  return <figure className={`ab-proctor-thumb ${flagged ? 'flagged' : ''}`}>
    {url ? <img src={url} alt={`Candidate ${snapshot.kind === 'reference' ? 'at verification' : 'during exam'}, ${formatTime(snapshot.captured_at)}`} />
      : <div className="ab-proctor-thumb-loading" aria-hidden="true" />}
    <figcaption>
      {snapshot.kind === 'reference' ? 'Reference photo' : flagged ? ISSUE_LABEL[snapshot.issue] || 'Flagged' : 'Face visible'}
      <span>{formatTime(snapshot.captured_at)}</span>
    </figcaption>
  </figure>;
}

function RecordingPlayer({ assessmentId, recording }) {
  const [state, setState] = useState({ status: 'idle', url: '', loaded: 0 });
  useEffect(() => () => { if (state.url) URL.revokeObjectURL(state.url); }, [state.url]);
  const load = async () => {
    setState({ status: 'loading', url: '', loaded: 0 });
    try {
      const parts = [];
      // Each chunk is a continuation of the same WebM stream, so they must be joined in order.
      for (const sequence of recording.chunks) {
        parts.push(await apiGetBlob(`/api/assessment/${assessmentId}/proctoring/recordings/${recording.stream}/${encodeURIComponent(recording.session_id)}/${sequence}`));
        setState(prev => ({ ...prev, loaded: parts.length }));
      }
      setState({ status: 'ready', url: URL.createObjectURL(new Blob(parts, { type: recording.mime_type })), loaded: parts.length });
    } catch {
      setState({ status: 'error', url: '', loaded: 0 });
    }
  };
  return <div className="ab-proctor-recording">
    <div className="ab-proctor-recording-head">
      <strong><i className={`fas ${recording.stream === 'screen' ? 'fa-desktop' : 'fa-video'}`} aria-hidden="true" /> {recording.stream === 'screen' ? 'Screen recording' : 'Camera and microphone'}</strong>
      <span>{formatTime(recording.started_at)} · about {Math.max(1, Math.round(recording.chunks.length / 6))} min · {formatSize(recording.bytes)}</span>
    </div>
    {state.status === 'ready'
      ? <video controls src={state.url} className="ab-proctor-video" />
      : <button type="button" className="btn btn-secondary" disabled={state.status === 'loading'} onClick={load}>
        {state.status === 'loading' ? `Loading ${state.loaded} / ${recording.chunks.length}…` : 'Load recording'}</button>}
    {state.status === 'error' && <p className="ab-error" role="alert">Could not load this recording.</p>}
  </div>;
}

export default function ProctoringEvidence({ assessmentId }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState('');
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiGet(`/api/assessment/${assessmentId}/proctoring`)
      .then(result => { if (!cancelled) setData(result); })
      .catch(err => { if (!cancelled) setError(err.message || 'Could not load proctoring evidence.'); });
    return () => { cancelled = true; };
  }, [assessmentId]);

  if (error) return <div className="ab-settings white-card"><h2>Proctoring evidence</h2><p className="ab-error">{error}</p></div>;
  if (!data) return null;
  const snapshots = data.snapshots || [];
  const important = snapshots.filter(s => s.kind === 'reference' || !s.face_ok);
  const rest = snapshots.filter(s => s.kind !== 'reference' && s.face_ok);
  const shown = showAll ? [...important, ...rest] : [...important, ...rest.slice(-PREVIEW_COUNT)];

  return <section className="ab-settings white-card ab-proctoring" aria-labelledby="ab-proctoring-title">
    <h2 id="ab-proctoring-title"><i className="fas fa-user-shield" aria-hidden="true" /> Proctoring evidence · {data.candidate_name}</h2>
    <p className="ab-proctor-summary">
      Face warnings: <strong>{data.face_violation_count} / 2</strong> · Focus and recording warnings: <strong>{data.proctoring_violation_count} / 2</strong>
      {data.recording_consent_at && <> · Recording consent given {formatTime(data.recording_consent_at)}</>}
    </p>
    {data.events?.length > 0 && <ul className="ab-proctor-events">
      {data.events.map((event, index) => <li key={event.event_id || event.snapshot_id || index}>
        <span>{formatTime(event.recorded_at)}</span> {REASON_LABEL[event.reason || event.issue] || event.reason || event.issue}
      </li>)}
    </ul>}
    <h3>Recordings</h3>
    {data.recordings?.length
      ? <div className="ab-proctor-recordings">{data.recordings.map(recording =>
        <RecordingPlayer key={`${recording.stream}-${recording.session_id}`} assessmentId={assessmentId} recording={recording} />)}</div>
      : <p className="ab-proctor-empty">No recordings yet.</p>}
    <h3>Face photos ({snapshots.length})</h3>
    {snapshots.length
      ? <div className="ab-proctor-grid">{shown.map(s => <SnapshotThumb key={s.snapshot_id} assessmentId={assessmentId} snapshot={s} />)}</div>
      : <p className="ab-proctor-empty">No photos yet.</p>}
    {!showAll && rest.length > PREVIEW_COUNT && <button type="button" className="btn btn-secondary" onClick={() => setShowAll(true)}>
      Show all {snapshots.length} photos</button>}
  </section>;
}
