import os
import json
import random
import time
import re
import asyncio
import hmac
import hashlib
from urllib.parse import parse_qsl
from pathlib import Path
from contextlib import closing

import psycopg
from psycopg.rows import dict_row

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
    MenuButtonWebApp,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

# =========================================================
# НАСТРОЙКИ
# =========================================================

BASE_DIR = Path(__file__).parent

DATABASE_URL = os.getenv("DATABASE_URL", "")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
PUBLIC_URL = os.getenv(
    "PUBLIC_URL",
    "https://pc-drop.onrender.com"
).rstrip("/")

ALLOW_DEV_AUTH = os.getenv("ALLOW_DEV_AUTH", "0") == "1"

ADMIN_IDS = {
    int(value.strip())
    for value in os.getenv("ADMIN_IDS", "").split(",")
    if value.strip().isdigit()
}

app = FastAPI(title="PC DROP")

app.mount(
    "/web",
    StaticFiles(directory=str(BASE_DIR / "web")),
    name="web",
)

bot = (
    Bot(
        token=BOT_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    if BOT_TOKEN
    else None
)

dp = Dispatcher() if bot else None
bot_task = None

# =========================================================
# КАРТОЧКИ
# =========================================================

CARDS = [
    {
        "id": "gpu_gtx1060",
        "name": "GeForce GTX 1060",
        "type": "gpu",
        "rarity": "common",
        "power": 35,
        "price": 180,
    },
    {
        "id": "gpu_rtx3060",
        "name": "GeForce RTX 3060",
        "type": "gpu",
        "rarity": "unusual",
        "power": 55,
        "price": 360,
    },
    {
        "id": "gpu_rtx4090",
        "name": "GeForce RTX 4090",
        "type": "gpu",
        "rarity": "legendary",
        "power": 95,
        "price": 1500,
    },
    {
        "id": "cpu_r5_5600",
        "name": "Ryzen 5 5600",
        "type": "cpu",
        "rarity": "common",
        "power": 35,
        "price": 180,
    },
    {
        "id": "cpu_i5_13600k",
        "name": "Core i5-13600K",
        "type": "cpu",
        "rarity": "rare",
        "power": 65,
        "price": 550,
    },
    {
        "id": "cpu_ryzen9",
        "name": "Ryzen 9 7950X",
        "type": "cpu",
        "rarity": "epic",
        "power": 85,
        "price": 1000,
    },
    {
        "id": "mb_b550",
        "name": "MSI B550 Tomahawk",
        "type": "motherboard",
        "rarity": "common",
        "power": 10,
        "price": 140,
    },
    {
        "id": "mb_x670e",
        "name": "ASUS X670E Hero",
        "type": "motherboard",
        "rarity": "epic",
        "power": 25,
        "price": 650,
    },
    {
        "id": "ram_ddr4",
        "name": "DDR4 16 GB",
        "type": "ram",
        "rarity": "common",
        "power": 8,
        "price": 90,
    },
    {
        "id": "ram_ddr5",
        "name": "DDR5 32 GB",
        "type": "ram",
        "rarity": "rare",
        "power": 18,
        "price": 240,
    },
    {
        "id": "ssd_1tb",
        "name": "NVMe SSD 1 TB",
        "type": "storage",
        "rarity": "unusual",
        "power": 8,
        "price": 120,
    },
    {
        "id": "psu_850",
        "name": "Блок питания 850 W Gold",
        "type": "psu",
        "rarity": "rare",
        "power": 12,
        "price": 230,
    },
    {
        "id": "cooler_aio",
        "name": "СЖО 360 мм",
        "type": "cooler",
        "rarity": "epic",
        "power": 15,
        "price": 320,
    },
    {
        "id": "case_airflow",
        "name": "Airflow Mid Tower",
        "type": "case",
        "rarity": "unusual",
        "power": 5,
        "price": 110,
    },
    {
        "id": "gpu_voodoo5",
        "name": "3dfx Voodoo5 6000 (прототип)",
        "type": "gpu",
        "rarity": "mythic",
        "power": 40,
        "price": 5000,
    },
    {
        "id": "gpu_geforce256",
        "name": "NVIDIA GeForce 256",
        "type": "gpu",
        "rarity": "legendary",
        "power": 20,
        "price": 1200,
    },
]

RARITY_WEIGHTS = {
    "common": 45,
    "unusual": 27,
    "rare": 16,
    "epic": 8,
    "legendary": 3.5,
    "mythic": 0.5,
}

CARD_MAP = {card["id"]: card for card in CARDS}

DROP_COOLDOWN = 3 * 60 * 60
DAILY_COOLDOWN = 24 * 60 * 60
DAILY_REWARD = 250

# =========================================================
# БАЗА ДАННЫХ
# =========================================================

def db():
    if not DATABASE_URL:
        raise RuntimeError("Не задана переменная DATABASE_URL")

    return psycopg.connect(
        DATABASE_URL,
        row_factory=dict_row,
    )

def init_db():
    with closing(db()) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    balance BIGINT NOT NULL DEFAULT 500,
                    last_drop BIGINT NOT NULL DEFAULT 0,
                    last_daily BIGINT NOT NULL DEFAULT 0,
                    created_at BIGINT NOT NULL DEFAULT 0
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS inventory (
                    id BIGSERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL
                        REFERENCES users(user_id)
                        ON DELETE CASCADE,
                    card_id TEXT NOT NULL,
                    acquired_at BIGINT NOT NULL
                )
            """)

            cur.execute("""
                CREATE INDEX IF NOT EXISTS inventory_user_idx
                ON inventory(user_id)
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS builds (
                    user_id BIGINT PRIMARY KEY
                        REFERENCES users(user_id)
                        ON DELETE CASCADE,
                    selected TEXT NOT NULL DEFAULT '{}'
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS promo_codes (
                    code TEXT PRIMARY KEY,
                    reward_type TEXT NOT NULL,
                    coins BIGINT NOT NULL DEFAULT 0,
                    card_id TEXT,
                    max_uses INTEGER NOT NULL,
                    uses INTEGER NOT NULL DEFAULT 0,
                    expires_at BIGINT NOT NULL,
                    created_by BIGINT NOT NULL,
                    created_at BIGINT NOT NULL
                )
            """)

            cur.execute("""
                CREATE TABLE IF NOT EXISTS promo_redemptions (
                    code TEXT NOT NULL
                        REFERENCES promo_codes(code)
                        ON DELETE CASCADE,
                    user_id BIGINT NOT NULL
                        REFERENCES users(user_id)
                        ON DELETE CASCADE,
                    redeemed_at BIGINT NOT NULL,
                    PRIMARY KEY (code, user_id)
                )
            """)

        conn.commit()

init_db()

def ensure_user(user_id: int, username: str = ""):
    now = int(time.time())

    with closing(db()) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO users (
                    user_id, username, balance, created_at
                )
                VALUES (%s, %s, 500, %s)
                ON CONFLICT (user_id)
                DO UPDATE SET username = EXCLUDED.username
            """, (user_id, username or "", now))

            cur.execute("""
                INSERT INTO builds (user_id, selected)
                VALUES (%s, '{}')
                ON CONFLICT (user_id) DO NOTHING
            """, (user_id,))
         
      conn.commit()

def get_user(user_id: int):
    with closing(db()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM users WHERE user_id = %s",
                (user_id,),
            )
            return cur.fetchone()

def inventory(user_id: int):
    with closing(db()) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, card_id, acquired_at
                FROM inventory
                WHERE user_id = %s
                ORDER BY id DESC
            """, (user_id,))
            rows = cur.fetchall()

    result = []

    for row in rows:
        card = CARD_MAP.get(row["card_id"])

        if not card:
            continue

        item = dict(card)
        item["inventory_id"] = row["id"]
        item["acquired_at"] = row["acquired_at"]
        result.append(item)

    return result

def pick_card():
    cards = list(CARDS)
    weights = [
        RARITY_WEIGHTS.get(card["rarity"], 1)
        for card in cards
    ]

    return random.choices(cards, weights=weights, k=1)[0]

def add_card(user_id: int, card_id: str):
    if card_id not in CARD_MAP:
        raise ValueError("Неизвестная карточка")

    with closing(db()) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO inventory (
                    user_id, card_id, acquired_at
                )
                VALUES (%s, %s, %s)
            """, (user_id, card_id, int(time.time())))

        conn.commit()

