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

<<<<<<< HEAD
// Automated reschedule / no-show recovery case shown on an interview card.
function recoveryLabel(recovery) {
  if (!recovery) return null;
  const noShow = recovery.recovery_type === 'NO_SHOW';
  switch (recovery.status) {
    case 'PENDING':
    case 'PROCESSING':
      return { text: noShow ? 'No-show follow-up in progress' : 'Reschedule requested', tone: 'warn' };
    case 'RETRY_SCHEDULED':
      return { text: noShow ? 'No-show follow-up in progress' : 'Searching for available slots', tone: 'warn' };
    case 'AWAITING_RESPONSE':
      return { text: 'No-show follow-up: awaiting candidate', tone: 'warn' };
    case 'SLOT_PROPOSED':
      return { text: 'Awaiting candidate slot choice', tone: 'warn' };
    case 'RESCHEDULED':
      return { text: 'New slot confirmed', tone: 'good' };
    case 'RECOVERED':
      return { text: 'Recovery completed', tone: 'good' };
    case 'ESCALATED':
      return { text: 'Escalation required', tone: 'bad' };
    case 'CLOSED':
      return recovery.outcome === 'candidate_declined' ? { text: 'Candidate withdrew', tone: 'bad' } : null;
    default:
      return null;
  }
}

const RECOVERY_TONE_CLASS = { good: 'interview-status-good', bad: 'interview-status-bad', warn: 'interview-status-warn' };

