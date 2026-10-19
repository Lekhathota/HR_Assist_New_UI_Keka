import React, { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import Layout from '../components/Layout.jsx';
import { toast } from '../components/EnterpriseFeedback.jsx';
import { apiGet, apiPost } from '../api.js';
import {
  formatAssessmentDate,
  formatAssessmentStatus,
  isAssessmentScoreVisible,
} from '../utils/assessmentDisplay.js';
import { initials } from '../utils/userDisplay.js';
import InterviewStatusMenu, { INTERVIEW_STATUS_OPTIONS } from '../components/InterviewStatusMenu.jsx';
import '../styles/hiring_pipeline.css';

function formatDateTime(value) {
  if (!value) return { date: 'N/A', time: '' };
  const parsed = new Date(String(value));
  if (Number.isNaN(parsed.getTime())) return { date: String(value).slice(0, 10), time: '' };
  return {
    date: parsed.toLocaleDateString([], { year: 'numeric', month: 'short', day: '2-digit' }),
    time: parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }),
  };
}

function statusClass(value) {
  const lowered = String(value || '').toLowerCase();
  if (
    lowered === 'sent' ||
    lowered === 'scheduled' ||
    lowered === 'rescheduled' ||
    lowered === 'client interview pending' ||
    lowered === 'selected'
  ) return 'interview-status-good';
  if (
    lowered === 'failed' ||
    lowered === 'cancelled' ||
    lowered === 'canceled' ||
    lowered === 'rejected after interview' ||
    lowered === 'rejected'
  ) return 'interview-status-bad';
  return 'interview-status-muted';
}

// Colour tone for a status pill: good / bad / warn / info / muted.
function toneOf(value) {
  const cls = statusClass(value);
  if (cls === 'interview-status-good') return 'good';
  if (/scheduled$/i.test(String(value || '').trim())) return 'good';
  if (cls === 'interview-status-bad') return 'bad';
  return 'muted';
}

const ASSESSMENT_REFRESH_MS = 30000;
const ASSESSMENT_TONE = {
  NOT_CREATED: 'muted', DRAFT: 'info', SENT: 'warn', IN_PROGRESS: 'warn', COMPLETED: 'info', PASSED: 'good', FAILED: 'bad', TERMINATED: 'bad',
};
const ASSESSMENT_FILTERS = [
  ['all', 'All'], ['NOT_CREATED', 'Not created'], ['DRAFT', 'Draft'], ['SENT', 'Sent'],
  ['IN_PROGRESS', 'In progress'], ['PASSED', 'Passed'], ['FAILED', 'Failed'], ['TERMINATED', 'Terminated'],
];
const INTERVIEW_VIEWS = [
  ['upcoming', 'Upcoming'], ['needs_followup', 'Needs follow-up'], ['past', 'Past'], ['cancelled', 'Cancelled'], ['all', 'All'],
];

// Automated no-show / reschedule recovery shown on an interview row.
function recoveryState(recovery) {
  if (!recovery) return null;
  const noShow = recovery.recovery_type === 'NO_SHOW';
  const delivered = Number(recovery.attempt_count || 0) > 0;
  switch (recovery.status) {
    case 'PENDING':
    case 'PROCESSING':
      return noShow ? { label: 'No-show detected · outreach pending', tone: 'warn' } : { label: 'Reschedule requested', tone: 'warn' };
    case 'RETRY_SCHEDULED':
      if (noShow && recovery.stage === 'awaiting_consent') return { label: delivered ? 'Follow-up retry scheduled' : 'Outreach pending (retrying)', tone: 'warn' };
      return { label: 'Finding new times', tone: 'warn' };
    case 'AWAITING_RESPONSE':
      return { label: 'Outreach sent · awaiting reply', tone: 'info' };
    case 'SLOT_PROPOSED':
      return { label: 'Candidate choosing new time', tone: 'info' };
    case 'RESCHEDULED':
    case 'RECOVERED':
      return { label: 'Rescheduled', tone: 'good' };
    case 'ESCALATED':
      return { label: 'Escalated to recruiter', tone: 'bad' };
    case 'CLOSED':
      return { label: recovery.outcome === 'candidate_declined' ? 'Resolved · candidate withdrew' : 'Resolved', tone: 'muted' };
    default:
      return null;
  }
}

// "72.0912" -> "72.1%", "85" -> "85%".
function pct(value) {
  const n = Number(value);
  if (!Number.isFinite(n)) return `${value}%`;
  return `${Number.isInteger(n) ? n : n.toFixed(1)}%`;
}

// Hide template placeholders such as "[Phone]" that some resumes leave in.
function realValue(value) {
  const text = String(value || '').trim();
  return text && !/^\[.*\]$/.test(text) ? text : '';
}

// "Scheduled" -> "Interview scheduled"; "Interview Scheduled" stays as is (no double prefix).
function interviewLabel(value) {
  const text = prettyStatus(value).trim();
  const label = /^interview\b/i.test(text) ? text : `Interview ${text.toLowerCase()}`;
  return label.charAt(0).toUpperCase() + label.slice(1).toLowerCase();
}

function prettyStatus(value) {
  return String(value || '').replace(/_/g, ' ');
}

function normalizeStatus(value) {
  return String(value || '').trim().toLowerCase();
}

const SLOT_START_HOUR = 9;
const SLOT_END_HOUR = 18;

function toMinutes(timeValue) {
  const [hours, minutes] = String(timeValue || '00:00').split(':').map(Number);
  return (hours * 60) + (minutes || 0);
}

