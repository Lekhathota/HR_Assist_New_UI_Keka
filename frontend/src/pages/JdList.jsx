import React, { useState, useEffect, useCallback, useMemo, useRef } from 'react';
import { Link } from 'react-router-dom';
import Layout from '../components/Layout.jsx';
import { SkeletonBlock, toast, useConfirm } from '../components/EnterpriseFeedback.jsx';
import { JD_CACHE_KEY, apiGet, readSessionCache, writeSessionCache, apiPost } from '../api.js';
import { formatJdDate } from '../utils/jdSections.js';
import '../styles/jd_list.css';
import '../styles/jd_list_extra.css';
import '../styles/jobs_module.css';
import jsPDF from 'jspdf';
import { Document, Packer, Paragraph, TextRun } from 'docx';
import { saveAs } from 'file-saver';
import * as XLSX from 'xlsx';
import { currentReportId, issueReportId } from '../utils/reportId.js';
import { useRoleCategories } from '../utils/useRoleCategories.js';


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

function JdList() {
  const [jds, setJds] = useState(() => readSessionCache(JD_CACHE_KEY) || []);
  const roleCategories = useRoleCategories(jds.map(jd => jd.job_category));
  const [loading, setLoading] = useState(() => !readSessionCache(JD_CACHE_KEY));
  const [error, setError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [filterStatus, setFilterStatus] = useState('active');
  const [filterCategory, setFilterCategory] = useState('');
  const [filterClient, setFilterClient] = useState('');
  const [filterDepartment, setFilterDepartment] = useState('');
  const [filterLocation, setFilterLocation] = useState('');
  const [showMoreFilters, setShowMoreFilters] = useState(false);
  const [page, setPage] = useState(1);

  const confirm = useConfirm();
  const [selectedIds, setSelectedIds] = useState(() => new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);
  const toggleSelect = (id) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };
  const toggleSelectAll = (rows) => {
    setSelectedIds(prev => (prev.size === rows.length && rows.length > 0 ? new Set() : new Set(rows.map(jd => jd.id))));
  };
  const deleteSelected = async () => {
    if (!selectedIds.size) return;
    const approved = await confirm({
      title: 'Remove job descriptions',
      message: `Remove ${selectedIds.size} selected job description(s)? Related comparisons may be removed. This cannot be undone.`,
      confirmLabel: 'Remove JDs',
      icon: 'fas fa-trash-alt',
      danger: true,
    });
    if (!approved) return;
    setBulkDeleting(true);
    try {
      const ids = Array.from(selectedIds);
      const results = await Promise.all(ids.map(id => apiPost(`/api/jds/${id}/delete`, { confirmed: true })));
      const removedIds = new Set(ids.filter((id, i) => results[i].ok && results[i].data?.success));
      const failedCount = ids.length - removedIds.size;
      setJds(prev => {
        const next = prev.filter(jd => !removedIds.has(jd.id));
        writeSessionCache(JD_CACHE_KEY, next);
        return next;
      });
      setSelectedIds(new Set());
      toast(failedCount
        ? { type: 'error', message: `${removedIds.size} removed, ${failedCount} could not be removed.` }
        : { type: 'success', message: `${removedIds.size} job description(s) removed.` });
    } finally {
      setBulkDeleting(false);
    }
  };

  // --- REPORT MODAL STATE ---
  const [showModal, setShowModal] = useState(false);
  const [selectedFormat, setSelectedFormat] = useState('pdf');
  const [recipientEmail, setRecipientEmail] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [showEmailInput, setShowEmailInput] = useState(false);

  const loadJds = useCallback(() => {
    const cached = readSessionCache(JD_CACHE_KEY);
    if (cached) {
      setJds(Array.isArray(cached) ? cached : []);
      setLoading(false);
    }

    setLoading(!cached);
    setError('');
    apiGet('/api/jds')
      .then(data => {
        const rows = Array.isArray(data) ? data : [];
        setJds(rows);
        writeSessionCache(JD_CACHE_KEY, rows);
      })
      .catch((err) => setError(err.message || 'Could not load job descriptions.'))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadJds();
  }, [loadJds]);

  useEffect(() => {
    const refresh = () => loadJds();
    window.addEventListener('focus', refresh);
    window.addEventListener('pageshow', refresh);
    return () => {
      window.removeEventListener('focus', refresh);
      window.removeEventListener('pageshow', refresh);
    };
  }, [loadJds]);

  // Filter options come only from values present in the loaded JDs.
  const distinctValues = useCallback(
    key => [...new Set(jds.map(jd => jd[key]).filter(Boolean))].sort((a, b) => String(a).localeCompare(String(b))),
    [jds],
  );
  const clientOptions = useMemo(() => distinctValues('client_name'), [distinctValues]);
  const departmentOptions = useMemo(() => distinctValues('department'), [distinctValues]);
  const locationOptions = useMemo(() => distinctValues('location'), [distinctValues]);

  const filteredJds = jds.filter(jd => {
    const haystack = [
      jd.title,
      jd.client_name,
      jd.department,
      jd.job_category,
      ...((jd.skills || []).map(skill => typeof skill === 'string' ? skill : '')),
    ].join(' ').toLowerCase();
    const matchSearch = haystack.includes(searchTerm.toLowerCase());
    const matchStatus = !filterStatus || (jd.status || '').toLowerCase() === filterStatus;
    const matchCategory = !filterCategory || jd.job_category === filterCategory;
    const matchClient = !filterClient || jd.client_name === filterClient;
    const matchDepartment = !filterDepartment || jd.department === filterDepartment;
    const matchLocation = !filterLocation || jd.location === filterLocation;
    return matchSearch && matchStatus && matchCategory && matchClient && matchDepartment && matchLocation;
  });

  const PAGE_SIZE = 10;
  const pageCount = Math.max(1, Math.ceil(filteredJds.length / PAGE_SIZE));
  const currentPage = Math.min(page, pageCount);
  const pageStart = (currentPage - 1) * PAGE_SIZE;
  const pageJds = filteredJds.slice(pageStart, pageStart + PAGE_SIZE);

  useEffect(() => {
    setPage(1);
  }, [searchTerm, filterStatus, filterCategory, filterClient, filterDepartment, filterLocation]);

  const STATUS_HEADINGS = { '': 'All Jobs', active: 'Active Jobs', closed: 'Closed Jobs', inactive: 'Inactive Jobs' };
  const activeFilterCount = [filterStatus !== 'active', filterCategory, filterClient, filterDepartment, filterLocation]
    .filter(Boolean).length;
  const filterMenuRef = useRef(null);

  useEffect(() => {
    if (!showMoreFilters) return undefined;
    const handlePointer = (event) => {
      if (filterMenuRef.current && !filterMenuRef.current.contains(event.target)) setShowMoreFilters(false);
    };
    const handleKey = (event) => { if (event.key === 'Escape') setShowMoreFilters(false); };
    document.addEventListener('mousedown', handlePointer);
    document.addEventListener('keydown', handleKey);
    return () => {
      document.removeEventListener('mousedown', handlePointer);
      document.removeEventListener('keydown', handleKey);
    };
  }, [showMoreFilters]);
  const clearFilters = () => {
    setSearchTerm('');
    setFilterStatus('active');
    setFilterCategory('');
    setFilterClient('');
    setFilterDepartment('');
    setFilterLocation('');
  };

  // ============================================================
  // JOBS REPORT FUNCTIONS
  // ============================================================

  const getJobStats = () => {
    const totalJobs = jds.length;
    const activeJobs = jds.filter(j => j.status === 'Active').length;
    const closedJobs = jds.filter(j => j.status === 'Closed' || j.status === 'Inactive').length;
    
    let totalResumes = 0;
    let totalSelected = 0;
    let totalRejected = 0;
    let avgMatchTotal = 0;
    let avgMatchCount = 0;
    let topJob = null;
    let hardestJob = null;
    let skillsMap = {};
    let hiringTrends = [];

    jds.forEach(j => {
      totalResumes += j.total_resumes || 0;
      totalSelected += j.selected_count || 0;
      totalRejected += j.rejected_count || 0;
      
      if (j.avg_match_score) {
        avgMatchTotal += j.avg_match_score;
        avgMatchCount++;
      }

      if (j.total_resumes > 0) {
        const rate = ((j.selected_count || 0) / j.total_resumes) * 100;
        if (!topJob || rate > topJob.rate) {
          topJob = { title: j.title, rate: Math.round(rate) };
        }
        if (!hardestJob || rate < hardestJob.rate) {
          hardestJob = { title: j.title, rate: Math.round(rate) };
        }
      }

      if (j.skills && Array.isArray(j.skills)) {
        j.skills.forEach(skill => {
          skillsMap[skill] = (skillsMap[skill] || 0) + 1;
        });
      }
    });

    const sortedSkills = Object.entries(skillsMap).sort((a, b) => b[1] - a[1]);
    const mostRequestedSkills = sortedSkills.slice(0, 5);

    const deptMap = {};
    jds.forEach(j => {
      const dept = j.department || 'Uncategorized';
      if (!deptMap[dept]) deptMap[dept] = { total: 0, active: 0 };
      deptMap[dept].total++;
      if (j.status === 'Active') deptMap[dept].active++;
    });
    hiringTrends = Object.entries(deptMap).map(([name, data]) => ({
      name,
      total: data.total,
      active: data.active
    }));

    return {
      totalJobs,
      activeJobs,
      closedJobs,
      totalResumes,
      totalSelected,
      totalRejected,
      avgMatch: avgMatchCount > 0 ? Math.round(avgMatchTotal / avgMatchCount) : 0,
      topJob,
      hardestJob,
      mostRequestedSkills,
      hiringTrends,
      overallSelectionRate: totalResumes > 0 ? Math.round((totalSelected / totalResumes) * 100) : 0
    };
  };

  const buildJobsReportText = () => {
    const stats = getJobStats();
    const now = new Date();
    const dateStr = now.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
    
    let report = '';
    
    report += '='.repeat(60) + '\n';
    report += '     JOBS REPORT\n';
    report += '='.repeat(60) + '\n\n';
    report += 'Generated: ' + dateStr + '\n';
    report += 'Report ID: ' + currentReportId() + '\n\n';
    
    report += '-'.repeat(60) + '\n';
    report += 'OVERALL JOB STATISTICS\n';
    report += '-'.repeat(60) + '\n';
    report += '  Total Jobs              : ' + stats.totalJobs + '\n';
    report += '  Active Jobs             : ' + stats.activeJobs + '\n';
    report += '  Closed Jobs             : ' + stats.closedJobs + '\n';
    report += '  Total Resumes           : ' + stats.totalResumes + '\n';
    report += '  Total Selected          : ' + stats.totalSelected + '\n';
    report += '  Total Rejected          : ' + stats.totalRejected + '\n';
    report += '  Overall Selection Rate  : ' + stats.overallSelectionRate + '%\n';
    report += '  Average Match Score     : ' + stats.avgMatch + '%\n\n';
    
    report += '-'.repeat(60) + '\n';
    report += 'TOP PERFORMING JOBS\n';
    report += '-'.repeat(60) + '\n';
    if (stats.topJob) {
      report += '  Top Performing JD       : ' + stats.topJob.title + ' (' + stats.topJob.rate + '% selection)\n';
    }
    if (stats.hardestJob) {
      report += '  Hardest JD to Fill      : ' + stats.hardestJob.title + ' (' + stats.hardestJob.rate + '% selection)\n';
    }
    report += '\n';
    
    report += '-'.repeat(60) + '\n';
    report += 'MOST REQUESTED SKILLS\n';
    report += '-'.repeat(60) + '\n';
    if (stats.mostRequestedSkills.length > 0) {
      stats.mostRequestedSkills.forEach(function(skill, index) {
        report += '  ' + (index + 1) + '. ' + skill[0] + ' : ' + skill[1] + ' jobs\n';
      });
    } else {
      report += '  No skills data available\n';
    }
    report += '\n';
    
    report += '-'.repeat(60) + '\n';
    report += 'HIRING TRENDS BY DEPARTMENT\n';
    report += '-'.repeat(60) + '\n';
    if (stats.hiringTrends.length > 0) {
      stats.hiringTrends.forEach(function(dept) {
        report += '  ' + dept.name + ' : ' + dept.total + ' jobs (' + dept.active + ' active)\n';
      });
    } else {
      report += '  No department data available\n';
    }
    report += '\n';
    
    report += '-'.repeat(60) + '\n';
    report += 'RECRUITER OBSERVATIONS\n';
    report += '-'.repeat(60) + '\n';
    report += '  Total Active Jobs       : ' + stats.activeJobs + '\n';
    report += '  Jobs with High Demand   : ' + (stats.mostRequestedSkills.length > 0 ? stats.mostRequestedSkills[0][0] : 'N/A') + '\n';
    report += '  Average Applications    : ' + (stats.totalJobs > 0 ? Math.round(stats.totalResumes / stats.totalJobs) : 0) + ' per job\n\n';
    
    report += '='.repeat(60) + '\n';
    report += '  Report generated by Recruitment Analytics System\n';
    report += '  (c) ' + new Date().getFullYear() + ' All Rights Reserved\n';
    report += '='.repeat(60);
    
    return report;
  };

  const generateJobsCSV = () => {
    const stats = getJobStats();
    const now = new Date();
    const dateStr = now.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
    
    let csvContent = '';
    
    csvContent += 'JOBS REPORT\n';
    csvContent += 'Generated: ' + dateStr + '\n';
    csvContent += 'Report ID: ' + currentReportId() + '\n\n';
    
    csvContent += '========================\n';
    csvContent += 'OVERALL JOB STATISTICS\n';
    csvContent += '========================\n';
    csvContent += 'Metric,Value\n';
    csvContent += 'Total Jobs,' + stats.totalJobs + '\n';
    csvContent += 'Active Jobs,' + stats.activeJobs + '\n';
    csvContent += 'Closed Jobs,' + stats.closedJobs + '\n';
    csvContent += 'Total Resumes,' + stats.totalResumes + '\n';
    csvContent += 'Total Selected,' + stats.totalSelected + '\n';
    csvContent += 'Total Rejected,' + stats.totalRejected + '\n';
    csvContent += 'Overall Selection Rate,' + stats.overallSelectionRate + '%\n';
    csvContent += 'Average Match Score,' + stats.avgMatch + '%\n\n';
    
    csvContent += '========================\n';
    csvContent += 'TOP PERFORMING JOBS\n';
    csvContent += '========================\n';
    csvContent += 'Category,Job Title,Rate\n';
    if (stats.topJob) csvContent += 'Top Performing,' + stats.topJob.title + ',' + stats.topJob.rate + '%\n';
    if (stats.hardestJob) csvContent += 'Hardest to Fill,' + stats.hardestJob.title + ',' + stats.hardestJob.rate + '%\n\n';
    
    csvContent += '========================\n';
    csvContent += 'MOST REQUESTED SKILLS\n';
    csvContent += '========================\n';
    csvContent += 'Rank,Skill,Jobs\n';
    stats.mostRequestedSkills.forEach(function(skill, index) {
      csvContent += (index + 1) + ',' + skill[0] + ',' + skill[1] + '\n';
    });
    csvContent += '\n';
    
    csvContent += '========================\n';
    csvContent += 'HIRING TRENDS BY DEPARTMENT\n';
    csvContent += '========================\n';
    csvContent += 'Department,Total Jobs,Active Jobs\n';
    stats.hiringTrends.forEach(function(dept) {
      csvContent += dept.name + ',' + dept.total + ',' + dept.active + '\n';
    });
    
    return csvContent;
  };

  const generateJobsExcel = () => {
    const stats = getJobStats();
    const now = new Date();
    const dateStr = now.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
    
    const wb = XLSX.utils.book_new();
    
    const overviewData = [
      ['JOBS REPORT'],
      ['Generated: ' + dateStr],
      ['Report ID: ' + currentReportId()],
      [],
      ['OVERALL JOB STATISTICS'],
      ['Metric', 'Value'],
      ['Total Jobs', stats.totalJobs],
      ['Active Jobs', stats.activeJobs],
      ['Closed Jobs', stats.closedJobs],
      ['Total Resumes', stats.totalResumes],
      ['Total Selected', stats.totalSelected],
      ['Total Rejected', stats.totalRejected],
      ['Overall Selection Rate', stats.overallSelectionRate + '%'],
      ['Average Match Score', stats.avgMatch + '%']
    ];
    const ws1 = XLSX.utils.aoa_to_sheet(overviewData);
    XLSX.utils.book_append_sheet(wb, ws1, 'Overview');
    
    const topJobsData = [
      ['TOP PERFORMING JOBS'],
      [],
      ['Category', 'Job Title', 'Rate'],
      ['Top Performing', stats.topJob ? stats.topJob.title : 'N/A', stats.topJob ? stats.topJob.rate + '%' : 'N/A'],
      ['Hardest to Fill', stats.hardestJob ? stats.hardestJob.title : 'N/A', stats.hardestJob ? stats.hardestJob.rate + '%' : 'N/A']
    ];
    const ws2 = XLSX.utils.aoa_to_sheet(topJobsData);
    XLSX.utils.book_append_sheet(wb, ws2, 'Top Jobs');
    
    const skillsData = [
      ['MOST REQUESTED SKILLS'],
      [],
      ['Rank', 'Skill', 'Jobs']
    ];
    stats.mostRequestedSkills.forEach(function(skill, index) {
      skillsData.push([index + 1, skill[0], skill[1]]);
    });
    const ws3 = XLSX.utils.aoa_to_sheet(skillsData);
    XLSX.utils.book_append_sheet(wb, ws3, 'Skills');
    
    const deptData = [
      ['HIRING TRENDS BY DEPARTMENT'],
      [],
      ['Department', 'Total Jobs', 'Active Jobs']
    ];
    stats.hiringTrends.forEach(function(dept) {
      deptData.push([dept.name, dept.total, dept.active]);
    });
    const ws4 = XLSX.utils.aoa_to_sheet(deptData);
    XLSX.utils.book_append_sheet(wb, ws4, 'Departments');
    
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
      
      if (line.indexOf('JOBS REPORT') !== -1) {
        doc.setFontSize(18);
        doc.setFont('helvetica', 'bold');
        doc.setTextColor(26, 54, 93);
      } else if (line.indexOf('===') !== -1 || line.indexOf('---') !== -1) {
        doc.setFontSize(10);
        doc.setFont('helvetica', 'normal');
        doc.setTextColor(113, 128, 150);
      } else if (line.indexOf('•') !== -1) {
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
      
      const x = line.indexOf('•') !== -1 ? margin + 5 : margin;
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
    
    const filename = 'Jobs_Report_' + new Date().toISOString().split('T')[0] + '.pdf';
    doc.save(filename);
    alert('✅ Jobs Report PDF downloaded successfully!');
    
  } catch (error) {
    console.error('PDF Error:', error);
    alert('❌ Failed to generate PDF. Please try again.');
  }
};

  const downloadDOCX = async (reportText) => {
    try {
      const lines = reportText.split('\n');
      const children = [];
      
      lines.forEach(function(line) {
        if (line.trim() === '') {
          children.push(new Paragraph({ spacing: { after: 100 } }));
          return;
        }
        const isBold = line.indexOf(':') !== -1 || 
                      line.indexOf('JOBS REPORT') !== -1 || 
                      line.indexOf('===') !== -1 ||
                      line.indexOf('---') !== -1;
        const isLarge = line.indexOf('JOBS REPORT') !== -1;
        
        children.push(
          new Paragraph({
            children: [new TextRun({ text: line, bold: isBold, size: isLarge ? 32 : 20, font: 'Arial' })],
            spacing: { before: 80, after: 80 }
          })
        );
      });
      
      const doc = new Document({
        sections: [{
          properties: { page: { margin: { top: 1440, bottom: 1440, left: 1440, right: 1440 } } },
          children: children
        }]
      });
      
      const blob = await Packer.toBlob(doc);
      const filename = 'Jobs_Report_' + new Date().toISOString().split('T')[0] + '.docx';
      saveAs(blob, filename);
      alert('✅ Jobs Report DOCX downloaded successfully!');
    } catch (error) {
      console.error('DOCX Error:', error);
      alert('❌ Failed to generate DOCX. Please try again.');
    }
  };

  const downloadCSV = function() {
    try {
      const csvContent = generateJobsCSV();
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'Jobs_Report_' + new Date().toISOString().split('T')[0] + '.csv';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      alert('✅ Jobs Report CSV downloaded successfully!');
    } catch (error) {
      console.error('CSV Error:', error);
      alert('❌ Failed to generate CSV. Please try again.');
    }
  };

  const downloadExcel = function() {
    try {
      const wb = generateJobsExcel();
      const wbout = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });
      const blob = new Blob([wbout], { type: 'application/octet-stream' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'Jobs_Report_' + new Date().toISOString().split('T')[0] + '.xlsx';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      alert('✅ Jobs Report Excel downloaded successfully!');
    } catch (error) {
      console.error('Excel Error:', error);
      alert('❌ Failed to generate Excel. Please try again.');
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
        
        if (line.indexOf('JOBS REPORT') !== -1) {
          doc.setFontSize(18);
          doc.setFont('helvetica', 'bold');
          doc.setTextColor(26, 54, 93);
        } else if (line.indexOf('===') !== -1 || line.indexOf('---') !== -1) {
          doc.setFontSize(10);
          doc.setFont('helvetica', 'normal');
          doc.setTextColor(113, 128, 150);
        } else if (line.indexOf('•') !== -1) {
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
        
        const x = line.indexOf('•') !== -1 ? margin + 5 : margin;
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
              subject: 'Jobs Report - ' + new Date().toISOString().split('T')[0],
              message: 'Please find attached the Jobs Report generated on ' + new Date().toLocaleString() + '.',
              attachment: {
                filename: 'Jobs_Report_' + new Date().toISOString().split('T')[0] + '.pdf',
                content: base64Data,
                mimeType: 'application/pdf'
              }
            });
            
            if (response.ok) {
              alert('✅ Jobs Report sent successfully to ' + email + '!');
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

  const handleGenerateReport = async function() {
    if (selectedFormat === 'email' && !recipientEmail) {
      alert('⚠️ Please enter a recipient email address');
      return;
    }

    setIsGenerating(true);
    
    try {
      await issueReportId('jobs', selectedFormat);
      const reportText = buildJobsReportText();
      
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
            ' Generate Jobs Report'
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
            React.createElement('span', null, 'Report includes: Job Statistics, Top Jobs, Skills, Department Trends')
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
  return (
    <Layout>
      <div className="jobs-page">
        <header className="jobs-head">
          <div className="jobs-head-text">
            <h1 className="jobs-head-title">Job Descriptions</h1>
            <p className="jobs-head-subtitle">Manage and view all job descriptions.</p>
          </div>
          <div className="jobs-head-actions">
            <button type="button" className="btn btn-secondary jobs-btn" onClick={() => setShowModal(true)}>
              <i className="fas fa-file-export"></i> Generate Report
            </button>
            <Link to="/jobs/create" className="btn btn-primary jobs-btn"><i className="fas fa-plus"></i> Create JD</Link>
          </div>
        </header>

        {loading ? (
          <SkeletonBlock variant="detail" count={4} />
        ) : error ? (
          <div className="jd-empty-state">
            <i className="fas fa-exclamation-circle jd-empty-icon"></i>
            <h2 className="jd-empty-title">Could Not Load Job Descriptions</h2>
            <p className="jd-empty-text">{error}</p>
          </div>
        ) : jds.length > 0 ? (
          <section className="jobs-panel">
            <div className="jobs-toolbar">
              <label className="jobs-search">
                <i className="fas fa-search" aria-hidden="true"></i>
                <input
                  type="search"
                  placeholder="Search jobs..."
                  aria-label="Search jobs by title, client, department, category, or skill"
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                />
              </label>
              <div className="jobs-filter" ref={filterMenuRef}>
                <button
                  type="button"
                  className={`jobs-more-btn${showMoreFilters || activeFilterCount ? ' is-active' : ''}`}
                  aria-expanded={showMoreFilters}
                  aria-controls="jobs-filter-panel"
                  onClick={() => setShowMoreFilters(v => !v)}
                >
                  <i className="fas fa-sliders-h" aria-hidden="true"></i> Filters
                  {activeFilterCount > 0 && <span className="jobs-filter-count">{activeFilterCount}</span>}
                </button>
                {showMoreFilters && (
                  <div id="jobs-filter-panel" className="jobs-filter-panel" role="dialog" aria-label="Job filters">
                    <label className="jobs-filter-field">
                      <span>Status</span>
                      <select className="jobs-select" value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
                        <option value="">All Status</option>
                        <option value="active">Active</option>
                        <option value="closed">Closed</option>
                        <option value="inactive">Inactive</option>
                      </select>
                    </label>
                    <label className="jobs-filter-field">
                      <span>Category</span>
                      <select className="jobs-select" value={filterCategory} onChange={(e) => setFilterCategory(e.target.value)}>
                        <option value="">All Categories</option>
                        {roleCategories.map(category => (
                          <option key={category} value={category}>{ROLE_CATEGORY_FILTER_LABELS[category] || category}</option>
                        ))}
                      </select>
                    </label>
                    <label className="jobs-filter-field">
                      <span>Client</span>
                      <select className="jobs-select" value={filterClient} onChange={(e) => setFilterClient(e.target.value)}>
                        <option value="">All Clients</option>
                        {clientOptions.map(client => <option key={client} value={client}>{client}</option>)}
                      </select>
                    </label>
                    <label className="jobs-filter-field">
                      <span>Department</span>
                      <select className="jobs-select" value={filterDepartment} onChange={(e) => setFilterDepartment(e.target.value)}>
                        <option value="">All Departments</option>
                        {departmentOptions.map(value => <option key={value} value={value}>{value}</option>)}
                      </select>
                    </label>
                    <label className="jobs-filter-field">
                      <span>Location</span>
                      <select className="jobs-select" value={filterLocation} onChange={(e) => setFilterLocation(e.target.value)}>
                        <option value="">All Locations</option>
                        {locationOptions.map(value => <option key={value} value={value}>{value}</option>)}
                      </select>
                    </label>
                    <div className="jobs-filter-actions">
                      <button type="button" className="jobs-clear-btn" onClick={clearFilters}>Clear filters</button>
                      <button type="button" className="btn btn-primary jobs-btn" onClick={() => setShowMoreFilters(false)}>Apply</button>
                    </div>
                  </div>
                )}
              </div>
            </div>

            <div className="jobs-section-head">
              <h2 className="jobs-section-title">{STATUS_HEADINGS[filterStatus] || 'Jobs'}</h2>
              <span className="jobs-count">{filteredJds.length}</span>
              {selectedIds.size > 0 && (
                <span className="jobs-bulk-bar">
                  <span>{selectedIds.size} selected</span>
                  <button type="button" className="btn btn-danger jobs-bulk-delete-btn" disabled={bulkDeleting} onClick={deleteSelected}>
                    {bulkDeleting ? 'Removing...' : <><i className="fas fa-trash"></i> Delete Selected</>}
                  </button>
                </span>
              )}
            </div>

            {filteredJds.length === 0 ? (
              <div className="jobs-empty">
                <p>No job descriptions match these filters.</p>
                <button type="button" className="jobs-clear-btn" onClick={clearFilters}>Clear filters</button>
              </div>
            ) : (
              <>
                <div className="jobs-table-wrap">
                  <table className="jobs-table">
                    <thead>
                      <tr>
                        <th className="jobs-select-col">
                          <input type="checkbox" checked={pageJds.length > 0 && selectedIds.size === pageJds.length}
                            onChange={() => toggleSelectAll(pageJds)} aria-label="Select all job descriptions" />
                        </th>
                        <th>Job Title</th><th>Job ID</th><th>Category</th><th>Client</th><th className="jobs-num">Posts</th>
                        <th>Date Posted</th><th>Status</th><th className="jobs-action-col">Action</th>
                      </tr>
                    </thead>
                    <tbody>
                      {pageJds.map(jd => {
                        const secondary = [jd.location, jd.experience].filter(Boolean).join(' · ');
                        return (
                          <tr key={jd.id}>
                            <td className="jobs-select-col">
                              <input type="checkbox" checked={selectedIds.has(jd.id)}
                                onChange={() => toggleSelect(jd.id)} aria-label={`Select ${jd.title}`} />
                            </td>
                            <td className="jobs-title-cell">
                              <Link to={`/jobs/${jd.id}`} className="jobs-title-link">{jd.title}</Link>
                              {secondary && <span className="jobs-title-meta">{secondary}</span>}
                            </td>
                            <td className="jobs-nowrap">{jd.job_code || '—'}</td>
                            <td><span className="jobs-pill">{jd.job_category || 'Others'}</span></td>
                            <td>{jd.client_name || '—'}</td>
                            <td className="jobs-num">{jd.required_candidate_count ?? '—'}</td>
                            <td className="jobs-nowrap">{formatJdDate(jd.created_date || (jd.created || '').slice(0, 10)) || '—'}</td>
                            <td>
                              <span className={`jobs-status jobs-status-${String(jd.status || '').toLowerCase()}`}>{jd.status}</span>
                            </td>
                            <td className="jobs-action-col">
                              <Link to={`/jobs/${jd.id}`} className="jobs-view-link" aria-label={`View details for ${jd.title}`}>
                                View<span className="jobs-view-extra"> Details</span>
                              </Link>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                <footer className="jobs-footer">
                  <span>
                    Showing {pageStart + 1} to {pageStart + pageJds.length} of {filteredJds.length} results
                  </span>
                  {pageCount > 1 && (
                    <nav className="jobs-pager" aria-label="Pagination">
                      <button type="button" aria-label="Previous page" disabled={currentPage === 1} onClick={() => setPage(currentPage - 1)}>
                        <i className="fas fa-chevron-left"></i>
                      </button>
                      {Array.from({ length: pageCount }, (_, i) => i + 1).map(n => (
                        <button
                          key={n}
                          type="button"
                          className={n === currentPage ? 'is-current' : ''}
                          aria-current={n === currentPage ? 'page' : undefined}
                          onClick={() => setPage(n)}
                        >
                          {n}
                        </button>
                      ))}
                      <button type="button" aria-label="Next page" disabled={currentPage === pageCount} onClick={() => setPage(currentPage + 1)}>
                        <i className="fas fa-chevron-right"></i>
                      </button>
                    </nav>
                  )}
                </footer>
              </>
            )}
          </section>
        ) : (
          <div className="jd-empty-state">
            <i className="fas fa-inbox jd-empty-icon"></i>
            <h2 className="jd-empty-title">No Job Descriptions Yet</h2>
            <p className="jd-empty-text">Create your first JD to get started</p>
            <Link to="/jobs/create" className="btn btn-primary"><i className="fas fa-plus"></i> Create Your First JD</Link>
          </div>
        )}

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

export default JdList;