# =========================================================
# TELEGRAM-КНОПКИ
# =========================================================

def web_keyboard():
    builder = InlineKeyboardBuilder()

    builder.button(
        text="🎮 Открыть PC DROP",
        web_app=WebAppInfo(url=PUBLIC_URL + "/"),
    )

    return builder.as_markup()

# =========================================================
# TELEGRAM-КОМАНДЫ
# =========================================================

if dp:

    @dp.message(CommandStart())
    async def start_command(message: Message):
        user = message.from_user

        ensure_user(user.id, user.username or "")

        await message.answer(
            "🎮 <b>Добро пожаловать в PC DROP!</b>\n\n"
            "Открывай карточки компьютерных комплектующих, "
            "собирай инвентарь и создавай свой ПК.\n\n"
            "Команды:\n"
            "/drop — получить карточку\n"
            "/inventory — инвентарь\n"
            "/balance — баланс\n"
            "/daily — ежедневная награда\n"
            "/redeem КОД — активировать промокод\n"
            "/help — помощь",
            reply_markup=web_keyboard(),
        )

    @dp.message(Command("help"))
    async def help_command(message: Message):
        await message.answer(
            "<b>PC DROP — команды</b>\n\n"
            "/start — открыть игру\n"
            "/drop — получить карточку раз в 3 часа\n"
            "/inventory — посмотреть инвентарь\n"
            "/sell ID — продать карточку по ID\n"
            "/balance — посмотреть баланс\n"
            "/daily — получить 250 монет раз в сутки\n"
            "/redeem КОД — активировать промокод\n"
            "/myid — узнать свой Telegram ID"
        )

    @dp.message(Command("myid"))
    async def myid_command(message: Message):
        await message.answer(
            f"Твой Telegram ID: <code>{message.from_user.id}</code>"
        )

    @dp.message(Command("balance"))
    async def balance_command(message: Message):
        user = message.from_user
        ensure_user(user.id, user.username or "")
        row = get_user(user.id)

        await message.answer(
            f"💰 Баланс: <b>{row['balance']}</b> монет"
        )

    @dp.message(Command("drop"))
    async def drop_command(message: Message):
        user = message.from_user
        ensure_user(user.id, user.username or "")

        now = int(time.time())

        with closing(db()) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT
                    last_drop
                    FROM users
                    WHERE user_id = %s
                    FOR UPDATE
                """, (user.id,))

                row = cur.fetchone()
                last_drop = row["last_drop"] if row else 0
                remaining = DROP_COOLDOWN - (now - last_drop)

                if remaining > 0:
                    hours = remaining // 3600
                    minutes = (remaining % 3600) // 60

                    await message.answer(
                        "⏳ Следующая карточка будет доступна "
                        f"через {hours} ч. {minutes} мин."
                    )
                    return

                card = pick_card()

                cur.execute("""
                    UPDATE users
                    SET last_drop = %s
                    WHERE user_id = %s
                """, (now, user.id))

                cur.execute("""
                    INSERT INTO inventory (
                        user_id, card_id, acquired_at
                    )
                    VALUES (%s, %s, %s)
                """, (user.id, card["id"], now))

            conn.commit()

        await message.answer(
            "🎁 <b>Тебе выпала карточка!</b>\n\n"
            f"🖥️ {card['name']}\n"
            f"✨ Редкость: {card['rarity']}\n"
            f"⚡ Мощность: {card['power']}\n"
            f"💰 Цена продажи: {card['price']} монет",
            reply_markup=web_keyboard(),
        )

    @dp.message(Command("inventory"))
    async def inventory_command(message: Message):
        user = message.from_user
        ensure_user(user.id, user.username or "")

        items = inventory(user.id)

        if not items:
            await message.answer("📦 Инвентарь пока пуст.")
            return

        lines = ["<b>📦 Твой инвентарь</b>\n"]

        for item in items[:30]:
            lines.append(
                f"ID: <code>{item['inventory_id']}</code> — "
                f"{item['name']} ({item['rarity']})"
            )

        lines.append("\nПродать карточку: /sell ID")

        await message.answer("\n".join(lines))

    @dp.message(Command("sell"))
    async def sell_command(message: Message):
        user = message.from_user
        ensure_user(user.id, user.username or "")

        parts = (message.text or "").split()

        if len(parts) != 2 or not parts[1].isdigit():
            await message.answer(
                "Использование: <code>/sell ID</code>\n"
                "Посмотреть ID можно командой /inventory."
            )
            return

        inv_id = int(parts[1])

        with closing(db()) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, card_id
                    FROM inventory
                    WHERE id = %s AND user_id = %s
                    FOR UPDATE
                """, (inv_id, user.id))

                item = cur.fetchone()

                if not item:
                    await message.answer(
                        "❌ Карточка не найдена в твоём инвентаре."
                    )
                    return

                card = CARD_MAP.get(item["card_id"])

                if not card:
                    await message.answer(
                        "❌ Не удалось найти данные карточки."
                    )
                    return

                cur.execute("""
                    DELETE FROM inventory
                    WHERE id = %s AND user_id = %s
                """, (inv_id, user.id))

                cur.execute("""
                    UPDATE users
                    SET balance = balance + %s
                    WHERE user_id = %s
                """, (card["price"], user.id))

            conn.commit()

        await message.answer(
            f"✅ Продано: {card['name']}\n"
            f"💰 Получено: {card['price']} монет"
        )

    @dp.message(Command("daily"))
    async def daily_command(message: Message):
        user = message.from_user
        ensure_user(user.id, user.username or "")

        now = int(time.time())

        with closing(db()) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT last_daily
                    FROM users
                    WHERE user_id = %s
                    FOR UPDATE
                """, (user.id,))

                row = cur.fetchone()
                last_daily = row["last_daily"] if row else 0
                remaining = DAILY_COOLDOWN - (now - last_daily)

                if remaining > 0:
                    hours = remaining // 3600
                    minutes = (remaining % 3600) // 60

                    await message.answer(
                        "⏳ Ежедневная награда уже получена.\n"
                        f"Следующая будет через {hours} ч. {minutes} мин."
                    )
                    return

                cur.execute("""
                    UPDATE users
                    SET balance = balance + %s,
                        last_daily = %s
                    WHERE user_id = %s
                """, (DAILY_REWARD, now, user.id))

            conn.commit()

        await message.answer(
            f"🎁 Ты получил {DAILY_REWARD} монет!"
        )

    # -----------------------------------------------------
    # ПРОМОКОДЫ
    # -----------------------------------------------------

    def is_admin(user_id: int) -> bool:
        return user_id in ADMIN_IDS

    def valid_promo_code(code: str) -> bool:
        return bool(re.fullmatch(r"[A-Za-z0-9_-]{2,32}", code))

    @dp.message(Command("promo_coins"))
    async def promo_coins_command(message: Message):
        user = message.from_user

        if not is_admin(user.id):
            await message.answer("⛔ Эта команда доступна только администратору.")
            return

        parts = (message.text or "").split()

        if len(parts) != 4:
            await message.answer(
                "Создание промокода на монеты:\n"
                "<code>/promo_coins КОД МОНЕТЫ МАКС_АКТИВАЦИЙ ЧАСЫ</code>\n\n"
                "Пример: <code>/promo_coins WELCOME 200 50 24</code>"
            )
            return

        _, code, coins_s, max_uses_s, hours_s = parts

        if not valid_promo_code(code):
            await message.answer(
                "❌ Код должен содержать 2–32 символа: "
                "буквы, цифры, _ или -."
            )
            return

        try:
            coins = int(coins_s)
            max_uses = int(max_uses_s)
            hours = int(hours_s)
        except ValueError:
            await message.answer("❌ Числа указаны неверно.")
            return

        if not (1 <= coins <= 1_000_000):
            await message.answer("❌ Количество монет должно быть от 1 до 1 000 000.")
            return

        if not (1 <= max_uses <= 1_000_000):
            await message.answer("❌ Лимит активаций должен быть от 1 до 1 000 000.")
            return

        if not (1 <= hours <= 8760):
            await message.answer("❌ Срок действия должен быть от 1 до 8760 часов.")
            return

        now = int(time.time())

        try:
            with closing(db()) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO promo_codes (
                            code, reward_type, coins, card_id,
                            max_uses, uses, expires_at,
                            created_by, created_at
                        )
                        VALUES (%s, 'coins', %s, NULL, %s, 0, %s, %s, %s)
                    """, (
                        code.upper(),
                        coins,
                        max_uses,
                        now + hours * 3600,
                        user.id,
                        now,
                    ))
                conn.commit()

        except psycopg.errors.UniqueViolation:
            await message.answer("❌ Такой промокод уже существует.")
            return

        await message.answer(
            "✅ Промокод создан!\n"
            f"Код: <code>{code.upper()}</code>\n"
            f"Награда: {coins} монет\n"
            f"Активаций: {max_uses}\n"
            f"Срок: {hours} ч."
        )

    @dp.message(Command("promo_card"))
    async def promo_card_command(message: Message):
        user = message.from_user

        if not is_admin(user.id):
            await message.answer("⛔ Эта команда доступна только администратору.")
            return

        parts = (message.text or "").split()

        if len(parts) != 4:
            await message.answer(
                "Создание промокода на карточку:\n"
                "<code>/promo_card КОД CARD_ID МАКС_АКТИВАЦИЙ ЧАСЫ</code>\n\n"
                "Пример: <code>/promo_card GPU gpu_rtx3060 20 48</code>\n\n"
                "Доступные карточки:\n"
                + "\n".join(
                    f"<code>{card['id']}</code> — {card['name']}"
                    for card in CARDS
                )
            )
            return

        # Формат команды:
        # /promo_card КОД CARD_ID МАКС_АКТИВАЦИЙ ЧАСЫ
        # Поэтому ожидается 5 элементов вместе с командой.
        if len(parts) != 5:
            await message.answer(
                "Использование:\n"
                "<code>/promo_card КОД CARD_ID МАКС_АКТИВАЦИЙ ЧАСЫ</code>"
            )
            return

        _, code, card_id, max_uses_s, hours_s = parts

        if not valid_promo_code(code):
            await message.answer("❌ Неверный формат промокода.")
            return

        if card_id not in CARD_MAP:
            await message.answer("❌ Такого ID карточки нет.")
            return

        try:
            max_uses = int(max_uses_s)
            hours = int(hours_s)
        except ValueError:
            await message.answer("❌ Числа указаны неверно.")
            return

        if not (1 <= max_uses <= 1_000_000):
            await message.answer("❌ Лимит активаций должен быть от 1 до 1 000 000.")
            return

        if not (1 <= hours <= 8760):
            await message.answer("❌ Срок действия должен быть от 1 до 8760 часов.")
            return

        now = int(time.time())

        try:
            with closing(db()) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO promo_codes (
                            code, reward_type, coins, card_id,
                            max_uses, uses, expires_at,
                            created_by, created_at
                        )
                        VALUES (%s, 'card', 0, %s, %s, 0, %s, %s, %s)
                    """, (
                        code.upper(),
                        card_id,
                        max_uses,
                        now + hours * 3600,
                        user.id,
                        now,
                    ))
                conn.commit()

        except psycopg.errors.UniqueViolation:
            await message.answer("❌ Такой промокод уже существует.")
            return

        card = CARD_MAP[card_id]

        await message.answer(
            "✅ Промокод создан!\n"
            f"Код: <code>{code.upper()}</code>\n"
            f"Награда: {card['name']}\n"
            f"Активаций: {max_uses}\n"
            f"Срок: {hours} ч."
        )

    @dp.message(Command("redeem"))
    async def redeem_command(message: Message):
        user = message.from_user
        ensure_user(user.id, user.username or "")

        parts = (message.text or "").split()

        if len(parts) != 2:
            await message.answer(
                "Использование: <code>/redeem КОД</code>"
            )
            return

        code = parts[1].upper()
        now = int(time.time())

        with closing(db()) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT *
                    FROM promo_codes
                    WHERE code = %s
                    FOR UPDATE
                """, (code,))

                promo = cur.fetchone()

                if not promo:
                    await message.answer("❌ Промокод не найден.")
                    return

                if promo["expires_at"] <= now: 
                    await message.answer("⌛ Срок действия промокода истёк.")
                    return

                if promo["uses"] >= promo["max_uses"]:
                    await message.answer("❌ Лимит активаций исчерпан.")
                    return

                cur.execute("""
                    SELECT 1
                    FROM promo_redemptions
                    WHERE code = %s AND user_id = %s
                """, (code, user.id))

                if cur.fetchone():
                    await message.answer(
                        "❌ Ты уже активировал этот промокод."
                    )
                    return

                cur.execute("""
                    INSERT INTO promo_redemptions (
                        code, user_id, redeemed_at
                    )
                    VALUES (%s, %s, %s)
                """, (code, user.id, now))

                if promo["reward_type"] == "coins":
                    cur.execute("""
                        UPDATE users
                        SET balance = balance + %s
                        WHERE user_id = %s
                    """, (promo["coins"], user.id))

                    reward_text = f"{promo['coins']} монет"

                elif promo["reward_type"] == "card":
                    card = CARD_MAP.get(promo["card_id"])

                    if not card:
                        raise HTTPException(
                            status_code=500,
                            detail="Неизвестная карточка промокода",
                        )

                    cur.execute("""
                        INSERT INTO inventory (
                            user_id, card_id, acquired_at
                        )
                        VALUES (%s, %s, %s)
                    """, (user.id, promo["card_id"], now))

                    reward_text = card["name"]

                else:
                    raise HTTPException(
                        status_code=500,
                        detail="Неизвестный тип награды",
                    )

                cur.execute("""
                    UPDATE promo_codes
                    SET uses = uses + 1
                    WHERE code = %s
                """, (code,))

            conn.commit()

        await message.answer(
            "🎉 <b>Промокод активирован!</b>\n"
            f"Награда: {reward_text}"
        )

