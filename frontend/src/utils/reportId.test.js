import { apiPost } from '../api.js';
import { currentReportId, issueReportId } from './reportId.js';

jest.mock('../api.js', () => ({ apiPost: jest.fn() }));

test('uses the server-issued report ID', async () => {
  apiPost.mockResolvedValue({ ok: true, data: { report_id: 'RPT-20261006-0007' } });
  await expect(issueReportId('jobs', 'pdf')).resolves.toBe('RPT-20261006-0007');
  expect(apiPost).toHaveBeenCalledWith('/api/reports/issue', { scope: 'jobs', format: 'pdf' });
  expect(currentReportId()).toBe('RPT-20261006-0007');
});

test('falls back to a timestamped local ID (no random numbers) when offline', async () => {
  apiPost.mockRejectedValue(new Error('offline'));
  const id = await issueReportId('talent', 'csv');
  expect(id).toMatch(/^RPT-\d{8}-L\d{6}$/);
});