function isRecoveryOpen(recovery) {
  return Boolean(recovery) && !['RESCHEDULED', 'RECOVERED', 'CLOSED'].includes(recovery.status);
=======
// Colour tone for a status pill: good / bad / warn / info / muted.
function toneOf(value) {
  const cls = statusClass(value);
  if (cls === 'interview-status-good') return 'good';
  if (/scheduled$/i.test(String(value || '').trim())) return 'good';
  if (cls === 'interview-status-bad') return 'bad';
  return 'muted';
}

const ASSESSMENT_TONE = {
  NOT_CREATED: 'muted', DRAFT: 'info', SENT: 'warn', IN_PROGRESS: 'warn', COMPLETED: 'info', PASSED: 'good', FAILED: 'bad',
};
const ASSESSMENT_FILTERS = [
  ['all', 'All'], ['NOT_CREATED', 'Not created'], ['DRAFT', 'Draft'], ['SENT', 'Sent'],
  ['IN_PROGRESS', 'In progress'], ['PASSED', 'Passed'], ['FAILED', 'Failed'],
];
const INTERVIEW_VIEWS = [
  ['upcoming', 'Upcoming'], ['needs_followup', 'Needs follow-up'], ['past', 'Past'], ['cancelled', 'Cancelled'], ['all', 'All'],
];

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
>>>>>>> acb8439f807499548dbc8d4144272bae1bb3f669
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
  const [escalations, setEscalations] = useState([]);
  const [recoveryCase, setRecoveryCase] = useState(null);
  const [recoveryBusy, setRecoveryBusy] = useState(false);
  const [logRequestActive, setLogRequestActive] = useState(null);
  const [logRequestReason, setLogRequestReason] = useState('');
  const [attendanceBusyId, setAttendanceBusyId] = useState(null);
  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const timeOptions = useMemo(() => buildTimeOptions(blockedSlots), [blockedSlots]);

  const loadAssessments = async () => {
    setLoadingAssessments(true);
    try {
      const data = await apiGet('/api/assessment/pipeline?limit=500');
      setAssessmentRows(data.pipeline || []);
    } catch (err) {
      toast({ type: 'error', message: err.message || 'Could not load assessment pipeline.' });
    } finally {
      setLoadingAssessments(false);
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

  const loadEscalations = async () => {
    try {
      const data = await apiGet('/api/interview-recovery/cases?status=ESCALATED');
      setEscalations(data.cases || []);
    } catch {
      setEscalations([]);
    }
  };

  useEffect(() => {
    loadInterviews();
    loadAssessments();
    loadEscalations();
  }, []);

  const refreshRecovery = async () => {
    await Promise.all([loadInterviews(), loadEscalations()]);
  };

  const openRecoveryCase = async (caseId) => {
    setRecoveryBusy(true);
    try {
      const data = await apiGet(`/api/interview-recovery/cases/${caseId}`);
      setRecoveryCase(data.case || null);
    } catch (err) {
      toast({ type: 'error', message: err.message || 'Could not load recovery history.' });
    } finally {
      setRecoveryBusy(false);
    }
  };

  const recoveryAction = async (caseId, action) => {
    setRecoveryBusy(true);
    try {
      const { ok, data } = await apiPost(`/api/interview-recovery/cases/${caseId}/${action}`, {});
      if (!ok || !data.success) throw new Error(data.error || 'Recovery action failed.');
      setRecoveryCase(data.case || null);
      toast({ type: 'success', message: action === 'retry' ? 'Automated recovery restarted.' : 'Recovery case closed.' });
      await refreshRecovery();
    } catch (err) {
      toast({ type: 'error', message: err.message || 'Recovery action failed.' });
    } finally {
      setRecoveryBusy(false);
    }
  };

  const markAttendance = async (interview, attendance) => {
    setAttendanceBusyId(interview.id);
    try {
      const { ok, data } = await apiPost(`/api/interviews/${interview.id}/attendance`, { attendance });
      if (!ok || !data.success) throw new Error(data.error || 'Could not record attendance.');
      toast({
        type: 'success',
        message: attendance === 'no_show' ? 'No-show recorded. The candidate is being contacted automatically.' : 'Attendance recorded.',
      });
      await refreshRecovery();
    } catch (err) {
      toast({ type: 'error', message: err.message || 'Could not record attendance.' });
    } finally {
      setAttendanceBusyId(null);
    }
  };

  const submitLoggedRequest = async () => {
    if (!logRequestActive) return;
    setRecoveryBusy(true);
    try {
      const { ok, data } = await apiPost(`/api/interviews/${logRequestActive.id}/recovery/reschedule-request`, {
        reason: logRequestReason.trim(),
      });
      if (!ok || !data.success) throw new Error(data.error || 'Could not start automated rescheduling.');
      setLogRequestActive(null);
      setLogRequestReason('');
      toast({ type: 'success', message: 'Automated rescheduling started. The candidate will receive available times.' });
      await refreshRecovery();
    } catch (err) {
      toast({ type: 'error', message: err.message || 'Could not start automated rescheduling.' });
    } finally {
      setRecoveryBusy(false);
    }
  };

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
    const counts = { NOT_CREATED: 0, DRAFT: 0, SENT: 0, IN_PROGRESS: 0, COMPLETED: 0, PASSED: 0, FAILED: 0 };
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

  const setInterviewOutcome = async (interview, outcome) => {
    setOutcomeBusyId(interview.id);
    try {
      let response = await apiPost(`/api/interviews/${interview.id}/outcome`, { outcome });
      if (!response.ok && response.status === 404) {
        response = await apiPost('/api/interviews/outcome', { interview_id: interview.id, outcome });
      }
      const { ok, status, data } = response;
      if (!ok || !data.success) {
        const detail = data.error || `Request failed with status ${status}`;
        throw new Error(`Could not update interview outcome. ${detail}`);
      }
      const updated = data.interview || {
        ...interview,
        status: outcome === 'selected' ? 'Client Interview Pending' : 'Rejected After Interview',
      };
      setInterviews(prev => prev.map(item => (item.id === interview.id ? updated : item)));
      toast({
        type: 'success',
        message: outcome === 'selected' ? 'Candidate moved to client interview pending.' : 'Candidate marked rejected after interview.',
      });
    } catch (err) {
      toast({ type: 'error', message: err.message || 'Could not update interview outcome.' });
    } finally {
      setOutcomeBusyId(null);
    }
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

<<<<<<< HEAD
            {loadingAssessments ? (
              <div className="interviews-empty">Loading assessment pipeline...</div>
            ) : filteredAssessments.length === 0 ? (
              <div className="interviews-empty">No assessment candidates match this view.</div>
            ) : (
              <div className="interviews-days">
                <section className="interviews-day">
                  <div className="interviews-day-header">
                    <h2>Assessment Queue</h2>
                    <span>{filteredAssessments.length} candidate{filteredAssessments.length === 1 ? '' : 's'}</span>
                  </div>
                  <div className="interviews-list">
                    {filteredAssessments.map(row => {
                      const showScore = isAssessmentScoreVisible(row.assessment_status);
                      const generatedKey = `${row.candidate_id}-${row.jd_id}`;
                      const activeInterview = hasActiveInterview(row);
                      return (
                        <article key={generatedKey} className="interview-card">
                          <div className="interview-card-time">
                            <span className={`badge ${assessmentBadgeClass(row.assessment_status)}`}>
                              {formatAssessmentStatus(row.assessment_status)}
                            </span>
                          </div>
                          <div className="interview-card-main">
                            <div className="interview-card-title-row">
                              <h3>{row.candidate_name || row.candidate_email}</h3>
                            </div>
                            <p>{row.jd_title}</p>
                            <div className="interview-detail-row">
                              {row.candidate_email && <span><i className="fas fa-envelope"></i> {row.candidate_email}</span>}
                              {row.candidate_phone && <span><i className="fas fa-phone"></i> {row.candidate_phone}</span>}
                              {row.match_score != null && <span><i className="fas fa-gauge-high"></i> Match {row.match_score}%</span>}
                              {row.sent_at && <span><i className="fas fa-paper-plane"></i> Sent {formatAssessmentDate(row.sent_at)}</span>}
                              {row.started_at && <span><i className="fas fa-play"></i> Started {formatAssessmentDate(row.started_at)}</span>}
                              {row.completed_at && <span><i className="fas fa-check-circle"></i> Completed {formatAssessmentDate(row.completed_at)}</span>}
                            </div>
                            <div className="interview-status-row">
                              <span className={statusClass(row.assessment_status)}>{formatAssessmentStatus(row.assessment_status)}</span>
                              <span className={statusClass(row.link_status)}>{row.link_status || 'Not Sent'}</span>
                              {showScore && row.assessment_percentage != null && <span className={statusClass(row.assessment_result)}>{row.assessment_percentage}%</span>}
                              {row.assessment_result && <span className={statusClass(row.assessment_result)}>{row.assessment_result}</span>}
                              {activeInterview && <span className={statusClass(row.interview_status)}>Interview: {prettyStatus(row.interview_status)}</span>}
                            </div>
                          </div>
                          <div className="interview-card-actions assessment-card-actions">
                            <Link to={`/talent/${row.candidate_id}`} className="btn btn-primary">
                              <i className="fas fa-eye"></i> Candidate
                            </Link>
                            {row.assessment_status === 'NOT_CREATED' && (
                              <button
                                type="button"
                                className="btn btn-primary"
                                disabled={generatingAssessmentId === generatedKey}
                                onClick={() => generateAssessment(row)}
                              >
                                <i className={`fas ${generatingAssessmentId === generatedKey ? 'fa-spinner fa-spin' : 'fa-magic'}`}></i>
                                {generatingAssessmentId === generatedKey ? 'Generating...' : 'Generate Assessment'}
                              </button>
                            )}
                            {row.assessment_id && ['DRAFT', 'COMPLETED', 'PASSED', 'FAILED'].includes(row.assessment_status) && (
                              <button type="button" className="btn btn-secondary" onClick={() => reviewAssessment(row)}>
                                <i className="fas fa-clipboard-check"></i> Review Assessment
                              </button>
                            )}
                            {row.eligible_for_interview && !activeInterview && (
                              <button type="button" className="btn btn-success" onClick={() => openSchedule(row)}>
                                <i className="fas fa-calendar-check"></i> Schedule Interview
                              </button>
                            )}
                          </div>
                        </article>
                      );
                    })}
                  </div>
                </section>
              </div>
            )}
          </>
        )}

        {activeTab === 'interviews' && (
          <>
        {escalations.length > 0 && (
          <section className="recovery-escalations" aria-label="Interview recovery needing attention">
            <h2><i className="fas fa-triangle-exclamation"></i> Needs your attention ({escalations.length})</h2>
            <p>Automated rescheduling could not finish for these interviews. Everything else is being handled automatically.</p>
            <ul>
              {escalations.map(entry => {
                const interview = interviews.find(item => item.id === entry.interview_id);
                return (
                  <li key={entry.id}>
                    <div>
                      <strong>{interview?.candidate_name || `Interview #${entry.interview_id}`}</strong>
                      <span>{entry.recovery_type === 'NO_SHOW' ? 'No-show' : 'Reschedule request'} - {entry.escalation_reason}</span>
                      {entry.recommended_action && <em>Next step: {entry.recommended_action}</em>}
                    </div>
                    <div className="recovery-escalation-actions">
                      <button type="button" className="btn btn-secondary" onClick={() => openRecoveryCase(entry.id)} disabled={recoveryBusy}>
                        <i className="fas fa-clock-rotate-left"></i> History
                      </button>
                      <button type="button" className="btn btn-primary" onClick={() => recoveryAction(entry.id, 'retry')} disabled={recoveryBusy}>
                        <i className="fas fa-rotate"></i> Retry
                      </button>
                    </div>
                  </li>
                );
              })}
            </ul>
          </section>
        )}
        <div className="interviews-toolbar">
          <div className="interviews-tabs" role="tablist" aria-label="Interview filters">
=======
        <section className="hp-panel">
          <nav className="hp-tabs" role="tablist" aria-label="Hiring pipeline sections">
>>>>>>> acb8439f807499548dbc8d4144272bae1bb3f669
            {[
              ['assessments', 'Assessments', 'fa-clipboard-check', assessmentRows.length],
              ['interviews', 'Interviews', 'fa-calendar-check', interviews.length],
            ].map(([value, label, icon, count]) => (
              <button key={value} type="button" role="tab" aria-selected={activeTab === value}
                className={`hp-tab${activeTab === value ? ' active' : ''}`} onClick={() => setActiveTab(value)}>
                <i className={`fas ${icon}`} aria-hidden="true"></i> {label}<span>{count}</span>
              </button>
            ))}
<<<<<<< HEAD
          </div>
          <div className="interviews-filter-controls">
            <div className="interviews-search">
              <i className="fas fa-search"></i>
              <input
                value={searchTerm}
                onChange={(event) => setSearchTerm(event.target.value)}
                placeholder="Search interviews"
              />
            </div>
            <select value={statusFilter} onChange={(event) => setStatusFilter(event.target.value)}>
              <option value="all">All statuses</option>
              <option value="scheduled">Scheduled</option>
              <option value="rescheduled">Rescheduled</option>
              <option value="cancelled">Cancelled</option>
              <option value="no show">No show</option>
              <option value="client interview pending">Client pending</option>
              <option value="rejected after interview">Rejected after interview</option>
            </select>
          </div>
        </div>
=======
          </nav>
>>>>>>> acb8439f807499548dbc8d4144272bae1bb3f669

          {activeTab === 'assessments' && (
            <>
              <div className="hp-toolbar">
                <div className="hp-chips" role="group" aria-label="Assessment filters">
                  {ASSESSMENT_FILTERS.map(([value, label]) => (
                    <button key={value} type="button" aria-pressed={assessmentFilter === value}
                      className={`hp-chip${assessmentFilter === value ? ' active' : ''}`} onClick={() => setAssessmentFilter(value)}>
                      {label}<span>{value === 'all' ? assessmentRows.length : assessmentCounts[value] || 0}</span>
                    </button>
                  ))}
                </div>
<<<<<<< HEAD
                <div className="interviews-list">
                  {rows.map(item => {
                    const stamp = formatDateTime(item.interview_start);
                    const emailStatus = deliveryStatus(item, 'email_status');
                    const textStatus = deliveryStatus(item, 'text_status');
                    const past = isPastInterview(item);
                    const cancelled = isCancelled(item);
                    const lockedOutcome = isOutcomeLocked(item);
                    const recovery = recoveryLabel(item.recovery);
                    const recoveryOpen = isRecoveryOpen(item.recovery);
                    const noShow = normalizeStatus(item.status) === 'no show';
                    const canMarkAttendance = past && !cancelled && !lockedOutcome && !noShow && item.attendance_status !== 'attended';
                    return (
                      <article
                        key={item.id}
                        id={`interview-${item.id}`}
                        className={`interview-card ${cancelled ? 'interview-card-cancelled' : ''} ${highlightedInterviewId === item.id ? 'interview-card-highlight' : ''}`}
                      >
                        <div className="interview-card-time">{stamp.time}</div>
                        <div className="interview-card-main">
                          <div className="interview-card-title-row">
                            <h3>{item.candidate_name || item.candidate_email}</h3>
                          </div>
                          <p>{item.job_role}</p>
                          <div className="interview-detail-row">
                            {item.interviewer && <span><i className="fas fa-user-tie"></i> {item.interviewer}</span>}
                            {item.interview_mode && <span><i className="fas fa-video"></i> {item.interview_mode}</span>}
                            {item.meeting_link && <a href={item.meeting_link} target="_blank" rel="noreferrer"><i className="fas fa-link"></i> Meeting link</a>}
                            {item.notes && <span><i className="fas fa-note-sticky"></i> {item.notes}</span>}
                          </div>
                          <div className="interview-status-row">
                            <span className={statusClass(item.status)}>{prettyStatus(item.status || 'scheduled')}</span>
                            <span className={statusClass(emailStatus)}>Email: {prettyStatus(emailStatus || 'sent')}</span>
                            <span className={statusClass(textStatus)}>Text: {prettyStatus(textStatus || 'sent')}</span>
                            <span className={statusClass(item.followup_status)}>Follow-up: {prettyStatus(item.followup_status || 'not sent')}</span>
                            {item.cancellation_status === 'sent' && <span className={statusClass('sent')}>Cancellation: sent</span>}
                            {recovery && (
                              <button type="button" className={`recovery-chip ${RECOVERY_TONE_CLASS[recovery.tone]}`}
                                onClick={() => openRecoveryCase(item.recovery.id)} title="View automated recovery history">
                                <i className="fas fa-robot"></i> {recovery.text}
                              </button>
                            )}
=======
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
                <div className="hp-row hp-row-head" aria-hidden="true">
                  <span>Candidate</span><span>Contact</span><span>Scores</span><span>Status</span><span className="hp-head-actions">Actions</span>
                </div>
                <ul className="hp-list" aria-label="Assessment queue">
                  {filteredAssessments.map(row => {
                    const showScore = isAssessmentScoreVisible(row.assessment_status);
                    const generatedKey = `${row.candidate_id}-${row.jd_id}`;
                    const activeInterview = hasActiveInterview(row);
                    const status = row.assessment_status || 'NOT_CREATED';
                    return (
                      <li key={generatedKey} className="hp-row">
                        <div className="hp-person">
                          <span className="hp-avatar" aria-hidden="true">{initials(row.candidate_name || row.candidate_email || '?')}</span>
                          <div>
                            <Link to={`/talent/${row.candidate_id}`} className="hp-name">{row.candidate_name || row.candidate_email}</Link>
                            <span className="hp-sub">{row.jd_title || 'No job'}</span>
>>>>>>> acb8439f807499548dbc8d4144272bae1bb3f669
                          </div>
                        </div>
                        <div className="hp-meta">
                          {row.candidate_email && <span><i className="fas fa-envelope" aria-hidden="true"></i>{row.candidate_email}</span>}
                          {realValue(row.candidate_phone) && <span><i className="fas fa-phone" aria-hidden="true"></i>{realValue(row.candidate_phone)}</span>}
                          {row.completed_at ? <span><i className="fas fa-flag-checkered" aria-hidden="true"></i>Completed {formatAssessmentDate(row.completed_at)}</span>
                            : row.started_at ? <span><i className="fas fa-play" aria-hidden="true"></i>Started {formatAssessmentDate(row.started_at)}</span>
                              : row.sent_at ? <span><i className="fas fa-paper-plane" aria-hidden="true"></i>Sent {formatAssessmentDate(row.sent_at)}</span> : null}
                        </div>
                        <div className="hp-score">
                          {row.match_score != null && <span className="hp-match" title="Resume match score">{pct(row.match_score)}<small>match</small></span>}
                          {showScore && row.assessment_percentage != null && <span className="hp-match hp-match-test" title="Assessment score">{pct(row.assessment_percentage)}<small>test</small></span>}
                        </div>
                        <div className="hp-pills">
                          <span className={`hp-pill ${ASSESSMENT_TONE[status] || 'muted'}`}>{formatAssessmentStatus(status)}</span>
                          {activeInterview
                            ? <span className={`hp-pill ${toneOf(row.interview_status)}`}>{interviewLabel(row.interview_status)}</span>
                            : status !== 'NOT_CREATED' && status !== 'DRAFT' && <span className={`hp-pill ${toneOf(row.link_status)}`}>Link {String(row.link_status || 'not sent').toLowerCase()}</span>}
                        </div>
                        <div className="hp-actions">
                          {status === 'NOT_CREATED' && (
                            <button type="button" className="hp-btn hp-btn-primary" disabled={generatingAssessmentId === generatedKey} onClick={() => generateAssessment(row)}>
                              <i className={`fas ${generatingAssessmentId === generatedKey ? 'fa-spinner fa-spin' : 'fa-wand-magic-sparkles'}`} aria-hidden="true"></i>
                              {generatingAssessmentId === generatedKey ? 'Generating…' : 'Generate assessment'}
                            </button>
                          )}
<<<<<<< HEAD
                          {!past && !cancelled && !recoveryOpen && (
                            <button type="button" className="btn btn-secondary" onClick={() => { setLogRequestActive(item); setLogRequestReason(''); }}
                              title="The candidate asked to move this interview: offer them new times automatically">
                              <i className="fas fa-wand-magic-sparkles"></i> Candidate asked to reschedule
                            </button>
                          )}
                          {canMarkAttendance && (
                            <>
                              <button type="button" className="btn btn-secondary" onClick={() => markAttendance(item, 'attended')} disabled={attendanceBusyId === item.id}>
                                <i className="fas fa-user-check"></i> Attended
                              </button>
                              <button type="button" className="btn btn-warning" onClick={() => markAttendance(item, 'no_show')} disabled={attendanceBusyId === item.id}>
                                {attendanceBusyId === item.id ? <><i className="fas fa-spinner fa-spin"></i> Saving...</> : <><i className="fas fa-user-slash"></i> No-show</>}
                              </button>
                            </>
                          )}
                          <button type="button" className="btn btn-primary" onClick={() => openFollowup(item)} disabled={cancelled}>
                            <i className="fas fa-reply"></i> Follow-up
                          </button>
                          {past && !cancelled && !lockedOutcome ? (
                            <>
                              <button type="button" className="btn btn-success" onClick={() => setInterviewOutcome(item, 'selected')} disabled={outcomeBusyId === item.id}>
                                {outcomeBusyId === item.id ? (
                                  <><i className="fas fa-spinner fa-spin"></i> Updating...</>
                                ) : (
                                  <><i className="fas fa-check"></i> Selected</>
                                )}
                              </button>
                              <button type="button" className="btn btn-danger" onClick={() => setInterviewOutcome(item, 'rejected')} disabled={outcomeBusyId === item.id}>
                                {outcomeBusyId === item.id ? (
                                  <><i className="fas fa-spinner fa-spin"></i> Updating...</>
                                ) : (
                                  <><i className="fas fa-xmark"></i> Rejected</>
                                )}
                              </button>
                            </>
                          ) : (
                            !past && !cancelled && (
                              <button type="button" className="btn btn-danger" onClick={() => openCancel(item)}>
                                <i className="fas fa-ban"></i> Cancel
                              </button>
                            )
=======
                          {row.assessment_id && ['DRAFT', 'COMPLETED', 'PASSED', 'FAILED'].includes(status) && (
                            <button type="button" className={`hp-btn ${status === 'DRAFT' ? 'hp-btn-primary' : 'hp-btn-ghost'}`} onClick={() => reviewAssessment(row)}>
                              <i className="fas fa-clipboard-check" aria-hidden="true"></i> {status === 'DRAFT' ? 'Review & send' : 'Review'}
                            </button>
>>>>>>> acb8439f807499548dbc8d4144272bae1bb3f669
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
                                <span className={`hp-pill ${toneOf(item.status || 'scheduled')}`}>{prettyStatus(item.status || 'Scheduled')}</span>
                                <span className="hp-delivery" title={`Email ${prettyStatus(emailStatus || 'sent')} · Text ${prettyStatus(textStatus || 'sent')} · Follow-up ${prettyStatus(item.followup_status || 'not sent')}`}>
                                  <i className={`fas fa-envelope ${toneOf(emailStatus || 'sent')}`} aria-label={`Email ${prettyStatus(emailStatus || 'sent')}`}></i>
                                  <i className={`fas fa-comment-sms ${toneOf(textStatus || 'sent')}`} aria-label={`Text ${prettyStatus(textStatus || 'sent')}`}></i>
                                  <i className={`fas fa-reply ${toneOf(item.followup_status)}`} aria-label={`Follow-up ${prettyStatus(item.followup_status || 'not sent')}`}></i>
                                </span>
                              </div>
                              <div className="hp-actions">
                                {past && !cancelled && !lockedOutcome && (
                                  <>
                                    <button type="button" className="hp-btn hp-btn-success" onClick={() => setInterviewOutcome(item, 'selected')} disabled={outcomeBusyId === item.id}>
                                      <i className={`fas ${outcomeBusyId === item.id ? 'fa-spinner fa-spin' : 'fa-check'}`} aria-hidden="true"></i> Selected
                                    </button>
                                    <button type="button" className="hp-btn hp-btn-danger" onClick={() => setInterviewOutcome(item, 'rejected')} disabled={outcomeBusyId === item.id}>
                                      <i className={`fas ${outcomeBusyId === item.id ? 'fa-spinner fa-spin' : 'fa-xmark'}`} aria-hidden="true"></i> Rejected
                                    </button>
                                  </>
                                )}
                                {!past && !cancelled && (
                                  <button type="button" className="hp-btn hp-btn-ghost" onClick={() => openReschedule(item)}>
                                    <i className="fas fa-calendar-plus" aria-hidden="true"></i> Reschedule
                                  </button>
                                )}
                                <button type="button" className="hp-btn hp-btn-ghost" onClick={() => openFollowup(item)} disabled={cancelled}>
                                  <i className="fas fa-reply" aria-hidden="true"></i> Follow-up
                                </button>
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

        {logRequestActive && (
          <div className="jd-modal-backdrop" role="presentation">
            <div className="jd-schedule-modal" role="dialog" aria-modal="true" aria-labelledby="log-request-title">
              <div className="jd-modal-header">
                <div>
                  <h2 id="log-request-title"><i className="fas fa-wand-magic-sparkles"></i> Automated Reschedule</h2>
                  <p>{logRequestActive.candidate_name || logRequestActive.candidate_email} - {logRequestActive.job_role}</p>
                </div>
                <button type="button" className="jd-modal-close" onClick={() => setLogRequestActive(null)} disabled={recoveryBusy} aria-label="Close">
                  <i className="fas fa-times"></i>
                </button>
              </div>
              <p className="recovery-modal-note">
                HR Assist will find times when you are free, email the candidate a link to choose one, and update this
                interview once they confirm. You will only be contacted if it cannot be resolved.
              </p>
              <div className="form-group">
                <label htmlFor="log-request-reason">What did the candidate say? (optional)</label>
                <textarea id="log-request-reason" rows={3} value={logRequestReason} onChange={(event) => setLogRequestReason(event.target.value)} />
              </div>
              <div className="jd-modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setLogRequestActive(null)} disabled={recoveryBusy}>Cancel</button>
                <button type="button" className="btn btn-primary" onClick={submitLoggedRequest} disabled={recoveryBusy}>
                  {recoveryBusy ? <><i className="fas fa-spinner fa-spin"></i> Starting...</> : <><i className="fas fa-paper-plane"></i> Offer new times</>}
                </button>
              </div>
            </div>
          </div>
        )}

        {recoveryCase && (
          <div className="jd-modal-backdrop" role="presentation">
            <div className="jd-schedule-modal" role="dialog" aria-modal="true" aria-labelledby="recovery-case-title">
              <div className="jd-modal-header">
                <div>
                  <h2 id="recovery-case-title"><i className="fas fa-robot"></i> Automated Recovery</h2>
                  <p>
                    {recoveryCase.recovery_type === 'NO_SHOW' ? 'No-show follow-up' : 'Reschedule request'} - {prettyStatus(recoveryCase.status).toLowerCase()}
                    {' '}- attempt {recoveryCase.attempt_count} of {recoveryCase.max_attempts}
                  </p>
                </div>
                <button type="button" className="jd-modal-close" onClick={() => setRecoveryCase(null)} aria-label="Close recovery history">
                  <i className="fas fa-times"></i>
                </button>
              </div>
              {recoveryCase.escalation_reason && (
                <div className="recovery-modal-alert">
                  <strong>{recoveryCase.escalation_reason}</strong>
                  {recoveryCase.recommended_action && <span>Next step: {recoveryCase.recommended_action}</span>}
                </div>
              )}
              {recoveryCase.confirmed_slot && <p className="recovery-modal-note">Confirmed: {recoveryCase.confirmed_slot.label}</p>}
              {recoveryCase.status === 'SLOT_PROPOSED' && (recoveryCase.proposed_slots || []).length > 0 && (
                <div className="recovery-modal-note">
                  Offered times:
                  <ul>{recoveryCase.proposed_slots.map(slot => <li key={slot.id}>{slot.label}</li>)}</ul>
                </div>
              )}
              <ol className="recovery-history">
                {(recoveryCase.history || []).map(entry => (
                  <li key={entry.id}>
                    <span className="recovery-history-time">{formatDateTime(entry.created_at).date} {formatDateTime(entry.created_at).time}</span>
                    <span className="recovery-history-action">{prettyStatus(entry.action)}</span>
                    {entry.outcome && <span className={statusClass(entry.outcome === 'delivered' || entry.outcome === 'booked' ? 'sent' : entry.outcome === 'delivery_failed' ? 'failed' : '')}>{prettyStatus(entry.outcome)}</span>}
                    {(entry.deliveries || []).filter(d => d.error).map((d, index) => (
                      <span key={index} className="recovery-history-error">{d.channel}: {d.error}</span>
                    ))}
                  </li>
                ))}
              </ol>
              <div className="jd-modal-actions">
                {!['RESCHEDULED', 'RECOVERED', 'CLOSED'].includes(recoveryCase.status) && (
                  <button type="button" className="btn btn-secondary" onClick={() => recoveryAction(recoveryCase.id, 'close')} disabled={recoveryBusy}>
                    <i className="fas fa-circle-xmark"></i> Close case
                  </button>
                )}
                {recoveryCase.status === 'ESCALATED' && (
                  <button type="button" className="btn btn-primary" onClick={() => recoveryAction(recoveryCase.id, 'retry')} disabled={recoveryBusy}>
                    <i className="fas fa-rotate"></i> Retry automation
                  </button>
                )}
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
