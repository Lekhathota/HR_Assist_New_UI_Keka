import { apiGet, apiGetBlob } from '../api.js';

function readImage(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error('Could not read a captured photo. Please retry.'));
    reader.readAsDataURL(blob);
  });
}

export async function downloadAssessmentPdf(assessmentId, onProgress = () => {}) {
  const { default: jsPDF } = await import('jspdf');
  // Fetch the full attempt at download time, including photos outside the UI preview.
  const [details, evidence] = await Promise.all([
    apiGet(`/api/assessment/${assessmentId}`),
    apiGet(`/api/assessment/${assessmentId}/proctoring`),
  ]);
  const assessment = details.assessment;
  if (!assessment) throw new Error('Could not load test details.');
  const result = ['PASSED', 'FAILED', 'COMPLETED'].includes(assessment.status)
    ? (await apiGet(`/api/assessment/result/${assessmentId}`)).result : null;
  const doc = new jsPDF('p', 'mm', 'a4');
  const margin = 15;
  const width = 180;
  let y = margin;
  const newPage = () => { doc.addPage(); y = margin; };
  const text = (value, { size = 10, bold = false, code = false } = {}) => {
    doc.setFont(code ? 'courier' : 'helvetica', bold ? 'bold' : 'normal');
    doc.setFontSize(size);
    const lines = doc.splitTextToSize(String(value ?? ''), width);
    const height = size * 0.3528 * 1.3;
    for (const line of lines) {
      if (y + height > 280) newPage();
      doc.text(line, margin, y + height);
      y += height;
    }
    y += 3;
  };
  const time = value => value ? new Date(value).toLocaleString() : 'Not recorded';
  text('Candidate test details', { size: 18, bold: true });
  text(`Test: ${assessment.title || assessmentId}`);
  text(`Candidate: ${assessment.candidate_name || evidence.candidate_name || 'Candidate'}`);
  text(`Email: ${assessment.candidate_email || 'Not recorded'}`);
  text(`Job: ${assessment.job_role || 'Not recorded'}`);
  text(`Assessment ID: ${assessmentId} | Status: ${assessment.status}`);
  text(`Started: ${time(assessment.started_at)} | Completed: ${time(assessment.completed_at)}`);
  text(`Time limit: ${assessment.time_limit_minutes ?? '-'} minutes | Passing score: ${assessment.passing_score ?? '-'}%`);
  text(`Report generated: ${new Date().toLocaleString()}`);
  if (assessment.status === 'IN_PROGRESS') text('Test in progress: this report includes answers and photos saved so far.');
  if (assessment.termination_reason) text(`Termination reason: ${assessment.termination_reason}`);
  if (result) {
    text(`Score: ${result.percentage ?? result.score_percentage ?? '-'}% (${result.score ?? result.earned_points ?? '-'}/${result.total_points ?? '-'} points)`);
    if (result.summary) text(result.summary);
  }
  const answers = new Map((details.answers || []).map(answer => [String(answer.question_id), answer]));
  const results = new Map((result?.question_results || []).map(row => [String(row.question_id), row]));
  text('Questions and candidate answers', { size: 14, bold: true });
  const questions = [...(details.questions || [])].sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
  for (const [index, question] of questions.entries()) {
    const answer = answers.get(String(question.id));
    const grade = results.get(String(question.id));
    text(`Q${index + 1}. ${question.question_text}`, { size: 12, bold: true });
    text(`Type: ${question.question_type} | Points: ${question.points ?? '-'}${question.skill_tag ? ` | Skill: ${question.skill_tag}` : ''}`);
    for (const [i, option] of (question.options || []).entries()) text(`${i + 1}. ${option}`);
    if (question.starter_code) text(`Starter code:\n${question.starter_code}`, { code: true });
    text(`Candidate answer${answer?.language ? ` (${answer.language})` : ''}:`, { bold: true });
    text(String(answer?.answer ?? '').trim() ? answer.answer : 'Not answered', {
      code: ['coding', 'sql'].includes(question.question_type),
    });
    if (question.correct_answer) text(`Correct / reference answer:\n${question.correct_answer}`);
    if (grade) {
      text(`Points earned: ${grade.points_earned}/${grade.points_possible} | Evaluation: ${grade.evaluation_method || 'Not recorded'}`);
      if (grade.feedback) text(`Feedback: ${grade.feedback}`);
      if (grade.review_notes) text(`Review notes: ${grade.review_notes}`);
      for (const [i, test] of (grade.metadata?.tests || []).entries()) {
        text(`Test ${i + 1}${test.hidden ? ' (hidden)' : ''}: ${test.passed ? 'Passed' : test.status || 'Failed'}${test.error ? `\n${test.error}` : ''}`);
      }
    }
  }
  newPage();
  text('Proctoring details and captured images', { size: 14, bold: true });
  text(`Face warnings: ${evidence.face_violation_count ?? 0} | Focus and recording warnings: ${evidence.proctoring_violation_count ?? 0}`);
  text(`Recording consent: ${time(evidence.recording_consent_at)}`);
  for (const event of evidence.events || []) text(`${time(event.recorded_at)}: ${event.reason || event.issue || 'Proctoring event'}`);
  const snapshots = evidence.snapshots || [];
  text(`Captured images: ${snapshots.length}`);
  if (!snapshots.length) text('No photos were captured for this attempt.');
  for (const [index, snapshot] of snapshots.entries()) {
    onProgress(`Adding photo ${index + 1} of ${snapshots.length}...`);
    // Do not silently produce an incomplete report when an image cannot be fetched.
    const blob = await apiGetBlob(`/api/assessment/${assessmentId}/proctoring/snapshots/${encodeURIComponent(snapshot.snapshot_id)}`);
    const dataUrl = await readImage(blob);
    const image = doc.getImageProperties(dataUrl);
    const scale = Math.min(width / image.width, 205 / image.height);
    const imageWidth = image.width * scale;
    const imageHeight = image.height * scale;
    newPage();
    text(`Photo ${index + 1} of ${snapshots.length}: ${snapshot.kind === 'reference' ? 'Reference photo' : 'During test'}`, { size: 12, bold: true });
    text(`Captured: ${time(snapshot.captured_at)} | ${snapshot.face_ok ? 'Face visible' : snapshot.issue || 'Face warning'}`);
    doc.addImage(dataUrl, image.fileType, margin, y, imageWidth, imageHeight);
  }
  const pageCount = doc.getNumberOfPages();
  for (let page = 1; page <= pageCount; page += 1) {
    doc.setPage(page);
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(8);
    doc.text(`Assessment ${assessmentId} | Page ${page} of ${pageCount}`, margin, 290);
  }
  const name = (assessment.candidate_name || 'Candidate').replace(/[^a-zA-Z0-9_-]+/g, '_');
  doc.save(`Candidate_Test_${name}_${assessmentId}.pdf`);
}
