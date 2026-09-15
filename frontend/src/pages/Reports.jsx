import React, { useState, useEffect } from 'react';
import Layout from '../components/Layout.jsx';
import { apiGet, apiPost } from '../api.js';
import '../styles/reports_extra.css';
import jsPDF from 'jspdf';
import { Document, Packer, Paragraph, TextRun } from 'docx';
import { saveAs } from 'file-saver';

function Reports() {
  // --- EXISTING STATE ---
  const [metrics, setMetrics] = useState({
    total_jobs: 0,
    total_candidates: 0,
    active_jobs: 0,
    selection_rate: 0
  });
  const [jdReports, setJdReports] = useState([]);
  const [funnel, setFunnel] = useState([]);
  const [skillGaps, setSkillGaps] = useState([]);

  // --- MODAL STATE ---
  const [showModal, setShowModal] = useState(false);
  const [selectedFormat, setSelectedFormat] = useState('pdf');
  const [recipientEmail, setRecipientEmail] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [showEmailInput, setShowEmailInput] = useState(false);

  // --- FETCH DATA ---
  useEffect(() => {
    const fetchData = async () => {
      try {
        const data = await apiGet('/api/reports');
        setMetrics(data.metrics || {});
        setJdReports(data.jd_reports || []);
        setFunnel(data.funnel || []);
        setSkillGaps(data.skill_gaps || []);
      } catch (error) {
        console.error('Error fetching reports data:', error);
        // Sample data for testing
        setMetrics({
          total_jobs: 12,
          total_candidates: 847,
          active_jobs: 8,
          selection_rate: 23
        });
        setJdReports([
          { title: 'Senior React Developer', total_screened: 45, selected: 12, rejected: 33, avg_match: 76 },
          { title: 'DevOps Engineer', total_screened: 38, selected: 9, rejected: 29, avg_match: 68 },
          { title: 'Product Manager', total_screened: 52, selected: 15, rejected: 37, avg_match: 82 }
        ]);
        setFunnel([
          { name: 'Applied', count: 847 },
          { name: 'Screened', count: 520 },
          { name: 'Interview', count: 210 },
          { name: 'Technical Test', count: 98 },
          { name: 'Selected', count: 36 }
        ]);
        setSkillGaps([
          { name: 'React', jd_count: 8, candidate_count: 12 },
          { name: 'Python', jd_count: 6, candidate_count: 4 },
          { name: 'AWS', jd_count: 10, candidate_count: 6 },
          { name: 'Docker', jd_count: 7, candidate_count: 9 },
          { name: 'Machine Learning', jd_count: 4, candidate_count: 2 }
        ]);
      }
    };
    fetchData();
  }, []);

  const totalFunnel = funnel.reduce((s, f) => s + f.count, 0);

  // --- BUILD REPORT TEXT ---
  const buildReportText = () => {
    const now = new Date();
    const dateStr = now.toLocaleDateString('en-US', { 
      year: 'numeric', 
      month: 'long', 
      day: 'numeric' 
    });
    
    let report = `
╔══════════════════════════════════════════════════════════════╗
║              RECRUITMENT ANALYTICS REPORT                   ║
╚══════════════════════════════════════════════════════════════╝

Generated: ${dateStr}
Report ID: RPT-${now.getFullYear()}${String(now.getMonth()+1).padStart(2,'0')}${String(now.getDate()).padStart(2,'0')}-${String(Math.floor(Math.random()*10000)).padStart(4,'0')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 OVERALL METRICS
───────────────────────────────────────────────────────────────
  Total Jobs              : ${metrics.total_jobs}
  Total Candidates        : ${metrics.total_candidates}
  Active Jobs             : ${metrics.active_jobs}
  Selection Rate          : ${metrics.selection_rate}%

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💼 JOB DESCRIPTION PERFORMANCE
───────────────────────────────────────────────────────────────
${jdReports.map(j => 
  `  • ${j.title}
    - Screened       : ${j.total_screened}
    - Selected       : ${j.selected} (${j.total_screened > 0 ? Math.floor((j.selected / j.total_screened) * 100) : 0}%)
    - Rejected       : ${j.rejected}
    - Avg Match Score: ${j.avg_match}%`
).join('\n\n')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📈 HIRING FUNNEL
───────────────────────────────────────────────────────────────
${funnel.map(f => `  • ${f.name.padEnd(15)} : ${f.count.toString().padStart(5)} candidates (${totalFunnel > 0 ? Math.round((f.count / totalFunnel) * 100) : 0}%)`).join('\n')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔍 SKILL GAP ANALYSIS
───────────────────────────────────────────────────────────────
${skillGaps.map(s => {
  const gap = s.jd_count - s.candidate_count;
  const status = gap > 0 ? `⚠️ Shortage of ${gap}` : 
                 gap < 0 ? `✅ Surplus of ${Math.abs(gap)}` : 
                 '⚖️ Balanced';
  return `  • ${s.name.padEnd(15)} : Demand: ${s.jd_count}, Available: ${s.candidate_count}, ${status}`;
}).join('\n')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚡ RECRUITER EFFICIENCY
───────────────────────────────────────────────────────────────
  Average Screening Time : 2.5 hrs per job
  Accuracy Rate          : 94% (AI-assisted)
  Time Saved             : 65% vs manual screening

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🔄 CONVERSION RATES
───────────────────────────────────────────────────────────────
  Screening → Selection        : 45%
  Selection → Technical        : 60%
  Technical → HR Round         : 70%
  HR Round → Offer             : 80%

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  Report generated by Recruitment Analytics System
  © ${new Date().getFullYear()} All Rights Reserved
`;

  return report;
  };

  // --- DOWNLOAD: PDF ---
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
      
      if (line.indexOf('RECRUITMENT ANALYTICS REPORT') !== -1) {
        doc.setFontSize(20);
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
    
    const filename = 'Recruitment_Report_' + new Date().toISOString().split('T')[0] + '.pdf';
    doc.save(filename);
    alert('✅ PDF downloaded successfully!');
    
  } catch (error) {
    console.error('PDF Error:', error);
    alert('❌ Failed to generate PDF. Please try again.');
  }
};

  // --- DOWNLOAD: DOCX ---
  const downloadDOCX = async (reportText) => {
    try {
      const lines = reportText.split('\n');
      const children = [];
      
      lines.forEach(line => {
        if (line.trim() === '') {
          children.push(new Paragraph({ spacing: { after: 100 } }));
          return;
        }
        
        const isBold = line.includes(':') || 
                      line.includes('RECRUITMENT ANALYTICS REPORT') || 
                      line.includes('===') ||
                      line.includes('---');
        
        const isLarge = line.includes('RECRUITMENT ANALYTICS REPORT');
        
        children.push(
          new Paragraph({
            children: [
              new TextRun({
                text: line,
                bold: isBold,
                size: isLarge ? 32 : 20,
                font: 'Arial',
              })
            ],
            spacing: {
              before: 80,
              after: 80,
            },
            indent: {
              firstLine: line.includes('•') ? 720 : 0,
              hanging: line.includes('•') ? 360 : 0,
            }
          })
        );
      });
      
      const doc = new Document({
        sections: [{
          properties: {
            page: {
              margin: {
                top: 1440,
                bottom: 1440,
                left: 1440,
                right: 1440,
              }
            }
          },
          children: children,
        }]
      });
      
      const blob = await Packer.toBlob(doc);
      const filename = `Recruitment_Report_${new Date().toISOString().split('T')[0]}.docx`;
      saveAs(blob, filename);
      alert('✅ DOCX downloaded successfully!');
    } catch (error) {
      console.error('DOCX Error:', error);
      alert('❌ Failed to generate Word document. Please try again.');
    }
  };

  // --- DOWNLOAD: CSV ---
  const downloadCSV = () => {
    try {
      const rows = [
        ['Report Section', 'Category', 'Sub-Category', 'Value']
      ];
      
      rows.push(['Overview', 'Total Jobs', '', metrics.total_jobs]);
      rows.push(['Overview', 'Total Candidates', '', metrics.total_candidates]);
      rows.push(['Overview', 'Active Jobs', '', metrics.active_jobs]);
      rows.push(['Overview', 'Selection Rate', '', metrics.selection_rate + '%']);
      
      jdReports.forEach(j => {
        rows.push(['JD Performance', j.title, 'Screened', j.total_screened]);
        rows.push(['JD Performance', j.title, 'Selected', j.selected]);
        rows.push(['JD Performance', j.title, 'Rejected', j.rejected]);
        rows.push(['JD Performance', j.title, 'Avg Match', j.avg_match + '%']);
      });
      
      funnel.forEach(f => {
        rows.push(['Hiring Funnel', f.name, 'Count', f.count]);
      });
      
      skillGaps.forEach(s => {
        rows.push(['Skill Gap', s.name, 'JD Demand', s.jd_count]);
        rows.push(['Skill Gap', s.name, 'Available', s.candidate_count]);
      });
      
      const csvContent = rows.map(row => row.join(',')).join('\n');
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `Recruitment_Report_${new Date().toISOString().split('T')[0]}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      alert('✅ CSV downloaded successfully!');
    } catch (error) {
      console.error('CSV Error:', error);
      alert('❌ Failed to generate CSV. Please try again.');
    }
  };

  // --- SEND: Email ---
  const sendEmailReport = async (email, reportText) => {
    try {
      const doc = new jsPDF('p', 'mm', 'a4');
      const margin = 20;
      const maxWidth = doc.internal.pageSize.getWidth() - (margin * 2);
      let y = 20;
      
      const lines = reportText.split('\n');
      lines.forEach(line => {
        if (y > 270) {
          doc.addPage();
          y = 20;
        }
        
        if (line.includes('RECRUITMENT ANALYTICS REPORT')) {
          doc.setFontSize(20);
          doc.setFont('helvetica', 'bold');
          doc.setTextColor(26, 54, 93);
        } else if (line.includes('===') || line.includes('---')) {
          doc.setFontSize(10);
          doc.setFont('helvetica', 'normal');
          doc.setTextColor(113, 128, 150);
        } else if (line.includes('•')) {
          doc.setFontSize(10);
          doc.setFont('helvetica', 'normal');
          doc.setTextColor(45, 55, 72);
        } else if (line.includes(':') && !line.includes('http')) {
          doc.setFontSize(10);
          doc.setFont('helvetica', 'bold');
          doc.setTextColor(45, 55, 72);
        } else {
          doc.setFontSize(10);
          doc.setFont('helvetica', 'normal');
          doc.setTextColor(74, 85, 104);
        }
        
        const x = line.includes('•') ? margin + 5 : margin;
        const wrappedLines = doc.splitTextToSize(line, maxWidth - (x - margin));
        wrappedLines.forEach(wrappedLine => {
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
      
      return new Promise((resolve, reject) => {
        reader.onload = async () => {
          try {
            const base64Data = reader.result.split(',')[1];
            
            const response = await apiPost('/api/report/email', {
              recipient: email,
              subject: `Recruitment Report - ${new Date().toISOString().split('T')[0]}`,
              message: `Please find attached the recruitment report generated on ${new Date().toLocaleString()}.\n\nThis report includes:\n- Overall Metrics\n- Job Description Performance\n- Hiring Funnel\n- Skill Gap Analysis\n\nBest regards,\nRecruitment Analytics System`,
              attachment: {
                filename: `Recruitment_Report_${new Date().toISOString().split('T')[0]}.pdf`,
                content: base64Data,
                mimeType: 'application/pdf'
              }
            });
            
            if (response.ok) {
              alert(`✅ Report sent successfully to ${email}!`);
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

  // --- MAIN HANDLER ---
  const handleGenerateReport = async () => {
    if (selectedFormat === 'email' && !recipientEmail) {
      alert('⚠️ Please enter a recipient email address');
      return;
    }

    setIsGenerating(true);
    
    try {
      const reportText = buildReportText();
      
      switch (selectedFormat) {
        case 'pdf':
          downloadPDF(reportText);
          break;
        case 'docx':
          await downloadDOCX(reportText);
          break;
        case 'csv':
          downloadCSV();
          break;
        case 'email':
          await sendEmailReport(recipientEmail, reportText);
          break;
        default:
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

  // --- MODAL COMPONENT (Positioned at Bottom) ---
  const ReportModal = () => {
    if (!showModal) return null;
    
    return (
      <div 
        className="modal-overlay" 
        onClick={() => setShowModal(false)}
        style={{
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
        }}
      >
        <div 
          className="modal-content" 
          onClick={(e) => e.stopPropagation()}
          style={{
            background: '#ffffff',
            borderRadius: '16px 16px 0 0',
            maxWidth: '480px',
            width: '95%',
            maxHeight: '80vh',
            overflowY: 'auto',
            boxShadow: '0 -10px 40px rgba(0,0,0,0.15)',
            border: '1px solid #e2e8f0',
            animation: 'slideUp 0.3s ease'
          }}
        >
          <div className="modal-header">
            <h2><i className="fas fa-file-alt"></i> Generate Report</h2>
            <button className="modal-close" onClick={() => setShowModal(false)}>×</button>
          </div>
          
          <div className="modal-body">
            <p className="modal-subtitle">Choose your report format</p>
            
            <div className="format-grid">
              <div 
                className={`format-option ${selectedFormat === 'pdf' ? 'active' : ''}`}
                onClick={() => {
                  setSelectedFormat('pdf');
                  setShowEmailInput(false);
                }}
              >
                <i className="fas fa-file-pdf"></i>
                <span>PDF</span>
              </div>
              <div 
                className={`format-option ${selectedFormat === 'docx' ? 'active' : ''}`}
                onClick={() => {
                  setSelectedFormat('docx');
                  setShowEmailInput(false);
                }}
              >
                <i className="fas fa-file-word"></i>
                <span>DOCX</span>
              </div>
              <div 
                className={`format-option ${selectedFormat === 'csv' ? 'active' : ''}`}
                onClick={() => {
                  setSelectedFormat('csv');
                  setShowEmailInput(false);
                }}
              >
                <i className="fas fa-file-excel"></i>
                <span>CSV</span>
              </div>
              <div 
                className={`format-option ${selectedFormat === 'email' ? 'active' : ''}`}
                onClick={() => {
                  setSelectedFormat('email');
                  setShowEmailInput(true);
                }}
              >
                <i className="fas fa-envelope"></i>
                <span>Email</span>
              </div>
            </div>
            
            {showEmailInput && (
              <div className="email-input">
                <label htmlFor="recipient-email">📧 Recipient Email</label>
                <input
                  id="recipient-email"
                  type="email"
                  placeholder="Enter recipient email address"
                  value={recipientEmail}
                  onChange={(e) => setRecipientEmail(e.target.value)}
                  required
                />
                <small>Report will be sent as a PDF attachment</small>
              </div>
            )}
            
            <div className="report-preview">
              <i className="fas fa-info-circle"></i>
              <span>Report includes: Metrics, JD Performance, Funnel, Skill Gaps</span>
            </div>
          </div>
          
          <div className="modal-footer">
            <button 
              className="btn-secondary" 
              onClick={() => {
                setShowModal(false);
                setSelectedFormat('pdf');
                setRecipientEmail('');
                setShowEmailInput(false);
              }}
            >
              Cancel
            </button>
            <button 
              className="btn-primary" 
              onClick={handleGenerateReport}
              disabled={isGenerating}
            >
              {isGenerating ? (
                <>
                  <i className="fas fa-spinner fa-spin"></i> Generating...
                </>
              ) : (
                <>
                  <i className="fas fa-download"></i> Generate
                </>
              )}
            </button>
          </div>
        </div>
      </div>
    );
  };

  // --- RENDER ---
  return (
    <Layout>
      <div className="reports-container">
        {/* HEADER - WITHOUT THE BUTTON */}
        <div className="reports-header">
          <div>
            <h1><i className="fas fa-chart-bar"></i> Reports &amp; Analytics</h1>
            <p className="reports-subtitle">Comprehensive recruitment analytics and insights</p>
          </div>
        </div>

        {/* EXISTING CONTENT - All your content stays here */}
        <h2 className="reports-section-title"><i className="fas fa-chart-pie"></i> Overall Metrics</h2>
        <div className="metrics">
          <div className="card"><h4>Total Job Descriptions</h4><span>{metrics.total_jobs}</span></div>
          <div className="card"><h4>Total Candidates</h4><span>{metrics.total_candidates}</span></div>
          <div className="card success"><h4>Active Jobs</h4><span>{metrics.active_jobs}</span></div>
          <div className="card warning"><h4>Overall Selection Rate</h4><span>{metrics.selection_rate}%</span></div>
        </div>

        <h2 className="reports-section-title-spaced"><i className="fas fa-briefcase"></i> Job Description Performance</h2>
        <div className="table-container">
          <table>
            <thead>
              <tr><th>Job Title</th><th>Total Screened</th><th>Selected</th><th>Rejected</th><th>Avg Match Score</th><th>Selection Rate</th></tr>
            </thead>
            <tbody>
              {jdReports.map((jd, i) => (
                <tr key={i}>
                  <td><strong>{jd.title}</strong></td>
                  <td>{jd.total_screened}</td>
                  <td><span className="badge badge-success">{jd.selected}</span></td>
                  <td><span className="badge badge-danger">{jd.rejected}</span></td>
                  <td>
                    <div className="reports-score-cell">
                      <span className="reports-score-value">{jd.avg_match}%</span>
                      <div className="progress reports-progress-wrap">
                        <div className="progress-bar" style={{ width: `${jd.avg_match}%` }}></div>
                      </div>
                    </div>
                  </td>
                  <td>{jd.total_screened > 0 ? `${Math.floor((jd.selected / jd.total_screened) * 100)}%` : 'N/A'}</td>
                </tr>
              ))}
              {jdReports.length === 0 && <tr><td colSpan="6" className="reports-table-empty">No data yet</td></tr>}
            </tbody>
          </table>
        </div>

        <h2 className="reports-section-title-spaced"><i className="fas fa-stream"></i> Hiring Funnel Overview</h2>
        <div className="grid grid-2">
          <div className="reports-white-card">
            <table className="reports-funnel-table">
              <thead><tr><th>Stage</th><th>Count</th><th>Progress</th></tr></thead>
              <tbody>
                {funnel.map((stage, i) => (
                  <tr key={i}>
                    <td><strong>{stage.name}</strong></td>
                    <td className="reports-funnel-count">{stage.count}</td>
                    <td>
                      <div className="progress">
                        <div className="progress-bar" style={{ width: `${totalFunnel > 0 ? Math.round((stage.count / totalFunnel) * 100) : 0}%` }}></div>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="reports-white-card">
            <h3 className="reports-insights-heading"><i className="fas fa-info-circle"></i> Funnel Insights</h3>
            <ul className="list-group">
              <li className="list-group-item">
                <div className="reports-insight-row">
                  <span className="reports-insight-label">Total Candidates Processed</span>
                  <span className="reports-insight-total">{metrics.total_candidates}</span>
                </div>
              </li>
              <li className="list-group-item">
                <div className="reports-insight-row">
                  <span className="reports-insight-label">Selection Rate</span>
                  <span className="reports-insight-rate">{metrics.selection_rate}%</span>
                </div>
              </li>
              <li className="list-group-item">
                <div className="reports-insight-row">
                  <span className="reports-insight-label">Active Jobs</span>
                  <span className="reports-insight-active">{metrics.active_jobs}</span>
                </div>
              </li>
            </ul>
          </div>
        </div>

        <h2 className="reports-section-title-spaced"><i className="fas fa-search"></i> Skill Gap Analysis</h2>
        {skillGaps.length > 0 ? (
          <div className="table-container">
            <table>
              <thead><tr><th>Skill</th><th>Demanded (JDs)</th><th>Available (Candidates)</th><th>Gap</th><th>Status</th></tr></thead>
              <tbody>
                {skillGaps.map((skill, i) => (
                  <tr key={i}>
                    <td><strong>{skill.name}</strong></td>
                    <td>{skill.jd_count}</td>
                    <td>{skill.candidate_count}</td>
                    <td>
                      {skill.jd_count > skill.candidate_count
                        ? <span className="reports-gap-negative">-{skill.jd_count - skill.candidate_count}</span>
                        : <span className="reports-gap-positive">+{skill.candidate_count - skill.jd_count}</span>}
                    </td>
                    <td>
                      {skill.jd_count > skill.candidate_count
                        ? <span className="badge badge-danger"><i className="fas fa-exclamation-triangle"></i> Shortage</span>
                        : skill.candidate_count > skill.jd_count
                          ? <span className="badge badge-success"><i className="fas fa-check"></i> Surplus</span>
                          : <span className="badge badge-primary"><i className="fas fa-equals"></i> Balanced</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="reports-white-card reports-skill-empty">
            <p className="reports-skill-empty-text">No skill gap data available</p>
          </div>
        )}

        <h2 className="reports-section-title-spaced"><i className="fas fa-tachometer-alt"></i> Recruiter Efficiency</h2>
        <div className="grid grid-3">
          {[{ label: 'Avg Screening Time', value: '2.5 hrs', sub: 'per job', cls: 'reports-efficiency-blue' },
            { label: 'Accuracy Rate', value: '94%', sub: 'AI-assisted screening', cls: 'reports-efficiency-green' },
            { label: 'Time Saved', value: '65%', sub: 'vs manual screening', cls: 'reports-efficiency-orange' }].map(item => (
            <div key={item.label} className="reports-white-card reports-efficiency-card">
              <div className="reports-efficiency-label">{item.label}</div>
              <div className={`reports-efficiency-value ${item.cls}`}>{item.value}</div>
              <div className="reports-efficiency-sub">{item.sub}</div>
            </div>
          ))}
        </div>

        <h2 className="reports-section-title-spaced"><i className="fas fa-chart-line"></i> Conversion Rate Analysis</h2>
        <div className="reports-conversion-card">
          {[['Screening → Selection', 45], ['Selection → Technical Interview', 60], ['Technical → HR Round', 70], ['HR → Offer', 80]].map(([label, pct]) => (
            <div key={label} className="reports-conversion-item">
              <div className="reports-conversion-row">
                <span className="reports-conversion-label">{label}</span>
                <span className="reports-conversion-pct">{pct}%</span>
              </div>
              <div className="progress"><div className="progress-bar" style={{ width: `${pct}%` }}></div></div>
            </div>
          ))}
        </div>

        {/* BUTTON AT THE BOTTOM */}
        <div className="reports-export-bar" style={{ 
          marginTop: '40px', 
          display: 'flex', 
          justifyContent: 'center',
          padding: '20px 0'
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
            <i className="fas fa-plus-circle"></i> Generate Report
          </button>
        </div>

        <ReportModal />
        
        {/* Animation Keyframes */}
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

export default Reports;