import boto3
import logging
from botocore.exceptions import ClientError
from app.core.config import settings
import base64
import uuid
from io import BytesIO

logger = logging.getLogger(__name__)


class S3Client:
    def __init__(self):
        self.s3 = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION
        )
        self.bucket_name = settings.AWS_BUCKET_NAME

    def upload_file(self, file_obj, file_name=None, content_type="image/jpeg"):
        if file_name is None:
            file_name = f"{uuid.uuid4()}.jpg"

        try:
            if isinstance(file_obj, bytes):
                file_obj = BytesIO(file_obj)
                file_obj.seek(0)

            self.s3.upload_fileobj(
                file_obj,
                self.bucket_name,
                file_name,
                ExtraArgs={"ContentType": content_type}
            )
            url = f"https://{self.bucket_name}.s3.{settings.AWS_REGION}.amazonaws.com/{file_name}"
            logger.info(f"Successfully uploaded file to S3: {url}")
            return url
        except Exception as e:
            logger.error(f"Error uploading file to S3: {e}")
            return None

    def upload_base64_image(self, base64_string, file_name=None):
        try:
            if "base64," in base64_string:
                base64_string = base64_string.split("base64,")[1]

            image_data = base64.b64decode(base64_string)
            file_obj = BytesIO(image_data)
            file_obj.seek(0)

            if file_name is None:
                file_name = f"{uuid.uuid4()}.jpg"

            return self.upload_file(file_obj, file_name)
        except Exception as e:
            logger.error(f"Error uploading base64 image to S3: {e}")
            return None

    def delete_file(self, file_url):
        try:
            if not file_url:
                return True

            if self.bucket_name in file_url:
                file_key = file_url.split("/")[-1]
            else:
                file_key = file_url

            self.s3.delete_object(Bucket=self.bucket_name, Key=file_key)
            logger.info(f"Successfully deleted file from S3: {file_key}")
            return True
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'AccessDenied':
                logger.error(f"Access denied when deleting file from S3: {e}")
            else:
                logger.error(f"Error deleting file from S3: {e}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error deleting file from S3: {e}")
            return False

    def get_file(self, file_key):
        try:
            response = self.s3.get_object(Bucket=self.bucket_name, Key=file_key)
            return response['Body'].read()
        except Exception as e:
            logger.error(f"Error getting file from S3: {e}")
            return None


s3_client = S3Client()