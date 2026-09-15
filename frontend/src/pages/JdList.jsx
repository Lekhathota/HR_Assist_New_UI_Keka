import React, { useState, useEffect, useCallback } from 'react';
import { Link } from 'react-router-dom';
import Layout from '../components/Layout.jsx';
import { SkeletonBlock } from '../components/EnterpriseFeedback.jsx';
import { JD_CACHE_KEY, apiGet, readSessionCache, writeSessionCache, apiPost } from '../api.js';
import '../styles/jd_list.css';
import '../styles/jd_list_extra.css';
import jsPDF from 'jspdf';
import { Document, Packer, Paragraph, TextRun } from 'docx';
import { saveAs } from 'file-saver';
import * as XLSX from 'xlsx';

const ROLE_CATEGORIES = [
  'Developer',
  'Tester',
  'PMO',
  'PM',
  'TL',
  'Business Analyst',
  'DevOps / Cloud',
  'Data',
  'Support',
  'Others',
];

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
  const [loading, setLoading] = useState(() => !readSessionCache(JD_CACHE_KEY));
  const [error, setError] = useState('');
  const [searchTerm, setSearchTerm] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  const [filterCategory, setFilterCategory] = useState('');

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
    return matchSearch && matchStatus && matchCategory;
  });

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
    report += 'Report ID: RPT-' + now.getFullYear() + String(now.getMonth()+1).padStart(2,'0') + String(now.getDate()).padStart(2,'0') + '-' + String(Math.floor(Math.random()*10000)).padStart(4,'0') + '\n\n';
    
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
    csvContent += 'Report ID: RPT-' + now.getFullYear() + String(now.getMonth()+1).padStart(2,'0') + String(now.getDate()).padStart(2,'0') + '-' + String(Math.floor(Math.random()*10000)).padStart(4,'0') + '\n\n';
    
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
      ['Report ID: RPT-' + now.getFullYear() + String(now.getMonth()+1).padStart(2,'0') + String(now.getDate()).padStart(2,'0') + '-' + String(Math.floor(Math.random()*10000)).padStart(4,'0')],
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
              background: isGenerating ? '#94a3b8' : '#4f46e5',
              color: 'white',
              boxShadow: isGenerating ? 'none' : '0 4px 14px rgba(79,70,229,0.4)',
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
      <div className="jd-list-container">
        <div className="jd-list-topbar">
          <h1><i className="fas fa-file-alt"></i> Job Descriptions</h1>
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            <Link to="/jobs/create" className="btn btn-primary"><i className="fas fa-plus"></i> Create JD</Link>
          </div>
        </div>

        {loading ? (
          <SkeletonBlock variant="cards" count={4} />
        ) : error ? (
          <div className="jd-empty-state">
            <i className="fas fa-exclamation-circle jd-empty-icon"></i>
            <h2 className="jd-empty-title">Could Not Load Job Descriptions</h2>
            <p className="jd-empty-text">{error}</p>
          </div>
        ) : jds.length > 0 ? (
          <>
            <div className="jd-filter-bar">
              <input
                type="text"
                placeholder="Search JDs by title, client, department, category, or skill..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
              />
              <select value={filterStatus} onChange={(e) => setFilterStatus(e.target.value)}>
                <option value="">All Status</option>
                <option value="active">Active</option>
                <option value="closed">Closed</option>
                <option value="inactive">Inactive</option>
              </select>
              <select value={filterCategory} onChange={(e) => setFilterCategory(e.target.value)}>
                <option value="">All Job Categories</option>
                {ROLE_CATEGORIES.map(category => (
                  <option key={category} value={category}>{ROLE_CATEGORY_FILTER_LABELS[category] || category}</option>
                ))}
              </select>
            </div>

            {filteredJds.length === 0 ? (
              <div className="jd-empty-state jd-filter-empty-state">
                <i className="fas fa-search jd-empty-icon"></i>
                <h2 className="jd-empty-title">No Job Descriptions Match</h2>
                <p className="jd-empty-text">Adjust the search or filters to see more JDs.</p>
              </div>
            ) : (
              <>
            <div className="grid grid-4 jd-cards-grid">
              {filteredJds.map(jd => (
                <div key={jd.id} className="jd-card">
                  <h3 className="jd-card-title">{jd.title}</h3>
                  <div className="jd-card-meta-row">
                    <div className="jd-card-meta-info">
                      <span className="jd-category-pill"><i className="fas fa-layer-group"></i> {jd.job_category || 'Others'}</span>
                      <span><i className="fas fa-building"></i> {jd.department}</span>
                      <span><i className="fas fa-handshake"></i> {jd.client_name || 'ShimentoX'}</span>
                      <span><i className="fas fa-calendar-alt"></i> {jd.created_date || (jd.created || '').slice(0, 10)}</span>
                    </div>
                    <span className={`badge ${jd.status === 'Active' ? 'badge-success' : 'badge-danger'}`}>{jd.status}</span>
                  </div>

                  <div className="jd-card-stats">
                    <div className="jd-card-stats-row">
                      {[['Total Resumes', jd.total_resumes, 'blue'], ['Selected', jd.selected_count, 'green'], ['Rejected', jd.rejected_count, 'red']].map(([label, val, color]) => (
                        <div key={label}>
                          <div className="jd-stat-label">{label}</div>
                          <div className={`jd-stat-value-${color}`}>{val}</div>
                        </div>
                      ))}
                    </div>
                    {jd.total_resumes > 0 && (
                      <div className="jd-card-progress-wrap">
                        <div className="jd-card-progress-label">Screening Progress</div>
                        <div className="progress">
                          <div className="progress-bar" style={{ width: `${Math.round(((jd.selected_count + jd.rejected_count) / jd.total_resumes) * 100)}%` }}></div>
                        </div>
                      </div>
                    )}
                  </div>

                  <div className="jd-card-actions-row jd-card-actions-bottom">
                    <Link to={`/jobs/${jd.id}`} className="btn btn-primary jd-card-btn">
                      <i className="fas fa-eye"></i> Details
                    </Link>
                    <Link to="/analyze" className="btn btn-secondary jd-card-btn">
                      <i className="fas fa-exchange-alt"></i> Compare
                    </Link>
                  </div>
                </div>
              ))}
            </div>

            <h2 className="jd-section-title"><i className="fas fa-list"></i> Detailed View</h2>
            <div className="table-container">
              <table>
                <thead>
                  <tr>
                    <th>Job Title</th><th>Job Category</th><th>Client</th><th>Department</th><th>Created</th>
                    <th>Total Resumes</th><th>Selected</th><th>Rejected</th>
                    <th>Status</th><th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredJds.map(jd => (
                    <tr key={jd.id}>
                      <td><strong>{jd.title}</strong></td>
                      <td><span className="jd-category-pill table-pill">{jd.job_category || 'Others'}</span></td>
                      <td>{jd.client_name || 'ShimentoX'}</td>
                      <td>{jd.department}</td>
                      <td>{jd.created_date || (jd.created || '').slice(0, 10)}</td>
                      <td>{jd.total_resumes}</td>
                      <td><span className="badge badge-success">{jd.selected_count}</span></td>
                      <td><span className="badge badge-danger">{jd.rejected_count}</span></td>
                      <td><span className={`badge ${jd.status === 'Active' ? 'badge-success' : 'badge-danger'}`}>{jd.status}</span></td>
                      <td>
                        <div className="jd-table-actions">
                          <Link to={`/jobs/${jd.id}`} className="btn btn-primary jd-table-btn">View</Link>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
              </>
            )}
          </>
        ) : (
          <div className="jd-empty-state">
            <i className="fas fa-inbox jd-empty-icon"></i>
            <h2 className="jd-empty-title">No Job Descriptions Yet</h2>
            <p className="jd-empty-text">Create your first JD to get started</p>
            <Link to="/jobs/create" className="btn btn-primary"><i className="fas fa-plus"></i> Create Your First JD</Link>
          </div>
        )}

        {/* BUTTON AT THE BOTTOM */}
        <div style={{ 
          marginTop: '40px', 
          display: 'flex', 
          justifyContent: 'center',
          padding: '20px 0',
          borderTop: '1px solid #e2e8f0'
        }}>
          <button 
            className="btn btn-primary reports-generate-btn"
            onClick={() => setShowModal(true)}
            style={{ 
              padding: '16px 48px', 
              fontSize: '18px',
              borderRadius: '14px',
              background: 'linear-gradient(135deg, #4f46e5 0%, #4338ca 100%)',
              color: 'white',
              border: 'none',
              boxShadow: '0 4px 16px rgba(79, 70, 229, 0.35)',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
              fontWeight: '600'
            }}
          >
            <i className="fas fa-plus-circle"></i> Generate Jobs Report
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

export default JdList;
