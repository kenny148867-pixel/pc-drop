import os, json, random, time
import psycopg
from psycopg.rows import dict_row
from pathlib import Path
from contextlib import closing
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from aiogram import Bot, Dispatcher
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

BASE_DIR = Path(__file__).parent
DATABASE_URL = os.getenv('DATABASE_URL', '').strip()
BOT_TOKEN = os.getenv('BOT_TOKEN', '').strip()
PUBLIC_URL = os.getenv('PUBLIC_URL', '').strip().rstrip('/')

app = FastAPI(title='PC DROP')
app.mount('/web', StaticFiles(directory=BASE_DIR / 'web'), name='web')
bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML)) if BOT_TOKEN else None
dp = Dispatcher()

CARDS = [
 {"id":"gpu_gtx1060","name":"GeForce GTX 1060","type":"Видеокарта","rarity":"Обычная","power":35,"price":180,"image":"gpu"},
 {"id":"gpu_rtx3060","name":"GeForce RTX 3060","type":"Видеокарта","rarity":"Необычная","power":55,"price":360,"image":"gpu"},
 {"id":"gpu_rtx4090","name":"GeForce RTX 4090","type":"Видеокарта","rarity":"Легендарная","power":95,"price":1500,"image":"gpu"},
 {"id":"cpu_r5_5600","name":"Ryzen 5 5600","type":"Процессор","rarity":"Обычная","power":35,"price":180,"image":"cpu"},
 {"id":"cpu_i5_13600k","name":"Core i5-13600K","type":"Процессор","rarity":"Редкая","power":65,"price":550,"image":"cpu"},
 {"id":"cpu_ryzen9","name":"Ryzen 9 7950X","type":"Процессор","rarity":"Эпическая","power":85,"price":1000,"image":"cpu"},
 {"id":"mb_b550","name":"MSI B550 Tomahawk","type":"Материнская плата","rarity":"Обычная","power":10,"price":140,"image":"board"},
 {"id":"mb_x670e","name":"ASUS X670E Hero","type":"Материнская плата","rarity":"Эпическая","power":25,"price":650,"image":"board"},
 {"id":"ram_ddr4","name":"DDR4 16 GB","type":"Оперативная память","rarity":"Обычная","power":8,"price":90,"image":"ram"},
 {"id":"ram_ddr5","name":"DDR5 32 GB","type":"Оперативная память","rarity":"Редкая","power":18,"price":240,"image":"ram"},
 {"id":"ssd_1tb","name":"NVMe SSD 1 TB","type":"Накопитель","rarity":"Необычная","power":8,"price":120,"image":"ssd"},
 {"id":"psu_850","name":"БП 850 W Gold","type":"Блок питания","rarity":"Редкая","power":12,"price":230,"image":"psu"},
 {"id":"cooler_aio","name":"AIO 360 mm","type":"Охлаждение","rarity":"Эпическая","power":15,"price":320,"image":"cooler"},
 {"id":"case_airflow","name":"Airflow Mid Tower","type":"Корпус","rarity":"Необычная","power":5,"price":110,"image":"case"},
 {"id":"gpu_voodoo5","name":"3dfx Voodoo5 6000 (прототип)","type":"Видеокарта","rarity":"Мифическая","power":40,"price":5000,"image":"mythic"},
 {"id":"gpu_geforce256","name":"NVIDIA GeForce 256","type":"Видеокарта","rarity":"Легендарная","power":20,"price":1200,"image":"gpu"},
]
RARITY_WEIGHTS = [("Обычная",45),("Необычная",27),("Редкая",16),("Эпическая",8),("Легендарная",3.5),("Мифическая",0.5)]
RARITY_COLORS = {"Обычная":"#9ca3af","Необычная":"#58c98b","Редкая":"#55a7ff","Эпическая":"#b28cff","Легендарная":"#ffbf59","Мифическая":"#ff68ce"}
CARD_MAP = {c['id']: c for c in CARDS}

def db():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured")
    return psycopg.connect(DATABASE_URL, row_factory=dict_row)


