import { assessFace } from './faceCheck.js';

// Normalised BlazeFace keypoints: right eye, left eye, nose, mouth, right ear, left ear.
const detection = ({ noseX = 0.5, score = 0.9, rightEarX = 0.3, leftEarX = 0.7, size = 0.3 } = {}) => ({
  categories: [{ score }],
  boundingBox: { width: size, height: size },
  keypoints: [
    { x: 0.42, y: 0.4 }, { x: 0.58, y: 0.4 }, { x: noseX, y: 0.5 },
    { x: 0.5, y: 0.6 }, { x: rightEarX, y: 0.4 }, { x: leftEarX, y: 0.4 },
  ],
});

test('a forward-facing face passes', () => {
  expect(assessFace([detection()])).toEqual({ faceCount: 1, faceOk: true, issue: '' });
});

test('no detections, or only low-confidence ones, mean no face', () => {
  expect(assessFace([])).toEqual({ faceCount: 0, faceOk: false, issue: 'no_face' });
  expect(assessFace([detection({ score: 0.3 })])).toMatchObject({ faceOk: false, issue: 'no_face' });
});

test('a head turned away from the screen is flagged', () => {
  expect(assessFace([detection({ noseX: 0.62 })])).toMatchObject({ faceOk: false, issue: 'looking_away' });
  expect(assessFace([detection({ noseX: 0.38 })])).toMatchObject({ faceOk: false, issue: 'looking_away' });
  expect(assessFace([detection({ leftEarX: 0.6 })])).toMatchObject({ faceOk: false, issue: 'looking_away' });
});

test('a slight turn is tolerated', () => {
  expect(assessFace([detection({ noseX: 0.55 })])).toMatchObject({ faceOk: true });
});

test('the largest face is judged when several are visible', () => {
  const result = assessFace([detection({ noseX: 0.7, size: 0.1 }), detection({ size: 0.4 })]);
  expect(result).toEqual({ faceCount: 2, faceOk: true, issue: '' });
});
