import os
import json
import random
import time
import re
import asyncio
from pathlib import Path
from contextlib import closing

import psycopg
from psycopg.rows import dict_row

from fastapi import FastAPI, HTTPException

from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    MenuButtonCommands,
    BotCommand,
    CallbackQuery,
    FSInputFile,
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

CARDS = [{'id': 'gpu_gtx1070', 'name': 'GeForce GTX 1070', 'type': 'gpu', 'rarity': 'rare', 'power': 58, 'price': 420, 'image': 'gpu_gtx1070.png'}, {'id': 'gpu_gtx1060', 'name': 'GeForce GTX 1060', 'type': 'gpu', 'rarity': 'common', 'power': 35, 'price': 180, 'image': 'gpu_gtx1060.png'}, {'id': 'gpu_rtx4090', 'name': 'GeForce RTX 4090', 'type': 'gpu', 'rarity': 'legendary', 'power': 95, 'price': 1500, 'image': 'gpu_rtx4090.png'}, {'id': 'cpu_r5_5600', 'name': 'Ryzen 5 5600', 'type': 'cpu', 'rarity': 'common', 'power': 35, 'price': 180, 'image': 'cpu_r5_5600.png'}, {'id': 'cpu_i5_13600k', 'name': 'Core i5-13600K', 'type': 'cpu', 'rarity': 'rare', 'power': 65, 'price': 550, 'image': 'cpu_i5_13600k.png'}, {'id': 'cpu_ryzen9', 'name': 'Ryzen 9 7950X', 'type': 'cpu', 'rarity': 'epic', 'power': 85, 'price': 1000, 'image': 'cpu_ryzen9.png'}, {'id': 'mb_b550', 'name': 'MSI B550 Tomahawk', 'type': 'motherboard', 'rarity': 'common', 'power': 10, 'price': 140, 'image': 'mb_b550.png'}, {'id': 'mb_x670e', 'name': 'ASUS X670E Hero', 'type': 'motherboard', 'rarity': 'epic', 'power': 25, 'price': 650, 'image': 'mb_x670e.png'}, {'id': 'ram_ddr4', 'name': 'DDR4 16 GB', 'type': 'ram', 'rarity': 'common', 'power': 8, 'price': 90, 'image': 'ram_ddr4.png'}, {'id': 'ram_ddr5', 'name': 'DDR5 32 GB', 'type': 'ram', 'rarity': 'rare', 'power': 18, 'price': 240, 'image': 'ram_ddr5.png'}, {'id': 'ssd_1tb', 'name': 'NVMe SSD 1 TB', 'type': 'storage', 'rarity': 'unusual', 'power': 8, 'price': 120, 'image': 'ssd_1tb.png'}, {'id': 'psu_850', 'name': 'Блок питания 850 W Gold', 'type': 'psu', 'rarity': 'rare', 'power': 12, 'price': 230, 'image': 'psu_850.png'}, {'id': 'cooler_aio', 'name': 'СЖО 360 мм', 'type': 'cooler', 'rarity': 'epic', 'power': 15, 'price': 320, 'image': 'cooler_aio.png'}, {'id': 'case_airflow', 'name': 'Airflow Mid Tower', 'type': 'case', 'rarity': 'unusual', 'power': 5, 'price': 110, 'image': 'case_airflow.png'}, {'id': 'gpu_voodoo5', 'name': '3dfx Voodoo5 6000 (прототип)', 'type': 'gpu', 'rarity': 'mythic', 'power': 40, 'price': 5000, 'image': 'gpu_voodoo5.png'}, {'id': 'gpu_geforce256', 'name': 'NVIDIA GeForce 256', 'type': 'gpu', 'rarity': 'legendary', 'power': 20, 'price': 1200, 'image': 'gpu_geforce256.png'}, {'id': 'gpu_gtx1050ti', 'name': 'GTX 1050 Ti', 'type': 'gpu', 'rarity': 'common', 'power': 15, 'price': 100, 'image': 'gpu_gtx1050ti.png'}, {'id': 'storage_hdd1tb', 'name': 'HDD 1TB', 'type': 'storage', 'rarity': 'common', 'power': 15, 'price': 100, 'image': 'storage_hdd1tb.png'}, {'id': 'ram_ddr4_8gb', 'name': 'DDR4 8GB', 'type': 'ram', 'rarity': 'common', 'power': 15, 'price': 100, 'image': 'ram_ddr4_8gb.png'}, {'id': 'cpu_i3_10100f', 'name': 'Intel Core i3-10100F', 'type': 'cpu', 'rarity': 'common', 'power': 15, 'price': 100, 'image': 'cpu_i3_10100f.png'}, {'id': 'gpu_gtx1660super', 'name': 'GTX 1660 Super', 'type': 'gpu', 'rarity': 'rare', 'power': 30, 'price': 220, 'image': 'gpu_gtx1660super.png'}, {'id': 'storage_crucial_mx500', 'name': 'Crucial MX500 500GB', 'type': 'storage', 'rarity': 'rare', 'power': 30, 'price': 220, 'image': 'storage_crucial_mx500.png'}, {'id': 'ram_ddr4_16gb_3200', 'name': 'DDR4 16GB 3200MHz', 'type': 'ram', 'rarity': 'rare', 'power': 30, 'price': 220, 'image': 'ram_ddr4_16gb_3200.png'}, {'id': 'cpu_i5_10400f', 'name': 'Intel Core i5-10400F', 'type': 'cpu', 'rarity': 'rare', 'power': 30, 'price': 220, 'image': 'cpu_i5_10400f.png'}, {'id': 'gpu_rtx2060', 'name': 'RTX 2060', 'type': 'gpu', 'rarity': 'epic', 'power': 50, 'price': 450, 'image': 'gpu_rtx2060.png'}, {'id': 'storage_samsung970evo', 'name': 'Samsung 970 EVO 1TB', 'type': 'storage', 'rarity': 'epic', 'power': 50, 'price': 450, 'image': 'storage_samsung970evo.png'}, {'id': 'ram_corsair_vengeance16', 'name': 'Corsair Vengeance 16GB', 'type': 'ram', 'rarity': 'epic', 'power': 50, 'price': 450, 'image': 'ram_corsair_vengeance16.png'}, {'id': 'cpu_ryzen53600', 'name': 'AMD Ryzen 5 3600', 'type': 'cpu', 'rarity': 'epic', 'power': 50, 'price': 450, 'image': 'cpu_ryzen53600.png'}, {'id': 'gpu_rtx3060', 'name': 'RTX 3060', 'type': 'gpu', 'rarity': 'legendary', 'power': 70, 'price': 900, 'image': 'gpu_rtx3060.png'}, {'id': 'gpu_rtx3070', 'name': 'RTX 3070', 'type': 'gpu', 'rarity': 'legendary', 'power': 70, 'price': 900, 'image': 'gpu_rtx3070.png'}, {'id': 'storage_wd_black_sn850', 'name': 'WD Black SN850 1TB', 'type': 'storage', 'rarity': 'legendary', 'power': 70, 'price': 900, 'image': 'storage_wd_black_sn850.png'}, {'id': 'cpu_ryzen75800x', 'name': 'AMD Ryzen 7 5800X', 'type': 'cpu', 'rarity': 'legendary', 'power': 70, 'price': 900, 'image': 'cpu_ryzen75800x.png'}, {'id': 'gpu_rtx3080', 'name': 'RTX 3080', 'type': 'gpu', 'rarity': 'mythic', 'power': 90, 'price': 1800, 'image': 'gpu_rtx3080.png'}, {'id': 'gpu_rtx3090', 'name': 'RTX 3090', 'type': 'gpu', 'rarity': 'mythic', 'power': 90, 'price': 1800, 'image': 'gpu_rtx3090.png'}, {'id': 'ram_gskill_tridentz_32', 'name': 'G.Skill Trident Z Neo 32GB', 'type': 'ram', 'rarity': 'mythic', 'power': 90, 'price': 1800, 'image': 'ram_gskill_tridentz_32.png'}, {'id': 'cpu_ryzen95900x', 'name': 'AMD Ryzen 9 5900X', 'type': 'cpu', 'rarity': 'mythic', 'power': 90, 'price': 1800, 'image': 'cpu_ryzen95900x.png'}, {'id': 'gpu_rx5500xt8', 'name': 'RX 5500 XT 8GB', 'type': 'gpu', 'rarity': 'common', 'power': 15, 'price': 100, 'image': 'gpu_rx5500xt8.png'}, {'id': 'gpu_gtx1650', 'name': 'GTX 1650', 'type': 'gpu', 'rarity': 'common', 'power': 15, 'price': 100, 'image': 'gpu_gtx1650.png'}, {'id': 'gpu_gtx1660', 'name': 'GTX 1660', 'type': 'gpu', 'rarity': 'rare', 'power': 30, 'price': 220, 'image': 'gpu_gtx1660.png'}, {'id': 'gpu_rx5700xt', 'name': 'RX 5700 XT', 'type': 'gpu', 'rarity': 'epic', 'power': 50, 'price': 450, 'image': 'gpu_rx5700xt.png'}, {'id': 'cpu_i7_10700k', 'name': 'Intel Core i7-10700K', 'type': 'cpu', 'rarity': 'rare', 'power': 30, 'price': 220, 'image': 'cpu_i7_10700k.png'}, {'id': 'cpu_i9_11900k', 'name': 'Intel Core i9-11900K', 'type': 'cpu', 'rarity': 'epic', 'power': 50, 'price': 450, 'image': 'cpu_i9_11900k.png'}, {'id': 'storage_samsung980pro', 'name': 'Samsung 980 PRO 1TB', 'type': 'storage', 'rarity': 'rare', 'power': 30, 'price': 220, 'image': 'storage_samsung980pro.png'}, {'id': 'storage_kingston_nv2', 'name': 'Kingston NV2 1TB', 'type': 'storage', 'rarity': 'common', 'power': 15, 'price': 100, 'image': 'storage_kingston_nv2.png'}, {'id': 'storage_seagate_barracuda2', 'name': 'Seagate Barracuda 2TB', 'type': 'storage', 'rarity': 'common', 'power': 15, 'price': 100, 'image': 'storage_seagate_barracuda2.png'}, {'id': 'ram_adata_xpg16', 'name': 'ADATA XPG 16GB', 'type': 'ram', 'rarity': 'epic', 'power': 50, 'price': 450, 'image': 'ram_adata_xpg16.png'}, {'id': 'ram_teamgroup_tforce16', 'name': 'TeamGroup T-Force 16GB', 'type': 'ram', 'rarity': 'rare', 'power': 30, 'price': 220, 'image': 'ram_teamgroup_tforce16.png'}, {'id': 'mb_asus_tuf_b450', 'name': 'ASUS TUF B450-PLUS', 'type': 'motherboard', 'rarity': 'rare', 'power': 30, 'price': 220, 'image': 'mb_asus_tuf_b450.png'}, {'id': 'mb_msi_b550a', 'name': 'MSI B550-A PRO', 'type': 'motherboard', 'rarity': 'common', 'power': 15, 'price': 100, 'image': 'mb_msi_b550a.png'}, {'id': 'mb_gigabyte_z590', 'name': 'Gigabyte Z590 AORUS ELITE', 'type': 'motherboard', 'rarity': 'epic', 'power': 50, 'price': 450, 'image': 'mb_gigabyte_z590.png'}, {'id': 'psu_corsair_rm650x', 'name': 'Corsair RM650x 650W', 'type': 'psu', 'rarity': 'rare', 'power': 30, 'price': 220, 'image': 'psu_corsair_rm650x.png'}, {'id': 'psu_corsair_rm750', 'name': 'Corsair RM750 750W', 'type': 'psu', 'rarity': 'epic', 'power': 50, 'price': 450, 'image': 'psu_corsair_rm750.png'}, {'id': 'cooler_deepcool_gammaxx', 'name': 'DeepCool Gammaxx 400', 'type': 'cooler', 'rarity': 'common', 'power': 15, 'price': 100, 'image': 'cooler_deepcool_gammaxx.png'}, {'id': 'cooler_bequiet_purerock', 'name': 'be quiet! Pure Rock 2', 'type': 'cooler', 'rarity': 'rare', 'power': 30, 'price': 220, 'image': 'cooler_bequiet_purerock.png'}, {'id': 'case_nzxt_h510', 'name': 'NZXT H510', 'type': 'case', 'rarity': 'epic', 'power': 50, 'price': 450, 'image': 'case_nzxt_h510.png'}, {'id': 'case_aerocool_cylon', 'name': 'AeroCool Cylon 4F', 'type': 'case', 'rarity': 'rare', 'power': 30, 'price': 220, 'image': 'case_aerocool_cylon.png'}, {'id': 'gpu_rx580_mined', 'name': 'RX 580 8GB — МАЙНЕННАЯ', 'type': 'gpu', 'rarity': 'ultra_legendary', 'power': 100, 'price': 5000, 'image': 'gpu_rx580_mined.png'}]
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
    
