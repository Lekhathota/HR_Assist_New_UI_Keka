// Browser-side face check for exam proctoring, using MediaPipe's BlazeFace detector.
// The runtime is copied to /proctoring/vendor at build time and loaded on demand,
// so it never enters the main bundle and is only downloaded by exam candidates.
const BASE = `${process.env.PUBLIC_URL || ''}/proctoring`;
const MIN_SCORE = 0.6;
// Horizontal nose offset from the eye midpoint, relative to eye distance. About 0 when
// facing the camera; beyond this the head is turned roughly 35-40 degrees away.
const MAX_YAW = 0.5;
// Ratio of each eye's distance to its ear; strongly lopsided means a profile view.
const MAX_EAR_RATIO = 3;

let detectorPromise = null;

export function loadFaceDetector() {
  if (!detectorPromise) {
    detectorPromise = (async () => {
      const { FilesetResolver, FaceDetector } = await import(/* webpackIgnore: true */ `${BASE}/vendor/vision_bundle.mjs`);
      const fileset = await FilesetResolver.forVisionTasks(`${BASE}/vendor/wasm`);
      return FaceDetector.createFromOptions(fileset, {
        baseOptions: { modelAssetPath: `${BASE}/blaze_face_short_range.tflite`, delegate: 'CPU' },
        runningMode: 'IMAGE',
        minDetectionConfidence: MIN_SCORE,
      });
    })().catch(err => {
      detectorPromise = null;
      throw err;
    });
  }
  return detectorPromise;
}

const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

export function assessFace(detections) {
  const faces = (detections || []).filter(face => (face.categories?.[0]?.score ?? 0) >= MIN_SCORE);
  if (!faces.length) return { faceCount: 0, faceOk: false, issue: 'no_face' };
  const area = face => (face.boundingBox?.width || 0) * (face.boundingBox?.height || 0);
  const primary = faces.reduce((best, face) => (area(face) > area(best) ? face : best));
  // BlazeFace keypoints: right eye, left eye, nose tip, mouth, right ear, left ear.
  const [rightEye, leftEye, nose, , rightEar, leftEar] = primary.keypoints || [];
  if (rightEye && leftEye && nose) {
    const eyeSpan = distance(rightEye, leftEye);
    const yaw = eyeSpan ? (nose.x - (rightEye.x + leftEye.x) / 2) / eyeSpan : 0;
    const earRatio = rightEar && leftEar && distance(leftEye, leftEar)
      ? distance(rightEye, rightEar) / distance(leftEye, leftEar) : 1;
    if (Math.abs(yaw) > MAX_YAW || earRatio > MAX_EAR_RATIO || earRatio < 1 / MAX_EAR_RATIO) {
      return { faceCount: faces.length, faceOk: false, issue: 'looking_away' };
    }
  }
  return { faceCount: faces.length, faceOk: true, issue: '' };
}

/** Draws the current camera frame and returns the JPEG plus the face check result. */
export async function captureAndCheck(video, { width = 480, quality = 0.75 } = {}) {
  if (!video?.videoWidth) throw new Error('The camera is not ready yet.');
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = Math.round((video.videoHeight / video.videoWidth) * width);
  canvas.getContext('2d').drawImage(video, 0, 0, canvas.width, canvas.height);
  const detector = await loadFaceDetector();
  const result = assessFace(detector.detect(canvas).detections);
  const image = await new Promise((resolve, reject) => canvas.toBlob(
    blob => (blob ? resolve(blob) : reject(new Error('Could not capture a photo.'))), 'image/jpeg', quality));
  return { ...result, image };
}

export const FACE_ISSUE_TEXT = {
  no_face: 'Face not detected. Keep your face fully visible in the camera.',
  looking_away: 'Face not detected looking at the screen. Face the camera directly.',
};
