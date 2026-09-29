import React, { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import Layout from '../components/Layout.jsx';
import { toast } from '../components/EnterpriseFeedback.jsx';
import { apiGet, apiPost } from '../api.js';
import {
  assessmentBadgeClass,
  formatAssessmentDate,
  formatAssessmentStatus,
  isAssessmentScoreVisible,
} from '../utils/assessmentDisplay.js';

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

  useEffect(() => {
    loadInterviews();
    loadAssessments();
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
      <div className="interviews-container">
        <div className="interviews-header">
          <div>
            <h1><i className="fas fa-route"></i> Hiring Pipeline</h1>
            <p>Manage assessments, candidate progress, interviews, follow-ups, and outcomes.</p>
          </div>
          <button type="button" className="btn btn-secondary" onClick={refreshPipeline} disabled={loading || loadingAssessments}>
            <i className="fas fa-rotate"></i> Refresh
          </button>
        </div>

        <div className="interviews-toolbar hp-main-tabs" role="tablist" aria-label="Hiring pipeline sections">
          {[
            ['assessments', 'Assessments'],
            ['interviews', 'Interviews'],
          ].map(([value, label]) => (
            <button
              key={value}
              type="button"
              className={activeTab === value ? 'active' : ''}
              onClick={() => setActiveTab(value)}
            >
              {label}
            </button>
          ))}
        </div>

        {activeTab === 'assessments' && (
          <>
            <div className="interviews-toolbar">
              <div className="interviews-tabs" role="tablist" aria-label="Assessment filters">
                {[
                  ['all', 'All'],
                  ['NOT_CREATED', 'Not created'],
                  ['DRAFT', 'Draft'],
                  ['SENT', 'Sent'],
                  ['IN_PROGRESS', 'In progress'],
                  ['PASSED', 'Passed'],
                  ['FAILED', 'Failed'],
                ].map(([value, label]) => (
                  <button
                    key={value}
                    type="button"
                    className={assessmentFilter === value ? 'active' : ''}
                    onClick={() => setAssessmentFilter(value)}
                  >
                    {label}
                  </button>
                ))}
              </div>
              <div className="interviews-filter-controls">
                <div className="interviews-search">
                  <i className="fas fa-search"></i>
                  <input
                    value={assessmentSearch}
                    onChange={(event) => setAssessmentSearch(event.target.value)}
                    placeholder="Search assessments"
                  />
                </div>
              </div>
            </div>

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
        <div className="interviews-toolbar">
          <div className="interviews-tabs" role="tablist" aria-label="Interview filters">
            {[
              ['upcoming', 'Upcoming'],
              ['needs_followup', 'Needs follow-up'],
              ['past', 'Past'],
              ['cancelled', 'Cancelled'],
              ['all', 'All'],
            ].map(([value, label]) => (
              <button
                key={value}
                type="button"
                className={viewFilter === value ? 'active' : ''}
                onClick={() => setViewFilter(value)}
              >
                {label}
              </button>
            ))}
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
              <option value="client interview pending">Client pending</option>
              <option value="rejected after interview">Rejected after interview</option>
            </select>
          </div>
        </div>

        {loading ? (
          <div className="interviews-empty">Loading interviews...</div>
        ) : grouped.length === 0 ? (
          <div className="interviews-empty">No interviews match this view.</div>
        ) : (
          <div className="interviews-days">
            {grouped.map(([date, rows]) => (
              <section key={date} className="interviews-day">
                <div className="interviews-day-header">
                  <h2>{date}</h2>
                  <span>{rows.length} interview{rows.length === 1 ? '' : 's'}</span>
                </div>
                <div className="interviews-list">
                  {rows.map(item => {
                    const stamp = formatDateTime(item.interview_start);
                    const emailStatus = deliveryStatus(item, 'email_status');
                    const textStatus = deliveryStatus(item, 'text_status');
                    const past = isPastInterview(item);
                    const cancelled = isCancelled(item);
                    const lockedOutcome = isOutcomeLocked(item);
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
                          </div>
                        </div>
                        <div className="interview-card-actions">
                          {!past && !cancelled && (
                            <button type="button" className="btn btn-secondary" onClick={() => openReschedule(item)}>
                              <i className="fas fa-calendar-plus"></i> Reschedule
                            </button>
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
                          )}
                        </div>
                      </article>
                    );
                  })}
                </div>
              </section>
            ))}
          </div>
        )}
          </>
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