function formatSlotLabel(timeValue) {
  const [hours, minutes] = String(timeValue).split(':').map(Number);
  const date = new Date();
  date.setHours(hours, minutes || 0, 0, 0);
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function formatDateInput(value) {
  const parsed = new Date(String(value || ''));
  if (Number.isNaN(parsed.getTime())) return '';
  return [
    parsed.getFullYear(),
    String(parsed.getMonth() + 1).padStart(2, '0'),
    String(parsed.getDate()).padStart(2, '0'),
  ].join('-');
}

function formatTimeInput(value) {
  const parsed = new Date(String(value || ''));
  if (Number.isNaN(parsed.getTime())) return '';
  return `${String(parsed.getHours()).padStart(2, '0')}:${String(parsed.getMinutes()).padStart(2, '0')}`;
}

function buildTimeOptions(blockedSlots) {
  const options = [];
  for (let hour = SLOT_START_HOUR; hour < SLOT_END_HOUR; hour += 1) {
    for (const minute of [0, 30]) {
      const value = `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
      const start = toMinutes(value);
      const end = start + 60;
      const blocked = blockedSlots.some(slot => {
        const blockedStart = toMinutes(slot.start);
        const blockedEnd = toMinutes(slot.end);
        return blockedStart < end && blockedEnd > start;
      });
      options.push({ value, label: formatSlotLabel(value), blocked });
    }
  }
  return options;
}

function buildRescheduleTextBody(interview, form) {
  const candidateName = interview?.candidate_name || 'Candidate';
  const firstName = candidateName.split(/\s+/)[0] || candidateName;
  const jobRole = interview?.job_role || 'the role';
  const timeLabel = form.interview_time ? formatSlotLabel(form.interview_time) : form.interview_time;
  const parts = [
    `Hi ${firstName}, your interview for ${jobRole} has been rescheduled.`,
    `Date: ${form.interview_date}. Time: ${timeLabel}.`,
  ];
  if (form.interview_mode) parts.push(`Mode: ${form.interview_mode}.`);
  if (form.meeting_link) parts.push(`Link: ${form.meeting_link}.`);
  return [...parts, '- Recruitment Team'].join(' ');
}

function buildInterviewTextBody(candidate, interviewDate, interviewTime) {
  const candidateName = candidate?.candidate_name || 'Candidate';
  const firstName = candidateName.split(/\s+/)[0] || candidateName;
  const jobRole = candidate?.jd_title || 'the role';
  const timeLabel = interviewTime ? formatSlotLabel(interviewTime) : interviewTime;
  return [
    `Hi ${firstName}, congratulations!`,
    `You have been selected for an interview for ${jobRole}.`,
    `Date: ${interviewDate}. Time: ${timeLabel}.`,
    'Please reply to confirm your availability.',
    '- Recruitment Team',
  ].join(' ');
}

function hasActiveInterview(row) {
  const status = normalizeStatus(row?.interview_status || row?.interview?.status);
  return Boolean(row?.interview_id) && !['cancelled', 'canceled', 'rejected after interview'].includes(status);
}

function isCancelled(interview) {
  const status = normalizeStatus(interview?.status);
  return status === 'cancelled' || status === 'canceled';
}

function isPastInterview(interview) {
  const end = new Date(String(interview?.interview_end || interview?.interview_start || ''));
  return !Number.isNaN(end.getTime()) && end < new Date();
}

function isOutcomeLocked(interview) {
  const status = normalizeStatus(interview?.status);
  return status === 'rejected after interview' || status === 'client interview pending';
}

// Recruiter-set labels persisted as `candidate_status`; they never touch recovery or outreach attempts.
const CANDIDATE_LABELS = ['interested', 'not_interested', 'follow_up', 'awaiting_reply', 'pending_review'];

function isNoShow(interview) {
  return normalizeStatus(interview?.status) === 'no show' || interview?.attendance_status === 'no_show';
}

// Status shown in the dropdown: final outcomes first, then the recruiter label, then workflow state.
function candidateStatusOf(interview) {
  const status = normalizeStatus(interview?.status);
  if (status === 'client interview pending' || status === 'selected') return 'selected';
  if (status === 'rejected after interview' || status === 'rejected') return 'rejected';
  if (isCancelled(interview)) return 'cancelled';
  if (CANDIDATE_LABELS.includes(interview?.candidate_status)) return interview.candidate_status;
  const recoveryStatus = interview?.recovery?.status;
  if (recoveryStatus === 'AWAITING_RESPONSE') return 'awaiting_reply';
  if (recoveryStatus === 'RESCHEDULED' || recoveryStatus === 'RECOVERED' || status === 'rescheduled') return 'rescheduled';
  if (isNoShow(interview)) return 'no_show';
  if (isPastInterview(interview)) return 'pending_review';
  return null;
}

// Options that cannot be chosen for this interview, with the reason shown in the menu.
function statusDisabledReasons(interview) {
  const past = isPastInterview(interview);
  const reasons = {};
  if (isOutcomeLocked(interview)) {
    // The outcome is final; only the follow-up email stays available.
    INTERVIEW_STATUS_OPTIONS.forEach(({ value }) => { if (value !== 'follow_up') reasons[value] = 'Interview outcome already recorded'; });
    return reasons;
  }
  if (!past) {
    reasons.selected = 'Available after the interview';
    reasons.rejected = 'Available after the interview';
    reasons.no_show = 'Available after the interview';
  } else {
    reasons.rescheduled = 'Past interviews are rescheduled through the no-show follow-up';
    reasons.cancelled = 'Only upcoming interviews can be cancelled';
    if (isNoShow(interview)) reasons.no_show = 'No-show already recorded';
    else if (interview?.attendance_status === 'attended') reasons.no_show = 'Candidate marked as attended';
  }
  return reasons;
}

function deliveryStatus(item, key) {
  const value = item[key];
  if (!value || value === 'pending' || value === 'not_configured') {
    return item.status === 'Scheduled' || item.status === 'Rescheduled' || item.email_subject || item.email_body ? 'sent' : value;
  }
  return value;
}

function HiringPipeline() {
  const navigate = useNavigate();
  const [interviews, setInterviews] = useState([]);
  const [assessmentRows, setAssessmentRows] = useState([]);
  const [loading, setLoading] = useState(true);
  const [loadingAssessments, setLoadingAssessments] = useState(true);
  const [activeTab, setActiveTab] = useState('assessments');
  const [assessmentFilter, setAssessmentFilter] = useState('all');
  const [assessmentSearch, setAssessmentSearch] = useState('');
  const [generatingAssessmentId, setGeneratingAssessmentId] = useState(null);
  const [active, setActive] = useState(null);
  const [followupType, setFollowupType] = useState('thanks');
  const [draft, setDraft] = useState({ subject: '', body: '' });
  const [busy, setBusy] = useState(false);
  const [cancelActive, setCancelActive] = useState(null);
  const [cancelType, setCancelType] = useState('schedule_conflict');
  const [cancelDraft, setCancelDraft] = useState({ subject: '', body: '' });
  const [cancelBusy, setCancelBusy] = useState(false);
  const [cancelError, setCancelError] = useState('');
  const [viewFilter, setViewFilter] = useState('upcoming');
  const [statusFilter, setStatusFilter] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');
  const [rescheduleActive, setRescheduleActive] = useState(null);
  const [rescheduleForm, setRescheduleForm] = useState({
    interview_date: '',
    interview_time: '',
    interviewer: '',
    interview_mode: 'Online',
    meeting_link: '',
    notes: '',
  });
  const [rescheduleMessage, setRescheduleMessage] = useState({
    subject: '',
    body: '',
    text_body: '',
  });
  const [blockedSlots, setBlockedSlots] = useState([]);
  const [loadingSlots, setLoadingSlots] = useState(false);
  const [generatingRescheduleEmail, setGeneratingRescheduleEmail] = useState(false);
  const [rescheduleBusy, setRescheduleBusy] = useState(false);
  const [rescheduleError, setRescheduleError] = useState('');
  const [rescheduleSuccess, setRescheduleSuccess] = useState(null);
  const [outcomeBusyId, setOutcomeBusyId] = useState(null);
  const [statusErrors, setStatusErrors] = useState({});
  const [highlightedInterviewId, setHighlightedInterviewId] = useState(null);
  const [scheduleActive, setScheduleActive] = useState(null);
  const [scheduleDate, setScheduleDate] = useState('');
  const [scheduleTime, setScheduleTime] = useState('');
  const [scheduleDetails, setScheduleDetails] = useState({
    interviewer: '',
    interview_mode: 'Online',
    meeting_link: '',
    notes: '',
  });
  const [scheduleMessage, setScheduleMessage] = useState({
    from_email: '',
    to_email: '',
    subject: '',
    body: '',
    text_body: '',
  });
  const [generatingScheduleEmail, setGeneratingScheduleEmail] = useState(false);
  const [scheduleBusy, setScheduleBusy] = useState(false);
  const [scheduleError, setScheduleError] = useState('');
  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const timeOptions = useMemo(() => buildTimeOptions(blockedSlots), [blockedSlots]);

  const loadAssessments = async ({ silent = false } = {}) => {
    if (!silent) setLoadingAssessments(true);
    try {
      const data = await apiGet('/api/assessment/pipeline?limit=500');
      setAssessmentRows(data.pipeline || []);
    } catch (err) {
      if (!silent) toast({ type: 'error', message: err.message || 'Could not load assessment pipeline.' });
    } finally {
      if (!silent) setLoadingAssessments(false);
    }
  };

  const [recoveryCase, setRecoveryCase] = useState(null);
  const [recoveryBusy, setRecoveryBusy] = useState(false);
  const [attendanceBusyId, setAttendanceBusyId] = useState(null);

  const openRecoveryCase = async (caseId) => {
    setRecoveryBusy(true);
    try {
      const data = await apiGet(`/api/interview-recovery/cases/${caseId}`);
      setRecoveryCase(data.case || null);
    } catch (err) {
      toast({ type: 'error', message: err.message || 'Could not load the follow-up history.' });
    } finally {
      setRecoveryBusy(false);
    }
  };

  const recoveryAction = async (caseId, action) => {
    setRecoveryBusy(true);
    try {
      const { ok, data } = await apiPost(`/api/interview-recovery/cases/${caseId}/${action}`, {});
      if (!ok || !data.success) throw new Error(data.error || 'Could not update the follow-up.');
      setRecoveryCase(data.case || null);
      toast({ type: 'success', message: action === 'retry' ? 'Automatic follow-up restarted.' : 'Follow-up closed.' });
      await loadInterviews();
    } catch (err) {
      toast({ type: 'error', message: err.message || 'Could not update the follow-up.' });
    } finally {
      setRecoveryBusy(false);
    }
  };

  const markAttendance = async (interview, attendance) => {
    if (attendance === 'no_show' && !window.confirm(`Record ${interview.candidate_name || 'the candidate'} as a no-show? They will be emailed automatically with a link to choose a new time.`)) return;
    setAttendanceBusyId(interview.id);
    try {
      const { ok, data } = await apiPost(`/api/interviews/${interview.id}/attendance`, { attendance });
      if (!ok || !data.success) throw new Error(data.error || 'Could not record attendance.');
      toast({ type: 'success', message: attendance === 'no_show' ? 'No-show recorded. The candidate is being contacted automatically.' : 'Attendance recorded.' });
      await loadInterviews();
    } catch (err) {
      toast({ type: 'error', message: err.message || 'Could not record attendance.' });
    } finally {
      setAttendanceBusyId(null);
    }
  };

  const loadInterviews = async () => {
    setLoading(true);
    try {
      const data = await apiGet('/api/interviews');
      setInterviews(data.interviews || []);
    } catch (err) {
      toast({ type: 'error', message: err.message || 'Could not load interviews.' });
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadInterviews();
    loadAssessments();
  }, []);

  // Candidates finish, fail or get terminated while this page is open; keep statuses current.
  useEffect(() => {
    const refresh = () => { if (document.visibilityState === 'visible') loadAssessments({ silent: true }); };
    const timer = window.setInterval(refresh, ASSESSMENT_REFRESH_MS);
    document.addEventListener('visibilitychange', refresh);
    return () => { window.clearInterval(timer); document.removeEventListener('visibilitychange', refresh); };
  }, []);

  useEffect(() => {
    const activeDate = rescheduleActive ? rescheduleForm.interview_date : scheduleActive ? scheduleDate : '';
    if (!activeDate) {
      setBlockedSlots([]);
      return;
    }
    setLoadingSlots(true);
    setRescheduleError('');
    apiGet(
      `/api/interviews/blocked-slots?date=${encodeURIComponent(activeDate)}${rescheduleActive ? `&exclude_interview_id=${rescheduleActive.id}` : ''}`
    )
      .then(data => setBlockedSlots(data.blocked_slots || []))
      .catch(() => {
        setBlockedSlots([]);
        if (rescheduleActive) setRescheduleError('Could not load blocked interview times.');
        if (scheduleActive) setScheduleError('Could not load blocked interview times.');
      })
      .finally(() => setLoadingSlots(false));
  }, [rescheduleActive, rescheduleForm.interview_date, scheduleActive, scheduleDate]);

  useEffect(() => {
    if (!rescheduleForm.interview_time) return;
    const option = timeOptions.find(item => item.value === rescheduleForm.interview_time);
    if (option?.blocked) {
      setRescheduleForm(prev => ({ ...prev, interview_time: '' }));
    }
  }, [timeOptions, rescheduleForm.interview_time]);

  useEffect(() => {
    if (!scheduleTime) return;
    const option = timeOptions.find(item => item.value === scheduleTime);
    if (option?.blocked) {
      setScheduleTime('');
    }
  }, [timeOptions, scheduleTime]);

  const filteredInterviews = useMemo(() => {
    const query = searchTerm.trim().toLowerCase();
    return interviews.filter(item => {
      const status = normalizeStatus(item.status || 'Scheduled');
      const matchesSearch = !query || [item.candidate_name, item.candidate_email, item.job_role, item.interviewer]
        .some(value => String(value || '').toLowerCase().includes(query));
      const matchesStatus = statusFilter === 'all' || status === statusFilter;
      const past = isPastInterview(item);
      const matchesView =
        viewFilter === 'all' ||
        (viewFilter === 'upcoming' && !past && !isCancelled(item)) ||
        (viewFilter === 'needs_followup' && !isCancelled(item) && isPastInterview(item)) ||
        (viewFilter === 'past' && past) ||
        (viewFilter === 'cancelled' && isCancelled(item));
      return matchesSearch && matchesStatus && matchesView;
    });
  }, [interviews, searchTerm, statusFilter, viewFilter]);

  const assessmentCounts = useMemo(() => {
    const counts = { NOT_CREATED: 0, DRAFT: 0, SENT: 0, IN_PROGRESS: 0, COMPLETED: 0, PASSED: 0, FAILED: 0, TERMINATED: 0 };
    assessmentRows.forEach(row => {
      const status = String(row.assessment_status || 'NOT_CREATED');
      counts[status] = (counts[status] || 0) + 1;
    });
    return counts;
  }, [assessmentRows]);

  const interviewViewCounts = useMemo(() => {
    const counts = { upcoming: 0, needs_followup: 0, past: 0, cancelled: 0, all: interviews.length };
    interviews.forEach(item => {
      const past = isPastInterview(item);
      const cancelled = isCancelled(item);
      if (!past && !cancelled) counts.upcoming += 1;
      if (past && !cancelled) counts.needs_followup += 1;
      if (past) counts.past += 1;
      if (cancelled) counts.cancelled += 1;
    });
    return counts;
  }, [interviews]);

  const filteredAssessments = useMemo(() => {
    const query = assessmentSearch.trim().toLowerCase();
    return assessmentRows.filter(row => {
      const status = String(row.assessment_status || 'NOT_CREATED');
      const matchesStatus = assessmentFilter === 'all' || status === assessmentFilter;
      const matchesSearch = !query || [
        row.candidate_name,
        row.candidate_email,
        row.jd_title,
        row.interview_status,
      ].some(value => String(value || '').toLowerCase().includes(query));
      return matchesStatus && matchesSearch;
    });
  }, [assessmentRows, assessmentFilter, assessmentSearch]);

  const grouped = useMemo(() => {
    const map = new Map();
    filteredInterviews.forEach(item => {
      const key = formatDateTime(item.interview_start).date;
      map.set(key, [...(map.get(key) || []), item]);
    });
    return Array.from(map.entries());
  }, [filteredInterviews]);

  const refreshPipeline = async () => {
    await Promise.all([loadAssessments(), loadInterviews()]);
  };

  const generateAssessment = async (row) => {
    setGeneratingAssessmentId(`${row.candidate_id}-${row.jd_id}`);
    try {
      const { ok, data } = await apiPost('/api/assessment/generate', {
        candidate_id: row.candidate_id,
        jd_id: row.jd_id,
      });
      if (!ok || !data.assessment?.id) throw new Error(data.error || 'Could not generate assessment.');
      navigate(`/hiring-pipeline/assessment/${data.assessment.id}`);
    } catch (err) {
      toast({ type: 'error', message: err.message || 'Assessment generation failed.' });
    } finally {
      setGeneratingAssessmentId(null);
    }
  };

  const reviewAssessment = (row) => {
    if (row.assessment_id) navigate(`/hiring-pipeline/assessment/${row.assessment_id}`);
  };

  const openSchedule = (row) => {
    if (!row.eligible_for_interview) {
      toast({ type: 'error', message: 'Candidate must pass the assessment before scheduling.' });
      return;
    }
    setScheduleActive(row);
    setScheduleDate('');
    setScheduleTime('');
    setBlockedSlots([]);
    setScheduleError('');
    setScheduleDetails({
      interviewer: '',
      interview_mode: 'Online',
      meeting_link: '',
      notes: '',
    });
    setScheduleMessage({
      from_email: '',
      to_email: row.candidate_email || '',
      subject: '',
      body: '',
      text_body: '',
    });
    apiGet('/api/interviews/defaults')
      .then(data => setScheduleMessage(prev => ({ ...prev, from_email: data.from_email || '' })))
      .catch(() => setScheduleMessage(prev => ({ ...prev, from_email: 'Configured sender email' })));
  };

  const closeSchedule = () => {
    if (scheduleBusy || generatingScheduleEmail) return;
    setScheduleActive(null);
    setScheduleError('');
  };

  const generateScheduleEmail = async () => {
    if (!scheduleActive || !scheduleDate || !scheduleTime) {
      setScheduleError('Choose an interview date and available time first.');
      return;
    }
    setGeneratingScheduleEmail(true);
    setScheduleError('');
    try {
      const { ok, data } = await apiPost('/api/interviews/generate-email', {
        candidate_id: scheduleActive.candidate_id,
        jd_id: scheduleActive.jd_id,
        interview_date: scheduleDate,
        interview_time: scheduleTime,
      });
      if (!ok) {
        setScheduleError(data.error || 'Could not generate email.');
        return;
      }
      setScheduleMessage({
        from_email: data.from_email || '',
        to_email: data.to_email || scheduleActive.candidate_email || '',
        subject: data.subject || '',
        body: data.body || '',
        text_body: buildInterviewTextBody(scheduleActive, scheduleDate, scheduleTime),
      });
    } catch {
      setScheduleError('Could not generate email.');
    } finally {
      setGeneratingScheduleEmail(false);
    }
  };

  const sendSchedule = async () => {
    if (!scheduleActive || !scheduleDate || !scheduleTime || !scheduleMessage.subject || !scheduleMessage.body) {
      setScheduleError('Generate and review the email before sending.');
      return;
    }
    if (!scheduleDetails.interviewer.trim()) {
      setScheduleError('Interviewer is required.');
      return;
    }
    if (scheduleDetails.interview_mode === 'Online' && !scheduleDetails.meeting_link.trim()) {
      setScheduleError('Meeting link is required for online interviews.');
      return;
    }
    setScheduleBusy(true);
    setScheduleError('');
    try {
      const { ok, data } = await apiPost('/api/interviews/schedule', {
        candidate_id: scheduleActive.candidate_id,
        jd_id: scheduleActive.jd_id,
        interview_date: scheduleDate,
        interview_time: scheduleTime,
        interviewer: scheduleDetails.interviewer,
        interview_mode: scheduleDetails.interview_mode,
        meeting_link: scheduleDetails.meeting_link,
        notes: scheduleDetails.notes,
        text_body: scheduleMessage.text_body,
        subject: scheduleMessage.subject,
        body: scheduleMessage.body,
      });
      if (!ok || !data.success) throw new Error(data.error || 'Could not schedule interview.');
      toast({ type: 'success', message: 'Interview scheduled successfully.' });
      setScheduleActive(null);
      setActiveTab('interviews');
      await refreshPipeline();
    } catch (err) {
      setScheduleError(err.message || 'Interview email sending failed. Please try again.');
    } finally {
      setScheduleBusy(false);
    }
  };

  const openFollowup = async (interview) => {
    setActive(interview);
    setDraft({ subject: '', body: '' });
    setBusy(true);
    try {
      const { ok, data } = await apiPost(`/api/interviews/${interview.id}/generate-followup`, { type: followupType });
      if (!ok || !data.success) throw new Error(data.error || 'Could not generate follow-up.');
      setDraft({ subject: data.subject || '', body: data.body || '' });
    } catch (err) {
      toast({ type: 'error', message: err.message || 'Could not generate follow-up.' });
    } finally {
      setBusy(false);
    }
  };

  const regenerateFollowup = async () => {
    if (!active) return;
    await openFollowup(active);
  };

  const sendFollowup = async () => {
    if (!active || !draft.subject || !draft.body) return;
    setBusy(true);
    try {
      const { ok, data } = await apiPost(`/api/interviews/${active.id}/send-followup`, draft);
      if (!ok || !data.success) throw new Error(data.error || 'Could not send follow-up.');
      toast({ type: 'success', message: 'Follow-up email sent successfully.' });
      setActive(null);
      await loadInterviews();
    } catch (err) {
      toast({ type: 'error', message: err.message || 'Could not send follow-up.' });
    } finally {
      setBusy(false);
    }
  };

  const openCancel = async (interview) => {
    setCancelActive(interview);
    setCancelDraft({ subject: '', body: '' });
    setCancelError('');
    setCancelBusy(true);
    try {
      const { ok, data } = await apiPost(`/api/interviews/${interview.id}/generate-cancellation`, { type: cancelType });
      if (!ok || !data.success) throw new Error(data.error || 'Could not generate cancellation email.');
      setCancelDraft({ subject: data.subject || '', body: data.body || '' });
    } catch (err) {
      setCancelError(err.message || 'Could not generate cancellation email.');
      toast({ type: 'error', message: err.message || 'Could not generate cancellation email.' });
    } finally {
      setCancelBusy(false);
    }
  };

  const regenerateCancel = async () => {
    if (!cancelActive) return;
    await openCancel(cancelActive);
  };

  const sendCancellation = async () => {
    if (!cancelActive || !cancelDraft.subject || !cancelDraft.body) return;
    setCancelBusy(true);
    setCancelError('');
    try {
      const { ok, data } = await apiPost(`/api/interviews/${cancelActive.id}/send-cancellation`, {
        type: cancelType,
        subject: cancelDraft.subject,
        body: cancelDraft.body,
      });
      if (!ok || !data.success) throw new Error(data.error || 'Could not send cancellation email.');
      const updated = data.interview || { ...cancelActive, status: 'Cancelled', cancellation_status: 'sent' };
      setInterviews(prev => prev.map(item => (item.id === cancelActive.id ? updated : item)));
      setCancelActive(null);
      toast({ type: 'success', message: 'Cancellation email sent and interview cancelled.' });
    } catch (err) {
      setCancelError(err.message || 'Could not send cancellation email.');
      toast({ type: 'error', message: err.message || 'Could not send cancellation email.' });
    } finally {
      setCancelBusy(false);
    }
  };

  // outcome: 'selected' / 'rejected' (final, stops recovery) or a recruiter label from CANDIDATE_LABELS.
  const setInterviewOutcome = async (interview, outcome) => {
    const isFinal = outcome === 'selected' || outcome === 'rejected';
    setOutcomeBusyId(interview.id);
    setStatusErrors(prev => ({ ...prev, [interview.id]: '' }));
    try {
      let response = await apiPost(`/api/interviews/${interview.id}/outcome`, { outcome });
      if (!response.ok && response.status === 404) {
        response = await apiPost('/api/interviews/outcome', { interview_id: interview.id, outcome });
      }
      const { ok, status, data } = response;
      if (!ok || !data?.success) {
        const detail = data?.error || `Request failed with status ${status}`;
        throw new Error(`Could not update ${isFinal ? 'interview outcome' : 'candidate status'}. ${detail}`);
      }
      const updated = isFinal
        ? data.interview || { ...interview, status: outcome === 'selected' ? 'Client Interview Pending' : 'Rejected After Interview' }
        // Keep the recovery summary (outreach attempts) the outcome response does not include.
        : { ...interview, ...(data.interview || {}), candidate_status: outcome, recovery: interview.recovery };
      setInterviews(prev => prev.map(item => (item.id === interview.id ? updated : item)));
      const label = INTERVIEW_STATUS_OPTIONS.find(option => option.value === outcome)?.label || outcome;
      toast({
        type: 'success',
        message: outcome === 'selected' ? 'Candidate moved to client interview pending.'
          : outcome === 'rejected' ? 'Candidate marked rejected after interview.'
            : `Status updated to ${label}.`,
      });
      return true;
    } catch (err) {
      const message = err.message || 'Could not update the status.';
      setStatusErrors(prev => ({ ...prev, [interview.id]: message }));
      toast({ type: 'error', message });
      return false;
    } finally {
      setOutcomeBusyId(null);
    }
  };

  const changeCandidateStatus = async (interview, value) => {
    const current = candidateStatusOf(interview);
    if (value === 'follow_up') {
      // Opening the composer never depends on the label being saved.
      if (current !== 'follow_up' && !isOutcomeLocked(interview)) await setInterviewOutcome(interview, 'follow_up');
      openFollowup(interview);
      return;
    }
    if (value === current) return;
    if (value === 'no_show') { await markAttendance(interview, 'no_show'); return; }
    if (value === 'rescheduled') { openReschedule(interview); return; }
    if (value === 'cancelled') { openCancel(interview); return; }
    await setInterviewOutcome(interview, value);
  };

  const updateRescheduleField = (key, value) => {
    setRescheduleForm(prev => ({ ...prev, [key]: value }));
  };

  const resetRescheduleMessage = () => {
    setRescheduleMessage({ subject: '', body: '', text_body: '' });
  };

  const openReschedule = (interview) => {
    setRescheduleActive(interview);
    const form = {
      interview_date: formatDateInput(interview.interview_start),
      interview_time: formatTimeInput(interview.interview_start),
      interviewer: interview.interviewer || '',
      interview_mode: interview.interview_mode || 'Online',
      meeting_link: interview.meeting_link || '',
      notes: interview.notes || '',
    };
    setRescheduleForm(form);
    setRescheduleMessage({
      subject: interview.email_subject || '',
      body: interview.email_body || '',
      text_body: interview.text_body || buildRescheduleTextBody(interview, form),
    });
    setBlockedSlots([]);
    setRescheduleError('');
    setRescheduleSuccess(null);
  };

  const closeReschedule = () => {
    if (rescheduleBusy || generatingRescheduleEmail) return;
    setRescheduleActive(null);
    setRescheduleError('');
    setRescheduleSuccess(null);
  };

  const saveReschedule = async () => {
    if (!rescheduleActive) return;
    if (!rescheduleForm.interview_date || !rescheduleForm.interview_time) {
      setRescheduleError('Choose an interview date and available time.');
      return;
    }
    if (!rescheduleForm.interviewer.trim()) {
      setRescheduleError('Interviewer is required.');
      return;
    }
    if (rescheduleForm.interview_mode === 'Online' && !rescheduleForm.meeting_link.trim()) {
      setRescheduleError('Meeting link is required for online interviews.');
      return;
    }
    if (!rescheduleMessage.subject.trim() || !rescheduleMessage.body.trim()) {
      setRescheduleError('Generate and review the email before saving changes.');
      return;
    }

    setRescheduleBusy(true);
    setRescheduleError('');
    setRescheduleSuccess(null);
    try {
      const { ok, data } = await apiPost(`/api/interviews/${rescheduleActive.id}/reschedule`, {
        ...rescheduleForm,
        subject: rescheduleMessage.subject,
        body: rescheduleMessage.body,
        text_body: rescheduleMessage.text_body,
      });
      if (!ok || !data.success) throw new Error(data.error || 'Could not reschedule interview.');
      const updated = data.interview || {
        ...rescheduleActive,
        interview_start: `${rescheduleForm.interview_date}T${rescheduleForm.interview_time}`,
        interviewer: rescheduleForm.interviewer,
        interview_mode: rescheduleForm.interview_mode,
        meeting_link: rescheduleForm.meeting_link,
        notes: rescheduleForm.notes,
        email_subject: rescheduleMessage.subject,
        email_body: rescheduleMessage.body,
        text_body: rescheduleMessage.text_body,
      };
      setInterviews(prev => prev.map(item => (item.id === rescheduleActive.id ? updated : item)));
      setRescheduleActive(updated);
      setRescheduleSuccess(updated);
      toast({ type: 'success', message: 'Interview rescheduled successfully.' });
    } catch (err) {
      setRescheduleError(err.message || 'Could not reschedule interview.');
    } finally {
      setRescheduleBusy(false);
    }
  };

  const generateRescheduleEmail = async () => {
    if (!rescheduleActive || !rescheduleForm.interview_date || !rescheduleForm.interview_time) {
      setRescheduleError('Choose an interview date and available time first.');
      return;
    }
    setGeneratingRescheduleEmail(true);
    setRescheduleError('');
    try {
      const { ok, data } = await apiPost('/api/interviews/generate-email', {
        candidate_id: rescheduleActive.candidate_id,
        jd_id: rescheduleActive.jd_id,
        interview_date: rescheduleForm.interview_date,
        interview_time: rescheduleForm.interview_time,
        exclude_interview_id: rescheduleActive.id,
      });
      if (!ok) {
        setRescheduleError(data.error || 'Could not generate email.');
        return;
      }
      setRescheduleMessage({
        subject: data.subject || '',
        body: data.body || '',
        text_body: buildRescheduleTextBody(rescheduleActive, rescheduleForm),
      });
    } catch {
      setRescheduleError('Could not generate email.');
    } finally {
      setGeneratingRescheduleEmail(false);
    }
  };

  const viewUpdatedInterview = () => {
    const id = rescheduleSuccess?.id || rescheduleActive?.id;
    setRescheduleActive(null);
    setRescheduleSuccess(null);
    setHighlightedInterviewId(id);
    window.setTimeout(() => {
      document.getElementById(`interview-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 0);
    window.setTimeout(() => setHighlightedInterviewId(null), 3500);
  };

  return (
    <Layout>
      <div className="interviews-container hp-page">
        <header className="hp-header">
          <div>
            <h1>Hiring Pipeline</h1>
            <p>Move screened candidates through assessments and interviews to an outcome.</p>
          </div>
          <button type="button" className="hp-btn hp-btn-ghost" onClick={refreshPipeline} disabled={loading || loadingAssessments}>
            <i className={`fas fa-rotate${loading || loadingAssessments ? ' fa-spin' : ''}`} aria-hidden="true"></i> Refresh
          </button>
        </header>

        <section className="hp-stats" aria-label="Pipeline summary">
          {[
            ['fa-clipboard-list', 'To assess', assessmentCounts.NOT_CREATED + assessmentCounts.DRAFT, 'Assessment not created or still a draft'],
            ['fa-paper-plane', 'With candidates', assessmentCounts.SENT + assessmentCounts.IN_PROGRESS, 'Assessment sent or in progress'],
            ['fa-circle-check', 'Passed', assessmentCounts.PASSED, 'Passed the assessment'],
            ['fa-calendar-day', 'Upcoming interviews', interviewViewCounts.upcoming, 'Scheduled and not yet held'],
            ['fa-reply', 'Needs follow-up', interviewViewCounts.needs_followup, 'Interview held - record the outcome or follow up'],
          ].map(([icon, label, value, hint]) => (
            <div key={label} className="hp-stat" title={hint}>
              <span className="hp-stat-icon"><i className={`fas ${icon}`} aria-hidden="true"></i></span>
              <div><span>{label}</span><strong>{loading || loadingAssessments ? '—' : value}</strong></div>
            </div>
          ))}
        </section>

        <section className="hp-panel">
          <nav className="hp-tabs" role="tablist" aria-label="Hiring pipeline sections">
            {[
              ['assessments', 'Assessments', 'fa-clipboard-check', assessmentRows.length],
              ['interviews', 'Interviews', 'fa-calendar-check', interviews.length],
            ].map(([value, label, icon, count]) => (
              <button key={value} type="button" role="tab" aria-selected={activeTab === value}
                className={`hp-tab${activeTab === value ? ' active' : ''}`} onClick={() => setActiveTab(value)}>
                <i className={`fas ${icon}`} aria-hidden="true"></i> {label}<span>{count}</span>
              </button>
            ))}
          </nav>

          {activeTab === 'assessments' && (
            <>
              <div className="hp-toolbar">
                <div className="hp-chips" role="group" aria-label="Assessment filters">
                  {/* Hide empty statuses so the bar only shows stages that have candidates. */}
                  {ASSESSMENT_FILTERS.filter(([value]) => value === 'all' || value === assessmentFilter || assessmentCounts[value] > 0).map(([value, label]) => (
                    <button key={value} type="button" aria-pressed={assessmentFilter === value}
                      className={`hp-chip${assessmentFilter === value ? ' active' : ''}`} onClick={() => setAssessmentFilter(value)}>
                      {label}<span>{value === 'all' ? assessmentRows.length : assessmentCounts[value] || 0}</span>
                    </button>
                  ))}
                </div>
                <label className="hp-search">
                  <i className="fas fa-search" aria-hidden="true"></i>
                  <input type="search" value={assessmentSearch} onChange={(event) => setAssessmentSearch(event.target.value)}
                    placeholder="Search candidate or job" aria-label="Search assessments" />
                </label>
              </div>

              {loadingAssessments ? (
                <div className="hp-empty"><i className="fas fa-spinner fa-spin" aria-hidden="true"></i><p>Loading assessments…</p></div>
              ) : filteredAssessments.length === 0 ? (
                <div className="hp-empty"><i className="fas fa-clipboard" aria-hidden="true"></i><p>No candidates match this view.</p></div>
              ) : (
                <>
                <div className="hp-row hp-row-assessment hp-row-head" aria-hidden="true">
                  <span>Candidate</span><span>Contact</span><span>Scores</span><span>Progress</span><span className="hp-head-actions">Next step</span>
                </div>
                <ul className="hp-list" aria-label="Assessment queue">
                  {filteredAssessments.map(row => {
                    const showScore = isAssessmentScoreVisible(row.assessment_status);
                    const generatedKey = `${row.candidate_id}-${row.jd_id}`;
                    const activeInterview = hasActiveInterview(row);
                    const status = row.assessment_status || 'NOT_CREATED';
                    const phone = realValue(row.candidate_phone);
                    const milestone = row.completed_at ? ['fa-flag-checkered', `Completed ${formatAssessmentDate(row.completed_at)}`]
                      : row.started_at ? ['fa-play', `Started ${formatAssessmentDate(row.started_at)}`]
                        : row.sent_at ? ['fa-paper-plane', `Sent ${formatAssessmentDate(row.sent_at)}`] : null;
                    const linkNote = !activeInterview && status !== 'NOT_CREATED' && status !== 'DRAFT'
                      ? `Link ${String(row.link_status || 'not sent').toLowerCase()}` : null;
                    const testScore = showScore && row.assessment_percentage != null;
                    return (
                      <li key={generatedKey} className="hp-row hp-row-assessment">
                        <div className="hp-person">
                          <span className="hp-avatar" aria-hidden="true">{initials(row.candidate_name || row.candidate_email || '?')}</span>
                          <div>
                            <Link to={`/talent/${row.candidate_id}`} className="hp-name">{row.candidate_name || row.candidate_email}</Link>
                            <span className="hp-sub" title={row.jd_title || undefined}><i className="fas fa-briefcase" aria-hidden="true"></i>{row.jd_title || 'No job'}</span>
                          </div>
                        </div>
                        <div className="hp-meta">
                          {row.candidate_email && <span title={row.candidate_email}><i className="fas fa-envelope" aria-hidden="true"></i>{row.candidate_email}</span>}
                          {phone && <span><i className="fas fa-phone" aria-hidden="true"></i>{phone}</span>}
                          {!row.candidate_email && !phone && <span className="hp-note">No contact details</span>}
                        </div>
                        <div className="hp-score">
                          <span className={`hp-match${row.match_score == null ? ' is-empty' : ''}`} title="Resume match score">{row.match_score != null ? pct(row.match_score) : '—'}<small>match</small></span>
                          <span className={`hp-match hp-match-test${testScore ? '' : ' is-empty'}`} title="Assessment score">{testScore ? pct(row.assessment_percentage) : '—'}<small>test</small></span>
                        </div>
                        <div className="hp-progress">
                          <div className="hp-progress-pills">
                            <span className={`hp-pill ${ASSESSMENT_TONE[status] || 'muted'}`}>{formatAssessmentStatus(status)}</span>
                            {activeInterview && <span className={`hp-pill ${toneOf(row.interview_status)}`}>{interviewLabel(row.interview_status)}</span>}
                          </div>
                          {(milestone || linkNote) && (
                            <span className="hp-progress-note">
                              {milestone && <><i className={`fas ${milestone[0]}`} aria-hidden="true"></i>{milestone[1]}</>}
                              {milestone && linkNote && <span className="hp-dot" aria-hidden="true">·</span>}
                              {linkNote}
                            </span>
                          )}
                          {status === 'TERMINATED' && row.termination_reason && (
                            <span className="hp-progress-note is-bad" title={row.termination_reason}>
                              <i className="fas fa-triangle-exclamation" aria-hidden="true"></i>{row.termination_reason}
                            </span>
                          )}
                        </div>
                        <div className="hp-actions">
                          {status === 'NOT_CREATED' && (
                            <button type="button" className="hp-btn hp-btn-primary" disabled={generatingAssessmentId === generatedKey} onClick={() => generateAssessment(row)}>
                              <i className={`fas ${generatingAssessmentId === generatedKey ? 'fa-spinner fa-spin' : 'fa-wand-magic-sparkles'}`} aria-hidden="true"></i>
                              {generatingAssessmentId === generatedKey ? 'Generating…' : 'Generate assessment'}
                            </button>
                          )}
                          {row.assessment_id && ['DRAFT', 'IN_PROGRESS', 'COMPLETED', 'PASSED', 'FAILED', 'TERMINATED'].includes(status) && (
                            <button type="button" className={`hp-btn ${status === 'DRAFT' ? 'hp-btn-primary' : 'hp-btn-ghost'}`} onClick={() => reviewAssessment(row)}
                              title={status === 'DRAFT' ? undefined : 'View candidate test'}>
                              <i className={`fas ${status === 'DRAFT' ? 'fa-clipboard-check' : 'fa-user-shield'}`} aria-hidden="true"></i> {status === 'DRAFT' ? 'Review & send' : 'View test'}
                            </button>
                          )}
                          {row.eligible_for_interview && !activeInterview && (
                            <button type="button" className="hp-btn hp-btn-success" onClick={() => openSchedule(row)}>
                              <i className="fas fa-calendar-plus" aria-hidden="true"></i> Schedule interview
                            </button>
                          )}
                          <Link to={`/talent/${row.candidate_id}`} className="hp-icon-btn" aria-label={`View ${row.candidate_name || 'candidate'}`} title="View candidate">
                            <i className="fas fa-arrow-up-right-from-square" aria-hidden="true"></i>
                          </Link>
                        </div>
                      </li>
                    );
                  })}
                </ul>
                </>
              )}
            </>
          )}

          {activeTab === 'interviews' && (
            <>
              <div className="hp-toolbar">
                <div className="hp-chips" role="group" aria-label="Interview filters">
                  {INTERVIEW_VIEWS.map(([value, label]) => (
                    <button key={value} type="button" aria-pressed={viewFilter === value}
                      className={`hp-chip${viewFilter === value ? ' active' : ''}`} onClick={() => setViewFilter(value)}>
                      {label}<span>{interviewViewCounts[value]}</span>
                    </button>
                  ))}
                </div>
                <div className="hp-toolbar-right">
                  <label className="hp-search">
                    <i className="fas fa-search" aria-hidden="true"></i>
                    <input type="search" value={searchTerm} onChange={(event) => setSearchTerm(event.target.value)}
                      placeholder="Search candidate, job or interviewer" aria-label="Search interviews" />
                  </label>
                  <select className="hp-select" value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)} aria-label="Interview status">
                    <option value="all">All statuses</option>
                    <option value="scheduled">Scheduled</option>
                    <option value="rescheduled">Rescheduled</option>
                    <option value="cancelled">Cancelled</option>
                    <option value="client interview pending">Client pending</option>
                    <option value="rejected after interview">Rejected after interview</option>
                  </select>
                </div>
              </div>

              {loading ? (
                <div className="hp-empty"><i className="fas fa-spinner fa-spin" aria-hidden="true"></i><p>Loading interviews…</p></div>
              ) : grouped.length === 0 ? (
                <div className="hp-empty"><i className="fas fa-calendar-xmark" aria-hidden="true"></i><p>No interviews match this view.</p></div>
              ) : (
                <>
                <div className="hp-row hp-row-interview hp-row-head" aria-hidden="true">
                  <span>Time</span><span>Candidate</span><span>Details</span><span>Status</span><span className="hp-head-actions">Actions</span>
                </div>
                <div className="hp-days">
                  {grouped.map(([date, rows]) => (
                    <section key={date} className="hp-day" aria-label={date}>
                      <h2 className="hp-day-head"><i className="fas fa-calendar" aria-hidden="true"></i> {date}<span>{rows.length} interview{rows.length === 1 ? '' : 's'}</span></h2>
                      <ul className="hp-list">
                        {rows.map(item => {
                          const stamp = formatDateTime(item.interview_start);
                          const emailStatus = deliveryStatus(item, 'email_status');
                          const textStatus = deliveryStatus(item, 'text_status');
                          const past = isPastInterview(item);
                          const cancelled = isCancelled(item);
                          const lockedOutcome = isOutcomeLocked(item);
                          const recovery = recoveryState(item.recovery);
                          const noShow = normalizeStatus(item.status) === 'no show' || item.attendance_status === 'no_show';
                          const canMarkAttendance = past && !cancelled && !lockedOutcome && !noShow && item.attendance_status !== 'attended';
                          return (
                            <li key={item.id} id={`interview-${item.id}`}
                              className={`hp-row hp-row-interview${cancelled ? ' is-cancelled' : ''}${highlightedInterviewId === item.id ? ' is-highlighted' : ''}`}>
                              <div className="hp-time">
                                <strong>{stamp.time || '—'}</strong>
                                <small>{item.interview_mode || 'Interview'}</small>
                              </div>
                              <div className="hp-person">
                                <span className="hp-avatar" aria-hidden="true">{initials(item.candidate_name || item.candidate_email || '?')}</span>
                                <div>
                                  {item.candidate_id
                                    ? <Link to={`/talent/${item.candidate_id}`} className="hp-name">{item.candidate_name || item.candidate_email}</Link>
                                    : <span className="hp-name">{item.candidate_name || item.candidate_email}</span>}
                                  <span className="hp-sub">{item.job_role || 'No job'}</span>
                                </div>
                              </div>
                              <div className="hp-meta">
                                {item.interviewer && <span><i className="fas fa-user-tie" aria-hidden="true"></i>{item.interviewer}</span>}
                                {item.meeting_link && <a href={item.meeting_link} target="_blank" rel="noreferrer"><i className="fas fa-video" aria-hidden="true"></i>Join meeting</a>}
                                {item.notes && <span className="hp-note" title={item.notes}><i className="fas fa-note-sticky" aria-hidden="true"></i>{item.notes}</span>}
                              </div>
                              <div className="hp-pills">
                                <span className={`hp-pill ${noShow ? 'bad' : toneOf(item.status || 'scheduled')}`}>{prettyStatus(item.status || 'Scheduled')}</span>
                                {item.attendance_status === 'attended' && <span className="hp-pill good">Attended</span>}
                                {recovery && (
                                  <button type="button" className={`hp-pill hp-pill-btn ${recovery.tone}`} onClick={() => openRecoveryCase(item.recovery.id)}
                                    disabled={recoveryBusy} title={`${recovery.label} · view follow-up history`}>
                                    <i className="fas fa-robot" aria-hidden="true"></i> {recovery.label}
                                  </button>
                                )}
                                {item.recovery && (
                                  <span className="hp-recovery-meta">
                                    {item.recovery.recovery_type === 'NO_SHOW' ? 'Follow-ups' : 'Offers'} sent: {item.recovery.attempt_count || 0} of {item.recovery.max_attempts || '—'}
                                    {item.recovery.last_outreach_at && ` · last ${formatDateTime(item.recovery.last_outreach_at).date} ${formatDateTime(item.recovery.last_outreach_at).time}`}
                                  </span>
                                )}
                                <span className="hp-delivery" title={`Email ${prettyStatus(emailStatus || 'sent')} · Text ${prettyStatus(textStatus || 'sent')} · Follow-up ${prettyStatus(item.followup_status || 'not sent')}`}>
                                  <i className={`fas fa-envelope ${toneOf(emailStatus || 'sent')}`} aria-label={`Email ${prettyStatus(emailStatus || 'sent')}`}></i>
                                  <i className={`fas fa-comment-sms ${toneOf(textStatus || 'sent')}`} aria-label={`Text ${prettyStatus(textStatus || 'sent')}`}></i>
                                  <i className={`fas fa-reply ${toneOf(item.followup_status)}`} aria-label={`Follow-up ${prettyStatus(item.followup_status || 'not sent')}`}></i>
                                </span>
                              </div>
                              <div className="hp-actions">
                                {canMarkAttendance && (
                                  <>
                                    <button type="button" className="hp-btn hp-btn-ghost" onClick={() => markAttendance(item, 'attended')} disabled={attendanceBusyId === item.id}
                                      title="The candidate attended this interview">
                                      <i className="fas fa-user-check" aria-hidden="true"></i> Attended
                                    </button>
                                    <button type="button" className="hp-btn hp-btn-warn" onClick={() => markAttendance(item, 'no_show')} disabled={attendanceBusyId === item.id}
                                      title="The candidate did not attend: send the automatic follow-up">
                                      <i className={`fas ${attendanceBusyId === item.id ? 'fa-spinner fa-spin' : 'fa-user-slash'}`} aria-hidden="true"></i> No-show
                                    </button>
                                  </>
                                )}
                                {!past && !cancelled && (
                                  <button type="button" className="hp-btn hp-btn-ghost" onClick={() => openReschedule(item)}>
                                    <i className="fas fa-calendar-plus" aria-hidden="true"></i> Reschedule
                                  </button>
                                )}
                                <InterviewStatusMenu
                                  value={candidateStatusOf(item)}
                                  onChange={(value) => changeCandidateStatus(item, value)}
                                  busy={outcomeBusyId === item.id || attendanceBusyId === item.id}
                                  disabled={cancelled}
                                  disabledTitle="This interview was cancelled"
                                  disabledReasons={statusDisabledReasons(item)}
                                  error={statusErrors[item.id]}
                                  label={`Status for ${item.candidate_name || 'candidate'}`}
                                />
                                {!past && !cancelled && (
                                  <button type="button" className="hp-icon-btn hp-icon-danger" onClick={() => openCancel(item)} aria-label={`Cancel interview with ${item.candidate_name || 'candidate'}`} title="Cancel interview">
                                    <i className="fas fa-ban" aria-hidden="true"></i>
                                  </button>
                                )}
                              </div>
                            </li>
                          );
                        })}
                      </ul>
                    </section>
                  ))}
                </div>
                </>
              )}
            </>
          )}
        </section>

        {recoveryCase && (
          <div className="jd-modal-backdrop" role="presentation">
            <div className="jd-schedule-modal" role="dialog" aria-modal="true" aria-labelledby="recovery-case-title">
              <div className="jd-modal-header">
                <div>
                  <h2 id="recovery-case-title"><i className="fas fa-robot"></i> {recoveryCase.recovery_type === 'NO_SHOW' ? 'No-show follow-up' : 'Reschedule request'}</h2>
                  <p>
                    {recoveryState(recoveryCase)?.label || prettyStatus(recoveryCase.status)} · attempt {recoveryCase.attempt_count} of {recoveryCase.max_attempts}
                    {recoveryCase.detected_at && ` · detected ${formatDateTime(recoveryCase.detected_at).date} ${formatDateTime(recoveryCase.detected_at).time}`}
                  </p>
                </div>
                <button type="button" className="jd-modal-close" onClick={() => setRecoveryCase(null)} aria-label="Close follow-up history">
                  <i className="fas fa-times"></i>
                </button>
              </div>
              {recoveryCase.escalation_reason && (
                <div className="recovery-modal-alert">
                  <strong>{recoveryCase.escalation_reason}</strong>
                  {recoveryCase.recommended_action && <span>Next step: {recoveryCase.recommended_action}</span>}
                </div>
              )}
              {recoveryCase.confirmed_slot && <p className="recovery-modal-note">New interview time: {recoveryCase.confirmed_slot.label}</p>}
              {recoveryCase.last_error && !recoveryCase.escalation_reason && <p className="recovery-modal-note">Last error: {recoveryCase.last_error}</p>}
              {recoveryCase.email_delivery_status && <p className="recovery-modal-note">Email delivery: {prettyStatus(recoveryCase.email_delivery_status)}</p>}
              {recoveryCase.next_retry_at && <p className="recovery-modal-note">Next recovery check: {formatDateTime(recoveryCase.next_retry_at).date} {formatDateTime(recoveryCase.next_retry_at).time}</p>}
              <ol className="recovery-history">
                {(recoveryCase.history || []).map(entry => (
                  <li key={entry.id}>
                    <span className="recovery-history-time">{formatDateTime(entry.created_at).date} {formatDateTime(entry.created_at).time}</span>
                    <span className="recovery-history-action">{prettyStatus(entry.action)}{entry.message_type ? ` (attempt ${entry.attempt_number})` : ''}</span>
                    {entry.delivery_status && <span className={`hp-pill ${entry.delivery_status === 'sent' ? 'good' : 'bad'}`}>{entry.delivery_status === 'sent' ? 'Email sent' : entry.delivery_status === 'unknown' ? 'Delivery uncertain' : 'Delivery failed'}</span>}
                    {entry.failure_reason && <span className="recovery-history-error">{entry.failure_reason}</span>}
                  </li>
                ))}
              </ol>
              <div className="jd-modal-actions">
                {!['RESCHEDULED', 'RECOVERED', 'CLOSED'].includes(recoveryCase.status) && (
                  <button type="button" className="btn btn-secondary" onClick={() => recoveryAction(recoveryCase.id, 'close')} disabled={recoveryBusy}>
                    <i className="fas fa-circle-xmark"></i> Mark resolved
                  </button>
                )}
                {recoveryCase.status === 'ESCALATED' && recoveryCase.recovery_type !== 'NO_SHOW' && (
                  <button type="button" className="btn btn-primary" onClick={() => recoveryAction(recoveryCase.id, 'retry')} disabled={recoveryBusy}>
                    <i className="fas fa-rotate"></i> Retry follow-up
                  </button>
                )}
              </div>
            </div>
          </div>
        )}

        {scheduleActive && (
          <div className="jd-modal-backdrop" role="presentation">
            <div className="jd-schedule-modal" role="dialog" aria-modal="true" aria-labelledby="schedule-title">
              <div className="jd-modal-header">
                <div>
                  <h2 id="schedule-title">Schedule Interview</h2>
                  <p>{scheduleActive.candidate_name || scheduleActive.candidate_email} - {scheduleActive.jd_title}</p>
                </div>
                <button type="button" className="jd-modal-close" onClick={closeSchedule} aria-label="Close schedule modal">
                  <i className="fas fa-times"></i>
                </button>
              </div>

              <div className="jd-schedule-grid">
                <div className="form-group">
                  <label>From</label>
                  <input value={scheduleMessage.from_email || 'Configured sender email'} readOnly />
                </div>
                <div className="form-group">
                  <label>Email To</label>
                  <input value={scheduleMessage.to_email || scheduleActive.candidate_email || ''} readOnly />
                </div>
                <div className="form-group">
                  <label>Phone To</label>
                  <input value={scheduleActive.candidate_phone || ''} readOnly />
                </div>
                <div className="form-group">
                  <label>Interview Date</label>
                  <input
                    type="date"
                    value={scheduleDate}
                    min={today}
                    onChange={(event) => {
                      setScheduleDate(event.target.value);
                      setScheduleTime('');
                      setScheduleMessage(prev => ({ ...prev, subject: '', body: '', text_body: '' }));
                    }}
                  />
                </div>
                <div className="form-group">
                  <label>Interview Time</label>
                  <select
                    value={scheduleTime}
                    disabled={!scheduleDate || loadingSlots}
                    onChange={(event) => {
                      setScheduleTime(event.target.value);
                      setScheduleMessage(prev => ({ ...prev, subject: '', body: '', text_body: '' }));
                    }}
                  >
                    <option value="">{loadingSlots ? 'Loading times...' : 'Select an available time'}</option>
                    {timeOptions.map(option => (
                      <option key={option.value} value={option.value} disabled={option.blocked}>
                        {option.label}{option.blocked ? ' - booked' : ''}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label>Interviewer</label>
                  <input
                    value={scheduleDetails.interviewer}
                    onChange={(event) => setScheduleDetails(prev => ({ ...prev, interviewer: event.target.value }))}
                    placeholder="Interviewer name"
                  />
                </div>
                <div className="form-group">
                  <label>Mode</label>
                  <select
                    value={scheduleDetails.interview_mode}
                    onChange={(event) => setScheduleDetails(prev => ({ ...prev, interview_mode: event.target.value }))}
                  >
                    <option value="Online">Online</option>
                    <option value="Phone">Phone</option>
                    <option value="In Person">In Person</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>Meeting Link</label>
                  <input
                    value={scheduleDetails.meeting_link}
                    onChange={(event) => setScheduleDetails(prev => ({ ...prev, meeting_link: event.target.value }))}
                    placeholder="https://..."
                  />
                </div>
                <div className="form-group">
                  <label>Notes</label>
                  <input
                    value={scheduleDetails.notes}
                    onChange={(event) => setScheduleDetails(prev => ({ ...prev, notes: event.target.value }))}
                    placeholder="Interview notes"
                  />
                </div>
              </div>

              {blockedSlots.length > 0 && (
                <div className="jd-blocked-slots">
                  {blockedSlots.map((slot, index) => (
                    <span key={`${slot.start}-${index}`}>{slot.start} - {slot.end} blocked</span>
                  ))}
                </div>
              )}

              <div className="form-group">
                <label>Subject</label>
                <input
                  value={scheduleMessage.subject}
                  onChange={(event) => setScheduleMessage(prev => ({ ...prev, subject: event.target.value }))}
                  placeholder="Generate email to fill subject"
                />
              </div>
              <div className="form-group">
                <label>Email Body</label>
                <textarea
                  className="jd-email-body"
                  value={scheduleMessage.body}
                  onChange={(event) => setScheduleMessage(prev => ({ ...prev, body: event.target.value }))}
                  placeholder="Generate email after selecting date and time"
                />
              </div>
              <div className="form-group">
                <label>Text Body</label>
                <textarea
                  className="jd-sms-body"
                  value={scheduleMessage.text_body}
                  onChange={(event) => setScheduleMessage(prev => ({ ...prev, text_body: event.target.value }))}
                  placeholder="Generate after selecting date and time"
                />
              </div>
              {scheduleError && <div className="jd-schedule-alert jd-schedule-alert-error">{scheduleError}</div>}

              <div className="jd-modal-actions">
                <button type="button" className="btn btn-secondary" onClick={closeSchedule} disabled={generatingScheduleEmail || scheduleBusy}>Cancel</button>
                <button type="button" className="btn btn-primary" onClick={generateScheduleEmail} disabled={generatingScheduleEmail || scheduleBusy || !scheduleDate || !scheduleTime}>
                  {generatingScheduleEmail ? <><i className="fas fa-spinner fa-spin"></i> Generating...</> : <><i className="fas fa-magic"></i> Generate</>}
                </button>
                <button
                  type="button"
                  className="btn btn-success"
                  onClick={sendSchedule}
                  disabled={
                    generatingScheduleEmail ||
                    scheduleBusy ||
                    !scheduleMessage.subject ||
                    !scheduleMessage.body ||
                    !scheduleDetails.interviewer.trim() ||
                    (scheduleDetails.interview_mode === 'Online' && !scheduleDetails.meeting_link.trim())
                  }
                >
                  {scheduleBusy ? <><i className="fas fa-spinner fa-spin"></i> Sending...</> : <><i className="fas fa-paper-plane"></i> Send & Schedule</>}
                </button>
              </div>
            </div>
          </div>
        )}

        {active && (
          <div className="jd-modal-backdrop" role="presentation">
            <div className="jd-schedule-modal" role="dialog" aria-modal="true">
              <div className="jd-modal-header">
                <h2><i className="fas fa-reply"></i> Follow-up Message</h2>
                <button type="button" className="jd-modal-close" onClick={() => setActive(null)}><i className="fas fa-times"></i></button>
              </div>
              <div className="form-group">
                <label>Template</label>
                <select value={followupType} onChange={(event) => setFollowupType(event.target.value)}>
                  <option value="thanks">Thanks for attending</option>
                  <option value="next_round">Next round invite</option>
                  <option value="rejection">Post-interview rejection</option>
                </select>
              </div>
              <div className="form-group">
                <label>Subject</label>
                <input value={draft.subject} onChange={(event) => setDraft(prev => ({ ...prev, subject: event.target.value }))} />
              </div>
              <div className="form-group">
                <label>Body</label>
                <textarea className="jd-email-body" value={draft.body} onChange={(event) => setDraft(prev => ({ ...prev, body: event.target.value }))} />
              </div>
              <div className="jd-modal-actions">
                <button type="button" className="btn btn-secondary" onClick={regenerateFollowup} disabled={busy}>Generate</button>
                <button type="button" className="btn btn-success" onClick={sendFollowup} disabled={busy || !draft.subject || !draft.body}>
                  {busy ? <><i className="fas fa-spinner fa-spin"></i> Working...</> : <><i className="fas fa-paper-plane"></i> Send Follow-up</>}
                </button>
              </div>
            </div>
          </div>
        )}

        {cancelActive && (
          <div className="jd-modal-backdrop" role="presentation">
            <div className="jd-schedule-modal" role="dialog" aria-modal="true">
              <div className="jd-modal-header">
                <div>
                  <h2><i className="fas fa-ban"></i> Cancel Interview</h2>
                  <p>{cancelActive.candidate_name || cancelActive.candidate_email} - {cancelActive.job_role}</p>
                </div>
                <button type="button" className="jd-modal-close" onClick={() => setCancelActive(null)} disabled={cancelBusy} aria-label="Close cancellation modal">
                  <i className="fas fa-times"></i>
                </button>
              </div>
              <div className="form-group">
                <label>Cancellation Type</label>
                <select
                  value={cancelType}
                  onChange={(event) => {
                    setCancelType(event.target.value);
                    setCancelDraft({ subject: '', body: '' });
                  }}
                  disabled={cancelBusy}
                >
                  <option value="schedule_conflict">Scheduling conflict</option>
                  <option value="role_on_hold">Role on hold</option>
                  <option value="position_closed">Position closed</option>
                  <option value="candidate_request">Candidate requested cancellation</option>
                </select>
              </div>
              <div className="form-group">
                <label>Subject</label>
                <input
                  value={cancelDraft.subject}
                  onChange={(event) => setCancelDraft(prev => ({ ...prev, subject: event.target.value }))}
                  placeholder="Generate cancellation email to fill subject"
                  disabled={cancelBusy}
                />
              </div>
              <div className="form-group">
                <label>Body</label>
                <textarea
                  className="jd-email-body"
                  value={cancelDraft.body}
                  onChange={(event) => setCancelDraft(prev => ({ ...prev, body: event.target.value }))}
                  placeholder="Generate cancellation email"
                  disabled={cancelBusy}
                />
              </div>
              {cancelError && <div className="jd-schedule-alert jd-schedule-alert-error">{cancelError}</div>}
              <div className="jd-modal-actions">
                <button type="button" className="btn btn-secondary" onClick={regenerateCancel} disabled={cancelBusy}>
                  {cancelBusy ? <><i className="fas fa-spinner fa-spin"></i> Generating...</> : <><i className="fas fa-magic"></i> Generate</>}
                </button>
                <button type="button" className="btn btn-danger" onClick={sendCancellation} disabled={cancelBusy || !cancelDraft.subject || !cancelDraft.body}>
                  {cancelBusy ? <><i className="fas fa-spinner fa-spin"></i> Working...</> : <><i className="fas fa-paper-plane"></i> Send Cancellation</>}
                </button>
              </div>
            </div>
          </div>
        )}

        {rescheduleActive && (
          <div className="jd-modal-backdrop" role="presentation">
            <div className="jd-schedule-modal" role="dialog" aria-modal="true" aria-labelledby="reschedule-title">
              <div className="jd-modal-header">
                <div>
                  <h2 id="reschedule-title"><i className="fas fa-calendar-plus"></i> Reschedule Interview</h2>
                  <p>{rescheduleActive.candidate_name || rescheduleActive.candidate_email} - {rescheduleActive.job_role}</p>
                </div>
                <button type="button" className="jd-modal-close" onClick={closeReschedule} aria-label="Close reschedule modal">
                  <i className="fas fa-times"></i>
                </button>
              </div>

              <div className="jd-schedule-grid">
                <div className="form-group">
                  <label>Email To</label>
                  <input value={rescheduleActive.to_email || rescheduleActive.candidate_email || ''} readOnly />
                </div>
                <div className="form-group">
                  <label>Phone To</label>
                  <input value={rescheduleActive.candidate_phone || ''} readOnly />
                </div>
                <div className="form-group">
                  <label>Interview Date</label>
                  <input
                    type="date"
                    value={rescheduleForm.interview_date}
                    min={today}
                    onChange={(event) => {
                      updateRescheduleField('interview_date', event.target.value);
                      updateRescheduleField('interview_time', '');
                      resetRescheduleMessage();
                    }}
                    disabled={Boolean(rescheduleSuccess)}
                  />
                </div>
                <div className="form-group">
                  <label>Interview Time</label>
                  <select
                    value={rescheduleForm.interview_time}
                    disabled={!rescheduleForm.interview_date || loadingSlots || Boolean(rescheduleSuccess)}
                    onChange={(event) => {
                      updateRescheduleField('interview_time', event.target.value);
                      resetRescheduleMessage();
                    }}
                  >
                    <option value="">{loadingSlots ? 'Loading times...' : 'Select an available time'}</option>
                    {timeOptions.map(option => (
                      <option key={option.value} value={option.value} disabled={option.blocked}>
                        {option.label}{option.blocked ? ' - booked' : ''}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="form-group">
                  <label>Interviewer</label>
                  <input
                    value={rescheduleForm.interviewer}
                    onChange={(event) => updateRescheduleField('interviewer', event.target.value)}
                    placeholder="Interviewer name"
                    disabled={Boolean(rescheduleSuccess)}
                  />
                </div>
                <div className="form-group">
                  <label>Mode</label>
                  <select
                    value={rescheduleForm.interview_mode}
                    onChange={(event) => {
                      updateRescheduleField('interview_mode', event.target.value);
                      resetRescheduleMessage();
                    }}
                    disabled={Boolean(rescheduleSuccess)}
                  >
                    <option value="Online">Online</option>
                    <option value="Phone">Phone</option>
                    <option value="In Person">In Person</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>Meeting Link</label>
                  <input
                    value={rescheduleForm.meeting_link}
                    onChange={(event) => {
                      updateRescheduleField('meeting_link', event.target.value);
                      resetRescheduleMessage();
                    }}
                    placeholder="https://..."
                    disabled={Boolean(rescheduleSuccess)}
                  />
                </div>
                <div className="form-group">
                  <label>Notes</label>
                  <input
                    value={rescheduleForm.notes}
                    onChange={(event) => updateRescheduleField('notes', event.target.value)}
                    placeholder="Interview notes"
                    disabled={Boolean(rescheduleSuccess)}
                  />
                </div>
              </div>

              {blockedSlots.length > 0 && !rescheduleSuccess && (
                <div className="jd-blocked-slots">
                  {blockedSlots.map((slot, index) => (
                    <span key={`${slot.start}-${index}`}>{slot.start} - {slot.end} blocked</span>
                  ))}
                </div>
              )}

              <div className="form-group">
                <label>Subject</label>
                <input
                  value={rescheduleMessage.subject}
                  onChange={(event) => setRescheduleMessage(prev => ({ ...prev, subject: event.target.value }))}
                  placeholder="Generate email to fill subject"
                  disabled={Boolean(rescheduleSuccess)}
                />
              </div>
              <div className="form-group">
                <label>Email Body</label>
                <textarea
                  className="jd-email-body"
                  value={rescheduleMessage.body}
                  onChange={(event) => setRescheduleMessage(prev => ({ ...prev, body: event.target.value }))}
                  placeholder="Generate email after selecting date and time"
                  disabled={Boolean(rescheduleSuccess)}
                />
              </div>
              <div className="form-group">
                <label>Text Body</label>
                <textarea
                  className="jd-sms-body"
                  value={rescheduleMessage.text_body}
                  onChange={(event) => setRescheduleMessage(prev => ({ ...prev, text_body: event.target.value }))}
                  placeholder="Generate after selecting date and time"
                  disabled={Boolean(rescheduleSuccess)}
                />
              </div>

              {rescheduleError && <div className="jd-schedule-alert jd-schedule-alert-error">{rescheduleError}</div>}
              {rescheduleSuccess && (
                <div className="jd-schedule-alert jd-schedule-alert-success">
                  Interview updated successfully.
                </div>
              )}

              <div className="jd-modal-actions">
                <button type="button" className="btn btn-secondary" onClick={closeReschedule} disabled={rescheduleBusy || generatingRescheduleEmail}>
                  {rescheduleSuccess ? 'Close' : 'Cancel'}
                </button>
                {rescheduleSuccess ? (
                  <button type="button" className="btn btn-primary" onClick={viewUpdatedInterview}>
                    <i className="fas fa-eye"></i> View Changes
                  </button>
                ) : (
                  <>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={generateRescheduleEmail}
                      disabled={generatingRescheduleEmail || rescheduleBusy || !rescheduleForm.interview_date || !rescheduleForm.interview_time}
                    >
                      {generatingRescheduleEmail ? <><i className="fas fa-spinner fa-spin"></i> Generating...</> : <><i className="fas fa-magic"></i> Generate</>}
                    </button>
                    <button
                      type="button"
                      className="btn btn-success"
                      onClick={saveReschedule}
                      disabled={
                        rescheduleBusy ||
                        generatingRescheduleEmail ||
                        !rescheduleForm.interview_date ||
                        !rescheduleForm.interview_time ||
                        !rescheduleForm.interviewer.trim() ||
                        !rescheduleMessage.subject.trim() ||
                        !rescheduleMessage.body.trim() ||
                        (rescheduleForm.interview_mode === 'Online' && !rescheduleForm.meeting_link.trim())
                      }
                    >
                      {rescheduleBusy ? <><i className="fas fa-spinner fa-spin"></i> Saving...</> : <><i className="fas fa-calendar-check"></i> Save Changes</>}
                    </button>
                  </>
                )}
              </div>
            </div>
          </div>
        )}
      </div>
    </Layout>
  );
}

export default HiringPipeline;
