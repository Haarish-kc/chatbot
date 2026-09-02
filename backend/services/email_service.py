import os
import base64
import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from config import settings

logger = logging.getLogger(__name__)

async def send_support_email(user_info: dict, description: str, issue_type: str, attachment: Optional[dict] = None) -> bool:
    """
    Formats and dispatches an IT Support email request asynchronously.
    Resolves the IT Manager dynamically from the users database if possible.
    Enforces attachment validation (max 5MB, PDF/PNG/JPG/JPEG/DOCX).
    If SMTP credentials are not configured in settings, falls back to logging to support_emails.log in development.
    """
    first = user_info.get("firstName", "")
    last = user_info.get("lastName", "")
    sender_name = f"{first} {last}".strip() or user_info.get("username", "Unknown User")
    sender_email = user_info.get("email", "unknown@company.com")
    sender_role = user_info.get("role", "STAFF")
    sender_dept = user_info.get("department", "General")
    server_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Target recipient email configured from .env
    recipient_email = settings.REPORT_RECIPIENT_EMAIL

    # Validate attachment if present
    file_data = None
    filename = None
    if attachment:
        filename = attachment.get("filename", "attachment")
        content_base64 = attachment.get("content", "")
        
        # 1. File type validation
        if not filename.lower().endswith(('.pdf', '.png', '.jpg', '.jpeg', '.docx')):
            logger.warning(f"Attachment rejected: unsupported file type ({filename})")
            raise ValueError("Unsupported file type. Only PDF, PNG, JPG, JPEG, and DOCX files are allowed.")
            
        # 2. File size validation (5 MB maximum)
        raw_b64 = content_base64.split(",")[1] if "," in content_base64 else content_base64
        size_in_bytes = len(raw_b64) * 3 / 4
        if size_in_bytes > 5 * 1024 * 1024:
            logger.warning(f"Attachment rejected: size exceeds 5MB ({filename})")
            raise ValueError("Attachment size exceeds the maximum limit of 5 MB.")
            
        # Decode base64
        try:
            file_data = base64.b64decode(raw_b64)
        except Exception as e:
            logger.error(f"Failed to decode base64 file data: {e}")
            raise ValueError("Invalid file attachment content.")

    subject = "Inventory AI Assistant - Issue Report"
    
    # Formatted support request body text
    email_body = f"""Report Details

User:
{sender_name}

Email:
{sender_email}

Role:
{sender_role}

Department:
{sender_dept}

Issue Description:
{description}

Submitted From:
Inventory AI Assistant

Timestamp:
{server_timestamp}
"""

    html_body = f"""
    <html>
      <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; border: 1px solid #e2e8f0; border-radius: 8px; padding: 20px;">
        <h2 style="color: #2563eb; border-bottom: 2px solid #e5e7eb; padding-bottom: 8px; margin-top: 0;">Issue Report Submitted</h2>
        <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px;">
          <tr>
            <td style="padding: 6px 0; font-weight: bold; width: 140px; color: #64748b;">User:</td>
            <td style="padding: 6px 0; color: #1e293b;">{sender_name}</td>
          </tr>
          <tr>
            <td style="padding: 6px 0; font-weight: bold; color: #64748b;">Email:</td>
            <td style="padding: 6px 0; color: #1e293b;"><a href="mailto:{sender_email}" style="color: #2563eb; text-decoration: none;">{sender_email}</a></td>
          </tr>
          <tr>
            <td style="padding: 6px 0; font-weight: bold; color: #64748b;">Role:</td>
            <td style="padding: 6px 0; color: #1e293b;">{sender_role}</td>
          </tr>
          <tr>
            <td style="padding: 6px 0; font-weight: bold; color: #64748b;">Department:</td>
            <td style="padding: 6px 0; color: #1e293b;">{sender_dept}</td>
          </tr>
          <tr>
            <td style="padding: 6px 0; font-weight: bold; color: #64748b;">Submitted From:</td>
            <td style="padding: 6px 0; color: #1e293b;">Inventory AI Assistant</td>
          </tr>
          <tr>
            <td style="padding: 6px 0; font-weight: bold; color: #64748b;">Timestamp:</td>
            <td style="padding: 6px 0; color: #1e293b;">{server_timestamp}</td>
          </tr>
        </table>
        
        <h3 style="color: #1e293b; border-top: 1px solid #f1f5f9; padding-top: 12px; margin-bottom: 8px;">Issue Description:</h3>
        <div style="background-color: #f8fafc; border: 1px solid #e2e8f0; padding: 12px; border-radius: 6px; white-space: pre-wrap; color: #334155; font-size: 0.95rem;">{description}</div>
        
        {f'<div style="margin-top: 16px; font-size: 0.85rem; color: #64748b;">📎 Attachment included: <strong>{filename}</strong></div>' if filename else ''}
      </body>
    </html>
    """

    # Dynamic SMTP Profile Resolution
    profile_name = str(settings.EMAIL_DEFAULT_PROFILE or "").upper().strip()
    
    # 1. Resolve host
    host = os.getenv(f"EMAIL_{profile_name}_HOST") if profile_name else None
    host = host or settings.EMAIL_HOST
    
    # 2. Resolve port
    port_str = os.getenv(f"EMAIL_{profile_name}_PORT") if profile_name else None
    port = int(port_str) if port_str else settings.EMAIL_PORT
    
    # 3. Resolve user
    user = os.getenv(f"EMAIL_{profile_name}_USER") if profile_name else None
    user = user or settings.EMAIL_USER
    
    # 4. Resolve password
    password = os.getenv(f"EMAIL_{profile_name}_PASSWORD") if profile_name else None
    password = password or settings.EMAIL_PASSWORD
    
    # 5. Resolve sender from
    sender_from = os.getenv(f"EMAIL_{profile_name}_FROM") if profile_name else None
    sender_from = sender_from or settings.EMAIL_FROM or user
    
    # 6. Resolve secure flag
    secure_str = os.getenv(f"EMAIL_{profile_name}_SECURE") if profile_name else None
    if secure_str is not None:
        secure_val = secure_str.lower() == "true"
    else:
        secure_val = settings.EMAIL_SECURE

    smtp_configured = all([host, port, user, password])
    print(f"[DEBUG SMTP] Profile: '{profile_name or 'default'}'. Host: {host}, Port: {port}, User: {user}. Configured: {smtp_configured}")
    
    if smtp_configured:
        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = sender_from
            msg["To"] = recipient_email
            msg["Reply-To"] = sender_email
            
            msg.attach(MIMEText(email_body, "plain"))
            msg.attach(MIMEText(html_body, "html"))
            
            if file_data and filename:
                part = MIMEBase("application", "octet-stream")
                part.set_payload(file_data)
                encoders.encode_base64(part)
                part.add_header(
                    "Content-Disposition",
                    f"attachment; filename= {filename}",
                )
                msg.attach(part)
            
            # Send the email
            # Decide between SMTP_SSL (port 465) or standard SMTP with STARTTLS (port 587)
            is_ssl = secure_val or port == 465
            if is_ssl:
                server_conn = smtplib.SMTP_SSL(host, port)
            else:
                server_conn = smtplib.SMTP(host, port)
                
            with server_conn as server:
                if not is_ssl:
                    server.starttls()
                server.login(user, password)
                server.sendmail(user, recipient_email, msg.as_string())
            
            logger.info(f"Support email successfully sent to {recipient_email} using profile '{profile_name or 'default'}'")
            return True
            
        except Exception as smtp_err:
            logger.error(f"SMTP delivery to {recipient_email} using profile '{profile_name or 'default'}' failed: {smtp_err}")
            # Raise exception in production to prevent false success feedback
            raise RuntimeError(f"Email delivery failed: {smtp_err}")
            
    # Fallback to local log file only in DEVELOPMENT (when SMTP settings are missing)
    try:
        log_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "support_emails.log")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("\n" + "="*60 + "\n")
            f.write(f"SUBJECT: {subject}\n")
            f.write(f"TO: {recipient_email}\n")
            f.write(email_body)
            f.write("="*60 + "\n")
            
        logger.info(f"Support request saved locally to {log_path} (SMTP not configured).")
        return True
    except Exception as log_err:
        logger.error(f"Failed to write fallback log file: {log_err}")
        return False
