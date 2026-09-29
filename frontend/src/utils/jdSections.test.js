import { formatJdDate, parseJdSections, normalizeJdText } from './jdSections.js';

test('formats stored dates as "24 Sep 2026"', () => {
  expect(formatJdDate('2026-09-24')).toBe('24 Sep 2026');
  expect(formatJdDate('2024-01-05T10:30:00')).toBe('5 Jan 2024');
  expect(formatJdDate('')).toBe('');
  expect(formatJdDate('Pending')).toBe('Pending');
});

const sectionsOf = groups => groups.filter(g => g.kind === 'section');

test('splits labelled header, overview and bulleted sections', () => {
  const raw = [
    'Job Title: Platform Engineer',
    'Location: Chennai',
    'Experience Required: 4+ years',
    '',
    'About the Role:',
    'You will run the build platform.',
    '',
    'Key Responsibilities:',
    '- Own the CI pipelines',
    '- Keep builds fast',
    '',
    'Preferred Skills:',
    '• Go',
    '• Bazel',
  ].join('\n');
  const [intro, ...rest] = parseJdSections({ raw_text: raw });

  expect(intro.fields).toEqual([
    { label: 'Job Title', value: 'Platform Engineer' },
    { label: 'Location', value: 'Chennai' },
    { label: 'Experience Required', value: '4+ years' },
  ]);
  expect(intro.blocks).toEqual([
    { heading: 'About the Role', paragraphs: ['You will run the build platform.'], items: [] },
  ]);
  expect(rest.map(s => [s.heading, s.sectionKind, s.items])).toEqual([
    ['Key Responsibilities', 'responsibilities', ['Own the CI pipelines', 'Keep builds fast']],
    ['Preferred Skills', 'preferred', ['Go', 'Bazel']],
  ]);
});

test('re-joins one-word-per-line text and finds headings without colons', () => {
  const words = 'Job Title: QA Lead Location: Pune Job Summary We test things well . Key Responsibilities ● Plan tests ● Report bugs';
  const raw = words.split(' ').join('\n') + '\n'.repeat(3);
  expect(normalizeJdText(raw).startsWith('Job Title: QA Lead')).toBe(true);

  const [intro, resp] = parseJdSections({ raw_text: raw });
  expect(intro.fields.map(f => f.value)).toEqual(['QA Lead', 'Pune']);
  expect(intro.blocks[0].heading).toBe('Job Summary');
  expect(resp.items).toEqual(['Plan tests', 'Report bugs']);
});

test('labels inside bullets and lowercase phrases are not treated as structure', () => {
  const raw = [
    'Location: Remote',
    'Technical Qualifications',
    '● Experience: Minimum of 3 years',
    '● Core Skills: strong SQL',
    '● Works across key responsibilities of the team',
  ].join('\n');
  const [intro, quals] = parseJdSections({ raw_text: raw });
  expect(intro.fields).toEqual([{ label: 'Location', value: 'Remote' }]);
  expect(quals.heading).toBe('Technical Qualifications');
  expect(quals.items).toEqual([
    'Experience: Minimum of 3 years',
    'Core Skills: strong SQL',
    'Works across key responsibilities of the team',
  ]);
});

test('uses the extracted list only when every item is verbatim in the section', () => {
  const raw = 'Role Overview: Build APIs.\nKey Responsibilities: Design scalable backend services Build and optimize REST APIs';
  const verbatim = { responsibilities: ['Design scalable backend services', 'Build and optimize REST APIs'] };
  const paraphrased = { responsibilities: ['Designs backend services at scale', 'Builds and optimizes REST APIs'] };

  expect(sectionsOf(parseJdSections({ raw_text: raw, structured_data: verbatim }))[0].items)
    .toEqual(verbatim.responsibilities);
  const fallback = sectionsOf(parseJdSections({ raw_text: raw, structured_data: JSON.stringify(paraphrased) }))[0];
  expect(fallback.items).toEqual([]);
  expect(fallback.paragraphs).toEqual(['Design scalable backend services Build and optimize REST APIs']);
});

test('text without any headings is shown as plain paragraphs', () => {
  const groups = parseJdSections({ raw_text: 'Just a short note about the role.' });
  expect(groups).toEqual([
    { kind: 'intro', title: '', fields: [], blocks: [{ heading: '', paragraphs: ['Just a short note about the role.'], items: [] }] },
  ]);
  expect(parseJdSections({ raw_text: '' })).toEqual([]);
});
