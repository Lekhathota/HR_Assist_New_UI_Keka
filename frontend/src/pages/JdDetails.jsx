import React, { useCallback, useState, useEffect, useMemo } from 'react';
import { Link, useParams, useNavigate, useSearchParams } from 'react-router-dom';
import Layout from '../components/Layout.jsx';
import { toast, useConfirm, SkeletonBlock } from '../components/EnterpriseFeedback.jsx';
import { apiDelete, apiGet, apiPost, apiPostForm, apiPut } from '../api.js';
import { resolveAssessmentRow } from '../utils/assessmentDisplay.js';
import { formatJdDate, parseJdSections } from '../utils/jdSections.js';
import JdHiringProcessEditor from '../components/JdHiringProcessEditor.jsx';
import '../styles/jd_details_extra.css';
import '../styles/jobs_module.css';
import jsPDF from 'jspdf';
import { saveAs } from 'file-saver';
import * as XLSX from 'xlsx';
import { currentReportId, issueReportId } from '../utils/reportId.js';
 
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

function buildInterviewTextBody(candidate, jd, interviewDate, interviewTime) {
  const candidateName = candidate?.name || 'Candidate';
  const firstName = candidateName.split(/\s+/)[0] || candidateName;
  const jobRole = jd?.title || 'the role';
  const timeLabel = interviewTime ? formatSlotLabel(interviewTime) : interviewTime;
  return [
    `Hi ${firstName}, congratulations!`,
    `You have been selected for an interview for ${jobRole}.`,
    `Date: ${interviewDate}. Time: ${timeLabel}.`,
    'Please reply to confirm your availability.',
    '- Recruitment Team',
  ].join(' ');
}

function jdStructuredData(jd) {
  const sd = jd && jd.structured_data;
  if (!sd) return {};
  if (typeof sd === 'string') {
    try { return JSON.parse(sd) || {}; } catch { return {}; }
  }
  return sd;
}

// Short overview used when the JD was uploaded before summaries were generated.
function synthesizeJdSummary(jd, sd) {
  const title = jd.title || 'This role';
  const experience = sd.experience_range || jd.experience || '';
  const skills = (sd.required_skills?.length ? sd.required_skills : jd.skills || []).filter(Boolean).slice(0, 5);
  const parts = [`${title} position`];
  if (experience) parts.push(`requiring ${experience} of experience`);
  if (skills.length) parts.push(`with a focus on ${skills.join(', ')}`);
  if (jd.location) parts.push(`based in ${jd.location}`);
  const text = parts.join(' ').trim();
  if (!text) return '';
  return text.charAt(0).toUpperCase() + text.slice(1) + '.';
}

// Paragraphs and bullet items of one JD section, exactly as written.
function JdSectionBody({ paragraphs, items }) {
  return (
    <>
      {paragraphs.map((text, i) => <p key={`p${i}`} className="jdd-paragraph">{text}</p>)}
      {items.length > 0 && (
        <ul className="jdd-bullets">
          {items.map((text, i) => <li key={`i${i}`}>{text}</li>)}
        </ul>
      )}
    </>
  );
}