# =========================================================
# АВТОРИЗАЦИЯ TELEGRAM MINI APP
# =========================================================

def auth_user(request: Request):
    init_data = request.headers.get("X-Telegram-Init-Data", "")

    if not init_data:
        if ALLOW_DEV_AUTH:
            dev_id = request.headers.get("X-Dev-User-Id")

            if dev_id and dev_id.isdigit():
                uid = int(dev_id)
                ensure_user(uid, "dev")
                return uid

        raise HTTPException(
            status_code=401,
            detail="Telegram initData отсутствует",
        )

    if not BOT_TOKEN:
        raise HTTPException(
            status_code=500,
            detail="BOT_TOKEN не настроен",
        )

    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = parsed.pop("hash", None)

        if not received_hash:
            raise ValueError("Нет подписи")

        auth_date = int(parsed.get("auth_date", "0"))
        now = int(time.time())

        if auth_date <= 0 or now - auth_date > 86400 or auth_date > now + 60:
            raise HTTPException(
                status_code=401,
                detail="Данные авторизации устарели",
            )

        data_check_string = "\n".join(
            f"{key}={value}"
            for key, value in sorted(parsed.items())
        )

        secret_key = hmac.new(
            b"WebAppData",
            BOT_TOKEN.encode(),
            hashlib.sha256,
        ).digest()

        calculated_hash = hmac.new(
            secret_key,
            data_check_string.encode(),
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(calculated_hash, received_hash):
            raise HTTPException(
                status_code=401,
                detail="Неверная подпись Telegram",
            )

        user_data = json.loads(parsed["user"])
        uid = int(user_data["id"])
        username = user_data.get("username", "")

        ensure_user(uid, username)
        return uid

    except HTTPException:
        raise

    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Не удалось проверить авторизацию Telegram",
        )

