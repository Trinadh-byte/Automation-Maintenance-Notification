import boto3
import smtplib
import imaplib
import email
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import getaddresses, formataddr
import os
import sys
from datetime import datetime

# --- CONFIGURATION ---
# AWS RDS Config
AWS_REGION = 'us-east-1'  # <--- CHANGE THIS IF YOUR RDS IS IN MUMBAI (ap-south-1) OR ELSEWHERE
DB_INSTANCE_ID = 'devdatabase' # <--- REPLACE WITH YOUR EXACT RDS INSTANCE IDENTIFIER

# Email Config
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
IMAP_SERVER = "imap.gmail.com"

# Secrets (From GitHub Actions)
EMAIL_USER = os.environ['EMAIL_USER']
EMAIL_PASS = os.environ['EMAIL_PASS']
AWS_KEY = os.environ['AWS_ACCESS_KEY_ID']
AWS_SECRET = os.environ['AWS_SECRET_ACCESS_KEY']

# Target Audience
RECIPIENTS = [
    "trinadh5121@gmail.com",
    "keerthisetty2001@gmail.com",
    "2021tm70803@wilp.bitspilani.ac.in"
]

# The Fixed Subject Line (Script searches for this)
MAIL_SUBJECT = "Weekly RDS Maintenance Report"

def get_rds_details():
    """Fetches details from your specific RDS Postgres instance."""
    try:
        client = boto3.client(
            'rds',
            region_name=AWS_REGION,
            aws_access_key_id=AWS_KEY,
            aws_secret_access_key=AWS_SECRET
        )
        
        # specific call to describe your instance
        response = client.describe_db_instances(DBInstanceIdentifier=DB_INSTANCE_ID)
        db = response['DBInstances'][0]
        
        # Extract meaningful data
        return {
            "engine": db['Engine'],
            "version": db['EngineVersion'],
            "status": db['DBInstanceStatus'],
            "endpoint": db.get('Endpoint', {}).get('Address', 'No Endpoint'),
            "maintenance_window": db['PreferredMaintenanceWindow'],
            "pending_mods": db.get('PendingModifiedValues', {})
        }
    except Exception as e:
        print(f"❌ Error fetching RDS details: {e}")
        # Return a dummy dict so the email still sends (alerting you of the error)
        return {"engine": "Error", "version": "Error", "status": str(e), "pending_mods": {}}

def find_existing_thread():
    """Searches Inbox for the latest email with our specific subject."""
    try:
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_USER, EMAIL_PASS)
        mail.select("inbox")

        # Search for subject
        status, messages = mail.search(None, f'(SUBJECT "{MAIL_SUBJECT}")')
        email_ids = messages[0].split()

        if not email_ids:
            mail.logout()
            return None

        # Fetch the latest one
        latest_id = email_ids[-1]
        _, msg_data = mail.fetch(latest_id, "(RFC822)")
        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)
        mail.logout()
        return msg
    except Exception as e:
        print(f"⚠️ IMAP Search Error (First run?): {e}")
        return None

def send_report(data):
    original_msg = find_existing_thread()
    msg = MIMEMultipart()
    
    # HTML Body content
    html_body = f"""
    <html>
    <body>
        <h3 style="color: #2E86C1;">RDS Maintenance Update</h3>
        <p><b>Target Database:</b> {DB_INSTANCE_ID}</p>
        <table border="1" cellpadding="5" cellspacing="0" style="border-collapse: collapse;">
            <tr style="background-color: #f2f2f2;"><th>Parameter</th><th>Value</th></tr>
            <tr><td>Engine</td><td>{data.get('engine')}</td></tr>
            <tr><td>Current Version</td><td>{data.get('version')}</td></tr>
            <tr><td>Status</td><td>{data.get('status')}</td></tr>
            <tr><td>Maintenance Window</td><td>{data.get('maintenance_window')}</td></tr>
        </table>
        <p><b>Pending Modifications:</b> {data.get('pending_mods') if data.get('pending_mods') else "None"}</p>
        <br>
        <p>Regards,<br>Cloud Automation Bot</p>
    </body>
    </html>
    """

    # --- LOGIC: NEW MAIL VS REPLY ---
    if original_msg is None:
        print("🔵 No existing thread found. Starting a NEW chain.")
        msg['Subject'] = MAIL_SUBJECT
        msg['To'] = ", ".join(RECIPIENTS)
        msg['Cc'] = EMAIL_USER # CC Yourself so it lands in your Inbox for next time!
        
        final_to_list = RECIPIENTS + [EMAIL_USER]
        
    else:
        print(f"🟢 Found existing thread: {original_msg['Subject']}. Replying...")
        
        # 1. Threading Headers
        new_subject = original_msg['Subject']
        if not new_subject.lower().startswith("re:"):
            new_subject = "Re: " + new_subject
        msg['Subject'] = new_subject
        msg['In-Reply-To'] = original_msg['Message-ID']
        msg['References'] = (original_msg['References'] or '') + ' ' + original_msg['Message-ID']

        # 2. Reply All Logic
        # Get everyone from the original email to ensure we don't drop anyone
        tos = original_msg.get_all('to', [])
        ccs = original_msg.get_all('cc', [])
        all_addrs = getaddresses(tos + ccs + [original_msg.get('from')])
        
        # Extract pure email strings
        reply_list = [addr for name, addr in all_addrs]
        
        # Merge with your mandatory list (in case someone was removed)
        final_set = set(reply_list + RECIPIENTS + [EMAIL_USER])
        
        # Remove the Bot itself from the TO list to prevent self-looping display (optional)
        # But we KEEP it in the sending list so it lands in the inbox
        
        msg['To'] = original_msg['To'] # Keep original display
        msg['Cc'] = original_msg['Cc'] # Keep original display
        
        final_to_list = list(final_set)

    msg['From'] = EMAIL_USER
    msg.attach(MIMEText(html_body, 'html'))

    # SENDING
    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(EMAIL_USER, EMAIL_PASS)
        server.sendmail(EMAIL_USER, final_to_list, msg.as_string())
        server.quit()
        print(f"✅ Email Sent Successfully to: {final_to_list}")
    except Exception as e:
        print(f"❌ SMTP Error: {e}")

if __name__ == "__main__":
    print("Fetching RDS Details...")
    rds_data = get_rds_details()
    send_report(rds_data)