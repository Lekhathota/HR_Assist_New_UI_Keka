import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Layout from '../components/Layout.jsx';
import { toast, useConfirm, SkeletonBlock } from '../components/EnterpriseFeedback.jsx';
import { apiGet, apiPost } from '../api.js';
import '../styles/profile.css';
import '../styles/candidates.css';
import jsPDF from 'jspdf';
import 'jspdf-autotable';
import { Document, Packer, Paragraph, TextRun } from 'docx';
import { saveAs } from 'file-saver';
import * as XLSX from 'xlsx';

function formatJdUploadDateTime(value) {
  if (!value) return { date: '—', time: '' };
  const raw = String(value).trim();
  const parsed = new Date(raw.includes('T') ? raw : raw.replace(' ', 'T'));
  if (Number.isNaN(parsed.getTime())) {
    return { date: raw.slice(0, 10) || '—', time: '' };
  }
  const day = String(parsed.getDate()).padStart(2, '0');
  const month = String(parsed.getMonth() + 1).padStart(2, '0');
  const year = parsed.getFullYear();
  const hours = String(parsed.getHours()).padStart(2, '0');
  const minutes = String(parsed.getMinutes()).padStart(2, '0');
  return { date: `${day}/${month}/${year}`, time: `${hours}:${minutes}` };
}

function SummaryList({ title, items, emptyText }) {
  const values = (items || []).filter(Boolean);
  return (
    <div>
      <h4>{title}</h4>
      {values.length ? (
        <ul className="profile-ai-bullet-list">
          {values.map(item => <li key={item}>{item}</li>)}
        </ul>
      ) : <em>{emptyText}</em>}
    </div>
  );
}

