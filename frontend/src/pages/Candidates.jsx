import React, { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import Layout from '../components/Layout.jsx';
import KebabMenu from '../components/KebabMenu.jsx';
import SendAssessmentModal from '../components/SendAssessmentModal.jsx';
import { TALENT_CACHE_KEY, apiGet, readSessionCache, writeSessionCache, apiPost } from '../api.js';
import { toast, useConfirm } from '../components/EnterpriseFeedback.jsx';
import '../styles/candidates.css';
import '../styles/talent_table.css';
import jsPDF from 'jspdf';
import 'jspdf-autotable';
import { Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell, AlignmentType, WidthType } from 'docx';
import { saveAs } from 'file-saver';
import * as XLSX from 'xlsx';
import { currentReportId, issueReportId } from '../utils/reportId.js';
import { useRoleCategories } from '../utils/useRoleCategories.js';
import { dedupeCandidates, candidateMatchesSelection } from '../utils/candidateGrouping.js';
import { appliedTime, formatApplied, initialsOf, locationOf, pageWindow, roleOf, scoreOf, scoreTone, stageOf } from '../utils/talentTable.js';


const ROLE_CATEGORY_FILTER_LABELS = {
  Developer: 'All Developers',
  Tester: 'All Testers',
  PMO: 'All PMOs',
  PM: 'All PMs',
  TL: 'All TLs',
  'Business Analyst': 'All Business Analysts',
  'DevOps / Cloud': 'All DevOps / Cloud',
  Data: 'All Data Candidates',
  Support: 'All Support Candidates',
  Others: 'Others',
};

// Multiple resume submissions for the same person create separate candidate
// records (one per JD match). Collapse those into one card per person, merging
// their applied roles, so the Talent page shows one candidate with every role
// they've applied for underneath their name instead of duplicate cards.

const EMPTY_QUICK_FILTERS = { stage: '', role: '', location: '', client: '' };
const PAGE_SIZES = [10, 20, 50, 100];

const EMPTY_FILTERS = { clientId: '', projectId: '', status: '', stageId: '', uploadFrom: '', uploadTo: '', interviewFrom: '', interviewTo: '' };

function Candidates() {
  const [candidates, setCandidates] = useState(() => dedupeCandidates(readSessionCache(TALENT_CACHE_KEY) || []));
  const roleCategories = useRoleCategories(candidates.map(candidate => candidate.primary_category));
  const [searchTerm, setSearchTerm] = useState('');
  const [filterCategory, setFilterCategory] = useState('');
  const [quickFilters, setQuickFilters] = useState(EMPTY_QUICK_FILTERS);
  const [sortDir, setSortDir] = useState('desc');
  const [pageSize, setPageSize] = useState(20);
  const [page, setPage] = useState(1);

  // --- TEMPORARY: bulk select + delete. Remove this whole block (and its
  // JSX usages) when no longer needed. ---
  const confirm = useConfirm();
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [assessmentCandidate, setAssessmentCandidate] = useState(null);
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const toggleSelect = (id) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };
  const deleteSelected = () => deleteRows(visibleSelected);
  // Bulk delete and the row menu's Remove share this path.
  const deleteRows = async (rows) => {
    if (!rows.length) return;
    const single = rows.length === 1 && !selectedIds.has(rows[0].id) ? rows[0] : null;
    const approved = await confirm({
      title: single ? 'Remove candidate' : 'Remove candidates',
      message: single
        ? `Remove candidate "${single.name}" from the repository? This cannot be undone.`
        : `Remove ${rows.length} selected candidate(s) from the repository? This cannot be undone.`,
      confirmLabel: 'Remove Candidates',
      icon: 'fas fa-user-times',
      danger: true,
    });
    if (!approved) return;
    setBulkDeleting(true);
    try {
      // A row can merge several resume submissions for one person; remove all of them.
      const ids = [...new Set(rows.flatMap(row => row.member_ids || [row.id]))];
      const results = await Promise.all(ids.map(id => apiPost(`/api/candidates/${id}/delete`, { confirmed: true })));
      const removedIds = new Set(ids.filter((id, i) => results[i].ok && results[i].data?.success));
      const isGone = row => (row.member_ids || [row.id]).every(id => removedIds.has(id));
      const removedRows = rows.filter(isGone).length;
      const failedCount = rows.length - removedRows;
      setCandidates(prev => prev.filter(c => !isGone(c)));
      writeSessionCache(TALENT_CACHE_KEY, (readSessionCache(TALENT_CACHE_KEY) || []).filter(c => !removedIds.has(c.id)));
      setServerFiltered(prev => (prev ? prev.filter(c => !isGone(c)) : prev));
      setSelectedIds(prev => new Set([...prev].filter(id => !rows.some(row => row.id === id && isGone(row)))));
      toast(failedCount
        ? { type: 'error', message: `${removedRows} removed, ${failedCount} could not be fully removed.` }
        : { type: 'success', message: `${removedRows} candidate(s) removed.` });
    } finally {
      setBulkDeleting(false);
    }
  };
  // --- END TEMPORARY ---

  // --- FILTERS PANEL STATE ---
  const [panelOpen, setPanelOpen] = useState(false);
  const [draftFilters, setDraftFilters] = useState(EMPTY_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState(EMPTY_FILTERS);
  const [serverFiltered, setServerFiltered] = useState(null);
  const [applying, setApplying] = useState(false);
  const [dateError, setDateError] = useState('');
  const [clients, setClients] = useState([]);
  const [projects, setProjects] = useState([]);
  const [stageGroups, setStageGroups] = useState([]);
  const [listError, setListError] = useState('');
  const filterAnchorRef = useRef(null);

  useEffect(() => {
    apiGet('/api/clients').then(data => setClients(data.clients || [])).catch(() => {});
    apiGet('/api/candidates/stage-options').then(data => setStageGroups(data.groups || [])).catch(() => {});
  }, []);

  useEffect(() => {
    if (!panelOpen) return undefined;
    const handleClickOutside = (event) => {
      if (filterAnchorRef.current && !filterAnchorRef.current.contains(event.target)) {
        setPanelOpen(false);
      }
    };
    const handleEscape = (event) => { if (event.key === 'Escape') setPanelOpen(false); };
    document.addEventListener('mousedown', handleClickOutside);
    document.addEventListener('keydown', handleEscape);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleEscape);
    };
  }, [panelOpen]);

  const handleClientChange = async (clientId) => {
    setDraftFilters(f => ({ ...f, clientId, projectId: '', stageId: '' }));
    setProjects([]);
    if (!clientId) {
      apiGet('/api/candidates/stage-options').then(data => setStageGroups(data.groups || [])).catch(() => {});
      return;
    }
    try {
      const details = await apiGet(`/api/clients/${clientId}`);
      setProjects(details.projects || []);
    } catch { setProjects([]); }
  };

  const handleProjectChange = (projectId) => {
    setDraftFilters(f => ({ ...f, projectId, stageId: '' }));
    const query = projectId ? `?project_id=${projectId}` : '';
    apiGet(`/api/candidates/stage-options${query}`).then(data => setStageGroups(data.groups || [])).catch(() => setStageGroups([]));
  };

  const applyFilters = async () => {
    setDateError('');
    if (draftFilters.uploadFrom && draftFilters.uploadTo && draftFilters.uploadFrom > draftFilters.uploadTo) {
      setDateError('Upload date range is reversed.'); return;
    }
    if (draftFilters.interviewFrom && draftFilters.interviewTo && draftFilters.interviewFrom > draftFilters.interviewTo) {
      setDateError('Interview date range is reversed.'); return;
    }
    setApplying(true);
    try {
      const params = new URLSearchParams();
      if (draftFilters.clientId) params.set('client_id', draftFilters.clientId);
      if (draftFilters.projectId) params.set('project_id', draftFilters.projectId);
      if (draftFilters.status) params.set('status', draftFilters.status);
      if (draftFilters.stageId) params.set('stage', draftFilters.stageId);
      if (draftFilters.uploadFrom) params.set('upload_from', draftFilters.uploadFrom);
      if (draftFilters.uploadTo) params.set('upload_to', draftFilters.uploadTo);
      if (draftFilters.interviewFrom) params.set('interview_from', draftFilters.interviewFrom);
      if (draftFilters.interviewTo) params.set('interview_to', draftFilters.interviewTo);
      params.set('tz', Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC');
      const data = await apiGet(`/api/candidates?${params.toString()}`);
      setServerFiltered(dedupeCandidates(Array.isArray(data) ? data : []));
      setAppliedFilters({ ...draftFilters });
      setPanelOpen(false);
    } catch {
      setDateError('Could not apply filters. Please try again.');
    } finally {
      setApplying(false);
    }
  };

  const clearFilters = () => {
    setDraftFilters(EMPTY_FILTERS);
    setAppliedFilters(EMPTY_FILTERS);
    setServerFiltered(null);
    setProjects([]);
    setDateError('');
    setFilterCategory('');
  };

  const activeFilterCount = Object.values(appliedFilters).filter(Boolean).length + (filterCategory ? 1 : 0);


  // --- REPORT MODAL STATE ---
  const [showModal, setShowModal] = useState(false);
  const [selectedFormat, setSelectedFormat] = useState('pdf');
  const [recipientEmail, setRecipientEmail] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [showEmailInput, setShowEmailInput] = useState(false);

  useEffect(() => {
    const cached = readSessionCache(TALENT_CACHE_KEY);
    if (cached) {
      setCandidates(dedupeCandidates(Array.isArray(cached) ? cached : []));
    }

    apiGet('/api/candidates')
      .then(data => {
        const rows = Array.isArray(data) ? data : [];
        setCandidates(dedupeCandidates(rows));
        writeSessionCache(TALENT_CACHE_KEY, rows);
        setListError('');
      })
      .catch(() => {
        setListError('Could not load the latest candidate list. Showing cached results, if any.');
      });
  }, []);

  const baseRows = serverFiltered ?? candidates;
  const matchingRows = baseRows.filter(c => {
    const haystack = `${c.name || ''} ${c.client_name || ''} ${c.primary_category || ''} ${(c.job_applications || []).map(job => job.jd_title).join(' ')}`.toLowerCase();
    const matchSearch = haystack.includes(searchTerm.toLowerCase());
    const matchCategory = !filterCategory || c.primary_category === filterCategory;
    return matchSearch && matchCategory;
  });
  const decorated = matchingRows.map(c => ({
    c, stage: stageOf(c), role: roleOf(c), location: locationOf(c), score: scoreOf(c), applied: appliedTime(c),
  }));
  // Quick filters (Stage / Role / Location / Client) and the Applied On sort run in the browser.
  const rows = decorated
    .filter(row => (!quickFilters.stage || row.stage.label === quickFilters.stage)
      && (!quickFilters.role || row.role.primary === quickFilters.role || row.role.others.includes(quickFilters.role))
      && (!quickFilters.location || row.location === quickFilters.location)
      && (!quickFilters.client || row.c.client_name === quickFilters.client))
    .sort((a, b) => {
      const diff = (a.applied?.getTime() ?? 0) - (b.applied?.getTime() ?? 0);
      return sortDir === 'desc' ? -diff : diff;
    });
  // Reports and bulk actions cover exactly the rows the table shows.
  const filtered = rows.map(row => row.c);
  const pageCount = Math.max(1, Math.ceil(rows.length / pageSize));
  const currentPage = Math.min(page, pageCount);
  const pageRows = rows.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  // Selections hidden by a later search or filter are never acted on.
  const visibleSelected = filtered.filter(c => selectedIds.has(c.id));

  // ============================================================
  // CANDIDATES STATISTICS
  // ============================================================

  // Reports cover the candidates currently shown (search, filters and category applied).
  const getCandidateStats = () => {
    const candidates = filtered;
    const resultOf = c => String(c.outcome ?? c.status ?? '').toLowerCase();
    const totalCandidates = candidates.length;
    const selected = candidates.filter(c => resultOf(c) === 'selected');
    const rejected = candidates.filter(c => resultOf(c) === 'rejected');
    // Passed screening, not rejected later and not on hold.
    const inProcess = selected.filter(c => !c.on_hold);
    
    let totalMatchScore = 0;
    let matchCount = 0;
    let highestMatch = null;
    let lowestMatch = null;
    let skillsMap = {};
    let educationMap = {};
    let hiringStagesMap = {};

    candidates.forEach(c => {
      if (c.match_score !== undefined && c.match_score !== null) {
        totalMatchScore += c.match_score;
        matchCount++;
        if (!highestMatch || c.match_score > highestMatch.match_score) {
          highestMatch = { name: c.name, match_score: c.match_score };
        }
        if (!lowestMatch || c.match_score < lowestMatch.match_score) {
          lowestMatch = { name: c.name, match_score: c.match_score };
        }
      }

      const skills = (c.structured_data?.skills || c.skills || []);
      skills.forEach(skill => {
        skillsMap[skill] = (skillsMap[skill] || 0) + 1;
      });

      const education = c.education || c.structured_data?.education || 'Not Specified';
      educationMap[education] = (educationMap[education] || 0) + 1;

      const stage = c.hiring_stage || 'Not Started';
      hiringStagesMap[stage] = (hiringStagesMap[stage] || 0) + 1;
    });

    const avgMatch = matchCount > 0 ? Math.round(totalMatchScore / matchCount) : 0;
    const sortedSkills = Object.entries(skillsMap).sort((a, b) => b[1] - a[1]);
    const topSkills = sortedSkills.slice(0, 10);

    return {
      totalCandidates,
      selected: selected.length,
      rejected: rejected.length,
      inProcess: inProcess.length,
      avgMatch,
      highestMatch,
      lowestMatch,
      topSkills,
      educationDistribution: Object.entries(educationMap),
      hiringStages: Object.entries(hiringStagesMap),
      selectionRate: totalCandidates > 0 ? Math.round((selected.length / totalCandidates) * 100) : 0
    };
  };

  // ============================================================
  // PROFESSIONAL PDF GENERATION (Direct)
  // ============================================================

  const downloadPDF = () => {
  try {
    const stats = getCandidateStats();
    const doc = new jsPDF('p', 'mm', 'a4');
    const pageWidth = doc.internal.pageSize.getWidth();
    const margin = 20;
    let y = 25;

    // --- TITLE ---
    doc.setFontSize(24);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(26, 54, 93);
    doc.text('CANDIDATES REPORT', pageWidth / 2, y, { align: 'center' });
    y += 10;

    // --- DIVIDER ---
    doc.setDrawColor(26, 54, 93);
    doc.setLineWidth(0.8);
    doc.line(margin, y, pageWidth - margin, y);
    y += 12;

    // --- METADATA ---
    doc.setFontSize(10);
    doc.setFont('helvetica', 'normal');
    doc.setTextColor(100, 100, 100);
    const now = new Date();
    const dateStr = now.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
    doc.text('Generated: ' + dateStr, margin, y);
    y += 6;
    doc.text('Total Candidates: ' + stats.totalCandidates, margin, y);
    y += 14;

    // --- SECTION 1: OVERALL STATISTICS ---
    doc.setFontSize(16);
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(26, 54, 93);
    doc.text('1. Overall Statistics', margin, y);
    y += 10;

    const statsData = [
      ['Total Candidates', stats.totalCandidates],
      ['Selected', stats.selected],
      ['Rejected', stats.rejected],
      ['In Process', stats.inProcess],
      ['Selection Rate', stats.selectionRate + '%'],
      ['Average Match Score', stats.avgMatch + '%']
    ];

    // Table headers
    doc.setFillColor(26, 54, 93);
    doc.rect(margin, y - 4, 70, 9, 'F');
    doc.rect(margin + 70, y - 4, 60, 9, 'F');
    doc.setFont('helvetica', 'bold');
    doc.setTextColor(255, 255, 255);
    doc.text('Metric', margin + 2, y + 3);
    doc.text('Value', margin + 72, y + 3);
    y += 8;

    doc.setFont('helvetica', 'normal');
    statsData.forEach(function(row, index) {
      if (y > 270) { doc.addPage(); y = 20; }
      if (index % 2 === 0) {
        doc.setFillColor(240, 245, 250);
        doc.rect(margin, y - 3, 130, 7, 'F');
      }
      doc.setTextColor(50, 50, 50);
      doc.text(row[0], margin + 2, y + 2);
      doc.text(String(row[1]), margin + 72, y + 2);
      y += 8;
    });
    y += 10;

    // --- SECTION 2: TOP SKILLS ---
    if (stats.topSkills.length > 0) {
      if (y > 240) { doc.addPage(); y = 20; }

      doc.setFontSize(16);
      doc.setFont('helvetica', 'bold');
      doc.setTextColor(26, 54, 93);
      doc.text('2. Top Skills', margin, y);
      y += 10;

      doc.setFillColor(26, 54, 93);
      doc.rect(margin, y - 4, 70, 9, 'F');
      doc.rect(margin + 70, y - 4, 60, 9, 'F');
      doc.setFont('helvetica', 'bold');
      doc.setTextColor(255, 255, 255);
      doc.text('Skill', margin + 2, y + 3);
      doc.text('Count', margin + 72, y + 3);
      y += 8;

      doc.setFont('helvetica', 'normal');
      stats.topSkills.slice(0, 10).forEach(function(skill, index) {
        if (y > 270) { doc.addPage(); y = 20; }
        if (index % 2 === 0) {
          doc.setFillColor(240, 245, 250);
          doc.rect(margin, y - 3, 130, 7, 'F');
        }
        doc.setTextColor(50, 50, 50);
        doc.text(skill[0], margin + 2, y + 2);
        doc.text(String(skill[1]), margin + 72, y + 2);
        y += 8;
      });
      y += 10;
    }

    // --- SECTION 3: EDUCATION DISTRIBUTION ---
    if (stats.educationDistribution.length > 0) {
      if (y > 240) { doc.addPage(); y = 20; }

      doc.setFontSize(16);
      doc.setFont('helvetica', 'bold');
      doc.setTextColor(26, 54, 93);
      doc.text('3. Education Distribution', margin, y);
      y += 10;

      doc.setFillColor(26, 54, 93);
      doc.rect(margin, y - 4, 80, 9, 'F');
      doc.rect(margin + 80, y - 4, 50, 9, 'F');
      doc.setFont('helvetica', 'bold');
      doc.setTextColor(255, 255, 255);
      doc.text('Education', margin + 2, y + 3);
      doc.text('Count', margin + 82, y + 3);
      y += 8;

      doc.setFont('helvetica', 'normal');
      stats.educationDistribution.forEach(function(edu, index) {
        if (y > 270) { doc.addPage(); y = 20; }
        if (index % 2 === 0) {
          doc.setFillColor(240, 245, 250);
          doc.rect(margin, y - 3, 130, 7, 'F');
        }
        doc.setTextColor(50, 50, 50);
        doc.text(edu[0], margin + 2, y + 2);
        doc.text(String(edu[1]), margin + 82, y + 2);
        y += 8;
      });
      y += 10;
    }

    // --- SECTION 4: HIRING STAGES ---
    if (stats.hiringStages.length > 0) {
      if (y > 240) { doc.addPage(); y = 20; }

      doc.setFontSize(16);
      doc.setFont('helvetica', 'bold');
      doc.setTextColor(26, 54, 93);
      doc.text('4. Hiring Stages', margin, y);
      y += 10;

      doc.setFillColor(26, 54, 93);
      doc.rect(margin, y - 4, 80, 9, 'F');
      doc.rect(margin + 80, y - 4, 50, 9, 'F');
      doc.setFont('helvetica', 'bold');
      doc.setTextColor(255, 255, 255);
      doc.text('Stage', margin + 2, y + 3);
      doc.text('Count', margin + 82, y + 3);
      y += 8;

      doc.setFont('helvetica', 'normal');
      stats.hiringStages.forEach(function(stage, index) {
        if (y > 270) { doc.addPage(); y = 20; }
        if (index % 2 === 0) {
          doc.setFillColor(240, 245, 250);
          doc.rect(margin, y - 3, 130, 7, 'F');
        }
        doc.setTextColor(50, 50, 50);
        doc.text(stage[0], margin + 2, y + 2);
        doc.text(String(stage[1]), margin + 82, y + 2);
        y += 8;
      });
      y += 10;
    }

    // --- SECTION 5: TOP PERFORMING CANDIDATES ---
    if (stats.highestMatch || stats.lowestMatch) {
      if (y > 240) { doc.addPage(); y = 20; }

      doc.setFontSize(16);
      doc.setFont('helvetica', 'bold');
      doc.setTextColor(26, 54, 93);
      doc.text('5. Top Performing Candidates', margin, y);
      y += 10;

      doc.setFontSize(11);
      doc.setFont('helvetica', 'normal');
      doc.setTextColor(50, 50, 50);

      if (stats.highestMatch) {
        doc.text('Highest Match: ' + stats.highestMatch.name + ' (' + stats.highestMatch.match_score + '%)', margin + 2, y);
        y += 8;
      }
      if (stats.lowestMatch) {
        doc.text('Lowest Match: ' + stats.lowestMatch.name + ' (' + stats.lowestMatch.match_score + '%)', margin + 2, y);
        y += 8;
      }
      y += 10;
    }

    // --- FOOTER ---
    if (y > 260) { doc.addPage(); y = 20; }

    doc.setDrawColor(200, 200, 200);
    doc.setLineWidth(0.3);
    doc.line(margin, y, pageWidth - margin, y);
    y += 8;

    doc.setFontSize(9);
    doc.setFont('helvetica', 'italic');
    doc.setTextColor(150, 150, 150);
    doc.text('Recruitment Analytics System - Confidential Report', pageWidth / 2, y, { align: 'center' });
    y += 5;
    doc.text('Generated on ' + dateStr + ' | Page ' + doc.internal.getNumberOfPages(), pageWidth / 2, y, { align: 'center' });

    const filename = 'Candidates_Report_' + new Date().toISOString().split('T')[0] + '.pdf';
    doc.save(filename);
    alert('✅ Candidates Report PDF downloaded successfully!');
    
  } catch (error) {
    console.error('PDF Error:', error);
    alert('❌ Failed to generate PDF. Please try again.');
  }
};
 

  // ============================================================
  // PROFESSIONAL CSV GENERATION
  // ============================================================

  const downloadCSV = function() {
    try {
      const stats = getCandidateStats();
      const now = new Date();
      const dateStr = now.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });

      let csvContent = '';

      // --- TITLE ---
      csvContent += 'CANDIDATES REPORT\n';
      csvContent += 'Generated: ' + dateStr + '\n';
      csvContent += 'Report ID: ' + currentReportId() + '\n\n';

      // --- SECTION 1: OVERALL STATISTICS ---
      csvContent += 'OVERALL STATISTICS\n';
      csvContent += 'Metric,Value\n';
      csvContent += 'Total Candidates,' + stats.totalCandidates + '\n';
      csvContent += 'Selected,' + stats.selected + '\n';
      csvContent += 'Rejected,' + stats.rejected + '\n';
      csvContent += 'In Process,' + stats.inProcess + '\n';
      csvContent += 'Selection Rate,' + stats.selectionRate + '%\n';
      csvContent += 'Average Match Score,' + stats.avgMatch + '%\n\n';

      // --- SECTION 2: TOP SKILLS ---
      csvContent += 'TOP SKILLS\n';
      csvContent += 'Rank,Skill,Count\n';
      stats.topSkills.slice(0, 10).forEach(function(skill, index) {
        csvContent += (index + 1) + ',"' + skill[0] + '",' + skill[1] + '\n';
      });
      csvContent += '\n';

      // --- SECTION 3: EDUCATION DISTRIBUTION ---
      csvContent += 'EDUCATION DISTRIBUTION\n';
      csvContent += 'Education,Count\n';
      stats.educationDistribution.forEach(function(edu) {
        csvContent += '"' + edu[0] + '",' + edu[1] + '\n';
      });
      csvContent += '\n';

      // --- SECTION 4: HIRING STAGES ---
      csvContent += 'HIRING STAGES\n';
      csvContent += 'Stage,Count\n';
      stats.hiringStages.forEach(function(stage) {
        csvContent += '"' + stage[0] + '",' + stage[1] + '\n';
      });
      csvContent += '\n';

      // --- SECTION 5: TOP PERFORMING CANDIDATES ---
      csvContent += 'TOP PERFORMING CANDIDATES\n';
      csvContent += 'Category,Name,Score\n';
      if (stats.highestMatch) {
        csvContent += 'Highest Match,"' + stats.highestMatch.name + '","' + stats.highestMatch.match_score + '%"\n';
      }
      if (stats.lowestMatch) {
        csvContent += 'Lowest Match,"' + stats.lowestMatch.name + '","' + stats.lowestMatch.match_score + '%"\n';
      }
      csvContent += '\n';

      // --- FOOTER ---
      csvContent += 'Report generated by Recruitment Analytics System\n';
      csvContent += 'Confidential - For internal use only\n';

      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'Candidates_Report_' + new Date().toISOString().split('T')[0] + '.csv';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      alert('✅ Candidates Report CSV downloaded successfully!');
    } catch (error) {
      console.error('CSV Error:', error);
      alert('❌ Failed to generate CSV. Please try again.');
    }
  };

  // ============================================================
  // DOCX GENERATION
  // ============================================================

  const downloadDOCX = async function() {
    try {
      const stats = getCandidateStats();
      const now = new Date();
      const dateStr = now.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });

      const children = [];

      // Title
      children.push(
        new Paragraph({
          children: [new TextRun({ text: 'CANDIDATES REPORT', bold: true, size: 36, color: '1A365D' })],
          alignment: AlignmentType.CENTER,
          spacing: { after: 200 }
        })
      );

      // Date
      children.push(
        new Paragraph({
          children: [new TextRun({ text: 'Generated: ' + dateStr, size: 20, color: '666666' })],
          alignment: AlignmentType.CENTER,
          spacing: { after: 200 }
        })
      );

      // Section 1: Overall Statistics
      children.push(
        new Paragraph({
          children: [new TextRun({ text: '1. OVERALL STATISTICS', bold: true, size: 24, color: '1A365D' })],
          spacing: { before: 200, after: 150 }
        })
      );

      const statsRows = [
        ['Total Candidates', stats.totalCandidates],
        ['Selected', stats.selected],
        ['Rejected', stats.rejected],
        ['In Process', stats.inProcess],
        ['Selection Rate', stats.selectionRate + '%'],
        ['Average Match Score', stats.avgMatch + '%']
      ];

      const statsTableRows = [
        new TableRow({
          children: [
            new TableCell({ children: [new Paragraph({ children: [new TextRun({ text: 'Metric', bold: true, color: 'FFFFFF' })], alignment: AlignmentType.CENTER })], shading: { fill: '1A365D' } }),
            new TableCell({ children: [new Paragraph({ children: [new TextRun({ text: 'Value', bold: true, color: 'FFFFFF' })], alignment: AlignmentType.CENTER })], shading: { fill: '1A365D' } })
          ]
        })
      ];

      statsRows.forEach(function(row, index) {
        statsTableRows.push(
          new TableRow({
            children: [
              new TableCell({ children: [new Paragraph({ children: [new TextRun({ text: row[0] })] })] }),
              new TableCell({ children: [new Paragraph({ children: [new TextRun({ text: String(row[1]) })] })] })
            ],
            shading: { fill: index % 2 === 0 ? 'F0F5FA' : 'FFFFFF' }
          })
        );
      });

      children.push(
        new Table({
          rows: statsTableRows,
          width: { size: 100, type: WidthType.PERCENTAGE }
        })
      );

      // Section 2: Top Skills
      if (stats.topSkills.length > 0) {
        children.push(
          new Paragraph({
            children: [new TextRun({ text: '2. TOP SKILLS', bold: true, size: 24, color: '1A365D' })],
            spacing: { before: 300, after: 150 }
          })
        );

        const skillsRows = [
          new TableRow({
            children: [
              new TableCell({ children: [new Paragraph({ children: [new TextRun({ text: 'Rank', bold: true, color: 'FFFFFF' })], alignment: AlignmentType.CENTER })], shading: { fill: '1A365D' } }),
              new TableCell({ children: [new Paragraph({ children: [new TextRun({ text: 'Skill', bold: true, color: 'FFFFFF' })], alignment: AlignmentType.CENTER })], shading: { fill: '1A365D' } }),
              new TableCell({ children: [new Paragraph({ children: [new TextRun({ text: 'Count', bold: true, color: 'FFFFFF' })], alignment: AlignmentType.CENTER })], shading: { fill: '1A365D' } })
            ]
          })
        ];

        stats.topSkills.slice(0, 10).forEach(function(skill, index) {
          skillsRows.push(
            new TableRow({
              children: [
                new TableCell({ children: [new Paragraph({ children: [new TextRun({ text: String(index + 1) })] })] }),
                new TableCell({ children: [new Paragraph({ children: [new TextRun({ text: skill[0] })] })] }),
                new TableCell({ children: [new Paragraph({ children: [new TextRun({ text: String(skill[1]) })] })] })
              ],
              shading: { fill: index % 2 === 0 ? 'F0F5FA' : 'FFFFFF' }
            })
          );
        });

        children.push(
          new Table({
            rows: skillsRows,
            width: { size: 100, type: WidthType.PERCENTAGE }
          })
        );
      }

      // Section 3: Education Distribution
      if (stats.educationDistribution.length > 0) {
        children.push(
          new Paragraph({
            children: [new TextRun({ text: '3. EDUCATION DISTRIBUTION', bold: true, size: 24, color: '1A365D' })],
            spacing: { before: 300, after: 150 }
          })
        );

        const eduRows = [
          new TableRow({
            children: [
              new TableCell({ children: [new Paragraph({ children: [new TextRun({ text: 'Education', bold: true, color: 'FFFFFF' })], alignment: AlignmentType.CENTER })], shading: { fill: '1A365D' } }),
              new TableCell({ children: [new Paragraph({ children: [new TextRun({ text: 'Count', bold: true, color: 'FFFFFF' })], alignment: AlignmentType.CENTER })], shading: { fill: '1A365D' } })
            ]
          })
        ];

        stats.educationDistribution.forEach(function(edu, index) {
          eduRows.push(
            new TableRow({
              children: [
                new TableCell({ children: [new Paragraph({ children: [new TextRun({ text: edu[0] })] })] }),
                new TableCell({ children: [new Paragraph({ children: [new TextRun({ text: String(edu[1]) })] })] })
              ],
              shading: { fill: index % 2 === 0 ? 'F0F5FA' : 'FFFFFF' }
            })
          );
        });

        children.push(
          new Table({
            rows: eduRows,
            width: { size: 100, type: WidthType.PERCENTAGE }
          })
        );
      }

      // Section 4: Hiring Stages
      if (stats.hiringStages.length > 0) {
        children.push(
          new Paragraph({
            children: [new TextRun({ text: '4. HIRING STAGES', bold: true, size: 24, color: '1A365D' })],
            spacing: { before: 300, after: 150 }
          })
        );

        const stageRows = [
          new TableRow({
            children: [
              new TableCell({ children: [new Paragraph({ children: [new TextRun({ text: 'Stage', bold: true, color: 'FFFFFF' })], alignment: AlignmentType.CENTER })], shading: { fill: '1A365D' } }),
              new TableCell({ children: [new Paragraph({ children: [new TextRun({ text: 'Count', bold: true, color: 'FFFFFF' })], alignment: AlignmentType.CENTER })], shading: { fill: '1A365D' } })
            ]
          })
        ];

        stats.hiringStages.forEach(function(stage, index) {
          stageRows.push(
            new TableRow({
              children: [
                new TableCell({ children: [new Paragraph({ children: [new TextRun({ text: stage[0] })] })] }),
                new TableCell({ children: [new Paragraph({ children: [new TextRun({ text: String(stage[1]) })] })] })
              ],
              shading: { fill: index % 2 === 0 ? 'F0F5FA' : 'FFFFFF' }
            })
          );
        });

        children.push(
          new Table({
            rows: stageRows,
            width: { size: 100, type: WidthType.PERCENTAGE }
          })
        );
      }

      // Footer
      children.push(
        new Paragraph({
          children: [new TextRun({ text: 'Recruitment Analytics System - Confidential Report', size: 16, color: '999999', italics: true })],
          alignment: AlignmentType.CENTER,
          spacing: { before: 300 }
        })
      );

      const doc = new Document({
        sections: [{
          properties: { page: { margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } } },
          children: children
        }]
      });

      const blob = await Packer.toBlob(doc);
      const filename = 'Candidates_Report_' + new Date().toISOString().split('T')[0] + '.docx';
      saveAs(blob, filename);
      alert('✅ Candidates Report DOCX downloaded successfully!');
    } catch (error) {
      console.error('DOCX Error:', error);
      alert('❌ Failed to generate DOCX. Please try again.');
    }
  };

  // ============================================================
  // EXCEL GENERATION
  // ============================================================

  const downloadExcel = function() {
    try {
      const stats = getCandidateStats();
      const now = new Date();
      const dateStr = now.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });

      const wb = XLSX.utils.book_new();

      // Sheet 1: Overview
      const overviewData = [
        ['CANDIDATES REPORT'],
        ['Generated: ' + dateStr],
        ['Report ID: ' + currentReportId()],
        [],
        ['OVERALL STATISTICS'],
        ['Metric', 'Value'],
        ['Total Candidates', stats.totalCandidates],
        ['Selected', stats.selected],
        ['Rejected', stats.rejected],
        ['In Process', stats.inProcess],
        ['Selection Rate', stats.selectionRate + '%'],
        ['Average Match Score', stats.avgMatch + '%'],
        [],
        ['TOP PERFORMING CANDIDATES'],
        ['Category', 'Name', 'Score'],
        ['Highest Match', stats.highestMatch ? stats.highestMatch.name : 'N/A', stats.highestMatch ? stats.highestMatch.match_score + '%' : 'N/A'],
        ['Lowest Match', stats.lowestMatch ? stats.lowestMatch.name : 'N/A', stats.lowestMatch ? stats.lowestMatch.match_score + '%' : 'N/A']
      ];
      const ws1 = XLSX.utils.aoa_to_sheet(overviewData);
      XLSX.utils.book_append_sheet(wb, ws1, 'Overview');

      // Sheet 2: Skills
      const skillsData = [
        ['TOP SKILLS'],
        [],
        ['Rank', 'Skill', 'Count']
      ];
      stats.topSkills.slice(0, 10).forEach(function(skill, index) {
        skillsData.push([index + 1, skill[0], skill[1]]);
      });
      const ws2 = XLSX.utils.aoa_to_sheet(skillsData);
      XLSX.utils.book_append_sheet(wb, ws2, 'Skills');

      // Sheet 3: Education
      const eduData = [
        ['EDUCATION DISTRIBUTION'],
        [],
        ['Education', 'Count']
      ];
      stats.educationDistribution.forEach(function(edu) {
        eduData.push([edu[0], edu[1]]);
      });
      const ws3 = XLSX.utils.aoa_to_sheet(eduData);
      XLSX.utils.book_append_sheet(wb, ws3, 'Education');

      // Sheet 4: Hiring Stages
      const stageData = [
        ['HIRING STAGES'],
        [],
        ['Stage', 'Count']
      ];
      stats.hiringStages.forEach(function(stage) {
        stageData.push([stage[0], stage[1]]);
      });
      const ws4 = XLSX.utils.aoa_to_sheet(stageData);
      XLSX.utils.book_append_sheet(wb, ws4, 'Hiring Stages');

      const wbout = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });
      const blob = new Blob([wbout], { type: 'application/octet-stream' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'Candidates_Report_' + new Date().toISOString().split('T')[0] + '.xlsx';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      alert('✅ Candidates Report Excel downloaded successfully!');
    } catch (error) {
      console.error('Excel Error:', error);
      alert('❌ Failed to generate Excel. Please try again.');
    }
  };

  // ============================================================
  // EMAIL GENERATION
  // ============================================================

  const sendEmailReport = async function(email) {
    try {
      // First generate PDF
      const stats = getCandidateStats();
      const doc = new jsPDF('p', 'mm', 'a4');
      const pageWidth = doc.internal.pageSize.getWidth();
      const margin = 20;
      let y = 25;

      // Simple PDF generation for email
      doc.setFontSize(24);
      doc.setFont('helvetica', 'bold');
      doc.setTextColor(26, 54, 93);
      doc.text('CANDIDATES REPORT', pageWidth / 2, y, { align: 'center' });
      y += 10;

      doc.setDrawColor(26, 54, 93);
      doc.setLineWidth(0.8);
      doc.line(margin, y, pageWidth - margin, y);
      y += 12;

      doc.setFontSize(10);
      doc.setFont('helvetica', 'normal');
      doc.setTextColor(100, 100, 100);
      const now = new Date();
      const dateStr = now.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
      doc.text('Generated: ' + dateStr, margin, y);
      y += 6;
      doc.text('Total Candidates: ' + stats.totalCandidates, margin, y);
      y += 14;

      doc.setFontSize(16);
      doc.setFont('helvetica', 'bold');
      doc.setTextColor(26, 54, 93);
      doc.text('1. Overall Statistics', margin, y);
      y += 10;

      const statsData = [
        ['Total Candidates', stats.totalCandidates],
        ['Selected', stats.selected],
        ['Rejected', stats.rejected],
        ['In Process', stats.inProcess],
        ['Selection Rate', stats.selectionRate + '%'],
        ['Average Match Score', stats.avgMatch + '%']
      ];

      doc.setFillColor(26, 54, 93);
      doc.rect(margin, y - 4, 70, 9, 'F');
      doc.rect(margin + 70, y - 4, 60, 9, 'F');
      doc.setFont('helvetica', 'bold');
      doc.setTextColor(255, 255, 255);
      doc.text('Metric', margin + 2, y + 3);
      doc.text('Value', margin + 72, y + 3);
      y += 8;

      doc.setFont('helvetica', 'normal');
      statsData.forEach(function(row, index) {
        if (y > 270) { doc.addPage(); y = 20; }
        if (index % 2 === 0) {
          doc.setFillColor(240, 245, 250);
          doc.rect(margin, y - 3, 130, 7, 'F');
        }
        doc.setTextColor(50, 50, 50);
        doc.text(row[0], margin + 2, y + 2);
        doc.text(String(row[1]), margin + 72, y + 2);
        y += 8;
      });

      const pdfBlob = doc.output('blob');
      const reader = new FileReader();

      return new Promise(function(resolve, reject) {
        reader.onload = async function() {
          try {
            const base64Data = reader.result.split(',')[1];

            const response = await apiPost('/api/report/email', {
              recipient: email,
              subject: 'Candidates Report - ' + new Date().toISOString().split('T')[0],
              message: 'Please find attached the Candidates Report generated on ' + new Date().toLocaleString() + '.',
              attachment: {
                filename: 'Candidates_Report_' + new Date().toISOString().split('T')[0] + '.pdf',
                content: base64Data,
                mimeType: 'application/pdf'
              }
            });

            if (response.ok) {
              alert('✅ Candidates Report sent successfully to ' + email + '!');
              resolve();
            } else {
              throw new Error(response.data?.error || 'Failed to send email');
            }
          } catch (error) {
            console.error('Email send error:', error);
            alert('❌ Failed to send email. Please check your email settings.');
            reject(error);
          }
        };
        reader.onerror = reject;
        reader.readAsDataURL(pdfBlob);
      });
    } catch (error) {
      console.error('Email Error:', error);
      alert('❌ Failed to prepare email. Please try again.');
    }
  };

  // ============================================================
  // MAIN HANDLER
  // ============================================================

  const handleGenerateReport = async function() {
    if (selectedFormat === 'email' && !recipientEmail) {
      alert('⚠️ Please enter a recipient email address');
      return;
    }

    setIsGenerating(true);

    try {
      await issueReportId('talent', selectedFormat);
      if (selectedFormat === 'pdf') {
        downloadPDF();
      } else if (selectedFormat === 'docx') {
        await downloadDOCX();
      } else if (selectedFormat === 'csv') {
        downloadCSV();
      } else if (selectedFormat === 'excel') {
        downloadExcel();
      } else if (selectedFormat === 'email') {
        await sendEmailReport(recipientEmail);
      } else {
        alert('Unsupported format');
      }

      setShowModal(false);
      setSelectedFormat('pdf');
      setRecipientEmail('');
      setShowEmailInput(false);

    } catch (error) {
      console.error('Report generation error:', error);
      alert('❌ Failed to generate report. Please try again.');
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
            ' Generate Candidates Report'
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
        React.createElement('div', { style: { padding: '20px' } },
          React.createElement('p', {
            style: {
              color: '#1e293b',
              fontSize: '14px',
              fontWeight: '500',
              margin: '0 0 16px 0'
            }
          }, 'Choose your report format'),
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
            React.createElement('span', null, `Report covers the ${filtered.length} candidate${filtered.length === 1 ? '' : 's'} currently shown: Statistics, Skills, Education, Hiring Stages`)
          )
        ),
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

  const stageOptions = [...new Set(decorated.map(row => row.stage.label))].sort();
  const roleOptions = [...new Set(decorated.flatMap(row => [row.role.primary, ...row.role.others]).filter(Boolean))].sort();
  const locationOptions = [...new Set(decorated.map(row => row.location).filter(Boolean))].sort();
  const clientOptions = [...new Set(decorated.map(row => row.c.client_name).filter(Boolean))].sort();
  const quickActive = Object.values(quickFilters).some(Boolean);
  const anyFilterActive = quickActive || activeFilterCount > 0 || Boolean(searchTerm);
  const clearAllFilters = () => {
    setQuickFilters(EMPTY_QUICK_FILTERS);
    setSearchTerm('');
    clearFilters();
    setPage(1);
  };
  const setQuick = (key, value) => { setQuickFilters(prev => ({ ...prev, [key]: value })); setPage(1); };
  const inProcessCount = candidates.filter(c => candidateMatchesSelection(c, 'selected') && !c.on_hold).length;
  const firstEntry = rows.length ? (currentPage - 1) * pageSize + 1 : 0;
  const lastEntry = Math.min(currentPage * pageSize, rows.length);
  const pageAllSelected = pageRows.length > 0 && pageRows.every(row => selectedIds.has(row.c.id));

  const QUICK_FILTERS = [
    ['stage', 'Stage', stageOptions],
    ['role', 'Role', roleOptions],
    ['location', 'Location', locationOptions],
    ['client', 'Client', clientOptions],
  ];

  return (
    <Layout>
      <div className="tl-page">
        <section className="tl-card">
          <header className="tl-header">
            <div className="tl-heading">
              <h1>Talent</h1>
              <p className="tl-summary">
                <span className="tl-dot" aria-hidden="true"></span>
                {inProcessCount} in process · {candidates.length} candidate{candidates.length === 1 ? '' : 's'}
              </p>
            </div>
            <div className="tl-toolbar">
              <label className="tl-search">
                <i className="fas fa-search" aria-hidden="true"></i>
                <input type="search" className="tl-input" placeholder="Search candidates..." value={searchTerm} aria-label="Search candidates"
                  onChange={(e) => { setSearchTerm(e.target.value); setPage(1); }} />
              </label>
              <div className="candidates-filters-anchor tl-filters-anchor" ref={filterAnchorRef}>
                <button type="button" className="tl-btn tl-btn-outline" aria-expanded={panelOpen} onClick={() => setPanelOpen(o => !o)}>
                  <i className="fas fa-filter" aria-hidden="true"></i> Filters
                  {activeFilterCount > 0 && <span className="tl-badge">{activeFilterCount}</span>}
                </button>
                {panelOpen && (
                  <div className="candidates-filters-panel">
                    <div className="candidates-filters-grid">
                      <label>Role Category
                        <select value={filterCategory} onChange={(e) => setFilterCategory(e.target.value)}>
                          <option value="">All Role Categories</option>
                          {roleCategories.map(category => (
                            <option key={category} value={category}>{ROLE_CATEGORY_FILTER_LABELS[category] || category}</option>
                          ))}
                        </select>
                      </label>
                      <label>Client
                        <select value={draftFilters.clientId} onChange={(e) => handleClientChange(e.target.value)}>
                          <option value="">All Clients</option>
                          {clients.map(cl => <option key={cl.id} value={cl.id}>{cl.name}</option>)}
                        </select>
                      </label>
                      <label>Requirement
                        <select value={draftFilters.projectId} onChange={(e) => handleProjectChange(e.target.value)} disabled={!draftFilters.clientId}>
                          <option value="">{draftFilters.clientId ? 'All Requirements' : 'Select a client first'}</option>
                          {projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                        </select>
                      </label>
                      <label>Status
                        <select value={draftFilters.status} onChange={(e) => setDraftFilters(f => ({ ...f, status: e.target.value }))}>
                          <option value="">All Status</option>
                          <option value="selected">Selected</option>
                          <option value="rejected">Rejected</option>
                          <option value="on hold">On Hold</option>
                          <option value="in process">In Process</option>
                        </select>
                      </label>
                      <label>Stage
                        <select value={draftFilters.stageId} onChange={(e) => setDraftFilters(f => ({ ...f, stageId: e.target.value }))}>
                          <option value="">All Stages</option>
                          {stageGroups.map(group => (
                            <optgroup key={group.project_id ?? 'none'} label={group.project_name || 'Unassigned'}>
                              {group.steps.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
                            </optgroup>
                          ))}
                        </select>
                      </label>
                    </div>
                    <div className="candidates-filters-dates">
                      <fieldset>
                        <legend>Upload Date</legend>
                        <input type="date" value={draftFilters.uploadFrom} onChange={(e) => setDraftFilters(f => ({ ...f, uploadFrom: e.target.value }))} />
                        <span>to</span>
                        <input type="date" value={draftFilters.uploadTo} onChange={(e) => setDraftFilters(f => ({ ...f, uploadTo: e.target.value }))} />
                      </fieldset>
                      <fieldset>
                        <legend>Interview Date</legend>
                        <input type="date" value={draftFilters.interviewFrom} onChange={(e) => setDraftFilters(f => ({ ...f, interviewFrom: e.target.value }))} />
                        <span>to</span>
                        <input type="date" value={draftFilters.interviewTo} onChange={(e) => setDraftFilters(f => ({ ...f, interviewTo: e.target.value }))} />
                      </fieldset>
                    </div>
                    {dateError && <div className="candidates-filters-error">{dateError}</div>}
                    <div className="candidates-filters-actions">
                      <button type="button" className="btn btn-success jd-table-btn" disabled={applying} onClick={() => { setPage(1); applyFilters(); }}>
                        {applying ? 'Applying...' : 'Apply'}
                      </button>
                      <button type="button" className="btn btn-secondary jd-table-btn" onClick={clearFilters}>Clear</button>
                    </div>
                  </div>
                )}
              </div>
              <KebabMenu label="More actions" className="tl-page-menu" items={[
                { label: 'Generate report', icon: 'fa-file-export', onSelect: () => setShowModal(true), disabled: candidates.length === 0 },
                { label: visibleSelected.length ? `Delete selected (${visibleSelected.length})` : 'Delete selected', icon: 'fa-trash',
                  danger: true, disabled: !visibleSelected.length || bulkDeleting, title: visibleSelected.length ? undefined : 'Select candidates first', onSelect: deleteSelected },
                { label: 'Clear selection', icon: 'fa-square-minus', disabled: !selectedIds.size, onSelect: () => setSelectedIds(new Set()) },
              ]} />
              <Link to="/analyze" className="tl-btn tl-btn-primary">
                <i className="fas fa-plus" aria-hidden="true"></i> Add Candidate
              </Link>
            </div>
          </header>

          {listError && <div className="analyze-submit-error" role="alert">{listError}</div>}

          {candidates.length > 0 ? (
            <>
              <div className="tl-quick-filters" role="group" aria-label="Quick filters">
                {QUICK_FILTERS.map(([key, label, options]) => (
                  <label key={key} className={`tl-select${quickFilters[key] ? ' is-active' : ''}`}>
                    <select className="tl-input" value={quickFilters[key]} onChange={(e) => setQuick(key, e.target.value)} aria-label={label}>
                      <option value="">{label}</option>
                      {options.map(option => <option key={option} value={option}>{option}</option>)}
                    </select>
                    <i className="fas fa-chevron-down" aria-hidden="true"></i>
                  </label>
                ))}
                {anyFilterActive && (
                  <button type="button" className="tl-clear" onClick={clearAllFilters}>
                    <i className="fas fa-rotate-left" aria-hidden="true"></i> Clear Filters
                  </button>
                )}
                {visibleSelected.length > 0 && (
                  <span className="tl-selection-bar" role="status">
                    {visibleSelected.length} selected
                    <button type="button" className="tl-btn tl-btn-danger" disabled={bulkDeleting} onClick={deleteSelected}>
                      {bulkDeleting ? 'Removing…' : <><i className="fas fa-trash" aria-hidden="true"></i> Delete</>}
                    </button>
                  </span>
                )}
              </div>

              {rows.length === 0 ? (
                <div className="candidates-empty-state">
                  <i className="fas fa-filter-circle-xmark empty-state-icon"></i>
                  <h2 className="empty-state-title">No Matching Candidates</h2>
                  <p className="empty-state-subtitle">Try adjusting or clearing your filters.</p>
                </div>
              ) : (
                <div className="tl-table-wrap">
                  <table className="tl-table">
                    <thead>
                      <tr>
                        <th className="tl-col-select">
                          <input type="checkbox" checked={pageAllSelected} aria-label="Select all candidates on this page"
                            onChange={() => setSelectedIds(prev => {
                              const next = new Set(prev);
                              pageRows.forEach(row => (pageAllSelected ? next.delete(row.c.id) : next.add(row.c.id)));
                              return next;
                            })} />
                        </th>
                        <th>Candidate Name</th>
                        <th>Role</th>
                        <th>Stage</th>
                        <th>AI Score</th>
                        <th aria-sort={sortDir === 'desc' ? 'descending' : 'ascending'}>
                          <button type="button" className="tl-sort" onClick={() => setSortDir(dir => (dir === 'desc' ? 'asc' : 'desc'))}
                            title={sortDir === 'desc' ? 'Newest first' : 'Oldest first'}>
                            Applied On <i className={`fas fa-arrow-${sortDir === 'desc' ? 'down-wide-short' : 'up-short-wide'}`} aria-hidden="true"></i>
                          </button>
                        </th>
                        <th>Location</th>
                        <th className="tl-col-actions">Actions</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pageRows.map(({ c, stage, role, location, score, applied }) => (
                        <tr key={c.id} className={selectedIds.has(c.id) ? 'is-selected' : ''}>
                          <td className="tl-col-select">
                            <input type="checkbox" checked={selectedIds.has(c.id)} onChange={() => toggleSelect(c.id)} aria-label={`Select ${c.name}`} />
                          </td>
                          <td data-label="Candidate">
                            <Link to={`/talent/${c.id}`} className="tl-person">
                              <span className="tl-avatar" aria-hidden="true">{initialsOf(c.name)}</span>
                              <span className="tl-name">{c.name || c.email || 'Unnamed candidate'}</span>
                            </Link>
                          </td>
                          <td data-label="Role">
                            <span className="tl-role">{role.primary || '—'}</span>
                            {role.others.length > 0 && <small className="tl-more" title={role.others.join(', ')}>+{role.others.length} more</small>}
                          </td>
                          <td data-label="Stage"><span className={`tl-stage tl-stage-${stage.kind}`} title={stage.title}>{stage.label}</span></td>
                          <td data-label="AI Score">
                            {score === null ? <span className="tl-muted">—</span> : <span className={`tl-score tl-score-${scoreTone(score)}`}>{score}%</span>}
                          </td>
                          <td data-label="Applied On" className="tl-date">{formatApplied(applied)}</td>
                          <td data-label="Location">
                            {location ? <span className="tl-location"><i className="fas fa-location-dot" aria-hidden="true"></i>{location}</span> : <span className="tl-muted">—</span>}
                          </td>
                          <td className="tl-col-actions">
                            <KebabMenu label={`Actions for ${c.name || 'candidate'}`} items={[
                              { label: 'All Details', icon: 'fa-eye', to: `/talent/${c.id}` },
                              { label: 'Send Assessment', icon: 'fa-clipboard-question', onSelect: () => setAssessmentCandidate(c) },
                              { label: 'Remove', icon: 'fa-user-xmark', danger: true, disabled: bulkDeleting, onSelect: () => deleteRows([c]) },
                            ]} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}

              {rows.length > 0 && (
                <footer className="tl-footer">
                  <div className="tl-rows">
                    <span>Showing</span>
                    <label className="tl-select tl-select-sm">
                      <select className="tl-input" value={pageSize} aria-label="Rows per page" onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }}>
                        {PAGE_SIZES.map(size => <option key={size} value={size}>{size}</option>)}
                      </select>
                      <i className="fas fa-chevron-down" aria-hidden="true"></i>
                    </label>
                    <span>Rows</span>
                    <span className="tl-divider" aria-hidden="true"></span>
                    <span>{firstEntry}-{lastEntry} of {rows.length} Entries</span>
                  </div>
                  <nav className="tl-pages" aria-label="Pagination">
                    <span>Page</span>
                    <button type="button" className="tl-page-btn" aria-label="Previous page" disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)}>
                      <i className="fas fa-chevron-left" aria-hidden="true"></i>
                    </button>
                    {pageWindow(currentPage, pageCount).map(number => (
                      <button key={number} type="button" className={`tl-page-btn${number === currentPage ? ' is-current' : ''}`}
                        aria-current={number === currentPage ? 'page' : undefined} onClick={() => setPage(number)}>{number}</button>
                    ))}
                    <button type="button" className="tl-page-btn" aria-label="Next page" disabled={currentPage === pageCount} onClick={() => setPage(currentPage + 1)}>
                      <i className="fas fa-chevron-right" aria-hidden="true"></i>
                    </button>
                    <span>of {pageCount}</span>
                  </nav>
                </footer>
              )}
            </>
          ) : listError ? (
            <div className="candidates-empty-state">
              <i className="fas fa-triangle-exclamation empty-state-icon"></i>
              <h2 className="empty-state-title">Could Not Load Candidates</h2>
              <p className="empty-state-subtitle">{listError}</p>
            </div>
          ) : (
            <div className="candidates-empty-state">
              <i className="fas fa-inbox empty-state-icon"></i>
              <h2 className="empty-state-title">No Candidates Yet</h2>
              <p className="empty-state-subtitle">Upload resumes to get started</p>
              <Link to="/analyze" className="btn btn-primary"><i className="fas fa-upload"></i> Upload Resumes</Link>
            </div>
          )}
        </section>

        {ReportModal()}
        {assessmentCandidate && (
          <SendAssessmentModal candidate={assessmentCandidate} onClose={() => setAssessmentCandidate(null)} />
        )}

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

export default Candidates;
