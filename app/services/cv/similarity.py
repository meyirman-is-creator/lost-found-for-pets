import cv2
import numpy as np
from scipy.spatial.distance import cosine
import logging
import requests
from io import BytesIO
import base64
from skimage.metrics import structural_similarity as ssim

logger = logging.getLogger(__name__)


class PetSimilarityService:
    def __init__(self):
        # Инициализация детектора ключевых точек
        self.sift = cv2.SIFT_create()
        # Инициализация сопоставителя признаков
        self.bf = cv2.BFMatcher()
        # Создание HOG дескриптора для извлечения признаков формы
        self.hog = cv2.HOGDescriptor()

    def _download_image(self, image_url):
        """Загрузка изображения по URL"""
        try:
            response = requests.get(image_url)
            response.raise_for_status()

            img_array = np.asarray(bytearray(response.content), dtype=np.uint8)
            img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            return img
        except Exception as e:
            logger.error(f"Error downloading image from {image_url}: {e}")
            return None

    def _preprocess_image(self, img):
        """Предобработка изображения"""
        if img is None:
            return None

        # Изменение размера изображения
        img = cv2.resize(img, (300, 300))

        # Преобразование в оттенки серого
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

        # Применение размытия по Гауссу для уменьшения шума
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)

        # Улучшение контраста
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
        enhanced = clahe.apply(blurred)

        return enhanced

    def _extract_features_sift(self, img):
        """Извлечение признаков SIFT из изображения"""
        processed_img = self._preprocess_image(img)
        if processed_img is None:
            return None, None

        # Обнаружение ключевых точек и вычисление дескрипторов
        keypoints, descriptors = self.sift.detectAndCompute(processed_img, None)
        return keypoints, descriptors

    def _extract_features_hog(self, img):
        """Извлечение признаков HOG из изображения"""
        if img is None:
            return None

        img = cv2.resize(img, (128, 128))
        features = self.hog.compute(img)
        return features

    def _extract_color_histogram(self, img):
        """Извлечение цветовой гистограммы"""
        if img is None:
            return None

        # Конвертация в цветовое пространство HSV
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

        # Вычисление гистограммы
        hist = cv2.calcHist([hsv], [0, 1, 2], None, [8, 8, 8], [0, 180, 0, 256, 0, 256])

        # Нормализация гистограммы
        cv2.normalize(hist, hist)

        return hist.flatten()

    def _compare_features_sift(self, desc1, desc2):
        """Сравнение признаков SIFT"""
        if desc1 is None or desc2 is None or len(desc1) == 0 or len(desc2) == 0:
            return 0.0

        # Поиск соответствий между дескрипторами
        matches = self.bf.knnMatch(desc1, desc2, k=2)

        # Применение теста соотношения для фильтрации хороших совпадений
        good_matches = []
        for m, n in matches:
            if m.distance < 0.75 * n.distance:
                good_matches.append(m)

        # Вычисление оценки сходства
        similarity_score = len(good_matches) / max(len(desc1), len(desc2))
        return similarity_score

    def _compare_features_hog(self, feat1, feat2):
        """Сравнение признаков HOG"""
        if feat1 is None or feat2 is None:
            return 0.0

        # Вычисление косинусного расстояния между признаками
        sim = 1 - cosine(feat1.flatten(), feat2.flatten())
        return max(0, sim)  # Ensure non-negative similarity

    def _compare_color_histograms(self, hist1, hist2):
        """Сравнение цветовых гистограмм"""
        if hist1 is None or hist2 is None:
            return 0.0

        # Вычисление метрики сравнения гистограмм
        sim = cv2.compareHist(np.float32(hist1), np.float32(hist2), cv2.HISTCMP_CORREL)
        return max(0, sim)  # Ensure non-negative similarity

    def _compute_structural_similarity(self, img1, img2):
        """Вычисление показателя структурного сходства (SSIM)"""
        if img1 is None or img2 is None:
            return 0.0

        # Преобразование в оттенки серого
        gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
        gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

        # Изменение размера
        gray1 = cv2.resize(gray1, (300, 300))
        gray2 = cv2.resize(gray2, (300, 300))

        # Вычисление SSIM
        similarity = ssim(gray1, gray2)
        return max(0, similarity)  # Ensure non-negative similarity

    def compute_similarity(self, img1_source, img2_source):
        """
        Вычисление общей оценки сходства между двумя изображениями.

        Args:
            img1_source: URL или base64 первого изображения
            img2_source: URL или base64 второго изображения

        Returns:
            float: Оценка сходства от 0 до 1
        """
        # Загрузка изображений
        if img1_source.startswith('http'):
            img1 = self._download_image(img1_source)
        else:
            # Обработка base64
            try:
                if "base64," in img1_source:
                    img1_source = img1_source.split("base64,")[1]
                img_data = base64.b64decode(img1_source)
                img_array = np.asarray(bytearray(BytesIO(img_data).read()), dtype=np.uint8)
                img1 = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            except Exception as e:
                logger.error(f"Error decoding base64 image: {e}")
                return 0.0

        if img2_source.startswith('http'):
            img2 = self._download_image(img2_source)
        else:
            # Обработка base64
            try:
                if "base64," in img2_source:
                    img2_source = img2_source.split("base64,")[1]
                img_data = base64.b64decode(img2_source)
                img_array = np.asarray(bytearray(BytesIO(img_data).read()), dtype=np.uint8)
                img2 = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            except Exception as e:
                logger.error(f"Error decoding base64 image: {e}")
                return 0.0

        if img1 is None or img2 is None:
            logger.error("Failed to load one or both images")
            return 0.0

        # Извлечение признаков
        keypoints1, descriptors1 = self._extract_features_sift(img1)
        keypoints2, descriptors2 = self._extract_features_sift(img2)

        hog_features1 = self._extract_features_hog(img1)
        hog_features2 = self._extract_features_hog(img2)

        color_hist1 = self._extract_color_histogram(img1)
        color_hist2 = self._extract_color_histogram(img2)

        # Сравнение признаков
        sift_similarity = self._compare_features_sift(descriptors1, descriptors2)
        hog_similarity = self._compare_features_hog(hog_features1, hog_features2)
        color_similarity = self._compare_color_histograms(color_hist1, color_hist2)
        structural_similarity = self._compute_structural_similarity(img1, img2)

        # Взвешенное среднее для итоговой оценки
        weights = {
            'sift': 0.4,
            'hog': 0.2,
            'color': 0.3,
            'ssim': 0.1
        }

        final_similarity = (
                weights['sift'] * sift_similarity +
                weights['hog'] * hog_similarity +
                weights['color'] * color_similarity +
                weights['ssim'] * structural_similarity
        )

        logger.info(f"Similarity details - SIFT: {sift_similarity:.4f}, HOG: {hog_similarity:.4f}, "
                    f"Color: {color_similarity:.4f}, SSIM: {structural_similarity:.4f}, "
                    f"Final: {final_similarity:.4f}")

        return final_similarity


# Singleton instance
similarity_service = PetSimilarityService()