# =========================================================
# СОСТОЯНИЕ ИГРЫ
# =========================================================

def state_for(uid: int):
    user = get_user(uid)

    if not user:
        ensure_user(uid)
        user = get_user(uid)

    with closing(db()) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT selected
                FROM builds
                WHERE user_id = %s
            """, (uid,))
            build = cur.fetchone()

    selected = {}

    if build and build.get("selected"):
        try:
            selected = json.loads(build["selected"])
        except (ValueError, TypeError):
            selected = {}

    return {
        "user": {
            "id": uid,
            "username": user["username"],
            "balance": user["balance"],
            "last_drop": user["last_drop"],
            "last_daily": user["last_daily"],
        },
        "inventory": inventory(uid),
        "catalog": CARDS,
        "build": selected,
        "drop_cooldown": DROP_COOLDOWN,
        "daily_cooldown": DAILY_COOLDOWN,
        "daily_reward": DAILY_REWARD,
    }

# =========================================================
# WEB-МАРШРУТЫ
# =========================================================

@app.get("/")
async def index():
    return FileResponse(BASE_DIR / "web" / "index.html")

@app.get("/api/state")
async def api_state(request: Request):
    uid = auth_user(request)
    return JSONResponse(state_for(uid))

"/api/drop"
async def api_drop(request: Request):
    uid = auth_user(request)
    now = int(time.time())

    with closing(db()) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT last_drop
                FROM users
                WHERE user_id = %s
                FOR UPDATE
            """, (uid,))

            row = cur.fetchone()

            if not row:
                raise HTTPException(status_code=404, detail="Пользователь не найден")

            remaining = DROP_COOLDOWN - (now - row["last_drop"])

            if remaining > 0:
                raise HTTPException(
                    status_code=429,
                    detail=f"Подожди ещё {remaining} секунд",
                )

            card = pick_card()

            cur.execute("""
                UPDATE users
                SET last_drop = %s
                WHERE user_id = %s
            """, (now, uid))

            cur.execute("""
                INSERT INTO inventory (
                    user_id, card_id, acquired_at
                )
                VALUES (%s, %s, %s)
                RETURNING id
            """, (uid, card["id"], now))

            inv_row = cur.fetchone()

        conn.commit()

    result = dict(card)
    result["inventory_id"] = inv_row["id"]
    result["acquired_at"] = now

    return JSONResponse({
        "card": result,
        "state": state_for(uid),
    })

