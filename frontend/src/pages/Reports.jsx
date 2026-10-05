import React, { useState, useEffect, useRef } from 'react';
import Layout from '../components/Layout.jsx';
import { apiPost } from '../api.js';
import '../styles/reports_extra.css';
import { useAnalytics, AnalyticsFilters, AnalyticsStatus } from '../components/Analytics.jsx';
import ReportAnalytics from '../components/ReportAnalytics.jsx';
import { analyticsReport } from '../utils/analytics.js';
import jsPDF from 'jspdf';
import { Document, Packer, Paragraph, TextRun } from 'docx';
import { saveAs } from 'file-saver';

function Reports() {
  const state = useAnalytics('/api/reports');
  const { data, filters } = state;
  const metrics = data?.metrics || {};
  const jdReports = data?.jd_reports || [];
  const funnel = data?.funnel || [];
  const skillGaps = data?.skill_gaps || [];

  const modalRef = useRef(null);
  // --- MODAL STATE ---
  const [showModal, setShowModal] = useState(false);
  const [selectedFormat, setSelectedFormat] = useState('pdf');
  const [recipientEmail, setRecipientEmail] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [showEmailInput, setShowEmailInput] = useState(false);

  useEffect(() => {
    if (!showModal) return undefined;
    const previous = document.activeElement;
    modalRef.current?.querySelector('button')?.focus();
    return () => previous?.focus();
  }, [showModal]);

  const buildReportText = () => analyticsReport(data, filters);

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

      rows.push(['Filters', 'From', '', filters.allTime ? 'All time' : filters.start], ['Filters', 'Through', '', filters.allTime ? 'All time' : filters.end], ['Filters', 'Job', '', filters.jobs?.join(', ') || filters.job || 'All jobs']);
      buildReportText().split('\n').forEach(line => rows.push(['Analytics', line, '', '']));
      const csvContent = rows.map(row => row.map(value => '"' + String(value ?? 'Not available').replaceAll('"', '""') + '"').join(',')).join('\n');
      const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
      const link = document.createElement('a');
      link.href = URL.createObjectURL(blob);
      link.download = `Recruitment_Report_${new Date().toISOString().split('T')[0]}.csv`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(link.href);
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
          ref={modalRef} role="dialog" aria-modal="true" aria-label="Export recruitment report"
          onKeyDown={event => {
            if (event.key === 'Escape' && !isGenerating) setShowModal(false);
            if (event.key === 'Tab') {
              const controls = [...event.currentTarget.querySelectorAll('button:not(:disabled), input, select')];
              const first = controls[0], last = controls[controls.length - 1];
              if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
              else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
            }
          }}
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
            <button className="modal-close" aria-label="Close export dialog" onClick={() => setShowModal(false)}>×</button>
          </div>

          <div className="modal-body">
            <p className="modal-subtitle">Choose your report format</p>

            <div className="format-grid">
              <button type="button" className={`format-option ${selectedFormat === 'pdf' ? 'active' : ''}`}
                onClick={() => {
                  setSelectedFormat('pdf');
                  setShowEmailInput(false);
                }}
              >
                <i className="fas fa-file-pdf"></i>
                <span>PDF</span>
              </button>
              <button type="button" className={`format-option ${selectedFormat === 'docx' ? 'active' : ''}`}
                onClick={() => {
                  setSelectedFormat('docx');
                  setShowEmailInput(false);
                }}
              >
                <i className="fas fa-file-word"></i>
                <span>DOCX</span>
              </button>
              <button type="button" className={`format-option ${selectedFormat === 'csv' ? 'active' : ''}`}
                onClick={() => {
                  setSelectedFormat('csv');
                  setShowEmailInput(false);
                }}
              >
                <i className="fas fa-file-excel"></i>
                <span>CSV</span>
              </button>
              <button type="button" className={`format-option ${selectedFormat === 'email' ? 'active' : ''}`}
                onClick={() => {
                  setSelectedFormat('email');
                  setShowEmailInput(true);
                }}
              >
                <i className="fas fa-envelope"></i>
                <span>Email</span>
              </button>
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

  return (
    <Layout><div className="insights-page reports-container">
      <div className="insights-heading"><div><h1>Reports</h1><p>Analyze your hiring data and track key metrics.</p></div>
        <button className="btn btn-primary" disabled={!data || state.loading} onClick={() => setShowModal(true)}>Export Report</button>
      </div>
      <AnalyticsStatus {...state} />
      {data && <ReportAnalytics data={data} filters={<AnalyticsFilters {...state} />} />}
      {data && ReportModal()}
    </div></Layout>
  );
}
export default Reports;