function JdDetails() {
  const { jdId: routeJdId } = useParams();
  const [searchParams] = useSearchParams();
  const jdId = routeJdId || searchParams.get('id');
  const navigate = useNavigate();
  const confirm = useConfirm();
  const [jd, setJd]           = useState(null);
  const [selected, setSelected] = useState([]);
  const [rejected, setRejected] = useState([]);
  const [error, setError] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [showFullJd, setShowFullJd] = useState(false);
  const [showEditModal, setShowEditModal] = useState(false);
  const [editForm, setEditForm] = useState(null);
  const [savingEdit, setSavingEdit] = useState(false);
  const [editError, setEditError] = useState('');
  const [assessmentMap, setAssessmentMap] = useState({});
  const [generatingAssessment, setGeneratingAssessment] = useState(null);
  const [scheduleCandidate, setScheduleCandidate] = useState(null);
  const [interviewDate, setInterviewDate] = useState('');
  const [interviewTime, setInterviewTime] = useState('');
  const [blockedSlots, setBlockedSlots] = useState([]);
  const [loadingSlots, setLoadingSlots] = useState(false);
  const [scheduleError, setScheduleError] = useState('');
  const [generatingEmail, setGeneratingEmail] = useState(false);
  const [sendingEmail, setSendingEmail] = useState(false);
  const [emailPreview, setEmailPreview] = useState({
    from_email: '',
    to_email: '',
    subject: '',
    body: '',
  });
  const [textPreview, setTextPreview] = useState({ to: '', body: '' });
  const [interviewDetails, setInterviewDetails] = useState({
    interviewer: '',
    interview_mode: 'Online',
    meeting_link: '',
    notes: '',
  });
  const [assignedVendors, setAssignedVendors] = useState([]);
  const [fulfilment, setFulfilment] = useState(null);
  const [assignVendorsOpen, setAssignVendorsOpen] = useState(false);
  const [availableVendors, setAvailableVendors] = useState([]);
  const [vendorSearch, setVendorSearch] = useState('');
  const [vendorFilter, setVendorFilter] = useState('Active');
  const [vendorSelection, setVendorSelection] = useState([]);
  const [loadingVendors, setLoadingVendors] = useState(false);
  const [vendorLoadError, setVendorLoadError] = useState('');
  const [savingAssignments, setSavingAssignments] = useState(false);
  const [vendorEmailModal, setVendorEmailModal] = useState(null);
  const [vendorEmailBusy, setVendorEmailBusy] = useState(false);
  const [vendorManualAttachment, setVendorManualAttachment] = useState(null);
  const [vendorEmailQueue, setVendorEmailQueue] = useState([]);
  const [vendorHistoryModal, setVendorHistoryModal] = useState(null);
  const [vendorHistory, setVendorHistory] = useState([]);
  const [vendorCandidateHistory, setVendorCandidateHistory] = useState([]);
  const [vendorHistoryLoading, setVendorHistoryLoading] = useState(false);
  const [fulfilmentTimeline, setFulfilmentTimeline] = useState([]);
  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const timeOptions = useMemo(() => buildTimeOptions(blockedSlots), [blockedSlots]);

  // --- REPORT MODAL STATE ---
  const [showModal, setShowModal] = useState(false);
  const [selectedFormat, setSelectedFormat] = useState('pdf');
  const [recipientEmail, setRecipientEmail] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [showEmailInput, setShowEmailInput] = useState(false);

  const loadAssignedVendors = useCallback(() => {
    apiGet(`/api/jds/${jdId}/vendors`)
      .then(data => { setAssignedVendors(data.vendors || []); setFulfilment(data.fulfilment || null); })
      .catch(() => setAssignedVendors([]));
  }, [jdId]);

  const loadFulfilmentTimeline = useCallback(() => {
    apiGet(`/api/jds/${jdId}/fulfilment/timeline`)
      .then(data => setFulfilmentTimeline(data.events || []))
      .catch(() => setFulfilmentTimeline([]));
  }, [jdId]);
 
  useEffect(() => {
    setError('');
    setJd(null);
    setAssessmentMap({});
    apiGet(`/api/jds/${jdId}`).then(data => {
      setJd(data.jd || null);
      setSelected(data.selected || []);
      setRejected(data.rejected || []);
    }).catch((err) => {
      setError(err.message || 'Could not load job description details.');
    });
    loadAssignedVendors();
    loadFulfilmentTimeline();
  }, [jdId, loadAssignedVendors, loadFulfilmentTimeline]);

  const acceptVendorCandidate = async (candidate) => {
    try {
      const { ok, data } = await apiPost(`/api/jds/${jdId}/vendor-candidates/${candidate.id}/accept`, {});
      if (!ok) throw new Error(data.error || 'Could not accept vendor candidate.');
      setFulfilment(data.fulfilment || null);
      setVendorCandidateHistory(prev => prev.map(row => row.id === candidate.id ? { ...row, selection_status: 'accepted_vendor' } : row));
      loadFulfilmentTimeline();
      toast({ type: 'success', message: 'Vendor candidate accepted.' });
    } catch (err) {
      toast({ type: 'error', message: err.message || 'Could not accept vendor candidate.' });
    }
  };

  const overrideBenchCandidate = async (candidate, selectionStatus) => {
    try {
      const { ok, data } = await apiPost(`/api/jds/${jdId}/bench-candidates/${candidate.id}/selection`, { selection_status: selectionStatus });
      if (!ok) throw new Error(data.error || 'Could not update candidate selection.');
      setFulfilment(data.fulfilment || null);
      toast({ type: 'success', message: 'Bench selection updated.' });
      loadFulfilmentTimeline();
      apiGet(`/api/jds/${jdId}`).then(payload => {
        setJd(payload.jd || null);
        setSelected(payload.selected || []);
        setRejected(payload.rejected || []);
      }).catch(() => {});
    } catch (err) {
      toast({ type: 'error', message: err.message || 'Could not update candidate selection.' });
    }
  };

  const markBenchUnavailable = async (candidate) => {
    try {
      const { ok, data } = await apiPost(`/api/jds/${jdId}/bench-candidates/${candidate.id}/unavailable`, {});
      if (!ok) throw new Error(data.error || 'Could not mark candidate unavailable.');
      setFulfilment(data.fulfilment || null);
      toast({ type: 'success', message: 'Candidate marked unavailable.' });
      loadFulfilmentTimeline();
      apiGet(`/api/jds/${jdId}`).then(payload => {
        setJd(payload.jd || null);
        setSelected(payload.selected || []);
        setRejected(payload.rejected || []);
      }).catch(() => {});
    } catch (err) {
      toast({ type: 'error', message: err.message || 'Could not mark candidate unavailable.' });
    }
  };

  useEffect(() => {
    if (!assignVendorsOpen) return;
    setLoadingVendors(true);
    setVendorLoadError('');
    const params = new URLSearchParams({ status: vendorFilter, sort: 'company_name' });
    if (vendorSearch.trim()) params.set('search', vendorSearch.trim());
    apiGet(`/api/vendors?${params.toString()}`)
      .then(data => setAvailableVendors(data.vendors || []))
      .catch((err) => {
        setAvailableVendors([]);
        setVendorLoadError(err.message || 'Could not load vendors.');
        toast({ type: 'error', message: err.message || 'Could not load vendors.' });
      })
      .finally(() => setLoadingVendors(false));
  }, [assignVendorsOpen, vendorSearch, vendorFilter]);

  useEffect(() => {
    if (!selected.length) {
      setAssessmentMap({});
      return;
    }
    Promise.all(
      selected.map(candidate =>
        apiGet(`/api/assessment/lookup?jd_id=${encodeURIComponent(jdId)}&candidate_id=${encodeURIComponent(candidate.id)}`)
          .then(row => [candidate.id, row])
          .catch(() => [candidate.id, null]),
      ),
    ).then(rows => {
      const next = {};
      rows.forEach(([id, row]) => {
        if (row) next[id] = row;
      });
      setAssessmentMap(next);
    });
  }, [selected, jdId]);

  useEffect(() => {
    if (!scheduleCandidate || !interviewDate) {
      setBlockedSlots([]);
      return;
    }
    setLoadingSlots(true);
    setScheduleError('');
    apiGet(`/api/interviews/blocked-slots?date=${encodeURIComponent(interviewDate)}`)
      .then(data => setBlockedSlots(data.blocked_slots || []))
      .catch(() => {
        setBlockedSlots([]);
        setScheduleError('Could not load blocked interview times.');
      })
      .finally(() => setLoadingSlots(false));
  }, [scheduleCandidate, interviewDate]);

  useEffect(() => {
    if (!interviewTime) return;
    const option = timeOptions.find(item => item.value === interviewTime);
    if (option?.blocked) {
      setInterviewTime('');
    }
  }, [timeOptions, interviewTime]);
 
  const handleRemove = async () => {
    if (!jd) return;
    const approved = await confirm({
      title: 'Remove job description',
      message: `Remove "${jd.title}"? Related comparisons may be removed. This cannot be undone.`,
      confirmLabel: 'Remove JD',
      icon: 'fas fa-trash-alt',
      danger: true,
    });
    if (!approved) return;
    setDeleting(true);
    try {
      const { ok, data } = await apiPost(`/api/jds/${jdId}/delete`, { confirmed: true });
      if (ok && data.success) {
        toast({ type: 'success', message: 'Job description removed.' });
        navigate('/jobs');
      } else {
        toast({ type: 'error', message: data.error || 'Could not remove job description.' });
      }
    } catch {
      toast({ type: 'error', message: 'Remove failed. Please try again.' });
    } finally {
      setDeleting(false);
    }
  };

  const openEditModal = () => {
    if (!jd) return;
    setEditError('');
    setEditForm({
      title: jd.title || '',
      job_code: jd.job_code || '',
      department: jd.department || '',
      location: jd.location || '',
      experience_required: jd.experience || jd.experience_required || '',
      job_category: jd.job_category || '',
      required_candidate_count: jd.required_candidate_count ?? '',
      status: jd.status || 'Active',
      skills: (jd.skills || []).join(', '),
      responsibilities: (jd.responsibilities || []).join('\n'),
      raw_text: jd.raw_text || '',
    });
    setShowEditModal(true);
  };

  const saveEdit = async () => {
    if (!editForm) return;
    const requiredCount = Number(editForm.required_candidate_count);
    if (!editForm.title.trim()) {
      setEditError('Title cannot be empty.');
      return;
    }
    if (!Number.isInteger(requiredCount) || requiredCount <= 0) {
      setEditError('Enter a required candidate count greater than zero.');
      return;
    }
    setEditError('');
    setSavingEdit(true);
    try {
      const { ok, data } = await apiPut(`/api/jds/${jdId}`, {
        title: editForm.title.trim(),
        job_code: editForm.job_code.trim(),
        department: editForm.department.trim(),
        location: editForm.location.trim(),
        experience_required: editForm.experience_required.trim(),
        job_category: editForm.job_category.trim(),
        required_candidate_count: requiredCount,
        status: editForm.status,
        skills: editForm.skills.split(',').map(s => s.trim()).filter(Boolean),
        responsibilities: editForm.responsibilities.split('\n').map(s => s.trim()).filter(Boolean),
        raw_text: editForm.raw_text,
      });
      if (ok && data.success) {
        setJd(data.jd);
        setShowEditModal(false);
        toast({ type: 'success', message: 'Job description updated.' });
      } else {
        setEditError(data.error || 'Could not update job description.');
      }
    } catch {
      setEditError('Update failed. Please try again.');
    } finally {
      setSavingEdit(false);
    }
  };

  const handleGenerateAssessment = async (candidate) => {
    setGeneratingAssessment(candidate.id);
    try {
      const { ok, data } = await apiPost('/api/assessment/generate', {
        candidate_id: candidate.id,
        jd_id: Number(jdId),
      });
      if (!ok || !data.assessment?.id) {
        toast({ type: 'error', message: data.error || 'Could not generate assessment.' });
        return;
      }
      navigate(`/jobs/${jdId}/assessment/${data.assessment.id}`);
    } catch {
      toast({ type: 'error', message: 'Assessment generation failed.' });
    } finally {
      setGeneratingAssessment(null);
    }
  };

  const openAssessmentBuilder = (candidate) => {
    const assessment = resolveAssessmentRow(candidate, assessmentMap);
    if (assessment.assessmentId) {
      navigate(`/jobs/${jdId}/assessment/${assessment.assessmentId}`);
    }
  };

  const openScheduleModal = (candidate) => {
    const assessment = resolveAssessmentRow(candidate, assessmentMap);
    if (!assessment.eligibleForInterview) {
      toast({ type: 'error', message: 'Candidate must pass the assessment before scheduling.' });
      return;
    }
    setScheduleCandidate(candidate);
    setInterviewDate('');
    setInterviewTime('');
    setBlockedSlots([]);
    setScheduleError('');
    setEmailPreview({
      from_email: '',
      to_email: candidate.email || '',
      subject: '',
      body: '',
    });
    setTextPreview({
      to: candidate.phone || '',
      body: '',
    });
    setInterviewDetails({
      interviewer: '',
      interview_mode: 'Online',
      meeting_link: '',
      notes: '',
    });
    apiGet('/api/interviews/defaults')
      .then(data => setEmailPreview(prev => ({ ...prev, from_email: data.from_email || '' })))
      .catch(() => setEmailPreview(prev => ({ ...prev, from_email: 'Configured sender email' })));
  };

  const closeScheduleModal = () => {
    if (generatingEmail || sendingEmail) return;
    setScheduleCandidate(null);
    setScheduleError('');
  };

  const handleGenerateEmail = async () => {
    if (!scheduleCandidate || !interviewDate || !interviewTime) {
      setScheduleError('Choose an interview date and available time first.');
      return;
    }
    setGeneratingEmail(true);
    setScheduleError('');
    try {
      const { ok, data } = await apiPost('/api/interviews/generate-email', {
        candidate_id: scheduleCandidate.id,
        jd_id: jd.id,
        interview_date: interviewDate,
        interview_time: interviewTime,
      });
      if (!ok) {
        setScheduleError(data.error || 'Could not generate email.');
        return;
      }
      setEmailPreview({
        from_email: data.from_email || '',
        to_email: data.to_email || scheduleCandidate.email || '',
        subject: data.subject || '',
        body: data.body || '',
      });
      setTextPreview(prev => ({
        ...prev,
        body: buildInterviewTextBody(scheduleCandidate, jd, interviewDate, interviewTime),
      }));
    } catch {
      setScheduleError('Could not generate email.');
    } finally {
      setGeneratingEmail(false);
    }
  };

  const handleSendSchedule = async () => {
    if (!scheduleCandidate || !interviewDate || !interviewTime || !emailPreview.subject || !emailPreview.body) {
      setScheduleError('Generate and review the email before sending.');
      return;
    }
    if (!interviewDetails.interviewer.trim()) {
      setScheduleError('Interviewer is required.');
      return;
    }
    if (interviewDetails.interview_mode === 'Online' && !interviewDetails.meeting_link.trim()) {
      setScheduleError('Meeting link is required for online interviews.');
      return;
    }
    setSendingEmail(true);
    setScheduleError('');
    try {
      const { ok, data } = await apiPost('/api/interviews/schedule', {
        candidate_id: scheduleCandidate.id,
        jd_id: jd.id,
        interview_date: interviewDate,
        interview_time: interviewTime,
        interviewer: interviewDetails.interviewer,
        interview_mode: interviewDetails.interview_mode,
        meeting_link: interviewDetails.meeting_link,
        notes: interviewDetails.notes,
        text_body: textPreview.body,
        subject: emailPreview.subject,
        body: emailPreview.body,
      });
      if (!ok || !data.success) {
        toast({ type: 'error', message: data.error || 'Could not schedule interview.' });
        return;
      }
      setSelected(prev => prev.map(candidate => (
        candidate.id === scheduleCandidate.id
          ? { ...candidate, hiring_stage: 'Interview Scheduled' }
          : candidate
      )));
      setScheduleCandidate(null);
      toast({ type: 'success', message: 'Interview scheduled successfully.' });
    } catch {
      toast({ type: 'error', message: 'Interview email sending failed. Please try again.' });
    } finally {
      setSendingEmail(false);
    }
  };

  // ============================================================
  // PROFESSIONAL INDIVIDUAL JOB REPORT
  // ============================================================

  const buildJobDetailsReport = () => {
    const now = new Date();
    const dateStr = now.toLocaleDateString('en-US', { 
      year: 'numeric', 
      month: 'long', 
      day: 'numeric' 
    });
    const timeStr = now.toLocaleTimeString('en-US', { 
      hour: '2-digit', 
      minute: '2-digit' 
    });
    
    let report = '';
    const selectionRate = jd?.total_resumes > 0 ? Math.round(((jd.selected_count || 0) / jd.total_resumes) * 100) : 0;
    
    // HEADER
    report += '='.repeat(60) + '\n';
    report += '     INDIVIDUAL JOB REPORT\n';
    report += '='.repeat(60) + '\n\n';
    report += '  Generated on  : ' + dateStr + ' at ' + timeStr + '\n';
    report += '  Report ID     : ' + currentReportId() + '\n';
    report += '  Job ID        : JD-' + (jd?.id || 'N/A') + '\n\n';
    
    // JOB DETAILS
    report += '-'.repeat(60) + '\n';
    report += 'JOB DETAILS\n';
    report += '-'.repeat(60) + '\n';
    report += '  Job Title           : ' + (jd?.title || 'N/A') + '\n';
    report += '  Department          : ' + (jd?.department || 'N/A') + '\n';
    report += '  Experience Required : ' + (jd?.experience || 'N/A') + '\n';
    report += '  Location            : ' + (jd?.location || 'N/A') + '\n';
    report += '  Status              : ' + (jd?.status || 'N/A') + '\n\n';
    
    // REQUIRED SKILLS
    report += '-'.repeat(60) + '\n';
    report += 'REQUIRED SKILLS\n';
    report += '-'.repeat(60) + '\n';
    if (jd?.skills && jd.skills.length > 0) {
      jd.skills.forEach(function(skill) {
        report += '  * ' + skill + '\n';
      });
    } else {
      report += '  No skills listed\n';
    }
    report += '\n';
    
    // CANDIDATE STATISTICS
    report += '-'.repeat(60) + '\n';
    report += 'CANDIDATE STATISTICS\n';
    report += '-'.repeat(60) + '\n';
    report += '  Total Applied       : ' + (jd?.total_resumes || 0) + ' candidates\n';
    report += '  Selected            : ' + (jd?.selected_count || 0) + ' candidates\n';
    report += '  Rejected            : ' + (jd?.rejected_count || 0) + ' candidates\n';
    report += '  Selection Rate      : ' + selectionRate + '%\n';
    report += '  Average Match Score : ' + (jd?.avg_match_score || 0) + '%\n\n';
    
    // SELECTED CANDIDATES
    report += '-'.repeat(60) + '\n';
    report += 'SELECTED CANDIDATES\n';
    report += '-'.repeat(60) + '\n';
    if (selected.length > 0) {
      report += '  #  Name                      Match    Stage\n';
      report += '  ' + '-'.repeat(55) + '\n';
      selected.slice(0, 20).forEach(function(c, index) {
        const num = String(index + 1).padStart(2);
        const name = (c.name || 'N/A').substring(0, 22).padEnd(22);
        const match = String(c.match_score || 0).padStart(6) + '%';
        const stage = (c.hiring_stage || 'N/A').substring(0, 18).padEnd(18);
        report += '  ' + num + '  ' + name + '  ' + match + '  ' + stage + '\n';
      });
      if (selected.length > 20) {
        report += '  ... and ' + (selected.length - 20) + ' more selected candidates\n';
      }
    } else {
      report += '  No selected candidates\n';
    }
    report += '\n';
    
    // REJECTED CANDIDATES
    report += '-'.repeat(60) + '\n';
    report += 'REJECTED CANDIDATES\n';
    report += '-'.repeat(60) + '\n';
    if (rejected.length > 0) {
      report += '  #  Name                      Match    Reason\n';
      report += '  ' + '-'.repeat(55) + '\n';
      rejected.slice(0, 20).forEach(function(c, index) {
        const num = String(index + 1).padStart(2);
        const name = (c.name || 'N/A').substring(0, 22).padEnd(22);
        const match = String(c.match_score || 0).padStart(6) + '%';
        const reason = (c.rejection_reason || 'N/A').substring(0, 18).padEnd(18);
        report += '  ' + num + '  ' + name + '  ' + match + '  ' + reason + '\n';
      });
      if (rejected.length > 20) {
        report += '  ... and ' + (rejected.length - 20) + ' more rejected candidates\n';
      }
    } else {
      report += '  No rejected candidates\n';
    }
    report += '\n';
    
    // HIRING RECOMMENDATION
    report += '-'.repeat(60) + '\n';
    report += 'HIRING RECOMMENDATION\n';
    report += '-'.repeat(60) + '\n';
    
    if (selectionRate > 30) {
      report += '  Strong selection rate. The job description is attracting\n';
      report += '  well-matched candidates. Continue with current strategy.\n';
    } else if (selectionRate > 15) {
      report += '  Moderate selection rate. Consider refining the job\n';
      report += '  description or expanding sourcing channels.\n';
    } else if (jd?.total_resumes > 0) {
      report += '  Low selection rate. Review the job requirements and\n';
      report += '  consider adjusting the screening criteria.\n';
    } else {
      report += '  No candidates have applied yet. Start promoting the job.\n';
    }
    report += '\n';
    
    // AI SUMMARY
    report += '-'.repeat(60) + '\n';
    report += 'AI SUMMARY\n';
    report += '-'.repeat(60) + '\n';
    report += '  This job has ' + (jd?.total_resumes || 0) + ' candidates in the pipeline.\n';
    report += '  ' + (jd?.selected_count || 0) + ' candidates selected (' + selectionRate + '% selection rate).\n';
    report += '  ' + (jd?.rejected_count || 0) + ' candidates rejected.\n';
    report += '  Average match score: ' + (jd?.avg_match_score || 0) + '%.\n';
    
    if (selected.length > 0) {
      report += '  Top candidate: ' + selected[0]?.name + ' with ' + (selected[0]?.match_score || 0) + '% match.\n';
    }
    
    if (jd?.skills && jd.skills.length > 0) {
      report += '  Required skills: ' + jd.skills.slice(0, 5).join(', ') + (jd.skills.length > 5 ? '...' : '') + '\n';
    }
    report += '\n';
    
    // FOOTER
    report += '='.repeat(60) + '\n';
    report += '  Report generated by Recruitment Analytics System\n';
    report += '  ' + dateStr + ' at ' + timeStr + '\n';
    report += '  Confidential - For internal use only\n';
    report += '  (c) ' + new Date().getFullYear() + ' All Rights Reserved\n';
    report += '='.repeat(60);
    
    return report;
  };

  const generateJobDetailsCSV = () => {
    const now = new Date();
    const dateStr = now.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
    const selectionRate = jd?.total_resumes > 0 ? Math.round(((jd.selected_count || 0) / jd.total_resumes) * 100) : 0;
    
    let csvContent = '';
    
    csvContent += '"INDIVIDUAL JOB REPORT"\n';
    csvContent += '"Generated: ' + dateStr + '"\n';
    csvContent += '"Report ID: ' + currentReportId() + '"\n\n';
    
    csvContent += '"JOB DETAILS"\n';
    csvContent += '"Field","Value"\n';
    csvContent += '"Job Title","' + (jd?.title || 'N/A') + '"\n';
    csvContent += '"Department","' + (jd?.department || 'N/A') + '"\n';
    csvContent += '"Experience Required","' + (jd?.experience || 'N/A') + '"\n';
    csvContent += '"Location","' + (jd?.location || 'N/A') + '"\n';
    csvContent += '"Status","' + (jd?.status || 'N/A') + '"\n\n';
    
    csvContent += '"REQUIRED SKILLS"\n';
    csvContent += '"Skill"\n';
    if (jd?.skills && jd.skills.length > 0) {
      jd.skills.forEach(function(skill) {
        csvContent += '"' + skill + '"\n';
      });
    } else {
      csvContent += '"No skills listed"\n';
    }
    csvContent += '\n';
    
    csvContent += '"CANDIDATE STATISTICS"\n';
    csvContent += '"Metric","Value"\n';
    csvContent += '"Total Applied",' + (jd?.total_resumes || 0) + '\n';
    csvContent += '"Selected",' + (jd?.selected_count || 0) + '\n';
    csvContent += '"Rejected",' + (jd?.rejected_count || 0) + '\n';
    csvContent += '"Selection Rate",' + selectionRate + '%\n';
    csvContent += '"Average Match Score",' + (jd?.avg_match_score || 0) + '%\n\n';
    
    csvContent += '"SELECTED CANDIDATES"\n';
    csvContent += '"#","Name","Email","Match Score","Stage"\n';
    if (selected.length > 0) {
      selected.forEach(function(c, index) {
        csvContent += '"' + (index + 1) + '","' + (c.name || 'N/A') + '","' + (c.email || 'N/A') + '","' + (c.match_score || 0) + '%","' + (c.hiring_stage || 'N/A') + '"\n';
      });
    } else {
      csvContent += '"No selected candidates"\n';
    }
    csvContent += '\n';
    
    csvContent += '"REJECTED CANDIDATES"\n';
    csvContent += '"#","Name","Email","Match Score","Reason"\n';
    if (rejected.length > 0) {
      rejected.forEach(function(c, index) {
        csvContent += '"' + (index + 1) + '","' + (c.name || 'N/A') + '","' + (c.email || 'N/A') + '","' + (c.match_score || 0) + '%","' + (c.rejection_reason || 'N/A') + '"\n';
      });
    } else {
      csvContent += '"No rejected candidates"\n';
    }
    csvContent += '\n';
    
    csvContent += '"HIRING RECOMMENDATION"\n';
    if (selectionRate > 30) {
      csvContent += '"Strong selection rate. Continue with current strategy."\n';
    } else if (selectionRate > 15) {
      csvContent += '"Moderate selection rate. Consider refining the job description."\n';
    } else if (jd?.total_resumes > 0) {
      csvContent += '"Low selection rate. Review job requirements and screening criteria."\n';
    } else {
      csvContent += '"No candidates applied yet. Start promoting the job."\n';
    }
    
    return csvContent;
  };

  const generateJobDetailsExcel = () => {
    const now = new Date();
    const dateStr = now.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
    const selectionRate = jd?.total_resumes > 0 ? Math.round(((jd.selected_count || 0) / jd.total_resumes) * 100) : 0;
    
    const wb = XLSX.utils.book_new();
    
    // Sheet 1: Job Details
    const jobData = [
      ['INDIVIDUAL JOB REPORT'],
      ['Generated: ' + dateStr],
      ['Report ID: ' + currentReportId()],
      [],
      ['JOB DETAILS'],
      ['Field', 'Value'],
      ['Job Title', jd?.title || 'N/A'],
      ['Department', jd?.department || 'N/A'],
      ['Experience Required', jd?.experience || 'N/A'],
      ['Location', jd?.location || 'N/A'],
      ['Status', jd?.status || 'N/A'],
      [],
      ['REQUIRED SKILLS'],
      ['Skill'],
    ];
    if (jd?.skills && jd.skills.length > 0) {
      jd.skills.forEach(function(skill) {
        jobData.push([skill]);
      });
    } else {
      jobData.push(['No skills listed']);
    }
    jobData.push([]);
    jobData.push(['CANDIDATE STATISTICS']);
    jobData.push(['Metric', 'Value']);
    jobData.push(['Total Applied', jd?.total_resumes || 0]);
    jobData.push(['Selected', jd?.selected_count || 0]);
    jobData.push(['Rejected', jd?.rejected_count || 0]);
    jobData.push(['Selection Rate', selectionRate + '%']);
    jobData.push(['Average Match Score', (jd?.avg_match_score || 0) + '%']);
    
    const ws1 = XLSX.utils.aoa_to_sheet(jobData);
    XLSX.utils.book_append_sheet(wb, ws1, 'Job Details');
    
    // Sheet 2: Selected Candidates
    const selectedData = [
      ['SELECTED CANDIDATES'],
      [],
      ['#', 'Name', 'Email', 'Match Score', 'Stage']
    ];
    if (selected.length > 0) {
      selected.forEach(function(c, index) {
        selectedData.push([index + 1, c.name || 'N/A', c.email || 'N/A', (c.match_score || 0) + '%', c.hiring_stage || 'N/A']);
      });
    } else {
      selectedData.push(['No selected candidates']);
    }
    const ws2 = XLSX.utils.aoa_to_sheet(selectedData);
    XLSX.utils.book_append_sheet(wb, ws2, 'Selected');
    
    // Sheet 3: Rejected Candidates
    const rejectedData = [
      ['REJECTED CANDIDATES'],
      [],
      ['#', 'Name', 'Email', 'Match Score', 'Reason']
    ];
    if (rejected.length > 0) {
      rejected.forEach(function(c, index) {
        rejectedData.push([index + 1, c.name || 'N/A', c.email || 'N/A', (c.match_score || 0) + '%', c.rejection_reason || 'N/A']);
      });
    } else {
      rejectedData.push(['No rejected candidates']);
    }
    const ws3 = XLSX.utils.aoa_to_sheet(rejectedData);
    XLSX.utils.book_append_sheet(wb, ws3, 'Rejected');
    
    // Sheet 4: Recommendation
    const recData = [
      ['HIRING RECOMMENDATION'],
      [],
      ['Recommendation']
    ];
    if (selectionRate > 30) {
      recData.push(['Strong selection rate. Continue with current strategy.']);
    } else if (selectionRate > 15) {
      recData.push(['Moderate selection rate. Consider refining the job description.']);
    } else if (jd?.total_resumes > 0) {
      recData.push(['Low selection rate. Review job requirements and screening criteria.']);
    } else {
      recData.push(['No candidates applied yet. Start promoting the job.']);
    }
    const ws4 = XLSX.utils.aoa_to_sheet(recData);
    XLSX.utils.book_append_sheet(wb, ws4, 'Recommendation');
    
    return wb;
  };

const downloadPDF = (reportText) => {
  try {
    const doc = new jsPDF('p', 'mm', 'a4');
    const margin = 20;
    const maxWidth = doc.internal.pageSize.getWidth() - (margin * 2);
    let y = 20;
    const lines = reportText.split('\n');
    
    lines.forEach(function(line) {
      if (y > 270) {
        doc.addPage();
        y = 20;
      }
      
      if (line.indexOf('INDIVIDUAL JOB REPORT') !== -1) {
        doc.setFontSize(18);
        doc.setFont('helvetica', 'bold');
        doc.setTextColor(26, 54, 93);
      } else if (line.indexOf('===') !== -1 || line.indexOf('---') !== -1) {
        doc.setFontSize(10);
        doc.setFont('helvetica', 'normal');
        doc.setTextColor(113, 128, 150);
      } else if (line.indexOf('*') !== -1) {
        doc.setFontSize(10);
        doc.setFont('helvetica', 'normal');
        doc.setTextColor(45, 55, 72);
      } else if (line.indexOf(':') !== -1 && line.indexOf('http') === -1) {
        doc.setFontSize(10);
        doc.setFont('helvetica', 'bold');
        doc.setTextColor(45, 55, 72);
      } else {
        doc.setFontSize(10);
        doc.setFont('helvetica', 'normal');
        doc.setTextColor(74, 85, 104);
      }
      
      const x = line.indexOf('*') !== -1 ? margin + 5 : margin;
      const wrappedLines = doc.splitTextToSize(line, maxWidth - (x - margin));
      wrappedLines.forEach(function(wrappedLine) {
        if (y > 270) {
          doc.addPage();
          y = 20;
        }
        doc.text(wrappedLine, x, y);
        y += 6;
      });
      y += 2;
    });
    
    const filename = 'Job_Report_' + (jd?.title || 'job').replace(/\s/g, '_') + '_' + new Date().toISOString().split('T')[0] + '.pdf';
    doc.save(filename);
    alert('✅ Job Report PDF downloaded successfully!');
    
  } catch (error) {
    console.error('PDF Error:', error);
    alert('❌ Failed to generate PDF. Please try again.');
  }
};
  const downloadDOCX = async (reportText) => {
    try {
      const escaped = reportText
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;');
      const html = `
        <html xmlns:o="urn:schemas-microsoft-com:office:office" xmlns:w="urn:schemas-microsoft-com:office:word">
          <head><meta charset="utf-8"><title>Job Report</title></head>
          <body><pre style="font-family: Arial, sans-serif; white-space: pre-wrap;">${escaped}</pre></body>
        </html>
      `;
      const blob = new Blob([html], { type: 'application/msword;charset=utf-8' });
      const filename = 'Job_Report_' + (jd?.title || 'job').replace(/\s/g, '_') + '_' + new Date().toISOString().split('T')[0] + '.doc';
      saveAs(blob, filename);
      alert('Job Report document downloaded successfully!');
    } catch (error) {
      console.error('DOCX Error:', error);
      alert('Failed to generate document. Please try again.');
    }
  };

  const downloadCSV = function() {
    try {
      const csvContent = generateJobDetailsCSV();
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'Job_Report_' + (jd?.title || 'job').replace(/\s/g, '_') + '_' + new Date().toISOString().split('T')[0] + '.csv';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      alert('Job Report CSV downloaded successfully!');
    } catch (error) {
      console.error('CSV Error:', error);
      alert('Failed to generate CSV. Please try again.');
    }
  };

  const downloadExcel = function() {
    try {
      const wb = generateJobDetailsExcel();
      const wbout = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });
      const blob = new Blob([wbout], { type: 'application/octet-stream' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'Job_Report_' + (jd?.title || 'job').replace(/\s/g, '_') + '_' + new Date().toISOString().split('T')[0] + '.xlsx';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      alert('Job Report Excel downloaded successfully!');
    } catch (error) {
      console.error('Excel Error:', error);
      alert('Failed to generate Excel. Please try again.');
    }
  };

  const sendEmailReport = async function(email, reportText) {
    try {
      const doc = new jsPDF('p', 'mm', 'a4');
      const margin = 20;
      const maxWidth = doc.internal.pageSize.getWidth() - (margin * 2);
      let y = 20;
      const lines = reportText.split('\n');
      
      lines.forEach(function(line) {
        if (y > 270) { doc.addPage(); y = 20; }
        
        if (line.indexOf('INDIVIDUAL JOB REPORT') !== -1) {
          doc.setFontSize(18);
          doc.setFont('helvetica', 'bold');
          doc.setTextColor(26, 54, 93);
        } else if (line.indexOf('===') !== -1 || line.indexOf('---') !== -1) {
          doc.setFontSize(10);
          doc.setFont('helvetica', 'normal');
          doc.setTextColor(113, 128, 150);
        } else if (line.indexOf('*') !== -1) {
          doc.setFontSize(10);
          doc.setFont('helvetica', 'normal');
          doc.setTextColor(45, 55, 72);
        } else if (line.indexOf(':') !== -1 && line.indexOf('http') === -1) {
          doc.setFontSize(10);
          doc.setFont('helvetica', 'bold');
          doc.setTextColor(45, 55, 72);
        } else {
          doc.setFontSize(10);
          doc.setFont('helvetica', 'normal');
          doc.setTextColor(74, 85, 104);
        }
        
        const x = line.indexOf('*') !== -1 ? margin + 5 : margin;
        const wrappedLines = doc.splitTextToSize(line, maxWidth - (x - margin));
        wrappedLines.forEach(function(wrappedLine) {
          if (y > 270) { doc.addPage(); y = 20; }
          doc.text(wrappedLine, x, y);
          y += 6;
        });
        y += 2;
      });
      
      const pdfBlob = doc.output('blob');
      const reader = new FileReader();
      
      return new Promise(function(resolve, reject) {
        reader.onload = async function() {
          try {
            const base64Data = reader.result.split(',')[1];
            
            const response = await apiPost('/api/report/email', {
              recipient: email,
              subject: 'Job Report - ' + (jd?.title || 'Job') + ' - ' + new Date().toISOString().split('T')[0],
              message: 'Please find attached the Job Report for ' + (jd?.title || 'the job') + ' generated on ' + new Date().toLocaleString() + '.',
              attachment: {
                filename: 'Job_Report_' + (jd?.title || 'job').replace(/\s/g, '_') + '_' + new Date().toISOString().split('T')[0] + '.pdf',
                content: base64Data,
                mimeType: 'application/pdf'
              }
            });
            
            if (response.ok) {
              alert('Job Report sent successfully to ' + email + '!');
              resolve();
            } else {
              throw new Error(response.data?.error || 'Failed to send email');
            }
          } catch (error) {
            console.error('Email send error:', error);
            alert('Failed to send email. Please check your email settings.');
            reject(error);
          }
        };
        reader.onerror = reject;
        reader.readAsDataURL(pdfBlob);
      });
    } catch (error) {
      console.error('Email Error:', error);
      alert('Failed to prepare email. Please try again.');
    }
  };

  const handleGenerateReport = async function() {
    if (selectedFormat === 'email' && !recipientEmail) {
      alert('Please enter a recipient email address');
      return;
    }

    setIsGenerating(true);
    
    try {
      await issueReportId('job_details', selectedFormat, { jd_id: jd?.id });
      const reportText = buildJobDetailsReport();
      
      if (selectedFormat === 'pdf') {
        downloadPDF(reportText);
      } else if (selectedFormat === 'docx') {
        await downloadDOCX(reportText);
      } else if (selectedFormat === 'csv') {
        downloadCSV();
      } else if (selectedFormat === 'excel') {
        downloadExcel();
      } else if (selectedFormat === 'email') {
        await sendEmailReport(recipientEmail, reportText);
      } else {
        alert('Unsupported format');
      }
      
      setShowModal(false);
      setSelectedFormat('pdf');
      setRecipientEmail('');
      setShowEmailInput(false);
      
    } catch (error) {
      console.error('Report generation error:', error);
      alert('Failed to generate report. Please try again.');
    } finally {
      setIsGenerating(false);
    }
  };

  // ============================================================
  // MODAL - POSITIONED AT BOTTOM
  // ============================================================
  const ReportModal = function() {
    if (!showModal) return null;
    
    const formatIcons = {
      pdf: '📄',
      docx: '📝',
      csv: '📊',
      excel: '📈',
      email: '✉️'
    };
    
    const formatColors = {
      pdf: { border: '#dc2626', bg: '#fef2f2', text: '#dc2626' },
      docx: { border: '#2563eb', bg: '#eff6ff', text: '#2563eb' },
      csv: { border: '#16a34a', bg: '#f0fdf4', text: '#16a34a' },
      excel: { border: '#7c3aed', bg: '#f5f3ff', text: '#7c3aed' },
      email: { border: '#f59e0b', bg: '#fffbeb', text: '#f59e0b' }
    };
    
    return React.createElement(
      'div',
      {
        style: {
          position: 'fixed',
          top: 0,
          left: 0,
          width: '100%',
          height: '100%',
          background: 'rgba(0, 0, 0, 0.3)',
          backdropFilter: 'blur(2px)',
          zIndex: 99998,
          display: 'flex',
          alignItems: 'flex-end',
          justifyContent: 'center',
          paddingBottom: '80px'
        },
        onClick: function() { setShowModal(false); }
      },
      React.createElement(
        'div',
        {
          style: {
            background: '#ffffff',
            borderRadius: '16px 16px 0 0',
            maxWidth: '480px',
            width: '95%',
            maxHeight: '80vh',
            overflowY: 'auto',
            boxShadow: '0 -10px 40px rgba(0,0,0,0.15)',
            border: '1px solid #e2e8f0',
            animation: 'slideUp 0.3s ease'
          },
          onClick: function(e) { e.stopPropagation(); }
        },
        // Header
        React.createElement('div', {
          style: {
            padding: '16px 20px 12px 20px',
            borderBottom: '2px solid #e2e8f0',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            background: '#f8fafc',
            borderRadius: '16px 16px 0 0'
          }
        },
          React.createElement('h2', {
            style: {
              fontSize: '18px',
              fontWeight: '700',
              color: '#0f172a',
              margin: 0,
              display: 'flex',
              alignItems: 'center',
              gap: '8px'
            }
          },
            React.createElement('span', null, '📋'),
            ' Generate Job Report'
          ),
          React.createElement('button', {
            onClick: function() { setShowModal(false); },
            style: {
              background: '#e2e8f0',
              border: 'none',
              fontSize: '20px',
              color: '#1e293b',
              cursor: 'pointer',
              padding: '2px 12px',
              borderRadius: '8px',
              lineHeight: '1.6',
              fontWeight: '700'
            }
          }, '✕')
        ),
        // Body
        React.createElement('div', { style: { padding: '20px' } },
          React.createElement('p', {
            style: {
              color: '#1e293b',
              fontSize: '14px',
              fontWeight: '500',
              margin: '0 0 16px 0'
            }
          }, 'Choose your report format'),
          // Format Grid
          React.createElement('div', {
            style: {
              display: 'grid',
              gridTemplateColumns: 'repeat(5, 1fr)',
              gap: '8px',
              marginBottom: '16px'
            }
          },
            ['pdf', 'docx', 'csv', 'excel', 'email'].map(function(format) {
              var isActive = selectedFormat === format;
              var colors = formatColors[format];
              return React.createElement('div', {
                key: format,
                onClick: function() {
                  setSelectedFormat(format);
                  setShowEmailInput(format === 'email');
                },
                style: {
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  gap: '4px',
                  padding: '10px 6px',
                  border: isActive ? '3px solid ' + colors.border : '3px solid #cbd5e1',
                  borderRadius: '12px',
                  cursor: 'pointer',
                  background: isActive ? colors.bg : '#ffffff',
                  boxShadow: isActive ? '0 0 0 4px ' + colors.bg : 'none'
                }
              },
                React.createElement('span', { style: { fontSize: '22px' } }, formatIcons[format]),
                React.createElement('span', {
                  style: {
                    fontSize: '10px',
                    fontWeight: '700',
                    color: isActive ? colors.text : '#475569',
                    textTransform: 'uppercase'
                  }
                }, format === 'excel' ? 'Excel' : format)
              );
            })
          ),
          // Email Input
          showEmailInput ? React.createElement('div', {
            style: {
              marginBottom: '14px',
              padding: '14px',
              background: '#f8fafc',
              borderRadius: '10px',
              border: '2px solid #e2e8f0'
            }
          },
            React.createElement('label', {
              style: {
                display: 'block',
                fontSize: '13px',
                fontWeight: '700',
                color: '#0f172a',
                marginBottom: '6px'
              }
            }, '📧 Recipient Email'),
            React.createElement('input', {
              type: 'email',
              placeholder: 'Enter recipient email',
              value: recipientEmail,
              onChange: function(e) { setRecipientEmail(e.target.value); },
              style: {
                width: '100%',
                padding: '10px 14px',
                border: '2px solid #cbd5e1',
                borderRadius: '8px',
                fontSize: '14px',
                boxSizing: 'border-box',
                background: '#ffffff',
                color: '#0f172a'
              }
            }),
            React.createElement('small', {
              style: {
                display: 'block',
                fontSize: '11px',
                color: '#64748b',
                marginTop: '4px'
              }
            }, 'Report will be sent as a PDF attachment')
          ) : null,
          // Preview
          React.createElement('div', {
            style: {
              padding: '10px 14px',
              background: '#f1f5f9',
              borderRadius: '8px',
              fontSize: '12px',
              color: '#0f172a',
              display: 'flex',
              alignItems: 'center',
              gap: '8px',
              border: '2px solid #e2e8f0'
            }
          },
            React.createElement('span', null, 'ℹ️'),
            React.createElement('span', null, 'Report includes: Job Details, Skills, Candidates, Recommendations')
          )
        ),
        // Footer
        React.createElement('div', {
          style: {
            padding: '14px 20px 20px 20px',
            borderTop: '2px solid #e2e8f0',
            display: 'flex',
            justifyContent: 'flex-end',
            gap: '10px',
            background: '#f8fafc',
            borderRadius: '0 0 16px 16px'
          }
        },
          React.createElement('button', {
            onClick: function() {
              setShowModal(false);
              setSelectedFormat('pdf');
              setRecipientEmail('');
              setShowEmailInput(false);
            },
            style: {
              padding: '10px 24px',
              borderRadius: '10px',
              fontSize: '14px',
              fontWeight: '700',
              border: '2px solid #cbd5e1',
              cursor: 'pointer',
              background: '#ffffff',
              color: '#1e293b'
            }
          }, 'Cancel'),
          React.createElement('button', {
            onClick: handleGenerateReport,
            disabled: isGenerating,
            style: {
              padding: '10px 28px',
              borderRadius: '10px',
              fontSize: '14px',
              fontWeight: '700',
              border: 'none',
              cursor: isGenerating ? 'not-allowed' : 'pointer',
              background: isGenerating ? '#94a3b8' : '#f97316',
              color: 'white',
              boxShadow: isGenerating ? 'none' : '0 4px 14px rgba(249, 115, 22,0.4)',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              opacity: isGenerating ? 0.6 : 1
            }
          }, isGenerating ? '⏳ Generating...' : '📥 Generate')
        )
      )
    );
  };

  // ============================================================
  // RENDER
  // ============================================================

  const openAssignVendors = () => {
    setVendorSelection(assignedVendors.map(vendor => Number(vendor.id)));
    setVendorSearch('');
    setVendorFilter('Active');
    setVendorLoadError('');
    setAssignVendorsOpen(true);
  };

  const toggleVendorSelection = (vendorId) => {
    const id = Number(vendorId);
    setVendorSelection(prev => (
      prev.includes(id) ? prev.filter(item => item !== id) : [...prev, id]
    ));
  };

  const saveVendorAssignments = async () => {
    setSavingAssignments(true);
    try {
      const previouslyAssigned = new Set(assignedVendors.map(vendor => Number(vendor.id)));
      const selectedIds = vendorSelection.map(Number);
      const keptExistingIds = selectedIds.filter(id => previouslyAssigned.has(id));
      const newVendorIds = selectedIds.filter(id => !previouslyAssigned.has(id));
      const removedVendorIds = assignedVendors.map(vendor => Number(vendor.id)).filter(id => !selectedIds.includes(id));

      if (removedVendorIds.length) {
        const { ok, data } = await apiPost(`/api/jds/${jdId}/vendors`, { vendor_ids: keptExistingIds });
        if (!ok || !data.success) {
          toast({ type: 'error', message: data.error || 'Could not update vendor assignments.' });
          return;
        }
        setAssignedVendors(data.vendors || []);
      }
      setAssignVendorsOpen(false);
      toast({ type: 'success', message: newVendorIds.length ? 'Send email to complete new vendor assignment.' : 'Vendor assignments updated.' });
      const newVendors = newVendorIds
        .map(id => availableVendors.find(vendor => Number(vendor.id) === Number(id)))
        .filter(Boolean);
      if (newVendors.length) {
        setVendorEmailQueue(newVendors.slice(1));
        openVendorEmail(newVendors[0]);
      }
    } catch {
      toast({ type: 'error', message: 'Could not assign vendors.' });
    } finally {
      setSavingAssignments(false);
    }
  };

  const removeAssignedVendor = async (vendor) => {
    const approved = await confirm({
      title: 'Remove vendor',
      message: `Remove "${vendor.vendor_name || vendor.company_name || vendor.email}" from this JD?`,
      confirmLabel: 'Remove Vendor',
      icon: 'fas fa-link-slash',
      danger: true,
    });
    if (!approved) return;
    try {
      const { ok, data } = await apiDelete(`/api/jds/${jdId}/vendors/${vendor.id}`);
      if (!ok || !data.success) throw new Error(data.error || 'Could not remove vendor.');
      setAssignedVendors(prev => prev.filter(item => Number(item.id) !== Number(vendor.id)));
      toast({ type: 'success', message: 'Vendor removed from JD.' });
    } catch (err) {
      toast({ type: 'error', message: err.message || 'Could not remove vendor.' });
    }
  };

  const openVendorEmail = async (vendor) => {
    setVendorManualAttachment(null);
    setVendorEmailModal({
      vendor,
      from_email: '',
      to_email: vendor.email || '',
      subject: '',
      body: '',
      attachments: [],
      error: '',
    });
    setVendorEmailBusy(true);
    try {
      const { ok, data } = await apiPost(`/api/jds/${jdId}/vendors/${vendor.id}/generate-email`, {});
      if (!ok) throw new Error(data.error || 'Could not generate vendor email.');
      setVendorEmailModal({ vendor, ...data, error: '' });
    } catch (err) {
      setVendorEmailModal(prev => ({ ...prev, error: err.message || 'Could not generate vendor email.' }));
    } finally {
      setVendorEmailBusy(false);
    }
  };

  const updateVendorEmail = (key, value) => {
    setVendorEmailModal(prev => ({ ...prev, [key]: value }));
  };

  const sendVendorEmail = async () => {
    if (!vendorEmailModal?.vendor || !vendorEmailModal.subject || !vendorEmailModal.body) {
      updateVendorEmail('error', 'Email subject and body are required.');
      return;
    }
    setVendorEmailBusy(true);
    try {
      const formData = new FormData();
      formData.append('to_email', vendorEmailModal.to_email || '');
      formData.append('subject', vendorEmailModal.subject || '');
      formData.append('body', vendorEmailModal.body || '');
      if (vendorManualAttachment) formData.append('attachment', vendorManualAttachment);
      const { ok, data } = await apiPostForm(`/api/jds/${jdId}/vendors/${vendorEmailModal.vendor.id}/assign-send-email`, formData);
      if (!ok || !data.success) throw new Error(data.error || 'Could not send vendor email.');
      toast({ type: 'success', message: 'JD email sent and vendor assigned.' });
      setVendorManualAttachment(null);
      loadAssignedVendors();
      const [nextVendor, ...rest] = vendorEmailQueue;
      if (nextVendor) {
        setVendorEmailQueue(rest);
        await openVendorEmail(nextVendor);
      } else {
        setVendorEmailModal(null);
        setVendorEmailQueue([]);
      }
    } catch (err) {
      const message = err.message || 'Email was not sent, so the vendor was not assigned.';
      updateVendorEmail('error', message);
      toast({ type: 'error', message });
    } finally {
      setVendorEmailBusy(false);
    }
  };

  const openVendorHistory = (vendor) => {
    setVendorHistoryModal(vendor);
    setVendorHistory([]);
    setVendorCandidateHistory([]);
    setVendorHistoryLoading(true);
    apiGet(`/api/jds/${jdId}/vendors/${vendor.id}/email-history`)
      .then(data => {
        setVendorHistory(data.history || []);
        setVendorCandidateHistory(data.candidates || []);
      })
      .catch(() => {
        setVendorHistory([]);
        setVendorCandidateHistory([]);
        toast({ type: 'error', message: 'Could not load vendor email history.' });
      })
      .finally(() => setVendorHistoryLoading(false));
  };

  if (error) {
    return (
      <Layout>
        <div className="jd-details-container">
          <div className="jd-empty-card">
            <i className="fas fa-exclamation-circle jd-empty-icon"></i>
            <p className="jd-empty-text">{error}</p>
            <Link to="/jobs" className="btn btn-secondary"><i className="fas fa-arrow-left"></i> Back to JDs</Link>
          </div>
        </div>
      </Layout>
    );
  }
 
  if (!jd) return <Layout><div className="jd-loading"><SkeletonBlock variant="detail" count={3} /></div></Layout>;
 
  const jdGroups = parseJdSections(jd);
  const structuredData = jdStructuredData(jd);
  const jdSummary = structuredData.summary || synthesizeJdSummary(jd, structuredData);
  const highlightSkills = (structuredData.required_skills?.length ? structuredData.required_skills : jd.skills || []).filter(Boolean).slice(0, 10);
  const highlightResponsibilities = (structuredData.responsibilities?.length ? structuredData.responsibilities : jd.responsibilities || []).filter(Boolean).slice(0, 5);
  const highlightGoodToHave = (structuredData.nice_to_haves || structuredData.preferred_skills || []).filter(Boolean).slice(0, 5);
  const postedDate = formatJdDate(jd.created_date);
  const screenedCount = (jd.selected_count || 0) + (jd.rejected_count || 0);
  const jobInfo = [
    ['Job ID', jd.job_code],
    ['Client Allotted', jd.client_name || '—'],
    ['No. of Posts', jd.required_candidate_count ?? '—'],
    ['Job Category', jd.job_category || '—'],
    ['Date Posted', postedDate || '—'],
    ['Department', jd.department],
    ['Location', jd.location],
  ].filter(([, value]) => value !== undefined && value !== null && value !== '');

  return (
    <Layout>
      <div className="jd-details-container">
        <div className="jdd-topbar">
          <Link to="/jobs" className="jdd-back"><i className="fas fa-arrow-left"></i> Back to Jobs</Link>
          <div className="jdd-topbar-actions">
            <button type="button" className="btn btn-secondary jdd-topbar-btn" onClick={openEditModal}>
              <i className="fas fa-pen"></i> Edit JD
            </button>
            <button type="button" className="btn btn-secondary jdd-topbar-btn" onClick={() => setShowModal(true)}>
              <i className="fas fa-file-export"></i> Generate Report
            </button>
          </div>
        </div>

        <div className="jdd-page">
          <header className="jdd-header">
            <div className="jdd-title-row">
              <h1 className="jdd-title">{jd.title}</h1>
              <span className={`badge ${jd.status === 'Active' ? 'badge-success' : 'badge-danger'}`}>{jd.status}</span>
            </div>
            <div className="jdd-subtitle">
              {[jd.job_category, jd.client_name, postedDate && `Posted ${postedDate}`].filter(Boolean).join(' · ')}
            </div>
          </header>

          <div className="jdd-top-row">
            <section className="jdd-section">
              <h2 className="jdd-section-title">Job Information</h2>
              <dl className="jdd-info-list">
                {jobInfo.map(([label, value]) => (
                  <div key={label} className="jdd-info-pair">
                    <dt>{label}</dt>
                    <dd>{value}</dd>
                  </div>
                ))}
              </dl>
            </section>

            {highlightResponsibilities.length > 0 && (
              <section className="jdd-section">
                <h2 className="jdd-section-title">Key Responsibilities</h2>
                <ul className="jdd-bullets">
                  {highlightResponsibilities.map((item, i) => <li key={i}>{item}</li>)}
                </ul>
              </section>
            )}
          </div>

          {(jdSummary || highlightSkills.length > 0 || highlightGoodToHave.length > 0) && (
            <section className="jdd-section">
              <h2 className="jdd-section-title">Summary</h2>
              {jdSummary && <p className="jdd-summary-text">{jdSummary}</p>}
              {(highlightSkills.length > 0 || highlightGoodToHave.length > 0) && (
                <div className="jdd-highlights-grid">
                  {highlightSkills.length > 0 && (
                    <div className="jdd-highlight-block">
                      <h3 className="jdd-subheading">Required Skills</h3>
                      <div className="jdd-chip-row">
                        {highlightSkills.map((skill, i) => <span key={`${skill}-${i}`} className="jdd-chip">{skill}</span>)}
                      </div>
                    </div>
                  )}
                  {highlightGoodToHave.length > 0 && (
                    <div className="jdd-highlight-block">
                      <h3 className="jdd-subheading">Good to Have Skills</h3>
                      <div className="jdd-chip-row">
                        {highlightGoodToHave.map((skill, i) => <span key={`${skill}-${i}`} className="jdd-chip">{skill}</span>)}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </section>
          )}

          {jdGroups.length > 0 && (
            <section className="jdd-section">
              <div className="jdd-section-title-row">
                <h2 className="jdd-section-title">Full Job Description</h2>
                <button type="button" className="btn btn-secondary jdd-toggle-full-btn" onClick={() => setShowFullJd(v => !v)}>
                  {showFullJd
                    ? <><i className="fas fa-chevron-up"></i> Hide</>
                    : <><i className="fas fa-chevron-down"></i> View Full Description</>}
                </button>
              </div>
            </section>
          )}

          {showFullJd && jdGroups.map((group, gi) => (group.kind === 'intro' ? (
            <section key={`g${gi}`} className="jdd-section">
              <h2 className="jdd-section-title">{gi === 0 ? 'Job Description' : group.title}</h2>
              {gi === 0 && group.title && <p className="jdd-doc-title">{group.title}</p>}
              {group.fields.length > 0 && (
                <dl className="jdd-stacked-fields">
                  {group.fields.map((field, fi) => (
                    <div key={`${field.label}-${fi}`} className="jdd-stacked-field">
                      <dt>{field.label}</dt>
                      <dd>{field.value}</dd>
                    </div>
                  ))}
                </dl>
              )}
              {group.blocks.map((block, bi) => (
                <div key={`b${bi}`} className="jdd-subsection">
                  {block.heading && <h3 className="jdd-subheading">{block.heading}</h3>}
                  <JdSectionBody paragraphs={block.paragraphs} items={block.items} />
                </div>
              ))}
            </section>
          ) : (
            <section key={`g${gi}`} className="jdd-section">
              <h2 className="jdd-section-title">{group.heading}</h2>
              <JdSectionBody paragraphs={group.paragraphs} items={group.items} />
            </section>
          )))}

          <section className="jdd-section">
            <h2 className="jdd-section-title">Resume Statistics</h2>
            <dl className="jdd-info-row jdd-stats-row">
              {[['Total Resumes', jd.total_resumes, ''], ['Selected', jd.selected_count, 'jdd-green'], ['Rejected', jd.rejected_count, 'jdd-red']].map(([label, value, tone]) => (
                <div key={label} className="jdd-info-item">
                  <dt>{label}</dt>
                  <dd className={tone}>{value ?? 0}</dd>
                </div>
              ))}
            </dl>
          </section>

          {jd.total_resumes > 0 && (
            <section className="jdd-section">
              <h2 className="jdd-section-title">Screening Progress</h2>
              <div className="progress jdd-progress">
                <div className="progress-bar" style={{ width: `${Math.round((screenedCount / jd.total_resumes) * 100)}%` }}></div>
              </div>
              <div className="jdd-progress-label">{screenedCount} of {jd.total_resumes} completed</div>
            </section>
          )}

          <section className="jdd-section jdd-actions">
            <button type="button" className="btn btn-primary jd-table-btn" onClick={openAssignVendors}>
              <i className="fas fa-handshake"></i> Assign Vendors
            </button>
          </section>
        </div>

        <div className="white-card jd-fulfilment-timeline-card">
          <h2 className="white-card-title"><i className="fas fa-timeline"></i> Fulfilment Timeline</h2>
          {fulfilmentTimeline.length > 0 ? (
            <div className="jd-fulfilment-timeline">
              {fulfilmentTimeline.slice(0, 8).map(event => (
                <article key={event.id || `${event.action}-${event.timestamp}`} className="jd-fulfilment-event">
                  <span>{event.action || 'Workflow Event'}</span>
                  <p>{event.details || event.outcome || 'No details recorded.'}</p>
                  <small>{event.timestamp ? String(event.timestamp).slice(0, 19).replace('T', ' ') : ''} {event.username ? `| ${event.username}` : ''}</small>
                </article>
              ))}
            </div>
          ) : (
            <div className="jd-empty-card jd-compact-empty"><p className="jd-empty-text">No workflow timeline events yet</p></div>
          )}
        </div>
 
        <h2 className="jd-section-heading"><i className="fas fa-handshake"></i> Assigned Vendors</h2>
        {assignedVendors.length > 0 ? (
          <div className="table-container jd-vendor-table-section">
            <table>
              <thead><tr><th>Vendor</th><th>Email</th><th>Assigned</th><th>Email Status</th><th>Last Email Sent</th><th>Actions</th></tr></thead>
              <tbody>
                {assignedVendors.map(vendor => (
                  <tr key={`${vendor.assignment_id}-${vendor.id}`}>
                    <td>
                      <strong>{vendor.vendor_name || vendor.company_name}</strong>
                      <span>{vendor.company_name || 'Independent vendor'}</span>
                    </td>
                    <td>{vendor.email}</td>
                    <td>{vendor.assigned_at ? String(vendor.assigned_at).slice(0, 10) : '-'}</td>
                    <td><span className={`badge ${vendor.email_status === 'sent' ? 'badge-success' : vendor.email_status === 'failed' ? 'badge-danger' : 'badge-primary'}`}>{vendor.email_status || 'not_sent'}</span></td>
                    <td>{vendor.last_email_sent_at ? String(vendor.last_email_sent_at).slice(0, 10) : 'Never'}</td>
                    <td>
                      <div className="jd-vendor-actions">
                        <button type="button" className="btn btn-secondary jd-table-btn" onClick={() => openVendorHistory(vendor)}>
                          <i className="fas fa-users"></i> History
                        </button>
                        <button type="button" className="btn btn-danger jd-table-btn" onClick={() => removeAssignedVendor(vendor)}>
                          <i className="fas fa-link-slash"></i> Remove
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="jd-empty-card">
            <i className="fas fa-handshake jd-empty-icon"></i>
            <p className="jd-empty-text">No vendors assigned to this JD</p>
          </div>
        )}
 
        <JdHiringProcessEditor jdId={jdId} hiringProcess={jd.hiring_process} />

        <h2 className="jd-section-heading"><i className="fas fa-check-circle"></i> Selected Candidates</h2>
        {selected.length > 0 ? (
          <div className="table-container jd-table-section">
            <table>
              <thead><tr><th>Candidate Name</th><th>Email</th><th>Match Score</th><th>Current Stage</th><th>Actions</th></tr></thead>
              <tbody>
                {selected.map(c => {
                  const assessment = resolveAssessmentRow(c, assessmentMap);
                  return (
                    <tr key={c.id}>
                      <td><strong>{c.name}</strong></td>
                      <td>{c.email}</td>
                      <td><span className="jd-table-score-green">{c.match_score}%</span></td>
                      <td><span className="badge badge-success">{c.hiring_stage}</span></td>
                      <td>
                        <div className="jd-candidate-actions">
                          <Link to={`/talent/${c.id}`} className="btn btn-primary jd-table-btn"><i className="fas fa-eye"></i> View</Link>
                          {c.candidate_source === 'bench' && (
                            <>
                              <button type="button" className="btn btn-secondary jd-table-btn" onClick={() => overrideBenchCandidate(c, 'waitlisted_bench')}>
                                <i className="fas fa-list"></i> Waitlist
                              </button>
                              <button type="button" className="btn btn-danger jd-table-btn" onClick={() => markBenchUnavailable(c)}>
                                <i className="fas fa-user-slash"></i> Unavailable
                              </button>
                            </>
                          )}

                          {assessment.status === 'NOT_CREATED' && (
                            <button
                              type="button"
                              className="btn btn-primary jd-table-btn"
                              disabled={generatingAssessment === c.id}
                              onClick={() => handleGenerateAssessment(c)}
                            >
                              <i className={`fas ${generatingAssessment === c.id ? 'fa-spinner fa-spin' : 'fa-clipboard-list'}`}></i>
                              {generatingAssessment === c.id ? 'Preparing...' : 'Schedule Assessment'}
                            </button>
                          )}

                          {assessment.status === 'DRAFT' && (
                            <button
                              type="button"
                              className="btn btn-secondary jd-table-btn"
                              onClick={() => openAssessmentBuilder(c)}
                            >
                              <i className="fas fa-edit"></i> Review Assessment
                            </button>
                          )}

                          {assessment.status === 'SENT' && (
                            <div className="jd-assessment-status-note">
                              <span><i className="fas fa-hourglass-half"></i> Waiting for Candidate</span>
                            </div>
                          )}

                          {assessment.status === 'IN_PROGRESS' && (
                            <div className="jd-assessment-status-note">
                              <span><i className="fas fa-spinner fa-spin"></i> In Progress</span>
                            </div>
                          )}

                          {assessment.status === 'FAILED' && (
                            <div className="jd-assessment-status-note">
                              <span><i className="fas fa-circle-xmark"></i> Assessment Failed</span>
                            </div>
                          )}

                          {assessment.eligibleForInterview && (
                            <button
                              type="button"
                              className="btn btn-success jd-table-btn"
                              onClick={() => openScheduleModal(c)}
                            >
                              <i className="fas fa-calendar-check"></i> Schedule Interview
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="jd-empty-card">
            <i className="fas fa-inbox jd-empty-icon"></i>
            <p className="jd-empty-text">No selected candidates yet</p>
          </div>
        )}
 
        <h2 className="jd-section-heading"><i className="fas fa-times-circle"></i> Rejected Candidates</h2>
        {rejected.length > 0 ? (
          <div className="table-container">
            <table>
              <thead><tr><th>Candidate Name</th><th>Email</th><th>Match Score</th><th>Rejection Reason</th><th>Actions</th></tr></thead>
              <tbody>
                {rejected.map(c => (
                  <tr key={c.id}>
                    <td><strong>{c.name}</strong></td>
                    <td>{c.email}</td>
                    <td><span className="jd-table-score-red">{c.match_score}%</span></td>
                    <td className="jd-table-summary">{c.rejection_reason}</td>
                    <td>
                      <div className="jd-candidate-actions">
                        <Link to={`/talent/${c.id}`} className="btn btn-primary jd-table-btn"><i className="fas fa-eye"></i> View</Link>
                        {c.candidate_source === 'bench' && (
                          <>
                            <button type="button" className="btn btn-success jd-table-btn" onClick={() => overrideBenchCandidate(c, 'selected_bench')}>
                              <i className="fas fa-check"></i> Select
                            </button>
                            <button type="button" className="btn btn-secondary jd-table-btn" onClick={() => overrideBenchCandidate(c, 'waitlisted_bench')}>
                              <i className="fas fa-list"></i> Waitlist
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="jd-empty-card">
            <i className="fas fa-inbox jd-empty-icon"></i>
            <p className="jd-empty-text">No rejected candidates yet</p>
          </div>
        )}

        {assignVendorsOpen && (
          <div className="jd-modal-backdrop" role="presentation">
            <div className="jd-schedule-modal jd-vendor-modal" role="dialog" aria-modal="true" aria-labelledby="assign-vendors-title">
              <div className="jd-modal-header">
                <div>
                  <h2 id="assign-vendors-title">Assign Vendors</h2>
                  <p>{jd.title}</p>
                  <p className="jd-vendor-shortage-note">
                    Shortage: {fulfilment?.remaining_vendor_requirement ?? jd.remaining_vendor_requirement ?? 0} | Category: {jd.job_category || 'Review required'}
                  </p>
                </div>
                <button type="button" className="jd-modal-close" onClick={() => setAssignVendorsOpen(false)} aria-label="Close assign vendors">
                  <i className="fas fa-times"></i>
                </button>
              </div>

              <div className="jd-vendor-toolbar">
                <input value={vendorSearch} onChange={(event) => setVendorSearch(event.target.value)} placeholder="Search vendors..." />
                <select value={vendorFilter} onChange={(event) => setVendorFilter(event.target.value)}>
                  <option value="Active">Active</option>
                  <option value="All">All</option>
                  <option value="Inactive">Inactive</option>
                </select>
              </div>

              <div className="jd-vendor-select-list">
                {loadingVendors ? (
                  <div className="jd-vendor-select-empty">Loading vendors...</div>
                ) : vendorLoadError ? (
                  <div className="jd-vendor-select-empty">
                    <strong>Could not load vendors.</strong>
                    <span>{vendorLoadError}</span>
                    <button type="button" className="btn btn-secondary" onClick={() => navigate('/vendors')}>
                      <i className="fas fa-handshake"></i> Open Vendors
                    </button>
                  </div>
                ) : availableVendors.length === 0 ? (
                  <div className="jd-vendor-select-empty">
                    <strong>No vendors found.</strong>
                    <span>Add an active vendor first, then assign it to this JD.</span>
                    <button type="button" className="btn btn-primary" onClick={() => navigate('/vendors')}>
                      <i className="fas fa-plus"></i> Add Vendor
                    </button>
                  </div>
                ) : availableVendors.map(vendor => {
                  const supportedCategories = Array.isArray(vendor.supported_categories) ? vendor.supported_categories : [];
                  const categoryEligible = Boolean(jd.job_category && supportedCategories.includes(jd.job_category));
                  return (
                    <label key={vendor.id} className={`jd-vendor-option${vendorSelection.includes(Number(vendor.id)) ? ' selected' : ''}`}>
                      <input
                        type="checkbox"
                        checked={vendorSelection.includes(Number(vendor.id))}
                        disabled={vendor.status !== 'Active'}
                        onChange={() => toggleVendorSelection(vendor.id)}
                      />
                      <span>
                        <strong>{vendor.vendor_name || vendor.company_name}</strong>
                        <small>{vendor.company_name || 'Independent vendor'} - {vendor.email}</small>
                        <small>{supportedCategories.length ? `Categories: ${supportedCategories.join(', ')}` : 'No automated categories configured'}</small>
                      </span>
                      <em className={`vendor-status-inline ${categoryEligible ? 'status-active' : 'status-inactive'}`}>
                        {categoryEligible ? 'Eligible' : 'Manual'}
                      </em>
                    </label>
                  );
                })}
              </div>

              <div className="jd-modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setAssignVendorsOpen(false)} disabled={savingAssignments}>Cancel</button>
                <button type="button" className="btn btn-success" onClick={saveVendorAssignments} disabled={savingAssignments}>
                  {savingAssignments ? <><i className="fas fa-spinner fa-spin"></i> Saving...</> : <><i className="fas fa-save"></i> Save Assignments</>}
                </button>
              </div>
            </div>
          </div>
        )}

        {vendorEmailModal && (
          <div className="jd-modal-backdrop" role="presentation">
            <div className="jd-schedule-modal jd-vendor-modal" role="dialog" aria-modal="true" aria-labelledby="vendor-email-title">
              <div className="jd-modal-header">
                <div>
                  <h2 id="vendor-email-title">Send JD</h2>
                  <p>{vendorEmailModal.vendor?.vendor_name || vendorEmailModal.vendor?.company_name || vendorEmailModal.to_email}</p>
                </div>
                <button type="button" className="jd-modal-close" onClick={() => {
                  if (!vendorEmailBusy) {
                    setVendorEmailModal(null);
                    setVendorManualAttachment(null);
                    setVendorEmailQueue([]);
                  }
                }} aria-label="Close vendor email">
                  <i className="fas fa-times"></i>
                </button>
              </div>

              <div className="jd-schedule-grid">
                <div className="form-group">
                  <label>From</label>
                  <input value={vendorEmailModal.from_email || 'Configured sender email'} readOnly />
                </div>
                <div className="form-group">
                  <label>To</label>
                  <input value={vendorEmailModal.to_email || ''} onChange={(event) => updateVendorEmail('to_email', event.target.value)} />
                </div>
              </div>
              <div className="form-group">
                <label>Subject</label>
                <input value={vendorEmailModal.subject || ''} onChange={(event) => updateVendorEmail('subject', event.target.value)} placeholder={vendorEmailBusy ? 'Generating...' : 'Subject'} />
              </div>
              <div className="form-group">
                <label>Message Body</label>
                <textarea className="jd-email-body" value={vendorEmailModal.body || ''} onChange={(event) => updateVendorEmail('body', event.target.value)} placeholder={vendorEmailBusy ? 'Generating email...' : 'Message body'} />
              </div>
              <div className="jd-email-attachments">
                <strong><i className="fas fa-paperclip"></i> Attachment</strong>
                <div className="jd-email-attachment-list">
                  {(vendorEmailModal.attachments || []).length > 0
                    ? vendorEmailModal.attachments.map(file => <span key={file}>{file}</span>)
                    : <span>No saved JD file found. Choose a file below.</span>}
                  {vendorManualAttachment && <span>{vendorManualAttachment.name}</span>}
                </div>
                <label className="jd-email-file-picker">
                  <i className="fas fa-upload"></i>
                  <span>{vendorManualAttachment ? 'Change Manual JD File' : 'Attach JD From Computer'}</span>
                  <input type="file" accept=".pdf,.doc,.docx" onChange={(event) => setVendorManualAttachment(event.target.files?.[0] || null)} />
                </label>
              </div>
              {vendorEmailModal.error && <div className="jd-schedule-alert jd-schedule-alert-error">{vendorEmailModal.error}</div>}
              <div className="jd-modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => {
                  setVendorEmailModal(null);
                  setVendorManualAttachment(null);
                  setVendorEmailQueue([]);
                }} disabled={vendorEmailBusy}>Cancel</button>
                <button type="button" className="btn btn-success" onClick={sendVendorEmail} disabled={vendorEmailBusy || !vendorEmailModal.subject || !vendorEmailModal.body}>
                  {vendorEmailBusy ? <><i className="fas fa-spinner fa-spin"></i> Working...</> : <><i className="fas fa-paper-plane"></i> Send Email</>}
                </button>
              </div>
            </div>
          </div>
        )}

        {vendorHistoryModal && (
          <div className="jd-modal-backdrop" role="presentation">
            <div className="jd-schedule-modal jd-vendor-modal" role="dialog" aria-modal="true" aria-labelledby="vendor-history-title">
              <div className="jd-modal-header">
                <div>
                  <h2 id="vendor-history-title">Vendor History</h2>
                  <p>{vendorHistoryModal.vendor_name || vendorHistoryModal.company_name || vendorHistoryModal.email}</p>
                </div>
                <button type="button" className="jd-modal-close" onClick={() => setVendorHistoryModal(null)} aria-label="Close vendor history">
                  <i className="fas fa-times"></i>
                </button>
              </div>

              {vendorHistoryLoading ? (
                <div className="jd-vendor-select-empty">Loading history...</div>
              ) : vendorCandidateHistory.length === 0 ? (
                <div className="jd-vendor-select-empty">No candidates provided by this vendor for this JD yet.</div>
              ) : (
                <div className="jd-vendor-history-list">
                  {vendorCandidateHistory.map(row => (
                    <article key={row.id} className="jd-vendor-history-item">
                      <div>
                        <strong>{row.name || 'Candidate'}</strong>
                        <span>{row.email || 'No email'}{row.resume_file ? ` - ${row.resume_file}` : ''}</span>
                      </div>
                      <em className="vendor-status-inline status-active">{row.status || 'Candidate'}</em>
                      {row.selection_status !== 'accepted_vendor' && <button type="button" className="btn btn-success jd-table-btn" onClick={() => acceptVendorCandidate(row)}><i className="fas fa-check"></i> Accept</button>}
                      {row.screening_summary && <p>{String(row.screening_summary).slice(0, 220)}</p>}
                    </article>
                  ))}
                </div>
              )}
              {!vendorHistoryLoading && vendorHistory.length > 0 && (
                <div className="jd-vendor-mail-count">
                  <i className="fas fa-envelope"></i> {vendorHistory.length} JD email{vendorHistory.length === 1 ? '' : 's'} sent or attempted.
                </div>
              )}
            </div>
          </div>
        )}
 
        {scheduleCandidate && (
          <div className="jd-modal-backdrop" role="presentation">
            <div className="jd-schedule-modal" role="dialog" aria-modal="true" aria-labelledby="schedule-title">
              <div className="jd-modal-header">
                <div>
                  <h2 id="schedule-title">Schedule Interview</h2>
                  <p>{scheduleCandidate.name} - {jd.title}</p>
                </div>
                <button type="button" className="jd-modal-close" onClick={closeScheduleModal} aria-label="Close schedule modal">
                  <i className="fas fa-times"></i>
                </button>
              </div>

              <div className="jd-schedule-grid">
                <div className="form-group">
                  <label>From</label>
                  <input value={emailPreview.from_email || 'Configured sender email'} readOnly />
                </div>
                <div className="form-group">
                  <label>Email To</label>
                  <input value={emailPreview.to_email || scheduleCandidate.email || ''} readOnly />
                </div>
                <div className="form-group">
                  <label>Phone To</label>
                  <input value={textPreview.to || scheduleCandidate.phone || ''} readOnly />
                </div>
                <div className="form-group">
                  <label>Interview Date</label>
                  <input
                    type="date"
                    value={interviewDate}
                    min={today}
                    onChange={(event) => {
                      setInterviewDate(event.target.value);
                      setInterviewTime('');
                      setEmailPreview(prev => ({ ...prev, subject: '', body: '' }));
                      setTextPreview(prev => ({ ...prev, body: '' }));
                    }}
                  />
                </div>
                <div className="form-group">
                  <label>Interview Time</label>
                  <select
                    value={interviewTime}
                    disabled={!interviewDate || loadingSlots}
                    onChange={(event) => {
                      setInterviewTime(event.target.value);
                      setEmailPreview(prev => ({ ...prev, subject: '', body: '' }));
                      setTextPreview(prev => ({ ...prev, body: '' }));
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
                    value={interviewDetails.interviewer}
                    onChange={(event) => setInterviewDetails(prev => ({ ...prev, interviewer: event.target.value }))}
                    placeholder="Interviewer name"
                  />
                </div>
                <div className="form-group">
                  <label>Mode</label>
                  <select
                    value={interviewDetails.interview_mode}
                    onChange={(event) => setInterviewDetails(prev => ({ ...prev, interview_mode: event.target.value }))}
                  >
                    <option value="Online">Online</option>
                    <option value="Phone">Phone</option>
                    <option value="In Person">In Person</option>
                  </select>
                </div>
                <div className="form-group">
                  <label>Meeting Link</label>
                  <input
                    value={interviewDetails.meeting_link}
                    onChange={(event) => setInterviewDetails(prev => ({ ...prev, meeting_link: event.target.value }))}
                    placeholder="https://..."
                  />
                </div>
                <div className="form-group">
                  <label>Notes</label>
                  <input
                    value={interviewDetails.notes}
                    onChange={(event) => setInterviewDetails(prev => ({ ...prev, notes: event.target.value }))}
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
                  value={emailPreview.subject}
                  onChange={(event) => setEmailPreview(prev => ({ ...prev, subject: event.target.value }))}
                  placeholder="Generate email to fill subject"
                />
              </div>
              <div className="form-group">
                <label>Email Body</label>
                <textarea
                  className="jd-email-body"
                  value={emailPreview.body}
                  onChange={(event) => setEmailPreview(prev => ({ ...prev, body: event.target.value }))}
                  placeholder="Generate email after selecting date and time"
                />
              </div>
              <div className="form-group">
                <label>Text Body</label>
                <textarea
                  className="jd-sms-body"
                  value={textPreview.body}
                  onChange={(event) => setTextPreview(prev => ({ ...prev, body: event.target.value }))}
                  placeholder="Generate after selecting date and time"
                />
              </div>
              {scheduleError && <div className="jd-schedule-alert jd-schedule-alert-error">{scheduleError}</div>}

              <div className="jd-modal-actions">
                <button type="button" className="btn btn-secondary" onClick={closeScheduleModal} disabled={generatingEmail || sendingEmail}>Cancel</button>
                <button type="button" className="btn btn-primary" onClick={handleGenerateEmail} disabled={generatingEmail || sendingEmail || !interviewDate || !interviewTime}>
                  {generatingEmail ? <><i className="fas fa-spinner fa-spin"></i> Generating...</> : <><i className="fas fa-magic"></i> Generate</>}
                </button>
                <button type="button" className="btn btn-success" onClick={handleSendSchedule} disabled={generatingEmail || sendingEmail || !emailPreview.subject || !emailPreview.body || !interviewDetails.interviewer.trim() || (interviewDetails.interview_mode === 'Online' && !interviewDetails.meeting_link.trim())}>
                  {sendingEmail ? <><i className="fas fa-spinner fa-spin"></i> Sending...</> : <><i className="fas fa-paper-plane"></i> Send & Schedule</>}
                </button>
              </div>
            </div>
          </div>
        )}

        {showEditModal && editForm && (
          <div className="jd-modal-backdrop" role="presentation">
            <div className="jd-schedule-modal jd-edit-modal" role="dialog" aria-modal="true" aria-labelledby="edit-jd-title">
              <div className="jd-modal-header">
                <div>
                  <h2 id="edit-jd-title">Edit Job Description</h2>
                  <p>{jd.title}</p>
                </div>
                <button type="button" className="jd-modal-close" onClick={() => setShowEditModal(false)} aria-label="Close edit job description">
                  <i className="fas fa-times"></i>
                </button>
              </div>

              <div className="jd-edit-form">
                <div className="form-group">
                  <label>Title</label>
                  <input type="text" value={editForm.title} onChange={(e) => setEditForm(f => ({ ...f, title: e.target.value }))} />
                </div>
                <div className="form-group">
                  <label>Job ID</label>
                  <input type="text" value={editForm.job_code} onChange={(e) => setEditForm(f => ({ ...f, job_code: e.target.value }))} placeholder="e.g. REQ-1023" />
                </div>
                <div className="jd-edit-form-row">
                  <div className="form-group">
                    <label>Department</label>
                    <input type="text" value={editForm.department} onChange={(e) => setEditForm(f => ({ ...f, department: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label>Location</label>
                    <input type="text" value={editForm.location} onChange={(e) => setEditForm(f => ({ ...f, location: e.target.value }))} />
                  </div>
                </div>
                <div className="jd-edit-form-row">
                  <div className="form-group">
                    <label>Experience Required</label>
                    <input type="text" value={editForm.experience_required} onChange={(e) => setEditForm(f => ({ ...f, experience_required: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label>Job Category</label>
                    <input type="text" value={editForm.job_category} onChange={(e) => setEditForm(f => ({ ...f, job_category: e.target.value }))} />
                  </div>
                </div>
                <div className="jd-edit-form-row">
                  <div className="form-group">
                    <label>No. of Posts</label>
                    <input type="number" min="1" value={editForm.required_candidate_count} onChange={(e) => setEditForm(f => ({ ...f, required_candidate_count: e.target.value }))} />
                  </div>
                  <div className="form-group">
                    <label>Status</label>
                    <select value={editForm.status} onChange={(e) => setEditForm(f => ({ ...f, status: e.target.value }))}>
                      <option value="Active">Active</option>
                      <option value="Closed">Closed</option>
                      <option value="Inactive">Inactive</option>
                    </select>
                  </div>
                </div>
                <div className="form-group">
                  <label>Skills (comma separated)</label>
                  <input type="text" value={editForm.skills} onChange={(e) => setEditForm(f => ({ ...f, skills: e.target.value }))} />
                </div>
                <div className="form-group">
                  <label>Responsibilities (one per line)</label>
                  <textarea rows="4" value={editForm.responsibilities} onChange={(e) => setEditForm(f => ({ ...f, responsibilities: e.target.value }))} />
                </div>
                <div className="form-group">
                  <label>Job Description Text</label>
                  <textarea rows="8" value={editForm.raw_text} onChange={(e) => setEditForm(f => ({ ...f, raw_text: e.target.value }))} />
                </div>
                {editError && <div className="jd-schedule-alert jd-schedule-alert-error">{editError}</div>}
              </div>

              <div className="jd-modal-actions">
                <button type="button" className="btn btn-secondary" onClick={() => setShowEditModal(false)} disabled={savingEdit}>Cancel</button>
                <button type="button" className="btn btn-success" onClick={saveEdit} disabled={savingEdit}>
                  {savingEdit ? <><i className="fas fa-spinner fa-spin"></i> Saving...</> : <><i className="fas fa-save"></i> Save Changes</>}
                </button>
              </div>
            </div>
          </div>
        )}

        <div className="jd-details-actions-footer">
          <button
            type="button"
            className="btn btn-danger jd-remove-footer-btn"
            disabled={deleting}
            onClick={handleRemove}
            title="Remove this job description"
          >
            {deleting
              ? <><i className="fas fa-spinner fa-spin"></i> Removing…</>
              : <><i className="fas fa-trash-alt"></i> Remove job description</>}
          </button>
        </div>

        <ReportModal />

        <style>{`
          @keyframes slideUp {
            from {
              opacity: 0;
              transform: translateY(30px);
            }
            to {
              opacity: 1;
              transform: translateY(0);
            }
          }
        `}</style>
      </div>
    </Layout>
  );
}
 
export default JdDetails;
