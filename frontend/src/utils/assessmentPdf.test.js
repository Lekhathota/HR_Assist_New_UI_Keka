import jsPDF from 'jspdf';
import { apiGet, apiGetBlob } from '../api.js';
import { downloadAssessmentPdf } from './assessmentPdf';

jest.mock('jspdf', () => jest.fn());
jest.mock('../api.js', () => ({ apiGet: jest.fn(), apiGetBlob: jest.fn() }));

let doc;
beforeEach(() => {
  jest.clearAllMocks();
  doc = {
    addPage: jest.fn(), setFont: jest.fn(), setFontSize: jest.fn(),
    splitTextToSize: value => value.split('\n'), text: jest.fn(),
    getImageProperties: () => ({ width: 640, height: 480, fileType: 'JPEG' }),
    addImage: jest.fn(), getNumberOfPages: () => 3, setPage: jest.fn(), save: jest.fn(),
  };
  jsPDF.mockImplementation(() => doc);
  apiGet.mockImplementation(async path => path.endsWith('/proctoring') ? {
    snapshots: Array.from({ length: 15 }, (_, i) => ({ snapshot_id: `photo-${i}`, kind: 'periodic', face_ok: true })),
  } : {
    assessment: { candidate_name: 'Test Candidate', status: 'TERMINATED', termination_reason: 'Left test' },
    questions: [
      { id: 2, sort_order: 2, question_text: 'Unanswered question', question_type: 'mcq' },
      { id: 1, sort_order: 1, question_text: 'Write code', question_type: 'coding' },
    ],
    answers: [{ question_id: 1, answer: 'def answer():\n    return 42', language: 'python' }],
  });
  apiGetBlob.mockResolvedValue(new Blob(['image'], { type: 'image/jpeg' }));
});

test('exports saved answers in question order and all photos beyond the preview limit', async () => {
  await downloadAssessmentPdf(7);
  const output = doc.text.mock.calls.map(call => call[0]).join('\n');
  expect(output).toContain('TERMINATED');
  expect(output).toContain('Left test');
  expect(output).toContain('def answer():\n    return 42');
  expect(output).toContain('Not answered');
  expect(output.indexOf('Write code')).toBeLessThan(output.indexOf('Unanswered question'));
  expect(apiGetBlob).toHaveBeenCalledTimes(15);
  expect(doc.addImage).toHaveBeenCalledTimes(15);
  expect(doc.save).toHaveBeenCalledWith('Candidate_Test_Test_Candidate_7.pdf');
});

test('does not download a partial report when a photo cannot be fetched', async () => {
  apiGetBlob.mockRejectedValueOnce(new Error('Photo unavailable'));
  await expect(downloadAssessmentPdf(7)).rejects.toThrow('Photo unavailable');
  expect(doc.save).not.toHaveBeenCalled();
});

test('paginates long answers without dropping text and handles attempts with no photos', async () => {
  const answer = Array.from({ length: 200 }, (_, i) => `Line ${i}`).join('\n');
  apiGet.mockImplementation(async path => path.endsWith('/proctoring') ? { snapshots: [] } : {
    assessment: { status: 'IN_PROGRESS' },
    questions: [{ id: 1, question_text: 'Long answer', question_type: 'short_answer' }],
    answers: [{ question_id: 1, answer }],
  });
  await downloadAssessmentPdf(7);
  const output = doc.text.mock.calls.map(call => call[0]).join('\n');
  expect(output).toContain('Line 199');
  expect(output).toContain('No photos were captured');
  expect(output).toContain('saved so far');
  expect(doc.addPage.mock.calls.length).toBeGreaterThan(2);
  expect(apiGetBlob).not.toHaveBeenCalled();
});
