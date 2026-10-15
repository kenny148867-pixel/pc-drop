PC DROP — Telegram-бот без веб-приложение

Содержимое:
- main.py — код Telegram-бота и FastAPI health/backend
- cards/ — 57 файлов изображений карточек + cards_manifest.json
- pc_builds/ — 5 изображений сборок ПК
- pc_build_rarity_map.json — соответствие редкости сборки изображению
- requirements.txt — зависимости

ВАЖНО ПРО ИЗОБРАЖЕНИЯ:
Все 57 карточек имеют отдельный файл, и название модели связано с правильным ID.
Однако изображения в этом архиве — игровые иллюстрации/заглушки, а НЕ реальные фотографии товаров. Не выдавайте их за фотографии производителя. Чтобы выполнить требование именно реальных фото, картинки нужно заменить на официальные изображения каждой точной модели.

Для Render:
- Root Directory: pc_drop (если содержимое архива распаковываете в папку pc_drop)
- Build Command: pip install -r requirements.txt
- Start Command: uvicorn main:app --host 0.0.0.0 --port $PORT

Переменные окружения:
BOT_TOKEN — токен Telegram-бота
DATABASE_URL — строка подключения PostgreSQL/Supabase
PUBLIC_URL — публичный URL Render
ADMIN_IDS — Telegram user IDs администраторов через запятую
ALLOW_DEV_AUTH=0

Не вставляйте токен и пароль БД в код или README. Если они ранее публиковались, смените их.
База данных не сбрасывается этим архивом; код использует настроенный DATABASE_URL.