"/api/sell/{inv_id}"
async def api_sell(inv_id: int, request: Request):
    uid = auth_user(request)

    with closing(db()) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, card_id
                FROM inventory
                WHERE id = %s AND user_id = %s
                FOR UPDATE
            """, (inv_id, uid))

            item = cur.fetchone()

            if not item:
                raise HTTPException(
                    status_code=404,
                    detail="Карточка не найдена",
                 )

            card = CARD_MAP.get(item["card_id"])

            if not card:
                raise HTTPException(
                    status_code=400,
                    detail="Неизвестная карточка",
                )

            cur.execute("""
                DELETE FROM inventory
                WHERE id = %s AND user_id = %s
            """, (inv_id, uid))

            cur.execute("""
                UPDATE users
                SET balance = balance + %s
                WHERE user_id = %s
            """, (card["price"], uid))

        conn.commit()

    return JSONResponse({
        "ok": True,
        "sold": card,
        "earned": card["price"],
        "state": state_for(uid),
    })

"/api/daily"
async def api_daily(request: Request):
    uid = auth_user(request)
    now = int(time.time())

    with closing(db()) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT last_daily
                FROM users
                WHERE user_id = %s
                FOR UPDATE
            """, (uid,))

            row = cur.fetchone()

            if not row:
                raise HTTPException(
                    status_code=404,
                    detail="Пользователь не найден",
                )

            remaining = DAILY_COOLDOWN - (now - row["last_daily"])

            if remaining > 0:
                raise HTTPException(
                    status_code=429,
                    detail=f"Следующая награда через {remaining} секунд",
                )

            cur.execute("""
                UPDATE users
                SET balance = balance + %s,
                    last_daily = %s
                WHERE user_id = %s
            """, (DAILY_REWARD, now, uid))

        conn.commit()

    return JSONResponse({
        "ok": True,
        "reward": DAILY_REWARD,
        "state": state_for(uid),
    })

