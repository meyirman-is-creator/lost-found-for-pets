# LostPets API

API для мобильного приложения поиска потерянных животных с использованием компьютерного зрения.

## Основные возможности

- Регистрация и аутентификация пользователей с верификацией по email
- Управление профилями питомцев (добавление, редактирование, изменение статуса)
- Поиск потерянных питомцев
- Загрузка фотографий найденных животных и сравнение с базой данных потерянных
- Уведомления о возможных совпадениях
- Интеграция с AWS S3 для хранения фотографий

## Технологии

- **Backend**: Python 3.10, FastAPI
- **База данных**: PostgreSQL
- **Хранение файлов**: AWS S3
- **Алгоритмы компьютерного зрения**: OpenCV, Scikit-image
- **Docker** для контейнеризации

## Установка и запуск

### Локальная разработка

1. Клонируйте репозиторий:
   ```bash
   git clone https://github.com/your-username/lostpets-api.git
   cd lostpets-api
   ```

2. Создайте и активируйте виртуальное окружение:
   ```bash
   python -m venv venv
   source venv/bin/activate  # для Linux/Mac
   venv\Scripts\activate     # для Windows
   ```

3. Установите зависимости:
   ```bash
   pip install -r requirements.txt
   ```

4. Создайте файл `.env` на основе примера выше с вашими настройками.

5. Создайте базу данных PostgreSQL:
   ```bash
   createdb lostpets_db
   ```

6. Запустите сервер:
   ```bash
   python run.py
   ```

7. Откройте документацию API в браузере:
   ```
   http://localhost:8000/api/v1/docs
   ```

### Запуск в Docker

1. Убедитесь, что у вас установлены Docker и Docker Compose.

2. Создайте файл `.env` с необходимыми настройками.

3. Запустите контейнеры:
   ```bash
   docker-compose up -d
   ```

4. Проверьте запущенные контейнеры:
   ```bash
   docker-compose ps
   ```

5. Откройте документацию API в браузере:
   ```
   http://localhost:8000/api/v1/docs
   ```

## Настройка AWS S3

1. Создайте аккаунт AWS и S3 бакет (если еще не создан).

2. Получите ключи доступа AWS (Access Key ID и Secret Access Key).

3. Добавьте ключи в файл `.env`:
   ```
   AWS_ACCESS_KEY_ID=ваш_ключ_доступа
   AWS_SECRET_ACCESS_KEY=ваш_секретный_ключ
   AWS_REGION=регион_бакета
   AWS_BUCKET_NAME=имя_бакета
   ```

## Описание API

### Аутентификация

- **POST /api/v1/auth/register** - Регистрация нового пользователя
- **POST /api/v1/auth/verify** - Верификация электронной почты
- **POST /api/v1/auth/login** - Вход в систему и получение токена
- **POST /api/v1/auth/resend-verification** - Повторная отправка кода верификации

### Пользователи

- **GET /api/v1/users/me** - Получение информации о текущем пользователе
- **PUT /api/v1/users/me** - Обновление профиля пользователя
- **DELETE /api/v1/users/me** - Удаление аккаунта пользователя

### Питомцы

- **GET /api/v1/pets/lost** - Получение списка потерянных питомцев
- **GET /api/v1/pets/lost/{pet_id}** - Детальная информация о потерянном питомце
- **GET /api/v1/pets/my** - Получение списка питомцев текущего пользователя
- **POST /api/v1/pets** - Добавление нового питомца
- **PATCH /api/v1/pets/{pet_id}** - Обновление информации о питомце
- **POST /api/v1/pets/upload-photo/{pet_id}** - Загрузка новой фотографии питомца
- **DELETE /api/v1/pets/{pet_id}** - Удаление питомца
- **POST /api/v1/pets/search** - Поиск похожих питомцев по фотографии

### Уведомления

- **GET /api/v1/notifications** - Получение списка уведомлений
- **GET /api/v1/notifications/{notification_id}** - Получение конкретного уведомления
- **PATCH /api/v1/notifications/{notification_id}/mark-read** - Отметить уведомление как прочитанное
- **PATCH /api/v1/notifications/mark-all-read** - Отметить все уведомления как прочитанные
- **DELETE /api/v1/notifications/{notification_id}** - Удаление уведомления

## Архитектура проекта

```
lostpets_project/
├── app/
│   ├── api/
│   │   ├── endpoints/
│   │   │   ├── auth.py
│   │   │   ├── users.py
│   │   │   ├── pets.py
│   │   │   └── notifications.py
│   │   ├── dependencies.py
│   │   └── api.py
│   ├── core/
│   │   ├── config.py
│   │   └── security.py
│   ├── db/
│   │   └── database.py
│   ├── models/
│   │   └── models.py
│   ├── schemas/
│   │   └── schemas.py
│   ├── services/
│   │   ├── aws/
│   │   │   └── s3.py
│   │   ├── cv/
│   │   │   └── similarity.py
│   │   └── email_service.py
│   ├── __init__.py
│   └── main.py
├── .env
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── README.md
└── run.py
```

## Разработчикам

### Добавление новых эндпоинтов

1. Создайте новый файл в директории `app/api/endpoints/`
2. Добавьте маршрут в `app/api/api.py`

### Изменение структуры базы данных

1. Внесите изменения в модели в файле `app/models/models.py`
2. Обновите схемы Pydantic в файле `app/schemas/schemas.py`
3. При необходимости выполните миграцию базы данных