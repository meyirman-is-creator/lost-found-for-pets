# app/services/cv/similarity.py
import logging
import os
import numpy as np
from io import BytesIO
import base64
import requests
import traceback

logger = logging.getLogger(__name__)

# Flag for TensorFlow availability
TENSORFLOW_AVAILABLE = False

try:
    import cv2
    import tensorflow as tf
    from tensorflow.keras.applications.mobilenet_v2 import MobileNetV2, preprocess_input
    from sklearn.metrics.pairwise import cosine_similarity

    # Force CPU usage instead of GPU to avoid protobuf issues
    os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
    tf.config.set_visible_devices([], 'GPU')

    TENSORFLOW_AVAILABLE = True
    logger.info("TensorFlow and OpenCV are available for image similarity computation")
except ImportError:
    logger.warning("TensorFlow or OpenCV not available, using fallback similarity service")


class PetSimilarityService:
    def __init__(self):
        self.model = None
        self.img_size = (224, 224)  # Standard input size for MobileNetV2

        if not TENSORFLOW_AVAILABLE:
            logger.warning("TensorFlow not available, will return fixed similarity score")
            return

        try:
            # Load MobileNetV2 model without top classification layers
            self.model = MobileNetV2(weights='imagenet',
                                     include_top=False,
                                     pooling='avg',
                                     input_shape=(self.img_size[0], self.img_size[1], 3))

            # Freeze all layers
            for layer in self.model.layers:
                layer.trainable = False

            logger.info("MobileNetV2 model successfully loaded")
        except Exception as e:
            logger.error(f"Error loading MobileNetV2 model: {e}")
            logger.error(traceback.format_exc())
            self.model = None

    def _download_image(self, image_url):
        if not TENSORFLOW_AVAILABLE:
            return None

        try:
            logger.debug(f"Downloading image from URL: {image_url}")
            response = requests.get(image_url, timeout=10)
            response.raise_for_status()

            # Convert content to numpy array
            img_array = np.asarray(bytearray(response.content), dtype=np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

            if img is None:
                logger.error(f"Failed to decode image from URL: {image_url}")
                return None

            # Process the image
            return self._preprocess_image(img)
        except Exception as e:
            logger.error(f"Error downloading image from {image_url}: {e}")
            logger.error(traceback.format_exc())
            return None

    def _process_base64_image(self, base64_string):
        if not TENSORFLOW_AVAILABLE:
            return None

        try:
            # Handle data URLs
            if "base64," in base64_string:
                base64_string = base64_string.split("base64,")[1]

            # Decode base64 to bytes
            img_data = base64.b64decode(base64_string)

            # Convert to numpy array
            img_array = np.asarray(bytearray(img_data), dtype=np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

            if img is None:
                logger.error("Failed to decode base64 image")
                return None

            # Process the image
            return self._preprocess_image(img)
        except Exception as e:
            logger.error(f"Error processing base64 image: {e}")
            logger.error(traceback.format_exc())
            return None

    def _preprocess_image(self, img):
        if img is None:
            return None

        try:
            # Convert from BGR to RGB color format
            img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            # Get original dimensions
            h, w = img_rgb.shape[:2]

            # Preserve aspect ratio while resizing
            if h > w:
                new_h = self.img_size[0]
                new_w = int(w * (new_h / h))
            else:
                new_w = self.img_size[1]
                new_h = int(h * (new_w / w))

            # Resize the image
            resized = cv2.resize(img_rgb, (new_w, new_h), interpolation=cv2.INTER_AREA)

            # Create a blank canvas of target size
            canvas = np.zeros((self.img_size[0], self.img_size[1], 3), dtype=np.uint8)

            # Calculate offset to center the image
            y_offset = (self.img_size[0] - new_h) // 2
            x_offset = (self.img_size[1] - new_w) // 2

            # Place the resized image on the canvas
            canvas[y_offset:y_offset + new_h, x_offset:x_offset + new_w] = resized

            return canvas
        except Exception as e:
            logger.error(f"Error preprocessing image: {e}")
            logger.error(traceback.format_exc())
            return None

    def _get_image_embedding(self, img):
        if not TENSORFLOW_AVAILABLE or self.model is None or img is None:
            return None

        try:
            # Convert to float32 and normalize
            img_array = img.astype(np.float32)

            # Add batch dimension
            img_array = np.expand_dims(img_array, axis=0)

            # Preprocess image for the model
            img_array = preprocess_input(img_array)

            # Get embedding vector with output suppressed
            with tf.device('/CPU:0'):  # Force CPU usage
                embedding = self.model.predict(img_array, verbose=0)

            # Normalize the embedding vector for better similarity comparison
            embedding_norm = embedding / np.linalg.norm(embedding)

            return embedding_norm
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            logger.error(traceback.format_exc())
            return None

    def compute_similarity(self, img1_source, img2_source):
        if not TENSORFLOW_AVAILABLE or self.model is None:
            logger.warning("TensorFlow or model not available, returning fixed similarity value")
            return 0.5

        logger.info("Computing similarity between two images")

        # Load and process first image
        if isinstance(img1_source, str) and img1_source.startswith('http'):
            img1 = self._download_image(img1_source)
            logger.debug(f"Processed first image from URL: {img1_source[:50]}...")
        else:
            img1 = self._process_base64_image(img1_source)
            logger.debug("Processed first image from base64 data")

        # Load and process second image
        if isinstance(img2_source, str) and img2_source.startswith('http'):
            img2 = self._download_image(img2_source)
            logger.debug(f"Processed second image from URL: {img2_source[:50]}...")
        else:
            img2 = self._process_base64_image(img2_source)
            logger.debug("Processed second image from base64 data")

        if img1 is None or img2 is None:
            logger.error("Failed to load one or both images")
            return 0.0

        # Get embeddings for images
        img1_embedding = self._get_image_embedding(img1)
        img2_embedding = self._get_image_embedding(img2)

        if img1_embedding is None or img2_embedding is None:
            logger.error("Failed to generate embeddings for one or both images")
            return 0.0

        # Compute cosine similarity between feature vectors
        similarity_score = cosine_similarity(img1_embedding, img2_embedding)[0][0]

        # Apply normalization to emphasize differences
        normalized_score = float(similarity_score)

        logger.info(f"Raw similarity score: {similarity_score:.4f}, Normalized: {normalized_score:.4f}")

        return normalized_score


# Singleton instance
similarity_service = PetSimilarityService()