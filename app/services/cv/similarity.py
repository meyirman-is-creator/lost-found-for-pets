import numpy as np
import requests
import logging
import cv2
from io import BytesIO
import base64
import os
import tensorflow as tf
from tensorflow.keras.applications.mobilenet_v2 import MobileNetV2, preprocess_input
from tensorflow.keras.preprocessing import image
from sklearn.metrics.pairwise import cosine_similarity

# Принудительно использовать CPU вместо GPU для избежания проблем с protobuf
os.environ['CUDA_VISIBLE_DEVICES'] = '-1'
tf.config.set_visible_devices([], 'GPU')

logger = logging.getLogger(__name__)


class PetSimilarityService:
    def __init__(self):
        """
        Инициализация сервиса сравнения изображений с использованием MobileNetV2.
        MobileNetV2 - легкая модель, которая работает быстрее и стабильнее чем VGG16.
        """
        try:
            # Загрузка модели MobileNetV2 без верхних слоев классификации
            self.model = MobileNetV2(weights='imagenet',
                                     include_top=False,
                                     pooling='avg',
                                     input_shape=(224, 224, 3))

            # Заморозка всех слоев модели (не требуется дообучение)
            for layer in self.model.layers:
                layer.trainable = False

            logger.info("MobileNetV2 model successfully loaded")
        except Exception as e:
            logger.error(f"Error loading MobileNetV2 model: {e}")
            raise

    def _download_image(self, image_url):
        """Загрузка изображения по URL"""
        try:
            response = requests.get(image_url)
            response.raise_for_status()

            # Преобразование содержимого в массив numpy
            img_array = np.asarray(bytearray(response.content), dtype=np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

            # Преобразование из BGR в RGB (OpenCV использует BGR, а Keras - RGB)
            img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

            # Изменение размера изображения
            img = cv2.resize(img, (224, 224))

            return img
        except Exception as e:
            logger.error(f"Error downloading image from {image_url}: {e}")
            return None

    def _process_base64_image(self, base64_string):
        """Обработка изображения из base64 строки"""
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
        if img is None:
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
        # Загрузка и обработка первого изображения
        if img1_source.startswith('http'):
            img1 = self._download_image(img1_source)
        else:
            img1 = self._process_base64_image(img1_source)

        # Загрузка и обработка второго изображения
        if img2_source.startswith('http'):
            img2 = self._download_image(img2_source)
        else:
            img2 = self._process_base64_image(img2_source)

        if img1 is None or img2 is None:
            logger.error("Failed to load one or both images")
            return 0.0

        # Получение embeddings для изображений
        img1_embedding = self._get_image_embedding(img1)
        img2_embedding = self._get_image_embedding(img2)

        if img1_embedding is None or img2_embedding is None:
            logger.error("Failed to generate embeddings for one or both images")
            return 0.0

        # Вычисление косинусного сходства между векторами признаков
        similarity_score = cosine_similarity(img1_embedding, img2_embedding)[0][0]

        logger.info(f"Similarity score: {similarity_score:.4f}")

        return float(similarity_score)


# Singleton instance
similarity_service = PetSimilarityService()