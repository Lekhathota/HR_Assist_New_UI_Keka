"""
Report Routes - Handles report generation and email sending
"""

from flask import Blueprint, request, jsonify
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import os
import base64
from datetime import datetime
from services.report_service import reports_payload
from services.auth_service import api_login_required

report_bp = Blueprint('report_routes', __name__)

@report_bp.route('/api/report/email', methods=['POST'])
@api_login_required
def send_report_email():
    """
    Send report via email with attachment
    Expects: { recipient, subject, message, attachment: { filename, content, mimeType } }
    """
    try:
        data = request.get_json(silent=True) or {}
        recipient = data.get('recipient')
        subject = data.get('subject', 'Recruitment Report')
        message = data.get('message', '')
        attachment = data.get('attachment', {})
        
        # Validate recipient
        if not recipient:
            return jsonify({'error': 'Recipient email required'}), 400
        
        # Get SMTP configuration from environment
        smtp_server = os.getenv('SMTP_SERVER', 'smtp.gmail.com')
        smtp_port = int(os.getenv('SMTP_PORT', 587))
        smtp_user = os.getenv('SMTP_USER')
        smtp_password = os.getenv('SMTP_PASSWORD')
        
        # Check if SMTP is configured
        if not smtp_user or not smtp_password:
            return jsonify({
                'error': 'SMTP not configured. Please set SMTP_USER and SMTP_PASSWORD in .env'
            }), 500
        
        # Create email
        msg = MIMEMultipart()
        msg['From'] = smtp_user
        msg['To'] = recipient
        msg['Subject'] = subject
        
        # Email body
        body = f"""
{message}

---
This report was generated automatically by Recruitment Analytics System.
Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

This is an automated message. Please do not reply to this email.
"""
        msg.attach(MIMEText(body, 'plain'))
        
        # Attach file if provided
        if attachment and attachment.get('content'):
            try:
                # Decode base64 content
                file_content = base64.b64decode(attachment['content'], validate=True)
                filename = attachment.get('filename', 'report.pdf')
                
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(file_content)
                encoders.encode_base64(part)
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename="{filename}"'
                )
                msg.attach(part)
            except Exception as e:
                print(f"Attachment error: {str(e)}")
                return jsonify({'error': f'Failed to process attachment: {str(e)}'}), 500
        
        # Send email
        try:
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_password)
                server.send_message(msg)
        except smtplib.SMTPAuthenticationError:
            return jsonify({'error': 'SMTP authentication failed. Check your email credentials.'}), 500
        except smtplib.SMTPException as e:
            return jsonify({'error': f'SMTP error: {str(e)}'}), 500
        
        return jsonify({
            'success': True,
            'message': f'Report sent successfully to {recipient}'
        })
        
    except Exception as e:
        print(f"Email error: {str(e)}")
        return jsonify({'error': str(e)}), 500


@report_bp.route('/api/reports', methods=['GET'])
@api_login_required
def api_reports():
    """
    Get report data for dashboards and report exports.
    """
    return jsonify(reports_payload())
