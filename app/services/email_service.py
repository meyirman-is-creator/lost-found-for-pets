import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.core.config import settings
import logging
from email.header import Header
from email import charset

logger = logging.getLogger(__name__)

# Настраиваем правильную кодировку для email
charset.add_charset('utf-8', charset.SHORTEST, charset.QP, 'utf-8')


class EmailService:
    def __init__(self):
        self.server = settings.SMTP_SERVER
        self.port = settings.SMTP_PORT
        self.username = settings.SMTP_USERNAME
        self.password = settings.SMTP_PASSWORD
        self.sender = settings.EMAIL_FROM

    def send_verification_email(self, to_email, verification_code):
        """
        Send verification email with the code
        """
        subject = "Verify your LostPets account"

        html_content = f"""
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; background-color: #f9f9f9; padding: 20px; border-radius: 5px; }}
                .header {{ background-color: #4CAF50; color: white; padding: 10px; text-align: center; border-radius: 5px 5px 0 0; }}
                .content {{ padding: 20px; }}
                .code {{ font-size: 24px; font-weight: bold; text-align: center; margin: 20px 0; letter-spacing: 5px; }}
                .footer {{ font-size: 12px; text-align: center; margin-top: 20px; color: #999; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>LostPets Email Verification</h2>
                </div>
                <div class="content">
                    <p>Hello,</p>
                    <p>Thank you for registering with LostPets. To complete your registration, please use the verification code below:</p>
                    <div class="code">{verification_code}</div>
                    <p>This code will expire in {settings.VERIFICATION_CODE_EXPIRE_MINUTES} minutes.</p>
                    <p>If you did not request this verification, please ignore this email.</p>
                </div>
                <div class="footer">
                    <p>LostPets - Helping reunite pets with their owners</p>
                </div>
            </div>
        </body>
        </html>
        """

        try:
            msg = MIMEMultipart('alternative')
            # Используем Header для правильной кодировки темы письма
            msg['Subject'] = Header(subject, 'utf-8')
            msg['From'] = self.sender
            msg['To'] = to_email

            # Явно указываем кодировку UTF-8 для содержимого письма
            html_part = MIMEText(html_content, 'html', _charset='utf-8')
            msg.attach(html_part)

            # Добавляем логирование для отладки
            logger.info(f"Attempting to send email to {to_email} using server {self.server}:{self.port}")
            logger.info(f"Using SMTP username: {self.username}")

            with smtplib.SMTP(self.server, self.port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)

            logger.info(f"Email successfully sent to {to_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send verification email: {e}")
            return False

    def send_match_notification_email(self, to_email, pet_name, similarity_score, found_location=None):
        """
        Send email notification about a potential pet match
        """
        subject = f"Potential Match Found for your pet {pet_name}"

        location_info = f" in {found_location}" if found_location else ""

        html_content = f"""
        <html>
        <head>
            <meta charset="utf-8">
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; color: #333; }}
                .container {{ max-width: 600px; margin: 0 auto; background-color: #f9f9f9; padding: 20px; border-radius: 5px; }}
                .header {{ background-color: #2196F3; color: white; padding: 10px; text-align: center; border-radius: 5px 5px 0 0; }}
                .content {{ padding: 20px; }}
                .match-info {{ font-size: 18px; font-weight: bold; margin: 20px 0; }}
                .button {{ display: inline-block; background-color: #4CAF50; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px; }}
                .footer {{ font-size: 12px; text-align: center; margin-top: 20px; color: #999; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h2>LostPets Match Alert</h2>
                </div>
                <div class="content">
                    <p>Hello,</p>
                    <p>Good news! Someone has found a pet that might be your {pet_name}{location_info}.</p>
                    <div class="match-info">Match similarity: {similarity_score:.1%}</div>
                    <p>Please log in to the LostPets app to view the details and contact the finder.</p>
                    <p><a href="#" class="button">Open LostPets App</a></p>
                </div>
                <div class="footer">
                    <p>LostPets - Helping reunite pets with their owners</p>
                </div>
            </div>
        </body>
        </html>
        """

        try:
            msg = MIMEMultipart('alternative')
            # Используем Header для правильной кодировки темы письма
            msg['Subject'] = Header(subject, 'utf-8')
            msg['From'] = self.sender
            msg['To'] = to_email

            # Явно указываем кодировку UTF-8 для содержимого письма
            html_part = MIMEText(html_content, 'html', _charset='utf-8')
            msg.attach(html_part)

            with smtplib.SMTP(self.server, self.port) as server:
                server.starttls()
                server.login(self.username, self.password)
                server.send_message(msg)

            return True
        except Exception as e:
            logger.error(f"Failed to send match notification email: {e}")
            return False


# Singleton instance
email_service = EmailService()