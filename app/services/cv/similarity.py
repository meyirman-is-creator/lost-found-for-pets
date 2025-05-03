import logging
import os
import numpy as np
from io import BytesIO
import base64
import requests
import boto3
import tempfile
from botocore.exceptions import ClientError
from app.core.config import settings

logger = logging.getLogger(__name__)

TENSORFLOW_AVAILABLE = False

try:
    import cv2
    import tensorflow as tf
    from tensorflow.keras.applications.mobilenet_v2 import MobileNetV2, preprocess_input
    from sklearn.metrics.pairwise import cosine_similarity

    os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
    tf.config.set_visible_devices([], 'GPU')

    TENSORFLOW_AVAILABLE = True
except ImportError:
    logger.warning("TensorFlow or OpenCV not available, using fallback similarity service")


class PetSimilarityService:
    def __init__(self):
        self.model = None
        self.s3_client = boto3.client(
            's3',
            aws_access_key_id=settings.AWS_ACCESS_KEY_ID,
            aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY,
            region_name=settings.AWS_REGION
        )
        self.bucket_name = settings.AWS_BUCKET_NAME

        if not TENSORFLOW_AVAILABLE:
            return

        try:
            self.model = MobileNetV2(weights='imagenet',
                                     include_top=False,
                                     pooling='avg',
                                     input_shape=(224, 224, 3))

            for layer in self.model.layers:
                layer.trainable = False
        except Exception as e:
            logger.error(f"Error loading MobileNetV2 model: {e}")
            self.model = None

    def _get_s3_object(self, url):
        try:
            if "s3.amazonaws.com" in url:
                parts = url.split(".amazonaws.com/")
                if len(parts) > 1:
                    key = parts[1]
                    bucket = parts[0].split("://")[1].split(".s3")[0]

                    with tempfile.NamedTemporaryFile() as tmp:
                        self.s3_client.download_file(bucket, key, tmp.name)
                        with open(tmp.name, 'rb') as f:
                            return f.read()
            return None
        except Exception as e:
            logger.error(f"Error accessing S3 object: {e}")
            return None

    def _download_image(self, image_url):
        if not TENSORFLOW_AVAILABLE:
            return None

        try:
            image_data = None

            if "s3.amazonaws.com" in image_url:
                image_data = self._get_s3_object(image_url)
                if image_data is None:
                    return None

                img_array = np.asarray(bytearray(image_data), dtype=np.uint8)
                img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            else:
                response = requests.get(image_url, timeout=10)
                response.raise_for_status()
                img_array = np.asarray(bytearray(response.content), dtype=np.uint8)
                img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

            if img is None:
                return None

            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img_resized = cv2.resize(img_rgb, (224, 224))
            return img_resized
        except Exception as e:
            logger.error(f"Error downloading image from {image_url}: {e}")
            return None

    def _process_base64_image(self, base64_string):
        if not TENSORFLOW_AVAILABLE:
            return None

        try:
            if "base64," in base64_string:
                base64_string = base64_string.split("base64,")[1]

            img_data = base64.b64decode(base64_string)
            img_array = np.asarray(bytearray(img_data), dtype=np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

            if img is None:
                return None

            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
            img_resized = cv2.resize(img_rgb, (224, 224))
            return img_resized
        except Exception as e:
            logger.error(f"Error processing base64 image: {e}")
            return None

    def _get_image_embedding(self, img):
        if not TENSORFLOW_AVAILABLE or self.model is None or img is None:
            return None

        try:
            img_array = img.astype(np.float32)
            img_array = np.expand_dims(img_array, axis=0)
            img_array = preprocess_input(img_array)

            with tf.device('/CPU:0'):
                embedding = self.model.predict(img_array, verbose=0)

            return embedding / np.linalg.norm(embedding)
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return None

    def compute_similarity(self, img1_source, img2_source):
        if not TENSORFLOW_AVAILABLE or self.model is None:
            return 0.5

        try:
            if isinstance(img1_source, str) and img1_source.startswith('http'):
                img1 = self._download_image(img1_source)
            else:
                img1 = self._process_base64_image(img1_source)

            if isinstance(img2_source, str) and img2_source.startswith('http'):
                img2 = self._download_image(img2_source)
            else:
                img2 = self._process_base64_image(img2_source)

            if img1 is None or img2 is None:
                logger.error("Failed to load one or both images")
                return 0.35

            img1_embedding = self._get_image_embedding(img1)
            img2_embedding = self._get_image_embedding(img2)

            if img1_embedding is None or img2_embedding is None:
                logger.error("Failed to generate embeddings for one or both images")
                return 0.35

            similarity_score = cosine_similarity(img1_embedding, img2_embedding)[0][0]

            # Adjust the similarity scale to provide more meaningful results
            # Scale from range [0.5-1.0] to [0.0-1.0] for more intuitive scoring
            adjusted_score = (similarity_score - 0.5) * 2
            adjusted_score = max(0.0, min(1.0, adjusted_score))

            # Add 0.35 as base similarity for pets of the same species and color
            # This will ensure that we still get matches even if visual features don't match well
            final_score = 0.35 + (adjusted_score * 0.65)

            logger.info(f"Raw similarity: {similarity_score:.4f}, Final score: {final_score:.4f}")
            return float(similarity_score)
        except Exception as e:
            logger.error(f"Error computing similarity: {e}")
            return 0.35


similarity_service = PetSimilarityService()