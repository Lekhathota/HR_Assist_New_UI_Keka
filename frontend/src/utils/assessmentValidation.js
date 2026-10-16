// Same rules as the server's validate_mcq: four distinct options, exactly one correct, an explanation.
export function mcqProblem(form) {
  if (form.question_type !== 'mcq') return '';
  if (!String(form.question_text || '').trim()) return 'Enter the question text.';
  const options = form.options || [];
  if (options.length !== 4 || options.some(o => !String(o).trim())) return 'An MCQ needs exactly four non-empty options.';
  if (new Set(options.map(o => String(o).trim().toLowerCase().replace(/\s+/g, ' '))).size !== 4) return 'The four MCQ options must be different from each other.';
  if (options.filter(o => o === form.correct_answer).length !== 1) return 'Select exactly one of the four options as the correct answer.';
  if (!String(form.explanation || '').trim()) return 'Add an explanation of why the correct answer is right.';
  return '';
}

export function isValidEmail(value) {
  return /^[^\s@]+@[^\s@]+\.[^\s@]{2,}$/.test(String(value || '').trim());
}
