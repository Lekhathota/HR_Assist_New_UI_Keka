import './StageTrackerDelivery.css';

const STAGES = ['Screening', 'Test', 'Interview'];

const SCREENING = {
  accepted: { label: 'Resume Accepted', tone: 'ok' },
  waitlisted: { label: 'Waitlisted', tone: 'warn' },
  rejected: { label: 'Rejected', tone: 'bad' },
};

const NOT_SCREENED = { label: 'Not screened', tone: 'none' };

const ICON_PATHS = {
  ok: 'M3.5 8.5l3 3 6-7',
  bad: 'M4.5 4.5l7 7M11.5 4.5l-7 7',
  warn: 'M4 8h8',
};

function StatusIcon({ tone }) {
  const d = ICON_PATHS[tone];
  if (!d) return null;
  return (
    <svg
      viewBox="0 0 16 16"
      width="12"
      height="12"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d={d} />
    </svg>
  );
}

export default function StageTrackerDelivery({ screeningStatus }) {
  const s = SCREENING[screeningStatus] || NOT_SCREENED;

  return (
    <div
      className={`stx stx--${s.tone}`}
      role="group"
      aria-label={`Stage: Screening, ${s.label}`}
      title={s.label}
    >
      <ol className="stx__steps" aria-hidden="true">
        {STAGES.map((name, i) => (
          <li key={name} className="stx__step">
            <span className="stx__dot">{i === 0 && <StatusIcon tone={s.tone} />}</span>
            <span className="stx__label">{name}</span>
          </li>
        ))}
      </ol>
      <div className="stx__status">{s.label}</div>
    </div>
  );
}