RARITY_WEIGHTS = {
    "common": 60,
    "rare": 25,
    "epic": 10,
    "legendary": 4,
    "ultra_legendary": 1
}    
ULTRA_CARD_ID = "gpu_rx580_mined"
ULTRA_DROP_CHANCE = 0.001

def pick_card():
    # Сначала отдельная проверка: майненная RX 580 выпадает с шансом 0,1%.
    ultra = CARD_MAP.get(ULTRA_CARD_ID)
    if ultra and random.random() < ULTRA_DROP_CHANCE:
        return ultra
    cards = [card for card in CARDS if card["id"] != ULTRA_CARD_ID]
    weights = [RARITY_WEIGHTS.get(card["rarity"], 1) for card in cards]
    return random.choices(cards, weights=weights, k=1)[0]

def card_image_path(card):
    filename = card.get("image")
    if not filename:
        return None
    path = BASE_DIR / "cards" / filename
    return path if path.is_file() else None

RARITY_LABELS = {
    "common": "Обычная",
    "unusual": "Необычная",
    "rare": "Редкая",
    "epic": "Эпическая",
    "legendary": "Легендарная",
    "mythic": "Мифическая",
    "ultra_legendary": "Ультра-легендарная",
}

def rarity_label(card):
    return RARITY_LABELS.get(card.get("rarity", "common"), card.get("rarity", "common"))

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

