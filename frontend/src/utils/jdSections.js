// Splits a JD's stored text (raw_text) into the sections its author wrote,
// e.g. "Job Title: ...", "Role Overview", "Key Responsibilities", so the
// Jobs pages can show structure instead of one block of text. Nothing is
// generated: every heading, label and sentence comes from the stored text.

const FIELD_LABELS = [
  'Job Title', 'Job Description', 'Department', 'Location', 'Experience Required',
  'Experience Level', 'Experience', 'Duration', 'Employment Type', 'Job Type',
  'Work Mode', 'Education', 'Salary',
];

const SECTION_HEADINGS = [
  'Role Overview', 'Position Overview', 'Job Overview', 'Job Summary', 'About the Role',
  'Overview', 'Summary',
  'Key Responsibilities', 'Roles and Responsibilities', 'Roles & Responsibilities',
  'Responsibilities', 'Key Duties',
  'Required Skills & Qualifications', 'Required Skills and Qualifications',
  'Required Qualifications', 'Required Skills', 'Technical Qualifications',
  'Technical Skills', 'Qualifications', 'Requirements', 'Skills',
  'Preferred Qualifications', 'Preferred Skills', 'Preferred Certifications',
  'Nice to Have', 'Good to Have', 'Soft Skills', 'Certifications', 'Benefits',
  'What We Offer',
];

const BULLET_CHARS = '•●▪◦►➢✓';

function alternation(phrases) {
  return [...phrases]
    .sort((a, b) => b.length - a.length)
    .map(p => p.replace(/[.*+?^${}()|[\]\\]/g, '\\$&').replace(/ /g, '\\s+'))
    .join('|');
}

// Groups: 1 = "<name> - Job Description" title line, 2 = "Label:", 3 = heading.
const MARKER_RE = new RegExp(
  `(^[^\\n]{3,100}?\\s[-–]\\s*Job Description[ \\t]*$)`
  + `|\\b(${alternation(FIELD_LABELS)})\\s*:`
  + `|\\b(${alternation(SECTION_HEADINGS)})(?![A-Za-z])([ \\t]*:)?`,
  'gim',
);

const collapse = text => String(text || '').replace(/\s+/g, ' ').trim();

export function sectionKind(heading) {
  const h = String(heading || '').toLowerCase();
  if (/overview|summary|about the role/.test(h)) return 'overview';
  if (/responsibilit|duties/.test(h)) return 'responsibilities';
  if (/preferred|nice to have|good to have/.test(h)) return 'preferred';
  if (/required|requirement|qualification|skills/.test(h)) return 'required';
  return 'other';
}

// Some PDF extractions store one word per line; join those back into prose.
export function normalizeJdText(rawText) {
  const text = String(rawText || '').replace(/\u200b/g, '').replace(/\r/g, '');
  const lines = text.split('\n');
  const avg = lines.reduce((sum, line) => sum + line.trim().length, 0) / (lines.length || 1);
  if (lines.length > 20 && avg < 15) return lines.map(l => l.trim()).filter(Boolean).join(' ');
  return text;
}

function isCapitalised(phrase) {
  return phrase.split(/\s+/).every(word => word.length < 4 || /^[A-Z]/.test(word));
}

function atLineStart(text, index) {
  const before = text.slice(0, index).replace(/[ \t]+$/, '');
  return before === '' || before.endsWith('\n');
}

function findMarkers(text) {
  const markers = [];
  let inHeader = true; // "Label:" fields only count in a JD's header area
  MARKER_RE.lastIndex = 0;
  let m;
  while ((m = MARKER_RE.exec(text)) !== null) {
    const [whole, title, field, heading, colon] = m;
    if (title) {
      markers.push({ type: 'title', index: m.index, end: m.index + whole.length, text: collapse(title) });
      inHeader = true;
    } else if (field) {
      if (inHeader) markers.push({ type: 'field', index: m.index, end: m.index + whole.length, label: collapse(field) });
    } else if (heading) {
      const multiWord = /\s/.test(heading.trim());
      const accepted = multiWord
        ? isCapitalised(heading)
        : isCapitalised(heading) && atLineStart(text, m.index);
      if (accepted) {
        markers.push({ type: 'section', index: m.index, end: m.index + whole.length, heading: collapse(heading), hasColon: Boolean(colon) });
        inHeader = false;
      }
    }
  }
  return markers;
}