"/api/build"
async def api_build(request: Request):
    uid = auth_user(request)

    try:
        data = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Неверный JSON")

    selected = data.get("selected", {})

    if not isinstance(selected, dict):
        raise HTTPException(
            status_code=400,
            detail="Неверный формат сборки",
        )

    owned_cards = inventory(uid)
    owned_ids = {item["card_id"] for item in owned_cards}

    for component_type, card_id in selected.items():
        if not isinstance(card_id, str):
            raise HTTPException(
                status_code=400,
                detail="Неверный ID компонента",
            )

        card = CARD_MAP.get(card_id)

        if not card:
            raise HTTPException(
                status_code=400,
                detail=f"Карточка {card_id} не существует",
            )

        if card_id not in owned_ids:
            raise HTTPException(
                status_code=403,
                detail=f"Карточка {card['name']} отсутствует в инвентаре",
            )

        if component_type != card["type"]:
            raise HTTPException(
                status_code=400,
                detail=f"Неверный тип компонента: {component_type}",
            )

    with closing(db()) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO builds (user_id, selected)
                VALUES (%s, %s)
                ON CONFLICT (user_id)
                DO UPDATE SET selected = EXCLUDED.selected
            """, (uid, json.dumps(selected)))

        conn.commit()

    return JSONResponse({
        "ok": True,
        "build": selected,
        "state": state_for(uid),
    })

# =========================================================
# ЗАПУСК TELEGRAM-БОТА И КНОПКИ «ИГРАТЬ»
# =========================================================

async def run_bot():
    if not bot or not dp:
        return

    try:
        await bot.set_chat_menu_button(
            menu_button=MenuButtonWebApp(
                text="🎮 Играть", 
                web_app=WebAppInfo(url=PUBLIC_URL + "/"),
            )
        )

        await dp.start_polling(bot)

    except asyncio.CancelledError:
        raise

    except Exception as exc:
        print(f"Ошибка Telegram-бота: {exc}")
        raise

@app.on_event("startup")
async def startup_event():
    global bot_task

    if bot and dp:
        bot_task = asyncio.create_task(run_bot())

@app.on_event("shutdown")
async def shutdown_event():
    global bot_task

    if bot_task:
        bot_task.cancel()

        try:
            await bot_task
        except asyncio.CancelledError:
            pass
        finally:
            bot_task = None

    if bot:
        await bot.session.close()
