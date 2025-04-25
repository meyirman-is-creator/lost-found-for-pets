# app/services/cv/similarity.py
import logging
import os
import numpy as np
from io import BytesIO
import base64
import requests

logger = logging.getLogger(__name__)

# Флаг доступности TensorFlow
TENSORFLOW_AVAILABLE = False

try:
    import cv2
    import tensorflow as tf
    from tensorflow.keras.applications.mobilenet_v2 import MobileNetV2, preprocess_input
    from sklearn.metrics.pairwise import cosine_similarity

    # Принудительно использовать CPU вместо GPU для избежания проблем с protobuf
    os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
    tf.config.set_visible_devices([], 'GPU')

    TENSORFLOW_AVAILABLE = True
except ImportError:
    logger.warning("TensorFlow или OpenCV не доступны, используется заглушка")


class PetSimilarityService:
    def __init__(self):
        """
        Инициализация сервиса сравнения изображений с использованием MobileNetV2.
        """
        self.model = None

        if not TENSORFLOW_AVAILABLE:
            logger.warning("TensorFlow недоступен, будет возвращаться фиксированный балл сходства")
            return

        try:
            # Загрузка модели MobileNetV2 без верхних слоев классификации
            self.model = MobileNetV2(weights='imagenet',
                                     include_top=False,
                                     pooling='avg',
                                     input_shape=(224, 224, 3))

            # Заморозка всех слоев модели
            for layer in self.model.layers:
                layer.trainable = False

            logger.info("MobileNetV2 model successfully loaded")
        except Exception as e:
            logger.error(f"Error loading MobileNetV2 model: {e}")
            self.model = None

    def _download_image(self, image_url):
        """Загрузка изображения по URL"""
        if not TENSORFLOW_AVAILABLE:
            return None

        try:
            response = requests.get(image_url)
            response.raise_for_status()

            # Преобразование содержимого в массив numpy
            img_array = np.asarray(bytearray(response.content), dtype=np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

            # Преобразование из BGR в RGB
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            # Изменение размера изображения
            img = cv2.resize(img, (224, 224))

            return img
        except Exception as e:
            logger.error(f"Error downloading image from {image_url}: {e}")
            return None

    def _process_base64_image(self, base64_string):
        """Обработка изображения из base64 строки"""
        if not TENSORFLOW_AVAILABLE:
            return None

        try:
            if "base64," in base64_string:
                base64_string = base64_string.split("base64,")[1]

            # Декодирование base64 в байты
            img_data = base64.b64decode(base64_string)

            # Преобразование в массив numpy
            img_array = np.asarray(bytearray(img_data), dtype=np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

            # Преобразование из BGR в RGB
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            # Изменение размера изображения
            img = cv2.resize(img, (224, 224))

            return img
        except Exception as e:
            logger.error(f"Error processing base64 image: {e}")
            return None

    def _get_image_embedding(self, img):
        """
        Получение embedding-вектора для изображения.
        """
        if not TENSORFLOW_AVAILABLE or self.model is None or img is None:
            return None

        try:
            # Преобразование в формат float32 и нормализация
            img_array = img.astype(np.float32)

            # Добавление размерности батча
            img_array = np.expand_dims(img_array, axis=0)

            # Предобработка изображения для модели
            img_array = preprocess_input(img_array)

            # Получение embedding-вектора с отключенным выводом
            with tf.device('/CPU:0'):  # Принудительно используем CPU
                embedding = self.model.predict(img_array, verbose=0)

            return embedding
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return None

    def compute_similarity(self, img1_source, img2_source):
        """
        Вычисление оценки сходства между двумя изображениями.
        """
        if not TENSORFLOW_AVAILABLE or self.model is None:
            logger.warning("TensorFlow или модель недоступны, возвращается фиксированное значение сходства")
            return 0.5  # Возвращаем условное среднее значение

        # Загрузка и обработка первого изображения
        if isinstance(img1_source, str) and img1_source.startswith('http'):
            img1 = self._download_image(img1_source)
        else:
            img1 = self._process_base64_image(img1_source)

        # Загрузка и обработка второго изображения
        if isinstance(img2_source, str) and img2_source.startswith('http'):
            img2 = self._download_image(img2_source)
        else:
            img2 = self._process_base64_image(img2_source)

        if img1 is None or img2 is None:
            logger.error("Failed to load one or both images")
            return 0.5

        # Получение embeddings для изображений
        img1_embedding = self._get_image_embedding(img1)
        img2_embedding = self._get_image_embedding(img2)

        if img1_embedding is None or img2_embedding is None:
            logger.error("Failed to generate embeddings for one or both images")
            return 0.5

        # Вычисление косинусного сходства между векторами признаков
        similarity_score = cosine_similarity(img1_embedding, img2_embedding)[0][0]

        logger.info(f"Similarity score: {similarity_score:.4f}")

        return float(similarity_score)


# Singleton instance
similarity_service = PetSimilarityService()