// Turns a section body into paragraphs and/or bullet items.
export function formatBody(body) {
  const text = String(body || '').trim();
  const bulletSplit = new RegExp(`[${BULLET_CHARS}]|(?:^|\\n)[ \\t]*[-*][ \\t]+`);
  if (bulletSplit.test(text)) {
    const parts = text.split(new RegExp(`[${BULLET_CHARS}]|(?:^|\\n)[ \\t]*[-*][ \\t]+`));
    const lead = collapse(parts.shift());
    return {
      paragraphs: lead ? [lead] : [],
      items: parts.map(collapse).filter(Boolean),
    };
  }
  return {
    paragraphs: text.split(/\n\s*\n/).map(collapse).filter(Boolean),
    items: [],
  };
}

function structuredData(jd) {
  const sd = jd && jd.structured_data;
  if (!sd) return {};
  if (typeof sd === 'string') {
    try { return JSON.parse(sd) || {}; } catch { return {}; }
  }
  return sd;
}

const comparable = s => collapse(s).toLowerCase().replace(/[.;,]+$/, '');

// For a section written as run-on text (no bullets), reuse the list the
// backend already extracted for it, but only when every item appears
// word-for-word in that section, so the list is the author's own text.
function extractedListFor(kind, body, jd) {
  const sd = structuredData(jd);
  const candidates = {
    responsibilities: [sd.responsibilities, jd && jd.responsibilities],
    required: [sd.must_haves],
    preferred: [sd.nice_to_haves],
  }[kind] || [];
  const haystack = comparable(body);
  for (const list of candidates) {
    if (!Array.isArray(list) || list.length < 2) continue;
    const items = list.map(item => collapse(item)).filter(Boolean);
    const avgLength = items.reduce((sum, item) => sum + item.length, 0) / (items.length || 1);
    if (avgLength >= 20 && items.every(item => haystack.includes(comparable(item)))) return items;
  }
  return null;
}

/**
 * Returns the JD as ordered groups:
 *   { kind: 'intro', title, fields: [{label, value}], blocks: [{heading, paragraphs, items}] }
 *   { kind: 'section', heading, sectionKind, paragraphs, items }
 * An intro group holds the header ("Job Title:", "Location:", ...) and any
 * overview/summary text; every other heading becomes its own section.
 */
export function parseJdSections(jd) {
  const text = normalizeJdText(jd && jd.raw_text);
  if (!text.trim()) return [];
  const markers = findMarkers(text);
  const groups = [];
  let intro = { kind: 'intro', title: '', fields: [], blocks: [] };
  groups.push(intro);

  const preamble = collapse(text.slice(0, markers.length ? markers[0].index : text.length));
  if (preamble.length > 3) {
    if (markers.length) intro.title = preamble;
    else intro.blocks.push({ heading: '', ...formatBody(text) });
  }

  markers.forEach((marker, i) => {
    const body = text.slice(marker.end, i + 1 < markers.length ? markers[i + 1].index : text.length);
    if (marker.type === 'title') {
      intro = { kind: 'intro', title: marker.text, fields: [], blocks: [] };
      groups.push(intro);
    } else if (marker.type === 'field') {
      const value = collapse(body);
      if (value) intro.fields.push({ label: marker.label, value });
    } else {
      const kind = sectionKind(marker.heading);
      let formatted = formatBody(body);
      if (!formatted.items.length) {
        const list = extractedListFor(kind, body, jd);
        if (list) formatted = { paragraphs: [], items: list };
      }
      if (!formatted.paragraphs.length && !formatted.items.length) return;
      if (kind === 'overview') {
        intro.blocks.push({ heading: marker.heading, ...formatted });
      } else {
        groups.push({ kind: 'section', heading: marker.heading, sectionKind: kind, ...formatted });
      }
    }
  });

  return groups.filter(g => g.kind === 'section' || g.title || g.fields.length || g.blocks.length);
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// Displays a stored "YYYY-MM-DD..." date as "24 Sep 2026"; other values pass through.
export function formatJdDate(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(value || ''));
  if (!match) return value || '';
  const [, year, month, day] = match;
  return `${Number(day)} ${MONTHS[Number(month) - 1]} ${year}`;
}