function CandidateProfile() {
  const { candidateId } = useParams();
  const navigate = useNavigate();
  const confirm = useConfirm();
  const [candidate, setCandidate] = useState(null);
  const [timeline, setTimeline] = useState([]);
  const [deleting, setDeleting] = useState(false);

  // --- REPORT MODAL STATE ---
  const [showModal, setShowModal] = useState(false);
  const [selectedFormat, setSelectedFormat] = useState('pdf');
  const [recipientEmail, setRecipientEmail] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [showEmailInput, setShowEmailInput] = useState(false);

  useEffect(() => {
    apiGet(`/api/candidates/${candidateId}`)
      .then(data => {
        const row = data.candidate || null;
        setCandidate(row);
        setTimeline(data.timeline || []);
      })
      .catch(() => {});
  }, [candidateId]);

  const handleRemove = async () => {
    if (!candidate) return;
    const approved = await confirm({
      title: 'Remove candidate',
      message: `Remove candidate "${candidate.name}" from the repository? This cannot be undone.`,
      confirmLabel: 'Remove Candidate',
      icon: 'fas fa-user-times',
      danger: true,
    });
    if (!approved) return;
    setDeleting(true);
    try {
      const { ok, data } = await apiPost(`/api/candidates/${candidateId}/delete`, { confirmed: true });
      if (ok && data.success) {
        toast({ type: 'success', message: 'Candidate removed.' });
        navigate('/talent');
      } else {
        toast({ type: 'error', message: data.error || 'Could not remove candidate.' });
      }
    } catch {
      toast({ type: 'error', message: 'Remove failed. Please try again.' });
    } finally {
      setDeleting(false);
    }
  };

  // ============================================================
  // BUILD REPORT TEXT (for DOCX and Email)
  // ============================================================

  const buildCandidateReportText = () => {
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
    
    const sd = candidate?.structured_data || {};
    const aiSummary = candidate?.ai_summary || {};
    const totalExperience = Number(sd.total_experience_years || 0);
    const experienceLabel = totalExperience < 1 ? 'No experience' : `${totalExperience} year${totalExperience === 1 ? '' : 's'}`;
    const matchedSkills = aiSummary.matched_skills || aiSummary.strengths || [];
    const missingSkills = aiSummary.missing_skills || aiSummary.risks || [];
    
    let report = '';
    
    report += '='.repeat(60) + '\n';
    report += '     CANDIDATE EVALUATION REPORT\n';
    report += '='.repeat(60) + '\n\n';
    report += '  Generated on  : ' + dateStr + ' at ' + timeStr + '\n';
    report += '  Report ID     : RPT-' + now.getFullYear() + String(now.getMonth()+1).padStart(2,'0') + String(now.getDate()).padStart(2,'0') + '-' + String(Math.floor(Math.random()*10000)).padStart(4,'0') + '\n\n';
    
    report += '-'.repeat(60) + '\n';
    report += 'CANDIDATE INFORMATION\n';
    report += '-'.repeat(60) + '\n';
    report += '  Name                : ' + (candidate?.name || 'N/A') + '\n';
    report += '  Email               : ' + (candidate?.email || 'N/A') + '\n';
    report += '  Phone               : ' + (candidate?.phone || sd.phone || 'N/A') + '\n';
    report += '  Experience          : ' + experienceLabel + '\n';
    report += '  Location            : ' + (candidate?.location || sd.location || 'N/A') + '\n';
    report += '  Status              : ' + (candidate?.status || 'N/A') + '\n';
    report += '  Hiring Stage        : ' + (candidate?.hiring_stage || 'N/A') + '\n\n';
    
    report += '-'.repeat(60) + '\n';
    report += 'SCREENING SUMMARY\n';
    report += '-'.repeat(60) + '\n';
    report += '  Match Score         : ' + (candidate?.match_score || 0) + '%\n';
    report += '  Recommendation      : ' + (aiSummary.recommendation || 'Review screening evidence') + '\n';
    report += '  Overall Rating      : ' + (candidate?.match_score > 80 ? 'Excellent' : candidate?.match_score > 60 ? 'Good' : 'Needs Review') + '\n\n';
    
    const skills = sd.skills || candidate?.skills || [];
    if (skills.length > 0) {
      report += '-'.repeat(60) + '\n';
      report += 'SKILLS\n';
      report += '-'.repeat(60) + '\n';
      skills.forEach(function(skill) {
        report += '  * ' + skill + '\n';
      });
      report += '\n';
    }
    
    if (matchedSkills.length > 0 || missingSkills.length > 0) {
      report += '-'.repeat(60) + '\n';
      report += 'STRENGTHS & MISSING SKILLS\n';
      report += '-'.repeat(60) + '\n';
      if (matchedSkills.length > 0) {
        report += '  Strengths       : ' + matchedSkills.join(', ') + '\n';
      }
      if (missingSkills.length > 0) {
        report += '  Missing Skills  : ' + missingSkills.join(', ') + '\n';
      }
      report += '\n';
    }
    
    if (sd.education) {
      report += '-'.repeat(60) + '\n';
      report += 'EDUCATION\n';
      report += '-'.repeat(60) + '\n';
      report += '  Degree              : ' + (sd.education.degree || 'N/A') + '\n';
      report += '  Field of Study      : ' + (sd.education.field || 'N/A') + '\n';
      report += '  Institution         : ' + (sd.education.institution || 'N/A') + '\n';
      report += '  Graduation Year     : ' + (sd.education.graduation_year || 'N/A') + '\n\n';
    }
    
    const workExp = sd.work_experience || [];
    if (workExp.length > 0) {
      report += '-'.repeat(60) + '\n';
      report += 'WORK EXPERIENCE\n';
      report += '-'.repeat(60) + '\n';
      workExp.forEach(function(exp, index) {
        report += '  ' + (index + 1) + '. ' + (exp.company || 'N/A') + '\n';
        report += '     Role    : ' + (exp.position || exp.designation || 'N/A') + '\n';
        report += '     Duration: ' + (exp.start_date || '') + (exp.end_date ? ' - ' + exp.end_date : '') + '\n';
      });
      report += '\n';
    }
    
    if (candidate?.jd_history && candidate.jd_history.length > 0) {
      report += '-'.repeat(60) + '\n';
      report += 'APPLIED ROLES\n';
      report += '-'.repeat(60) + '\n';
      candidate.jd_history.forEach(function(jd, index) {
        report += '  ' + (index + 1) + '. ' + jd.jd_title + ' : ' + (jd.match_score || 0) + '% match\n';
      });
      report += '\n';
    }
    
    report += '-'.repeat(60) + '\n';
    report += 'AI CANDIDATE SUMMARY\n';
    report += '-'.repeat(60) + '\n';
    let summaryText = '';
    if (aiSummary.recommendation) {
      summaryText = aiSummary.recommendation;
    } else {
      const name = candidate?.name || 'The candidate';
      const match = candidate?.match_score || 0;
      const skillCount = (sd.skills || candidate?.skills || []).length;
      summaryText = name + ' demonstrates ' + 
        (match > 70 ? 'strong' : match > 50 ? 'moderate' : 'limited') + 
        ' alignment with the applied roles. The candidate has ' + skillCount + 
        ' skills and ' + (matchedSkills.length > 0 ? 'relevant experience' : 'room for skill development') + 
        '. ' + (matchedSkills.length > 0 ? 'Key strengths include ' + matchedSkills.slice(0, 3).join(', ') + '.' : '') +
        (missingSkills.length > 0 ? ' Primary skill gaps: ' + missingSkills.slice(0, 3).join(', ') + '.' : '');
    }
    report += '  ' + summaryText + '\n\n';
    
    report += '='.repeat(60) + '\n';
    report += '  Report generated by Recruitment Analytics System\n';
    report += '  ' + dateStr + ' at ' + timeStr + '\n';
    report += '  Confidential - For internal use only\n';
    report += '='.repeat(60);
    
    return report;
  };

  // ============================================================
  // SIMPLIFIED PDF GENERATION (Working)
  // ============================================================

  const downloadPDF = () => {
  try {
    const reportText = buildCandidateReportText();
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
      
      if (line.indexOf('CANDIDATE EVALUATION REPORT') !== -1) {
        doc.setFontSize(20);
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
    
    const filename = 'Candidate_Report_' + (candidate?.name || 'candidate').replace(/\s/g, '_') + '_' + new Date().toISOString().split('T')[0] + '.pdf';
    doc.save(filename);
    alert('✅ Candidate Report PDF downloaded successfully!');
    
  } catch (error) {
    console.error('PDF Error:', error);
    alert('❌ Failed to generate PDF. Please try again.');
  }
};

  // ============================================================
  // PROFESSIONAL CSV
  // ============================================================

  const downloadCSV = function() {
    try {
      const sd = candidate?.structured_data || {};
      const aiSummary = candidate?.ai_summary || {};
      const now = new Date();
      const dateStr = now.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
      const timeStr = now.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
      const matchedSkills = aiSummary.matched_skills || aiSummary.strengths || [];
      const missingSkills = aiSummary.missing_skills || aiSummary.risks || [];

      let csvContent = '';

      csvContent += 'CANDIDATE EVALUATION REPORT\n';
      csvContent += 'Generated: ' + dateStr + ' at ' + timeStr + '\n';
      csvContent += 'Report ID: RPT-' + now.getFullYear() + String(now.getMonth()+1).padStart(2,'0') + String(now.getDate()).padStart(2,'0') + '-' + String(Math.floor(Math.random()*10000)).padStart(4,'0') + '\n\n';

      csvContent += 'CANDIDATE INFORMATION\n';
      csvContent += 'Field,Value\n';
      csvContent += '"Name","' + (candidate?.name || 'N/A') + '"\n';
      csvContent += '"Email","' + (candidate?.email || 'N/A') + '"\n';
      csvContent += '"Phone","' + (candidate?.phone || sd.phone || 'N/A') + '"\n';
      csvContent += '"Experience","' + (sd.total_experience_years || 0) + ' years"\n';
      csvContent += '"Status","' + (candidate?.status || 'N/A') + '"\n';
      csvContent += '"Hiring Stage","' + (candidate?.hiring_stage || 'N/A') + '"\n\n';

      csvContent += 'SCREENING SUMMARY\n';
      csvContent += 'Metric,Value\n';
      csvContent += '"Match Score","' + (candidate?.match_score || 0) + '%"\n';
      csvContent += '"Recommendation","' + (aiSummary.recommendation || 'Review screening evidence') + '"\n';
      csvContent += '"Overall Rating","' + (candidate?.match_score > 80 ? 'Excellent' : candidate?.match_score > 60 ? 'Good' : 'Needs Review') + '"\n\n';

      const skills = sd.skills || candidate?.skills || [];
      if (skills.length > 0) {
        csvContent += 'SKILLS\n';
        csvContent += 'Skill\n';
        skills.forEach(function(skill) {
          csvContent += '"' + skill + '"\n';
        });
        csvContent += '\n';
      }

      if (matchedSkills.length > 0) {
        csvContent += 'STRENGTHS\n';
        csvContent += 'Strength\n';
        matchedSkills.forEach(function(s) {
          csvContent += '"' + s + '"\n';
        });
        csvContent += '\n';
      }
      if (missingSkills.length > 0) {
        csvContent += 'MISSING SKILLS\n';
        csvContent += 'Skill\n';
        missingSkills.forEach(function(s) {
          csvContent += '"' + s + '"\n';
        });
        csvContent += '\n';
      }

      if (sd.education) {
        csvContent += 'EDUCATION\n';
        csvContent += 'Field,Details\n';
        csvContent += '"Degree","' + (sd.education.degree || 'N/A') + '"\n';
        csvContent += '"Field of Study","' + (sd.education.field || 'N/A') + '"\n';
        csvContent += '"Institution","' + (sd.education.institution || 'N/A') + '"\n';
        csvContent += '"Graduation Year","' + (sd.education.graduation_year || 'N/A') + '"\n\n';
      }

      const workExp = sd.work_experience || [];
      if (workExp.length > 0) {
        csvContent += 'WORK EXPERIENCE\n';
        csvContent += 'Company,Role,Duration\n';
        workExp.forEach(function(exp) {
          csvContent += '"' + (exp.company || 'N/A') + '","' + (exp.position || exp.designation || 'N/A') + '","' + (exp.start_date || '') + (exp.end_date ? ' - ' + exp.end_date : '') + '"\n';
        });
        csvContent += '\n';
      }

      if (candidate?.jd_history && candidate.jd_history.length > 0) {
        csvContent += 'APPLIED ROLES\n';
        csvContent += '#,Job Title,Match Score\n';
        candidate.jd_history.forEach(function(jd, index) {
          csvContent += '"' + (index + 1) + '","' + (jd.jd_title || 'N/A') + '","' + (jd.match_score || 0) + '%"\n';
        });
        csvContent += '\n';
      }

      csvContent += 'AI CANDIDATE SUMMARY\n';
      let summaryText = '';
      if (aiSummary.recommendation) {
        summaryText = aiSummary.recommendation;
      } else {
        const name = candidate?.name || 'The candidate';
        const match = candidate?.match_score || 0;
        const skillCount = (sd.skills || candidate?.skills || []).length;
        summaryText = name + ' demonstrates ' + 
          (match > 70 ? 'strong' : match > 50 ? 'moderate' : 'limited') + 
          ' alignment with the applied roles. The candidate has ' + skillCount + 
          ' skills and ' + (matchedSkills.length > 0 ? 'relevant experience' : 'room for skill development') + 
          '. ' + (matchedSkills.length > 0 ? 'Key strengths include ' + matchedSkills.slice(0, 3).join(', ') + '.' : '') +
          (missingSkills.length > 0 ? ' Primary skill gaps: ' + missingSkills.slice(0, 3).join(', ') + '.' : '');
      }
      csvContent += '"Summary","' + summaryText + '"\n\n';

      csvContent += 'Report generated by Recruitment Analytics System\n';
      csvContent += 'Confidential - For internal use only\n';

      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'Candidate_Report_' + (candidate?.name || 'candidate').replace(/\s/g, '_') + '_' + new Date().toISOString().split('T')[0] + '.csv';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      alert('✅ Candidate Report CSV downloaded successfully!');
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
      const reportText = buildCandidateReportText();
      const lines = reportText.split('\n');
      const children = [];
      
      lines.forEach(function(line) {
        if (line.trim() === '') {
          children.push(new Paragraph({ spacing: { after: 100 } }));
          return;
        }
        const isBold = line.indexOf(':') !== -1 || 
                      line.indexOf('CANDIDATE EVALUATION REPORT') !== -1 || 
                      line.indexOf('===') !== -1 ||
                      line.indexOf('---') !== -1;
        const isLarge = line.indexOf('CANDIDATE EVALUATION REPORT') !== -1;
        
        children.push(
          new Paragraph({
            children: [new TextRun({ text: line, bold: isBold, size: isLarge ? 32 : 20, font: 'Arial' })],
            spacing: { before: 80, after: 80 },
            indent: { firstLine: line.indexOf('*') !== -1 ? 720 : 0, hanging: line.indexOf('*') !== -1 ? 360 : 0 }
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
      const filename = 'Candidate_Report_' + (candidate?.name || 'candidate').replace(/\s/g, '_') + '_' + new Date().toISOString().split('T')[0] + '.docx';
      saveAs(blob, filename);
      alert('✅ Candidate Report DOCX downloaded successfully!');
    } catch (error) {
      console.error('DOCX Error:', error);
      alert('❌ Failed to generate DOCX. Please try again.');
    }
  };

  // ============================================================
  // EXCEL GENERATION
  // ============================================================

  const generateCandidateExcel = () => {
    const now = new Date();
    const dateStr = now.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
    const sd = candidate?.structured_data || {};
    const aiSummary = candidate?.ai_summary || {};
    const matchedSkills = aiSummary.matched_skills || aiSummary.strengths || [];
    const missingSkills = aiSummary.missing_skills || aiSummary.risks || [];
    
    const wb = XLSX.utils.book_new();
    
    const detailsData = [
      ['CANDIDATE EVALUATION REPORT'],
      ['Generated: ' + dateStr],
      ['Report ID: RPT-' + now.getFullYear() + String(now.getMonth()+1).padStart(2,'0') + String(now.getDate()).padStart(2,'0') + '-' + String(Math.floor(Math.random()*10000)).padStart(4,'0')],
      [],
      ['CANDIDATE INFORMATION'],
      ['Field', 'Value'],
      ['Name', candidate?.name || 'N/A'],
      ['Email', candidate?.email || 'N/A'],
      ['Phone', candidate?.phone || sd.phone || 'N/A'],
      ['Experience', (sd.total_experience_years || 0) + ' years'],
      ['Status', candidate?.status || 'N/A'],
      ['Hiring Stage', candidate?.hiring_stage || 'N/A'],
      [],
      ['SCREENING SUMMARY'],
      ['Metric', 'Value'],
      ['Match Score', (candidate?.match_score || 0) + '%'],
      ['Recommendation', aiSummary.recommendation || 'Review screening evidence'],
      ['Overall Rating', candidate?.match_score > 80 ? 'Excellent' : candidate?.match_score > 60 ? 'Good' : 'Needs Review']
    ];
    const ws1 = XLSX.utils.aoa_to_sheet(detailsData);
    XLSX.utils.book_append_sheet(wb, ws1, 'Candidate Details');
    
    const skills = sd.skills || candidate?.skills || [];
    const skillsData = [
      ['SKILLS'],
      [],
      ['Skill']
    ];
    skills.forEach(function(skill) {
      skillsData.push([skill]);
    });
    if (skills.length === 0) {
      skillsData.push(['No skills listed']);
    }
    skillsData.push([]);
    skillsData.push(['STRENGTHS']);
    skillsData.push(['Strength']);
    if (matchedSkills.length > 0) {
      matchedSkills.forEach(function(s) {
        skillsData.push([s]);
      });
    } else {
      skillsData.push(['No strengths captured']);
    }
    skillsData.push([]);
    skillsData.push(['MISSING SKILLS']);
    skillsData.push(['Skill']);
    if (missingSkills.length > 0) {
      missingSkills.forEach(function(s) {
        skillsData.push([s]);
      });
    } else {
      skillsData.push(['No missing skills']);
    }
    const ws2 = XLSX.utils.aoa_to_sheet(skillsData);
    XLSX.utils.book_append_sheet(wb, ws2, 'Skills');
    
    const expData = [
      ['EDUCATION'],
      ['Field', 'Details'],
      ['Degree', sd.education?.degree || 'N/A'],
      ['Field of Study', sd.education?.field || 'N/A'],
      ['Institution', sd.education?.institution || 'N/A'],
      ['Graduation Year', sd.education?.graduation_year || 'N/A'],
      [],
      ['WORK EXPERIENCE'],
      ['Company', 'Role', 'Duration']
    ];
    const workExp = sd.work_experience || [];
    if (workExp.length > 0) {
      workExp.forEach(function(exp) {
        expData.push([exp.company || 'N/A', exp.position || exp.designation || 'N/A', (exp.start_date || '') + (exp.end_date ? ' - ' + exp.end_date : '')]);
      });
    } else {
      expData.push(['No work experience listed']);
    }
    const ws3 = XLSX.utils.aoa_to_sheet(expData);
    XLSX.utils.book_append_sheet(wb, ws3, 'Experience');
    
    const rolesData = [
      ['APPLIED ROLES'],
      [],
      ['#', 'Job Title', 'Match Score']
    ];
    if (candidate?.jd_history && candidate.jd_history.length > 0) {
      candidate.jd_history.forEach(function(jd, index) {
        rolesData.push([index + 1, jd.jd_title || 'N/A', (jd.match_score || 0) + '%']);
      });
    } else {
      rolesData.push(['No applied roles']);
    }
    const ws4 = XLSX.utils.aoa_to_sheet(rolesData);
    XLSX.utils.book_append_sheet(wb, ws4, 'Applied Roles');
    
    const summaryData = [
      ['AI CANDIDATE SUMMARY'],
      [],
      ['Summary']
    ];
    let summaryText = '';
    if (aiSummary.recommendation) {
      summaryText = aiSummary.recommendation;
    } else {
      const name = candidate?.name || 'The candidate';
      const match = candidate?.match_score || 0;
      const skillCount = (sd.skills || candidate?.skills || []).length;
      summaryText = name + ' demonstrates ' + 
        (match > 70 ? 'strong' : match > 50 ? 'moderate' : 'limited') + 
        ' alignment with the applied roles. The candidate has ' + skillCount + 
        ' skills and ' + (matchedSkills.length > 0 ? 'relevant experience' : 'room for skill development') + 
        '. ' + (matchedSkills.length > 0 ? 'Key strengths include ' + matchedSkills.slice(0, 3).join(', ') + '.' : '') +
        (missingSkills.length > 0 ? ' Primary skill gaps: ' + missingSkills.slice(0, 3).join(', ') + '.' : '');
    }
    summaryData.push([summaryText]);
    if (aiSummary.interview_focus && aiSummary.interview_focus.length > 0) {
      summaryData.push([]);
      summaryData.push(['Interview Focus Areas']);
      aiSummary.interview_focus.forEach(function(focus) {
        summaryData.push([focus]);
      });
    }
    const ws5 = XLSX.utils.aoa_to_sheet(summaryData);
    XLSX.utils.book_append_sheet(wb, ws5, 'AI Summary');
    
    return wb;
  };

  const downloadExcel = function() {
    try {
      const wb = generateCandidateExcel();
      const wbout = XLSX.write(wb, { bookType: 'xlsx', type: 'array' });
      const blob = new Blob([wbout], { type: 'application/octet-stream' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = 'Candidate_Report_' + (candidate?.name || 'candidate').replace(/\s/g, '_') + '_' + new Date().toISOString().split('T')[0] + '.xlsx';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      alert('✅ Candidate Report Excel downloaded successfully!');
    } catch (error) {
      console.error('Excel Error:', error);
      alert('❌ Failed to generate Excel. Please try again.');
    }
  };

  // ============================================================
  // SEND EMAIL
  // ============================================================

  const sendEmailReport = async function(email) {
    try {
      const reportText = buildCandidateReportText();
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
        
        if (line.indexOf('CANDIDATE EVALUATION REPORT') !== -1) {
          doc.setFontSize(20);
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
      
      const pdfBlob = doc.output('blob');
      const reader = new FileReader();
      
      return new Promise(function(resolve, reject) {
        reader.onload = async function() {
          try {
            const base64Data = reader.result.split(',')[1];
            
            const response = await apiPost('/api/report/email', {
              recipient: email,
              subject: 'Candidate Report - ' + (candidate?.name || 'Candidate') + ' - ' + new Date().toISOString().split('T')[0],
              message: 'Please find attached the Candidate Evaluation Report for ' + (candidate?.name || 'the candidate') + ' generated on ' + new Date().toLocaleString() + '.',
              attachment: {
                filename: 'Candidate_Report_' + (candidate?.name || 'candidate').replace(/\s/g, '_') + '_' + new Date().toISOString().split('T')[0] + '.pdf',
                content: base64Data,
                mimeType: 'application/pdf'
              }
            });
            
            if (response.ok) {
              alert('✅ Candidate Report sent successfully to ' + email + '!');
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
            ' Generate Candidate Report'
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
            React.createElement('span', null, 'Report includes: Candidate Details, Skills, Experience, AI Summary')
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

  if (!candidate) return <Layout><div className="profile-loading"><SkeletonBlock variant="profile" count={3} /></div></Layout>;

  const sd = candidate.structured_data || {};
  const totalExperience = Number(sd.total_experience_years || 0);
  const experienceLabel = totalExperience < 1 ? 'No experience' : `${totalExperience} year${totalExperience === 1 ? '' : 's'}`;
  const phoneNumber = candidate.phone || sd.phone || 'N/A';
  const aiSummary = candidate.ai_summary || {};
  const goBack = () => navigate('/talent');

  return (
    <Layout>
      <div className="profile-container profile-max-width">
        <div className="profile-details-topbar">
          <div className="profile-hero">
            <div className="profile-hero-avatar" aria-hidden="true">
              <i className="fas fa-user"></i>
            </div>
            <h1 className="profile-hero-name">{candidate.name}</h1>
          </div>
          <div style={{ display: 'flex', gap: '12px', alignItems: 'center' }}>
            <button type="button" className="btn btn-secondary profile-back-btn" onClick={goBack}>
              <i className="fas fa-arrow-left"></i> Back to Talent
            </button>
          </div>
        </div>

        <div className="profile-info">
          {[['fas fa-building', 'Client', candidate.client_name || 'ShimentoX'], ['fas fa-envelope', 'Email', candidate.email || 'N/A'], ['fas fa-phone', 'Phone', phoneNumber], ['fas fa-tag', 'Status', candidate.status], ['fas fa-tasks', 'Current Stage', candidate.hiring_stage || 'N/A']].map(([icon, label, val]) => (
            <div key={label} className="profile-field">
              <strong><i className={icon}></i> {label}</strong>
              <span>{val}</span>
            </div>
          ))}
          <div className="profile-field">
            <strong><i className="fas fa-layer-group"></i> Role Category</strong>
            <span>{candidate.primary_category || 'Others'}</span>
          </div>
        </div>

        <div className="profile-section-box profile-section-compact">
          <h2 className="profile-section-title"><i className="fas fa-layer-group"></i> Role Category</h2>
          <div className="profile-category-panel">
            <div className="profile-category-summary">
              <span className="candidate-category-pill">{candidate.primary_category || 'Others'}</span>
              {(candidate.secondary_categories || []).map(category => (
                <span key={category} className="candidate-category-pill secondary">{category}</span>
              ))}
              <span className="profile-category-confidence">{candidate.confidence_score || 0}% confidence</span>
            </div>
            <p>{candidate.category_reason || 'No categorization reason captured.'}</p>
            <div className="profile-category-meta">
              <span>Source: {candidate.categorization_source || 'resume'}</span>
              <span>Matched: {(candidate.matched_keywords || []).slice(0, 8).join(', ') || 'None'}</span>
              <span>Updated: {(candidate.categorized_date || '').slice(0, 10) || 'N/A'}</span>
            </div>
          </div>
        </div>

        <div className="profile-section-box profile-section-compact">
          <h2 className="profile-section-title"><i className="fas fa-sparkles"></i> AI Candidate Summary</h2>
          <div className="profile-ai-summary">
            <div className="profile-ai-recommendation">
              <strong>Recommendation</strong>
              <span>{aiSummary.recommendation || 'Review screening evidence and validate role fit during the interview.'}</span>
            </div>
            <div className="profile-ai-grid">
              <SummaryList title="Matched Skills" items={aiSummary.matched_skills || aiSummary.strengths} emptyText="No matched skills captured" />
              <SummaryList title="Missing Skills" items={aiSummary.missing_skills || aiSummary.risks} emptyText="No missing skills captured" />
              <SummaryList title="Interview Focus" items={aiSummary.interview_focus} emptyText="Use screening summary" />
            </div>
          </div>
        </div>

        <div className="profile-section-box profile-section-compact">
          <h2 className="profile-section-title"><i className="fas fa-timeline"></i> Candidate Timeline</h2>
          <div className="profile-timeline">
            {timeline.length > 0 ? timeline.map((item, index) => {
              const stamp = formatJdUploadDateTime(item.date);
              return (
                <div key={`${item.type || 'event'}-${index}`} className={`profile-timeline-item profile-timeline-${item.type || 'event'}`}>
                  <div className="profile-timeline-dot"><i className={item.type === 'interview' ? 'fas fa-calendar-check' : item.type === 'followup' ? 'fas fa-reply' : 'fas fa-clipboard-check'}></i></div>
                  <div className="profile-timeline-body">
                    <div className="profile-timeline-head">
                      <strong>{item.label}</strong>
                      <span>{stamp.date} {stamp.time}</span>
                    </div>
                    <div className="profile-timeline-meta">{item.status}{item.score !== undefined ? ` · ${item.score}%` : ''}</div>
                    {item.summary && <p>{item.summary}</p>}
                  </div>
                </div>
              );
            }) : <div className="profile-screening-empty">No timeline events available</div>}
          </div>
        </div>

        <div className="profile-section-box profile-section-compact">
          <h2 className="profile-section-title"><i className="fas fa-file-pdf"></i> Resume Details</h2>
          <div className="profile-resume-inner">
            {candidate.structured_data ? (
              <>
                <div className="profile-resume-grid">
                  <div>
                    <h4 className="profile-sub-title"><i className="fas fa-graduation-cap"></i> Education</h4>
                    {sd.education
                      ? <div className="profile-edu-detail">
                          <div><strong>{sd.education.degree || 'N/A'}</strong></div>
                          <div>{sd.education.field || 'N/A'}</div>
                          <div className="profile-edu-meta">{sd.education.institution || 'N/A'} - {sd.education.graduation_year || 'N/A'}</div>
                        </div>
                      : <div className="profile-no-edu">No education info</div>}
                  </div>
                  <div>
                    <h4 className="profile-sub-title"><i className="fas fa-briefcase"></i> Experience</h4>
                    <div className="profile-edu-detail">
                      <div><strong>Total: {experienceLabel}</strong></div>
                      {(sd.work_experience || []).map((exp, i) => (
                        <div key={i} className="profile-exp-item">
                          {exp.position || exp.designation || 'N/A'} @ {exp.company || 'N/A'}
                          <div className="profile-exp-dates">{exp.start_date || ''}{exp.end_date ? ` - ${exp.end_date}` : ''}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
                <div className="profile-skills-list">
                  <h4 className="profile-sub-title"><i className="fas fa-code"></i> Skills</h4>
                  <div className="candidate-roles-badges">
                    {(sd.skills || []).map(skill => (
                      <span key={skill} className="profile-skill-badge">{skill}</span>
                    ))}
                  </div>
                </div>
              </>
            ) : <em>Resume details not available</em>}
          </div>
        </div>

        <div className="profile-section-box profile-section-compact profile-jd-section-full">
            <h2 className="profile-section-title"><i className="fas fa-briefcase"></i> Applied Roles</h2>
            <div className="profile-jd-grid profile-jd-grid-full">
              {(candidate.jd_history || []).length > 0
                ? candidate.jd_history.map((jd, i) => {
                    const uploaded = formatJdUploadDateTime(jd.comparison_date);
                    return (
                      <div key={i} className="profile-jd-item">
                        <div className="profile-jd-item-title"><i className="fas fa-check-circle"></i> {jd.jd_title}</div>
                        <div className="profile-jd-score">{jd.match_score}%</div>
                        <div className="profile-jd-date">
                          <span className="profile-jd-date-day">{uploaded.date}</span>
                          {uploaded.time && <span className="profile-jd-date-time">{uploaded.time}</span>}
                        </div>
                      </div>
                    );
                  })
                : <div className="profile-jd-empty">No applied roles available</div>}
            </div>
        </div>

        <div className="profile-section-box profile-section-box-mb profile-section-compact">
          <h2 className="profile-section-title"><i className="fas fa-clipboard-check"></i> Screening Summaries</h2>
          {candidate.screening_summary && (
            <div className="profile-screening-summary profile-inline-note">
              {candidate.screening_summary}
            </div>
          )}
          {candidate.rejection_reason && candidate.status === 'Rejected' && (
            <div className="profile-screening-gaps profile-inline-note">
              Rejection reason: {candidate.rejection_reason}
            </div>
          )}
          <div className="profile-screening-grid">
            {(candidate.screening_summaries || []).length > 0
              ? candidate.screening_summaries.map((item, i) => (
                  <div key={i} className="profile-screening-item">
                    <div className="profile-screening-header"><i className="fas fa-info-circle"></i> {item.jd_title}</div>
                    <div className="profile-screening-summary">{item.summary}</div>
                    <div className="profile-screening-status">
                      Status: <span className={item.status === 'Selected' ? 'profile-screening-status-selected' : 'profile-screening-status-rejected'}>{item.status}</span>
                    </div>
                    {item.strengths?.length > 0 && <div className="profile-screening-strengths">Strengths: {item.strengths.join(', ')}</div>}
                    {item.gaps?.length > 0 && <div className="profile-screening-gaps">Gaps: {item.gaps.join(', ')}</div>}
                    {item.rejection_reason && item.status === 'Rejected' && (
                      <div className="profile-screening-gaps">Rejection reason: {item.rejection_reason}</div>
                    )}
                    {item.recommendation && <div className="profile-screening-strengths">Recommendation: {item.recommendation}</div>}
                  </div>
                ))
              : <div className="profile-screening-empty">No screening summaries available</div>}
          </div>
        </div>

        <div className="profile-actions-footer">
          <button
            type="button"
            className="btn btn-danger profile-remove-footer-btn"
            disabled={deleting}
            onClick={handleRemove}
            title="Remove this candidate from the repository"
          >
            {deleting
              ? <><i className="fas fa-spinner fa-spin"></i> Removing…</>
              : <><i className="fas fa-user-times"></i> Remove candidate</>}
          </button>
        </div>

        {/* Generate Candidate Report Button at Bottom */}
        <div style={{ 
          marginTop: '30px', 
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
            <i className="fas fa-plus-circle"></i> Generate Candidate Report
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

export default CandidateProfile;
