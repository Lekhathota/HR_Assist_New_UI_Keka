import React, { useEffect, useRef, useState } from 'react';

export function CameraPreview({ stream, className = '', label = 'Your camera' }) {
  const videoRef = useRef(null);
  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.srcObject = stream || null;
    if (stream) video.play?.()?.catch?.(() => {});
  }, [stream]);
  return <div className={`ca-camera ${className}`}>
    {stream
      ? <video ref={videoRef} muted playsInline autoPlay aria-label={label} />
      : <div className="ca-camera-off"><i className="fas fa-video-slash" aria-hidden="true" /><span>Camera off</span></div>}
  </div>;
}

/** Live input level so candidates can confirm the microphone is picking them up. */
export function MicMeter({ stream }) {
  const [level, setLevel] = useState(0);
  useEffect(() => {
    const AudioContext = window.AudioContext || window.webkitAudioContext;
    if (!stream || !AudioContext) return undefined;
    const context = new AudioContext();
    const analyser = context.createAnalyser();
    analyser.fftSize = 512;
    context.createMediaStreamSource(stream).connect(analyser);
    const samples = new Uint8Array(analyser.fftSize);
    let frame;
    let last = 0;
    const tick = time => {
      if (time - last > 100) {
        analyser.getByteTimeDomainData(samples);
        const peak = samples.reduce((max, value) => Math.max(max, Math.abs(value - 128)), 0);
        setLevel(Math.min(1, peak / 64));
        last = time;
      }
      frame = window.requestAnimationFrame(tick);
    };
    frame = window.requestAnimationFrame(tick);
    return () => { window.cancelAnimationFrame(frame); context.close().catch(() => {}); };
  }, [stream]);
  return <div className="ca-mic-meter" role="meter" aria-label="Microphone level" aria-valuemin={0} aria-valuemax={100}
    aria-valuenow={Math.round(level * 100)}>
    <span style={{ width: `${Math.max(4, level * 100)}%` }} />
  </div>;
}
