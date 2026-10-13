import React, { useState } from 'react';
import { CameraPreview, MicMeter } from './ProctoringMedia.jsx';

const STEPS = [
  { key: 'consent', label: 'Permissions', icon: 'fa-user-shield' },
  { key: 'camera', label: 'Face photo', icon: 'fa-camera' },
  { key: 'mic', label: 'Microphone', icon: 'fa-microphone' },
  { key: 'screen', label: 'Screen', icon: 'fa-desktop' },
];

/** Pre-exam wizard: recording consent, face capture, microphone check and screen sharing. */
export default function ProctoringSetup({ media, proctoring, resuming, onBack, onStarted }) {
  const [step, setStep] = useState(0);
  const [consent, setConsent] = useState(false);
  const { streams, reference, busy } = media;
  const done = [consent, reference.status === 'ok' && !!streams.camera, !!streams.mic, !!streams.screen];
  const current = STEPS[step].key;
  const canStart = consent && media.ready && !proctoring.starting && !proctoring.syncing;

  const start = async () => {
    const started = await proctoring.start(true, consent);
    if (started) onStarted(started);
  };

  return <div className="ca-page ca-welcome-page" id="ca-root"><section className="ca-exam-rules ca-setup">
    <div className="ca-welcome-topbar">
      <img src="/ShimentoX-Logo-Dark.png" alt="ShimentoX" className="ca-welcome-logo" />
      <span className="ca-welcome-badge"><i className="fas fa-shield-alt" aria-hidden="true" /> Proctoring setup</span>
    </div>
    <header className="ca-welcome-heading">
      <span className="ca-welcome-eyebrow">SET UP EXAM MONITORING</span>
      <h1>Let’s get your devices ready</h1>
      <p>This exam is proctored. Complete each step below. Your session is recorded from the moment the exam starts.</p>
    </header>

    <div className="ca-setup-layout">
    <aside className="ca-setup-aside">
    <span className="ca-section-eyebrow">YOUR PROGRESS</span>
    <ol className="ca-setup-steps" aria-label="Setup steps">
      {STEPS.map((item, index) => <li key={item.key}>
        <button type="button" className={`ca-setup-step ${index === step ? 'active' : ''} ${done[index] ? 'done' : ''}`}
          aria-current={index === step ? 'step' : undefined}
          disabled={index > 0 && !done.slice(0, index).every(Boolean)} onClick={() => setStep(index)}>
          <span className="ca-setup-step-icon"><i className={`fas ${done[index] ? 'fa-check' : item.icon}`} aria-hidden="true" /></span>
          <span>{index + 1}. {item.label}</span>
        </button>
      </li>)}
    </ol>
    <div className="ca-setup-start">
      {proctoring.count > 0 && <p className="ca-proctoring-warning">Warning already recorded: {proctoring.count} / 2. One more violation will end your exam.</p>}
      {media.faceCount > 0 && <p className="ca-proctoring-warning">Face warning already recorded: {media.faceCount} / 2.</p>}
      {proctoring.error && <p className="ca-inline-error" role="alert">{proctoring.error}</p>}
      <button type="button" className="ca-btn ca-btn-primary" disabled={!canStart} onClick={start}>
        {proctoring.starting ? 'Starting…' : resuming ? 'Resume assessment' : 'Start assessment'} <i className="fas fa-arrow-right" aria-hidden="true" />
      </button>
      <p className="ca-start-note"><i className="fas fa-expand" aria-hidden="true" /> The exam opens in fullscreen and recording begins.</p>
    </div>
    </aside>

    <section className="ca-setup-panel" aria-live="polite">
      {current === 'consent' && <>
        <h2>Permission to record this exam session</h2>
        <p className="ca-section-intro">To keep the assessment fair, the following is captured from the moment you start until you submit:</p>
        <ul className="ca-setup-list">
          <li><i className="fas fa-video" aria-hidden="true" /><div><strong>Camera video and audio</strong><span>Your webcam and microphone are recorded for the whole session.</span></div></li>
          <li><i className="fas fa-desktop" aria-hidden="true" /><div><strong>Entire screen</strong><span>Your full screen is recorded. Sharing a single window or tab is not accepted.</span></div></li>
          <li><i className="fas fa-camera" aria-hidden="true" /><div><strong>Face photos</strong><span>A photo is taken at random about every 10 seconds to confirm you are present and facing the screen.</span></div></li>
          <li><i className="fas fa-database" aria-hidden="true" /><div><strong>Secure storage</strong><span>Recordings and photos are stored with your name and reviewed only by the hiring team.</span></div></li>
        </ul>
        <label className="ca-terms-consent">
          <input type="checkbox" checked={consent} onChange={event => setConsent(event.target.checked)} />
          <span>I allow my camera, microphone and screen to be recorded and my photo to be captured during this exam.</span>
        </label>
        {!media.supported && <p className="ca-inline-error" role="alert">This browser cannot record the exam. Use the latest Chrome, Edge or Firefox on a desktop or laptop computer.</p>}
        <div className="ca-setup-actions">
          <button type="button" className="ca-btn ca-btn-secondary" onClick={onBack}><i className="fas fa-arrow-left" aria-hidden="true" /> Back to instructions</button>
          <button type="button" className="ca-btn ca-btn-primary" disabled={!consent || !media.supported} onClick={() => setStep(1)}>Allow & continue <i className="fas fa-arrow-right" aria-hidden="true" /></button>
        </div>
      </>}

      {current === 'camera' && <>
        <h2>Capture your face</h2>
        <p className="ca-section-intro">Sit facing the screen in good light, with your whole face inside the frame. This photo verifies your identity.</p>
        <div className="ca-setup-media">
          {reference.status === 'ok' && reference.url
            ? <div className="ca-camera ca-camera-large"><img src={reference.url} alt="Your captured face" /></div>
            : <CameraPreview stream={streams.camera} className="ca-camera-large ca-camera-guide" />}
        </div>
        {reference.status === 'ok' && <p className="ca-setup-ok" role="status"><i className="fas fa-check-circle" aria-hidden="true" /> Face verified.</p>}
        {reference.status === 'failed' && <p className="ca-inline-error" role="alert">{reference.message}</p>}
        <div className="ca-setup-actions">
          {!streams.camera
            ? <button type="button" className="ca-btn ca-btn-primary" disabled={busy === 'camera'} onClick={media.requestCamera}>
              <i className="fas fa-video" aria-hidden="true" /> {busy === 'camera' ? 'Waiting for permission…' : 'Turn on camera'}</button>
            : reference.status === 'ok'
              ? <>
                <button type="button" className="ca-btn ca-btn-secondary" onClick={media.captureReference}>Retake photo</button>
                <button type="button" className="ca-btn ca-btn-primary" onClick={() => setStep(2)}>Continue <i className="fas fa-arrow-right" aria-hidden="true" /></button>
              </>
              : <button type="button" className="ca-btn ca-btn-primary" disabled={reference.status === 'checking'} onClick={media.captureReference}>
                <i className="fas fa-camera" aria-hidden="true" /> {reference.status === 'checking' ? 'Checking your face…' : 'Capture photo'}</button>}
        </div>
      </>}

      {current === 'mic' && <>
        <h2>Turn on your microphone</h2>
        <p className="ca-section-intro">Your microphone must stay on for the whole exam. Say a few words and check that the bar moves.</p>
        {streams.mic && <div className="ca-setup-mic"><i className="fas fa-microphone" aria-hidden="true" /><MicMeter stream={streams.mic} /></div>}
        <div className="ca-setup-actions">
          {!streams.mic
            ? <button type="button" className="ca-btn ca-btn-primary" disabled={busy === 'mic'} onClick={media.requestMicrophone}>
              <i className="fas fa-microphone" aria-hidden="true" /> {busy === 'mic' ? 'Waiting for permission…' : 'Turn on microphone'}</button>
            : <button type="button" className="ca-btn ca-btn-primary" onClick={() => setStep(3)}>My microphone works <i className="fas fa-arrow-right" aria-hidden="true" /></button>}
        </div>
      </>}

      {current === 'screen' && <>
        <h2>Share your entire screen</h2>
        <p className="ca-section-intro">In the browser’s dialog, choose <strong>Entire screen</strong> and click Share. Keep sharing on until you submit.</p>
        {streams.screen && <p className="ca-setup-ok" role="status"><i className="fas fa-check-circle" aria-hidden="true" /> Your screen is being shared.</p>}
        <div className="ca-setup-actions">
          <button type="button" className={`ca-btn ${streams.screen ? 'ca-btn-secondary' : 'ca-btn-primary'}`} disabled={busy === 'screen'} onClick={media.requestScreen}>
            <i className="fas fa-desktop" aria-hidden="true" /> {busy === 'screen' ? 'Choose a screen…' : streams.screen ? 'Share again' : 'Share entire screen'}</button>
        </div>
      </>}

      {media.error && <p className="ca-inline-error" role="alert">{media.error}</p>}
    </section>
    </div>
    <footer className="ca-welcome-footer"><span>ShimentoX · Candidate experience</span><span>Your recordings are used only to review this assessment.</span></footer>

  </section></div>;
}