def init_db():
    with closing(db()) as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id BIGINT PRIMARY KEY,
                username TEXT,
                balance BIGINT NOT NULL DEFAULT 500,
                last_drop BIGINT NOT NULL DEFAULT 0,
                last_daily BIGINT NOT NULL DEFAULT 0,
                created_at BIGINT NOT NULL
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS inventory (
                id BIGSERIAL PRIMARY KEY,
                user_id BIGINT NOT NULL,
                card_id TEXT NOT NULL,
                acquired_at BIGINT NOT NULL
            )
        """)
        con.execute("""
            CREATE TABLE IF NOT EXISTS builds (
                user_id BIGINT PRIMARY KEY,
                selected TEXT NOT NULL DEFAULT '{}'
            )
        """)
        con.commit()


init_db()


def ensure_user(user_id, username):
    with closing(db()) as con:
        con.execute(
            """
            INSERT INTO users (user_id, username, created_at)
            VALUES (%s, %s, %s)
            ON CONFLICT (user_id) DO NOTHING
            """,
            (user_id, username, int(time.time()))
        )
        con.execute(
            "UPDATE users SET username = %s WHERE user_id = %s",
            (username, user_id)
        )
        con.execute(
            """
            INSERT INTO builds (user_id, selected)
            VALUES (%s, %s)
            ON CONFLICT (user_id) DO NOTHING
            """,
            (user_id, '{}')
        )
        con.commit()


def get_user(user_id):
    with closing(db()) as con:
        row = con.execute(
            "SELECT * FROM users WHERE user_id = %s",
            (user_id,)
        ).fetchone()
        return dict(row) if row else None


def inventory(user_id):
    with closing(db()) as con:
        rows = con.execute(
            """
            SELECT id, card_id, acquired_at
            FROM inventory
            WHERE user_id = %s
            ORDER BY id DESC
            """,
            (user_id,)
        ).fetchall()

    cards = []
    for row in rows:
        card = CARD_MAP.get(row['card_id'])
        if card:
            cards.append({
                **card,
                'inventory_id': row['id'],
                'acquired_at': row['acquired_at']
            })

    return cards

def pick_card():
    rarity = random.choices([r[0] for r in RARITY_WEIGHTS], weights=[r[1] for r in RARITY_WEIGHTS], k=1)[0]
    choices = [c for c in CARDS if c['rarity']==rarity]
    return random.choice(choices or CARDS)


def add_card(user_id, card_id):
    with closing(db()) as con:
        con.execute(
            """
            INSERT INTO inventory (user_id, card_id, acquired_at)
            VALUES (%s, %s, %s)
            """,
            (user_id, card_id, int(time.time()))
        )
        con.commit()

def web_keyboard():
    url = PUBLIC_URL + '/' if PUBLIC_URL else ''
    if url:
        return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text='🎮 Открыть PC DROP', web_app=WebAppInfo(url=url))]])
    return None


@dp.message(CommandStart())
async def start(message: Message):
    ensure_user(message.from_user.id, message.from_user.username or '')
    text = ('<b>🖥 PC DROP</b>\n\nКоллекционируй комплектующие, открывай дропы и собирай свой игровой ПК!\n\n'
            '🎁 <b>/drop</b> — получить карточку\n🎒 <b>/inventory</b> — твои карточки\n'
            '💰 <b>/balance</b> — баланс\n📅 <b>/daily</b> — ежедневная награда\n\n'
            'Мини-приложение появится после публикации проекта на HTTPS-хостинге.')
    kb=web_keyboard()
    await message.answer(text, reply_markup=kb)


@dp.message(Command('help'))
async def help_cmd(message: Message):
    await message.answer('<b>PC DROP — команды</b>\n/drop — дроп раз в 3 часа\n/inventory — инвентарь\n/sell ID — продать карточку по номеру из инвентаря\n/balance — баланс\n/daily — ежедневная награда')


@dp.message(Command('drop'))
async def drop_cmd(message: Message):
    ensure_user(message.from_user.id, message.from_user.username or '')
    u=get_user(message.from_user.id); now=int(time.time()); wait=10800-(now-u['last_drop'])
    if wait>0:
        await message.answer(f'⏳ Следующий дроп через <b>{wait//3600} ч {(wait%3600)//60} мин</b>.')
        return
    card=pick_card(); add_card(message.from_user.id,card['id'])
    with closing(db()) as con:
        con.execute(
            'UPDATE users SET last_drop=%s WHERE user_id=%s',
            (now, message.from_user.id)
        )
        con.commit()

    await message.answer(
        f"🎁 <b>Дроп получен!</b>\n\n{card['name']}\n"
        f"Тип: {card['type']}\nРедкость: <b>{card['rarity']}</b>\n"
        f"Сила: {card['power']}\n\n"
        "Открой /inventory, чтобы посмотреть карточки."
    )

@dp.message(Command('inventory'))
async def inventory_cmd(message: Message):
    ensure_user(message.from_user.id, message.from_user.username or '')
    cards=inventory(message.from_user.id)
    if not cards:
        await message.answer('🎒 Инвентарь пока пуст. Используй /drop!'); return
    lines=['<b>🎒 Твой инвентарь</b>']
    for c in cards[:30]:
        lines.append(f"#{c['inventory_id']} · {c['name']} — {c['rarity']} · продажа {c['price']} ₵")
    lines.append('\nЧтобы продать карточку: <code>/sell номер</code>')
    await message.answer('\n'.join(lines))


@dp.message(Command('sell'))
async def sell_cmd(message: Message):
    ensure_user(message.from_user.id, message.from_user.username or '')
    parts = (message.text or '').split()

    if len(parts) != 2 or not parts[1].isdigit():
        await message.answer(
            'Укажи номер карточки из инвентаря: <code>/sell 12</code>'
        )
        return

    inv_id = int(parts[1])

    with closing(db()) as con:
        row = con.execute(
            'SELECT id, card_id FROM inventory WHERE id=%s AND user_id=%s',
            (inv_id, message.from_user.id)
        ).fetchone()

        if not row:
            await message.answer('Не нашёл такую карточку в твоём инвентаре.')
            return

        card = CARD_MAP[row['card_id']]

        con.execute('DELETE FROM inventory WHERE id=%s', (inv_id,))
        con.execute(
            'UPDATE users SET balance=balance+%s WHERE user_id=%s',
            (card['price'], message.from_user.id)
        )
        con.commit()

    await message.answer(
        f"💰 Продано: {card['name']}\nНачислено: <b>{card['price']} ₵</b>"
    )


@dp.message(Command('balance'))
async def balance_cmd(message: Message):
    ensure_user(message.from_user.id, message.from_user.username or '')
    u=get_user(message.from_user.id)
    await message.answer(f"💰 Твой баланс: <b>{u['balance']} ₵</b>")


@dp.message(Command('daily'))
async def daily_cmd(message: Message):
    ensure_user(message.from_user.id, message.from_user.username or '')
    now = int(time.time())
    u = get_user(message.from_user.id)

    if now - u['last_daily'] < 86400:
        left = 86400 - (now - u['last_daily'])
        await message.answer(
            f"📅 Награда уже получена. Возвращайся через "
            f"{left//3600} ч {(left%3600)//60} мин."
        )
        return

    with closing(db()) as con:
        con.execute(
            'UPDATE users SET balance=balance+250, last_daily=%s WHERE user_id=%s',
            (now, message.from_user.id)
        )
        con.commit()

    await message.answer('🎉 Ежедневная награда: <b>+250 ₵</b>')


def auth_user(request: Request):
    # For local preview only; production calls must be authenticated with Telegram initData.
    init_data=request.headers.get('x-telegram-init-data','')
    if not init_data:
        dev_id=request.headers.get('x-dev-user-id')
        if os.getenv('ALLOW_DEV_AUTH','1')=='1' and dev_id and dev_id.isdigit():
            uid=int(dev_id); ensure_user(uid,'Игрок'); return uid
        raise HTTPException(401,'Открой приложение из Telegram, чтобы войти.')
    if not BOT_TOKEN:
        raise HTTPException(503,'Не настроен BOT_TOKEN')
    import hashlib, hmac
    from urllib.parse import parse_qsl
    vals=dict(parse_qsl(init_data, keep_blank_values=True)); received=vals.pop('hash',None)
    if not received: raise HTTPException(401,'Неверные данные Telegram')
    data_check='\n'.join(f'{k}={v}' for k,v in sorted(vals.items()))
    secret=hmac.new(b'WebAppData',BOT_TOKEN.encode(),hashlib.sha256).digest()
    calculated=hmac.new(secret,data_check.encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated,received): raise HTTPException(401,'Не удалось проверить Telegram')
    try: user=json.loads(vals['user'])
    except Exception: raise HTTPException(401,'Не удалось определить игрока')
    uid=int(user['id']); ensure_user(uid,user.get('username','')); return uid


@app.get('/')
async def root():
    return FileResponse(BASE_DIR/'web'/'index.html')

@app.get('/api/state')
async def api_state(request: Request):
    uid = auth_user(request)
    u = get_user(uid)
    cards = inventory(uid)

    with closing(db()) as con:
        b = con.execute(
            'SELECT selected FROM builds WHERE user_id=%s',
            (uid,)
        ).fetchone()

    return {
        'user': {
            'id': uid,
            'balance': u['balance'],
            'last_drop': u['last_drop'],
            'last_daily': u['last_daily']
        },
        'inventory': cards,
        'catalog': CARDS,
        'build': json.loads(b['selected'] or '{}')
    }
    
@app.post('/api/drop')
async def api_drop(request: Request):
    uid = auth_user(request)
    now = int(time.time())
    u = get_user(uid)
    wait = 10800 - (now - u['last_drop'])

    if wait > 0:
        raise HTTPException(
            429,
            f'Следующий дроп будет доступен через '
            f'{wait//3600} ч {(wait%3600)//60} мин.'
        )

    card = pick_card()
    add_card(uid, card['id'])

    with closing(db()) as con:
        con.execute(
            'UPDATE users SET last_drop=%s WHERE user_id=%s',
            (now, uid)
        )
        con.commit()

    return {'card': card, 'state': await state_for(uid)}
    
async def state_for(uid):
    u = get_user(uid)

    with closing(db()) as con:
        b = con.execute(
            'SELECT selected FROM builds WHERE user_id=%s',
            (uid,)
        ).fetchone()

    return {
        'user': {
            'id': uid,
            'balance': u['balance'],
            'last_drop': u['last_drop'],
            'last_daily': u['last_daily']
        },
        'inventory': inventory(uid),
        'catalog': CARDS,
        'build': json.loads(b['selected'] or '{}')
    }
    
@app.post('/api/sell/{inv_id}')
async def api_sell(inv_id: int, request: Request):
    uid = auth_user(request)

    with closing(db()) as con:
        row = con.execute(
            'SELECT id, card_id FROM inventory WHERE id=%s AND user_id=%s',
            (inv_id, uid)
        ).fetchone()

        if not row:
            raise HTTPException(404, 'Карточка не найдена')

        card = CARD_MAP[row['card_id']]

        con.execute(
            'DELETE FROM inventory WHERE id=%s',
            (inv_id,)
        )
        con.execute(
            'UPDATE users SET balance=balance+%s WHERE user_id=%s',
            (card['price'], uid)
        )
        con.commit()

    return await state_for(uid)

@app.post('/api/daily')
async def api_daily(request: Request):
    uid = auth_user(request)
    now = int(time.time())
    u = get_user(uid)

    if now - u['last_daily'] < 86400:
        raise HTTPException(429, 'Ежедневная награда уже получена.')

    with closing(db()) as con:
        con.execute(
            'UPDATE users SET balance=balance+250, last_daily=%s WHERE user_id=%s',
            (now, uid)
        )
        con.commit()

    return await state_for(uid)
    
@app.post('/api/build')
async def api_build(request: Request):
    uid = auth_user(request)
    body = await request.json()
    selected = body.get('selected', {})

    if not isinstance(selected, dict):
        raise HTTPException(400, 'Неверная сборка')

    owned = {str(c['inventory_id']): c for c in inventory(uid)}
    valid = {}

    for slot, inv_id in selected.items():
        c = owned.get(str(inv_id))
        if c:
            valid[slot] = str(inv_id)

    with closing(db()) as con:
        con.execute(
            'UPDATE builds SET selected=%s WHERE user_id=%s',
            (json.dumps(valid), uid)
        )
        con.commit()

    return await state_for(uid)

async def run_bot():
    if not bot: return
    await dp.start_polling(bot)

@app.on_event('startup')
async def startup():
    if bot:
        import asyncio
        app.state.bot_task=asyncio.create_task(run_bot())

@app.on_event('shutdown')
async def shutdown():
    task=getattr(app.state,'bot_task',None)
    if task: task.cancel()
    if bot: await bot.session.close()
