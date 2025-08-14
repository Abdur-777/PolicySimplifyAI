# email_utils.py
import os, smtplib, ssl
from email.message import EmailMessage

def send_email_with_pdf(to_addr: str, subject: str, body: str, pdf_bytes: bytes, filename: str = "AuditPack.pdf"):
    host = os.getenv("SMTP_HOST")
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    pw   = os.getenv("SMTP_PASS")
    if not (host and port and user and pw):
        raise RuntimeError("SMTP env not set (SMTP_HOST/SMTP_PORT/SMTP_USER/SMTP_PASS)")

    msg = EmailMessage()
    msg["From"] = user; msg["To"] = to_addr; msg["Subject"] = subject
    msg.set_content(body)
    msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=filename)
    ctx = ssl.create_default_context()
    with smtplib.SMTP(host, port) as s:
        s.starttls(context=ctx); s.login(user, pw); s.send_message(msg)
