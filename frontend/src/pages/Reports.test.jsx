import React, { act } from 'react';
import { createRoot } from 'react-dom/client';
import { Simulate } from 'react-dom/test-utils';
import Reports from './Reports.jsx';
import { apiPost } from '../api.js';
import { Packer } from 'docx';
import { saveAs } from 'file-saver';
import jsPDF from 'jspdf';

jest.mock('../components/Layout.jsx', () => ({ children }) => <main>{children}</main>);
jest.mock('../components/Analytics.jsx', () => ({
  ...jest.requireActual('../components/Analytics.jsx'),
  useAnalytics: () => ({ filters: { start: '2026-01-01', end: '2026-01-31', job: '' }, jobs: [], setFilters: jest.fn(),
    data: { metrics: { total_candidates: 3 }, jd_reports: [], skill_gaps: [], funnel: [], analytics: {
      jobs: [], pipeline: [{ name: 'Uploaded', count: 3 }, { name: 'Screened', count: 0 }, { name: 'Interviewed', count: null }, { name: 'Offered', count: null }, { name: 'Hired', count: null }],
      sources: [], trend: [], source_trend: [], recruiters: [], notes: ['Test coverage'], time_to_hire: { days: null, sample_size: 0 },
    } } }),
}));
jest.mock('../api.js', () => ({ apiPost: jest.fn(), apiGet: jest.fn() }));
jest.mock('file-saver', () => ({ saveAs: jest.fn() }));
jest.mock('docx', () => ({ Document: jest.fn(), Paragraph: jest.fn(), TextRun: jest.fn(), Packer: { toBlob: jest.fn() } }));
jest.mock('jspdf', () => jest.fn());

let container, root, pdf;
beforeEach(() => {
  globalThis.IS_REACT_ACT_ENVIRONMENT = true;
  jest.clearAllMocks();
  window.alert = jest.fn();
  URL.createObjectURL = jest.fn(() => 'blob:test');
  URL.revokeObjectURL = jest.fn();
  jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  pdf = { internal: { pageSize: { getWidth: () => 210 } }, addPage: jest.fn(), setFontSize: jest.fn(), setFont: jest.fn(), setTextColor: jest.fn(), splitTextToSize: x => [x], text: jest.fn(), save: jest.fn(), output: () => new Blob(['pdf fixture'], { type: 'application/pdf' }) };
  jsPDF.mockImplementation(() => pdf);
  Packer.toBlob.mockResolvedValue(new Blob(['docx fixture']));
  apiPost.mockResolvedValue({ ok: true, data: { success: true } });
  container = document.createElement('div'); document.body.appendChild(container); root = createRoot(container);
  act(() => root.render(<Reports />));
  act(() => [...container.querySelectorAll('button')].find(b => b.textContent === 'Export Report').click());
});
afterEach(() => { act(() => root.unmount()); container.remove(); jest.restoreAllMocks(); });
async function generate(format) {
  act(() => [...container.querySelectorAll('.format-option')].find(b => b.textContent === format).click());
  await act(async () => container.querySelector('.modal-footer button:last-child').click());
}
test('PDF contains the loaded filter dates and actual values', async () => {
  await generate('PDF');
  expect(pdf.save).toHaveBeenCalled();
  expect(pdf.text.mock.calls.map(c => c[0]).join('\n')).toContain('total candidates: 3');
  expect(pdf.text.mock.calls.map(c => c[0]).join('\n')).toContain('2026-01-31');
});
test('Word export still creates and saves a document', async () => {
  await generate('DOCX');
  expect(Packer.toBlob).toHaveBeenCalled();
  expect(saveAs).toHaveBeenCalled();
});
test('CSV still downloads and revokes the temporary URL', async () => {
  await generate('CSV');
  expect(URL.createObjectURL).toHaveBeenCalled();
  expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:test');
});
test('email sends only the mocked attachment API with the entered recipient', async () => {
  act(() => [...container.querySelectorAll('.format-option')].find(b => b.textContent === 'Email').click());
  act(() => Simulate.change(container.querySelector('input[type="email"]'), { target: { value: 'test@example.com' } }));
  await act(async () => { container.querySelector('.modal-footer button:last-child').click(); await new Promise(resolve => setTimeout(resolve, 30)); });
  expect(apiPost).toHaveBeenCalledWith('/api/report/email', expect.objectContaining({ recipient: 'test@example.com', attachment: expect.objectContaining({ mimeType: 'application/pdf' }) }));
});