def main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.button(text="🎁 Дроп", callback_data="menu:drop")
    builder.button(text="👤 Профиль", callback_data="menu:profile")
    builder.button(text="📦 Инвентарь", callback_data="menu:inventory")
    builder.button(text="💰 Баланс", callback_data="menu:balance")
    builder.button(text="🎁 Ежедневная награда", callback_data="menu:daily")
    builder.button(text="🖥️ Мой ПК", callback_data="menu:build")
    builder.adjust(2, 2, 1, 1)
    return builder.as_markup()

def inventory_keyboard(items):
    builder = InlineKeyboardBuilder()
    for item in items[:30]:
        builder.button(
            text=item["name"],
            callback_data=f"invitem:{item['inventory_id']}",
        )

    builder.adjust(1)
    return builder.as_markup()
    
def inventory_text(items):
    lines = ["<b>📦 Твой инвентарь:</b>", ""]
    
    for item in items[:30]:
        lines.append(
            f"• {item['name']} — {rarity_label(item)}"
        )

    if len(items) > 30:
        lines.append(
            f"\nПоказаны первые 30 из {len(items)} предметов."
        )

    return "\n".join(lines)

async def send_card_photo(message: Message, card: dict, caption: str, reply_markup=None):
    image_path = card_image_path(card)
    if image_path:
        await message.answer_photo(
            photo=FSInputFile(image_path),
            caption=caption,
            reply_markup=reply_markup,
        )
    else:
        await message.answer(caption, reply_markup=reply_markup)


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
            "/promo КОД — активировать промокод\n"
            "/help — помощь",
        )

    @dp.message(Command("profile"))
    async def profile_command(message: Message):
        user = message.from_user
        ensure_user(user.id, user.username or "")
        row = get_user(user.id)
        items = inventory(user.id)
        builds = state_for(user.id)["build"]
        name = (user.full_name or user.username or "Игрок").replace("<", "").replace(">", "")
        await message.answer(
            f"👤 <b>Профиль {name}</b>\n\n"
            f"🆔 ID: <code>{user.id}</code>\n"
            f"⭐ Уровень: 1\n"
            f"💰 Монеты: {row['balance']}\n"
            f"🃏 Карточек: {len(items)}\n"
            f"🖥️ Выбрано компонентов: {len(builds)}",
        )

    @dp.message(Command("build"))
    async def build_command(message: Message):
        user = message.from_user
        ensure_user(user.id, user.username or "")
        state = state_for(user.id)
        selected = state["build"]
        if not selected:
            await message.answer(
                "🖥️ <b>Твой ПК пока не собран.</b>\n"
                "Сначала получи комплектующие через /drop, затем собери свой ПК командой /build.",
                reply_markup=main_keyboard(),
            )
            return
        parts = [CARD_MAP[cid] for cid in selected.values() if cid in CARD_MAP]
        rank_order = {"common":0,"unusual":1,"rare":2,"epic":3,"legendary":4,"mythic":5}
        rarity = max((c["rarity"] for c in parts), key=lambda r: rank_order.get(r,0), default="common")
        build_images = {
            "common":"pc_office_basic.png", "unusual":"pc_budget.png", "rare":"pc_budget.png",
            "epic":"pc_gaming_start.png", "legendary":"pc_gaming_pro.png", "mythic":"pc_dream_top.png"
        }
        image = BASE_DIR / "pc_builds" / build_images.get(rarity, "pc_office_basic.png")
        caption = "🖥️ <b>Твой собранный ПК</b>\n" + "\n".join(f"• {c['name']}" for c in parts)
        if image.is_file():
            await message.answer_photo(FSInputFile(image), caption=caption)
        else:
            await message.answer(caption)

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
            "/promo КОД — активировать промокод\n"
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
                    SELECT last_drop
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

                caption = (
                    "🎁 <b>Тебе выпала карточка!</b>\n\n"
                    f"🖥 <b>{card['name']}</b>\n"
                    f"✨ Редкость: <b>{rarity_label(card)}</b>\n"
                    f"⚡️ Мощность: {card['power']}\n"
                    f"💰 Цена продажи: {card['price']} монет\n"
                    f"🆔 ID: <code>{card['id']}</code>"
                )

                markup = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text="💰 Продать",
                        callback_data=f"sellcard:{user.id}:{card['id']}"
                    ),
                    InlineKeyboardButton(
                        text="📦 Инвентарь",
                        callback_data="showinventory"
                    ),
                ]])

                await send_card_photo(message, card, caption, markup)

                cur.execute("""
                    INSERT INTO inventory (
                        user_id, card_id, acquired_at
                    )
                    VALUES (%s, %s, %s)
                """, (user.id, card["id"], now))
                
                cur.execute("""
                    UPDATE users
                    SET last_drop = %s
                    WHERE user_id = %s
                """, (now, user.id))

            conn.commit()

    @dp.message(Command("inventory"))
    async def inventory_command(message: Message):
        user = message.from_user
        ensure_user(user.id, user.username or "")

        items = inventory(user.id)

        if not items:
            await message.answer("📦 Твой инвентарь пока пуст.")
            return

        await message.answer(
            inventory_text(items),
            reply_markup=inventory_keyboard(items),
        )

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

    @dp.callback_query()
    async def callback_router(callback: CallbackQuery):
        data = callback.data or ""
        if data.startswith("menu:"):
            actions = {
                "drop": "/drop", "profile": "/profile", "inventory": "/inventory",
                "balance": "/balance", "daily": "/daily", "build": "/build",
            }
            command = actions.get(data.split(":", 1)[1])
            await callback.answer()
            if callback.message and command:
                await callback.message.answer(
                    f"Выбери команду в меню Telegram: <code>{command}</code>"
                )
            return
            
        if data == "showinventory":
            await callback.answer()

            if not callback.from_user or not callback.message:
                return

            user_id = callback.from_user.id
            ensure_user(user_id, callback.from_user.username or "")
            items = inventory(user_id)

            if not items:
                await callback.message.answer("📦 Инвентарь пока пуст."
                )
                return

            lines = ["<b>📦 Твой инвентарь</b>\n"]

            for item in items[:30]:
                lines.append(
                    f"ID: <code>{item['inventory_id']}</code> — "
                    f"{item['name']} ({rarity_label(item)})"
                )

        lines.append("\nПродать карточку: /sell ID")

        await callback.message.answer("\n".join(lines))
        return

        if data.startswith("invitem:"):
            await callback.answer()

            if not callback.from_user or not callback.message:
                return

            user_id = callback.from_user.id
            inv_id = int(data.split(":", 1)[1])

            with closing(db()) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, card_id, acquired_at
                        FROM inventory
                        WHERE id = %s AND user_id = %s
                    """, (inv_id, user_id))
                    item = cur.fetchone()

            if not item:
                await callback.message.answer(
                    "❌ Этот предмет уже отсутствует в инвентаре."
                )
                return

            card = CARD_MAP.get(item["card_id"])

            if not card:
                await callback.message.answer(
                    "❌ Не удалось найти данные карточки."
                )
                return

            caption = (
                f"🖥️ <b>{card['name']}</b>\n\n"
                f"✨ Редкость: <b>{rarity_label(card)}</b>\n"
                f"⚡ Мощность: {card['power']}\n"
                f"💰 Цена продажи: {card['price']} монет\n"
                f"🆔 ID предмета: <code>{inv_id}</code>"
            )

            markup = InlineKeyboardMarkup(inline_keyboard=[[
                InlineKeyboardButton(
                    text="💰 Продать",
                    callback_data=f"invsell:{inv_id}",
                ),
                InlineKeyboardButton(
                    text="⬅️ Назад",
                    callback_data="invback",
                ),
            ]])

            image_path = card_image_path(card)

            if image_path:
                await callback.message.answer_photo(
                    photo=FSInputFile(image_path),
                    caption=caption,
                    reply_markup=markup,
                )
            else:
                await callback.message.answer(
                    caption,
                    reply_markup=markup,
                )
            return

        if data == "invback":
            await callback.answer()

            if not callback.from_user or not callback.message:
                return

            items = inventory(callback.from_user.id)

            if not items:
                await callback.message.answer(
                    "📦 Твой инвентарь пока пуст."
                )
                return

            await callback.message.answer(
                inventory_text(items),
                reply_markup=inventory_keyboard(items),
            )
            return

        if data.startswith("invsell:"):
            await callback.answer()

            if not callback.from_user or not callback.message:
                return

            user_id = callback.from_user.id
            inv_id = int(data.split(":", 1)[1])

            with closing(db()) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id, card_id
                        FROM inventory
                        WHERE id = %s AND user_id = %s
                        FOR UPDATE
                    """, (inv_id, user_id))
                    item = cur.fetchone()

                    if not item:
                        await callback.message.answer(
                            "❌ Этот предмет уже продан или отсутствует."
                        )
                        return

                    card = CARD_MAP.get(item["card_id"])

                    if not card:
                        await callback.message.answer(
                            "❌ Данные карточки не найдены."
                        )
                        return

                    cur.execute("""
                        DELETE FROM inventory
                        WHERE id = %s AND user_id = %s
                    """, (inv_id, user_id))

                    cur.execute("""
                        UPDATE users
                        SET balance = balance + %s
                        WHERE user_id = %s
                    """, (card["price"], user_id))

                conn.commit()

            await callback.message.answer(
                f"✅ Продано: <b>{card['name']}</b>\n"
                f"💰 Получено: {card['price']} монет",
            )
            return
        
        if data.startswith("sellcard:"):
            _, owner_s, card_id = data.split(":", 2)
            if not callback.from_user or str(callback.from_user.id) != owner_s:
                await callback.answer("Это не твоя карточка.", show_alert=True)
                return
            user_id = callback.from_user.id
            ensure_user(user_id, callback.from_user.username or "")
            card = CARD_MAP.get(card_id)
            if not card:
                await callback.answer("Карточка не найдена.", show_alert=True)
                return
            with closing(db()) as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        SELECT id FROM inventory
                        WHERE user_id=%s AND card_id=%s
                        ORDER BY id DESC LIMIT 1 FOR UPDATE
                    """, (user_id, card_id))
                    row = cur.fetchone()
                    if not row:
                        await callback.answer("Этой карточки уже нет в инвентаре.", show_alert=True)
                        return
                    cur.execute("DELETE FROM inventory WHERE id=%s", (row["id"],))
                    cur.execute("UPDATE users SET balance=balance+%s WHERE user_id=%s", (card["price"], user_id))
                conn.commit()
            await callback.answer("Продано!")
            if callback.message:
                await callback.message.answer(f"✅ Продано: {card['name']} за {card['price']} монет.")
            return
        await callback.answer()

    # -----------------------------------------------------
    # ПРОМОКОДЫ
    # -----------------------------------------------------

def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS

def valid_promo_code(code: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{2,32}", code))

if dp:
    @dp.message(Command("promo_coins"))
    async def promo_coins_command(message: Message):
        user = message.from_user

        if not is_admin(user.id):
            await message.answer("⛔ Эта команда доступна только администратору.")
            return

        parts = (message.text or "").split()

        if len(parts) != 5:
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

    @dp.message(Command("promo", "redeem"))
    async def redeem_command(message: Message):
        user = message.from_user
        ensure_user(user.id, user.username or "")

        parts = (message.text or "").split()

        if len(parts) != 2:
            await message.answer(
                "Использование: <code>/promo КОД</code>"
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
# ЗАПУСК TELEGRAM-БОТА И КНОПКИ «ИГРАТЬ»
# =========================================================

async def run_bot():
    if not bot or not dp:
        return

    try:
        await bot.set_my_commands([
            BotCommand(command="start", description="Главное меню"),
            BotCommand(command="profile", description="Мой профиль"),
            BotCommand(command="drop", description="Получить карточку"),
            BotCommand(command="inventory", description="Инвентарь"),
            BotCommand(command="balance", description="Баланс"),
            BotCommand(command="sell", description="Продать карточку по ID"),
            BotCommand(command="daily", description="Ежедневная награда"),
            BotCommand(command="build", description="Мой собранный ПК"),
            BotCommand(command="promo", description="Активировать промокод"),
            BotCommand(command="help", description="Помощь"),
            BotCommand(command="myid", description="Мой Telegram ID"),
        ])
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
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
