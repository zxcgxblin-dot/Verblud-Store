import os
import random
import requests
import json 
import re 
import io 
from datetime import datetime, timedelta
from dotenv import load_dotenv
from urllib.parse import urlencode 

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton, InputFile
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes, 
    CallbackQueryHandler,
    ConversationHandler
)

# НОВЫЙ ИМПОРТ: Подключаем логику управления стоком
import stock_manager

# ------------------------------
# 1. КОНФИГУРАЦИЯ: ЧТЕНИЕ ИЗ .ENV
# ------------------------------

load_dotenv()
TOKEN = "8544381766:AAGti1O0hA6Iopxav1223ZsRow3og9TndCw"

# --- Настройки Crypto Bot ---
CRYPTO_BOT_TOKEN = os.getenv("CRYPTO_BOT_TOKEN")
CRYPTO_BOT_URL = "https://pay.crypt.bot/api" 

# --- Настройки Lolz Market 
LOLZ_JWT="eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzUxMiJ9.eyJzdWIiOjkyNTYyODUsImlzcyI6Imx6dCIsImlhdCI6MTc2NTUwMjE1NCwianRpIjoiODk0Njc5Iiwic2NvcGUiOiJiYXNpYyByZWFkIHBvc3QgY29udmVyc2F0ZSBwYXltZW50IGludm9pY2UgY2hhdGJveCBtYXJrZXQiLCJleHAiOjE5MjMxODIxNTR9.De0B0GY741gesWPc6-skboeZdnM2cBZ8GkTNCmyDstgPIZaGOmsMUW2H_N6qFpKer8Fcx8J0tG1Ede0a2jUnguT5bmROPNDmoJA0F7muY7VIbQP8xnoKvP35P21omNOg4HEAi4ORtXTYBsbMghA5Up1NdkUj3YweWfn2ZLrP25o"

LZT_MERCHANT_ID = 1729 

LZT_API_URL_CREATE = "https://prod-api.lzt.market/invoice" 
LZT_API_URL_STATUS = "https://prod-api.lzt.market/invoice" 


# --- Общие настройки ---
PAYMENT_DEADLINE_MINUTES = 15
USDT_RATE = 79.68 

# --- Файлы базы данных ---
USERBASE = "userbase.txt"
ORDERBASE = "orderbase.txt"

# --- Состояния для ConversationHandler ---
CHOOSING_QUANTITY = 1
WAITING_PAYMENT = 2

# ----------------------------------------
# ИНИЦИАЛИЗАЦИЯ СЕССИИ ДЛЯ LZT
# ----------------------------------------
LZT_SESSION = requests.Session()
LZT_SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36",
    "Accept": "application/json", 
    "Content-Type": "application/json"
})
if LOLZ_JWT:
    LZT_SESSION.headers.update({
        "Authorization": f"Bearer {LOLZ_JWT}"
    })


# ------------------------------
# 2. УТИЛИТЫ: РАБОТА С ФАЙЛАМИ (База данных)
# ------------------------------

def load_users():
    if not os.path.exists(USERBASE):
        return {}
    users = {}
    with open(USERBASE, "r", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split("|")
            if len(parts) == 4:
                tg_id, username, uid, balance = parts
                users[int(tg_id)] = {"username": username, "uid": uid, "balance": int(balance)}
    return users

def save_users(users):
    with open(USERBASE, "w", encoding="utf-8") as f:
        for tg_id, data in users.items():
            f.write(f"{tg_id}|{data['username']}|{data['uid']}|{data['balance']}\n")

def generate_unique_uid(users):
    existing = {u["uid"] for u in users.values()}
    uid = str(random.randint(100000000, 999999999))
    while uid in existing:
        uid = str(random.randint(100000000, 999999999))
    return uid

def ensure_orderbase():
    if not os.path.exists(ORDERBASE):
        print(f"INFO: Создание пустого файла {ORDERBASE}")
        open(ORDERBASE, "w", encoding="utf-8").close()

def load_orders():
    orders = []
    if os.path.exists(ORDERBASE):
        with open(ORDERBASE, "r", encoding="utf-8") as f:
            for line in f:
                parts = line.strip().split("|")
                if len(parts) >= 10: 
                    try:
                        order_id, uid, qty, price, status, timestamp, payment_method, total, invoice_url, paid = parts[:10]
                        invoice_id = parts[10] if len(parts) > 10 else "" 
                        orders.append({
                            "order_id": order_id,
                            "uid": uid,
                            "quantity": int(qty),
                            "price": float(price), 
                            "status": status,
                            "timestamp": timestamp,
                            "payment_method": payment_method,
                            "total": float(total), 
                            "invoice_url": invoice_url,
                            "paid": paid == "True",
                            "invoice_id": invoice_id,
                            "product_name": "VERBLUD SQUAD" 
                        })
                    except ValueError as e:
                        print(f"WARNING: Ошибка парсинга строки в {ORDERBASE}: {line.strip()}. Ошибка: {e}")
                        continue
    return orders

def save_order(order):
    price_str = f"{order['price']:.2f}" 
    total_str = f"{order['total']:.2f}" 
    
    with open(ORDERBASE, "a", encoding="utf-8") as f:
        f.write(f"{order['order_id']}|{order['uid']}|{order['quantity']}|{price_str}|{order['status']}|{order['timestamp']}|{order['payment_method']}|{total_str}|{order.get('invoice_url','')}|{order.get('paid',False)}|{order.get('invoice_id','')}\n")

def update_order(order_to_update):
    orders = load_orders()
    with open(ORDERBASE, "w", encoding="utf-8") as f:
        for o in orders:
            current_order = o
            if o["order_id"] == order_to_update["order_id"]:
                current_order = order_to_update
            
            price_str = f"{current_order['price']:.2f}" 
            total_str = f"{current_order['total']:.2f}" 
            
            f.write(f"{current_order['order_id']}|{current_order['uid']}|{current_order['quantity']}|{price_str}|{current_order['status']}|{current_order['timestamp']}|{current_order['payment_method']}|{total_str}|{current_order.get('invoice_url','')}|{current_order.get('paid',False)}|{current_order.get('invoice_id','')}\n")


# ------------------------------
# 3. УТИЛИТЫ: LZT API (Lolz Market)
# ------------------------------

async def create_lzt_invoice(amount: float, order_id: str, tg_id: int, context: ContextTypes.DEFAULT_TYPE):
    """
    Создает счет через Lolz Market API.
    """
    if not LOLZ_JWT:
        await context.bot.send_message(tg_id, "❌ Ошибка конфигурации: Не установлен JWT токен Lolz Market.")
        return None, None
    
    amount_rub_int = int(amount) 

    payload = {
        "amount": amount_rub_int, 
        "currency": "rub", 
        "payment_id": order_id,  
        "comment": f"Оплата заказа #{order_id}", 
        "url_success": "https://t.me/verbludstore", 
        "url_callback": "https://t.me/verbludstore",
        "merchant_id": LZT_MERCHANT_ID, 
        "is_test": True, 
    }
    
    try:
        r = LZT_SESSION.post(LZT_API_URL_CREATE, json=payload, timeout=10)
        r.raise_for_status()
        data = r.json() 
        
        invoice_data = data.get("invoice")
        if not invoice_data:
            error_message = data.get('error') or 'Missing "invoice" field or Unknown format'
            await context.bot.send_message(tg_id, f"❌ Ошибка LZT API: {error_message}.")
            return None, None
            
        if invoice_data.get("status") in ["pending", "not_paid"] and invoice_data.get("url"): 
            invoice_url = invoice_data["url"]
            
            lzt_invoice_id = str(invoice_data.get("id") or invoice_data.get("invoice_id") or order_id)
            
            if lzt_invoice_id == order_id:
                match = re.search(r'/invoice/(\d+)/', invoice_url)
                if match:
                    lzt_invoice_id = match.group(1)
                else:
                    print(f"WARNING: Не удалось распарсить Lolz ID из URL: {invoice_url}. Используем order_id ({order_id}).")

            return invoice_url, str(lzt_invoice_id)
        
        error_message = invoice_data.get('status') or 'Unknown API Error in invoice data'
        await context.bot.send_message(tg_id, f"❌ Ошибка LZT API (ответ JSON): Сообщение: {error_message}.")
        return None, None
    
    except requests.exceptions.RequestException as e:
        print(f"ERROR LZT NEW API: {e}")
        await context.bot.send_message(tg_id, f"❌ Ошибка LZT API (Соединение): Детали: {e}")
        return None, None

def check_lzt_invoice(invoice_id: str, order_id: str):
    """
    Проверяет статус счета Lolz Market.
    """
    if not LOLZ_JWT or not invoice_id or not order_id:
        return False

    params = {"invoice_id": invoice_id, "payment_id": order_id}
    url = f"{LZT_API_URL_STATUS}?{urlencode(params)}"
    print(f"DEBUG LZT CHECK: Попытка: GET {url}")
    
    check_type = f"invoice_id={invoice_id}&payment_id={order_id}"

    try:
        r = LZT_SESSION.get(url, timeout=10)
        
        if r.status_code == 200:
            data = r.json()
            invoice_data = data.get("invoice")
            
            if invoice_data and invoice_data.get("status") == "paid":
                print(f"DEBUG LZT CHECK: Успех по ({check_type}). Статус: paid.")
                return True
            
            current_status = invoice_data.get("status") if invoice_data else "No invoice data"
            print(f"DEBUG LZT CHECK: Статус оплаты ({check_type}). API ответил (200). Статус: {current_status}.") 
            return False

        elif r.status_code in [404, 401]:
            print(f"DEBUG LZT CHECK: Ошибка API ({check_type}). HTTP {r.status_code}. Ответ: {r.text}")
            return False
        else:
            r.raise_for_status() 
            
    except requests.exceptions.RequestException as e:
        print(f"Error checking LZT invoice ({check_type} method failed): {e}")

    return False


# ------------------------------
# 4. УТИЛИТЫ: CRYPTO BOT API (Crypto Bot)
# ------------------------------

def create_crypto_invoice(amount: float, order_id: str, currency: str = "USDT"):
    """Создает счет через Crypto Bot API."""
    if not CRYPTO_BOT_TOKEN:
        print("Ошибка: CRYPTO_BOT_TOKEN не установлен.")
        return None, None
    
    url = f"{CRYPTO_BOT_URL}/createInvoice"
    
    headers = {
        "Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN, 
        "Content-Type": "application/json"
    }
    
    payload = {
        "asset": currency,
        "amount": f"{amount:.2f}",
        "description": f"Order #{order_id}",
        "payload": order_id
    }
    
    try:
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        r.raise_for_status() 
        data = r.json()
        
        if data.get("ok") and data.get("result"):
            invoice_url = data["result"]["pay_url"]
            invoice_id = data["result"]["invoice_id"]
            return invoice_url, str(invoice_id)
        
        print(f"Error: Crypto Bot API returned error: {data.get('error', 'Unknown error')}.")
        return None, None

    except requests.exceptions.RequestException as e:
        print(f"ERROR CRYPTO BOT: {e}")
        return None, None


def check_crypto_invoice(invoice_id: str):
    """Проверяет статус счета через Crypto Bot API."""
    if not CRYPTO_BOT_TOKEN or not invoice_id:
        return False
        
    url = f"{CRYPTO_BOT_URL}/getInvoices"
    
    headers = {"Crypto-Pay-API-Token": CRYPTO_BOT_TOKEN}
    
    params = {
        "invoice_ids": invoice_id,
        "status": "paid" 
    }
    
    try:
        r = requests.get(url, headers=headers, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()
        
        if data.get("ok") and data.get("result") and data["result"].get("items"):
            for item in data["result"]["items"]:
                if str(item.get("invoice_id")) == invoice_id and item.get("status") == "paid":
                    return True
            
    except Exception as e:
        print(f"Error checking crypto invoice {invoice_id}: {e}")
        return False

    return False

# ------------------------------
# 5. ОБРАБОТЧИКИ TELEGRAM (Взаимодействие)
# ------------------------------

START_MESSAGE = (
    "💜✨ Добро пожаловать в Verblud Store! ✨💜\n\n"
    "🖤 Здесь товары для тестирования оплаты."
)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    
    message_source = update.message if update.message else update.callback_query.message if update.callback_query else None
    if not message_source: return

    tg_id = message_source.from_user.id
    username = message_source.from_user.username or "no_username"

    if tg_id not in users:
        users[tg_id] = {"username": username, "uid": generate_unique_uid(users), "balance": 0}
        save_users(users)

    keyboard = [[KeyboardButton("💜Профиль💜"), KeyboardButton("🖤Купить товар🖤")]]
    reply_kb = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)

    inline_keyboard = [
        [InlineKeyboardButton("📩Канал📩", url="https://t.me/verbludstore")],
        [InlineKeyboardButton("💬Беседа💬", url="https://t.me/+ToqCAvaWDAthOGIy")],
        [InlineKeyboardButton("💎Находки💎", url="https://t.me/verblud_found")]
    ]
    inline_kb = InlineKeyboardMarkup(inline_keyboard)

    await context.bot.send_message(tg_id, START_MESSAGE, reply_markup=reply_kb)
    await context.bot.send_message(tg_id, "Полезные ссылки:", reply_markup=inline_kb)

async def profile(update: Update, context: ContextTypes.DEFAULT_TYPE):
    users = load_users()
    tg_id = update.message.from_user.id
    if tg_id not in users:
        return await update.message.reply_text("Профиль не найден")
    u = users[tg_id]
    await update.message.reply_text(f"@{u['username']}\n🔑UID: {u['uid']}\n💰Баланс: {u['balance']}")

async def buy_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "➖️➖️➖️Товары➖️➖️➖️"
    keyboard = [
        [InlineKeyboardButton("💜VERBLUD SQUAD🖤", callback_data="product_verblud")],
        [InlineKeyboardButton("⬅️Назад", callback_data="back_main")]
    ]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    data = q.data
    
    if data == "back_main":
        await q.edit_message_reply_markup(reply_markup=None) 
        await start(q, context)
        return ConversationHandler.END 
        
    if data == "product_verblud":
        
        product_price_rub = 50.0 
        # Используем функцию из stock_manager
        current_stock = stock_manager.get_initial_stock_count() 
        
        context.user_data["current_product"] = {"name":"VERBLUD SQUAD","price":product_price_rub,"stock":current_stock}
        
        await q.edit_message_text(
            f"💜Наличие {context.user_data['current_product']['stock']} шт.🖤\n"
            f"💜Цена: {product_price_rub:.0f}₽🖤\n" 
            f"💜Выберите количество товара, которое хотите купить🖤:"
        )
        return CHOOSING_QUANTITY

async def quantity(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        q = int(update.message.text.strip())
        if q <= 0:
            await update.message.reply_text("Введите количество > 0")
            return CHOOSING_QUANTITY
    except:
        await update.message.reply_text("Введите число")
        return ConversationHandler.END 
    
    product = context.user_data.get("current_product")
    if not product:
        await update.message.reply_text("Товар не выбран. Начните снова.")
        return ConversationHandler.END
        
    # Используем функцию из stock_manager
    current_stock = stock_manager.get_initial_stock_count() 
    if q > current_stock:
        await update.message.reply_text(f"Недостаточно товара на складе. В наличии: {current_stock} шт.")
        return ConversationHandler.END

    context.user_data["current_product"]["quantity"] = q
    
    keyboard = [
        [InlineKeyboardButton("🔷️Crypto Bot🔷️", callback_data="pay_crypto")],
        [InlineKeyboardButton("💚LOLZ_MERCHANT🖤", callback_data="pay_lzt")]
    ]
    
    await update.message.reply_text("💜Выберите способ оплаты🖤", reply_markup=InlineKeyboardMarkup(keyboard))
    return WAITING_PAYMENT

async def payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    users = load_users()
    tg_id = q.from_user.id
    u = users.get(tg_id)
    product = context.user_data.get("current_product")
    
    if not u or not product:
        await q.edit_message_text("Ошибка: профиль или продукт не найдены.")
        return ConversationHandler.END

    order_id = str(random.randint(100000000,999999999))
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    product_price_rub = product["price"]
    product_quantity = product["quantity"]
    
    total_rub_amount = product_price_rub * product_quantity 

    data = q.data
    invoice_url, invoice_id = None, None
    total_amount = 0.0
    PAYMENT_METHOD = ""

    if data == "pay_crypto":
        current_usdt_rate = USDT_RATE
        
        if current_usdt_rate == 0:
            await q.edit_message_text("❌ Не удалось получить актуальный курс валют (курс 0).")
            return ConversationHandler.END
            
        total_usdt_amount = total_rub_amount / current_usdt_rate
        total_amount = total_usdt_amount
        PAYMENT_METHOD = "Crypto Bot (USDT)" 
        invoice_url, invoice_id = create_crypto_invoice(total_amount, order_id, currency="USDT")
        
    elif data == "pay_lzt":
        total_amount = total_rub_amount
        PAYMENT_METHOD = "LOLZ_MERCHANT (RUB)"
        invoice_url, invoice_id = await create_lzt_invoice(total_rub_amount, order_id, tg_id, context)
        
    else:
        await q.edit_message_text("Неизвестный способ оплаты.")
        return ConversationHandler.END

    if not invoice_url or not invoice_id:
        return ConversationHandler.END 

    # 2. save order 
    order = {
        "order_id":order_id,
        "uid":u["uid"],
        "quantity":product_quantity, 
        "price":product_price_rub,  
        "status":"waiting",
        "timestamp":now,
        "payment_method":PAYMENT_METHOD,
        "total":total_amount, 
        "invoice_url":invoice_url,
        "paid":False,
        "invoice_id":invoice_id,
    }
    save_order(order)

    line = "➖️"*16
    deadline = (datetime.strptime(now, "%Y-%m-%d %H:%M:%S") + timedelta(minutes=PAYMENT_DEADLINE_MINUTES)).strftime("%Y-%m-%d %H:%M:%S")
    
    if "USDT" in PAYMENT_METHOD:
        total_display = f"💜Итого: {total_amount:.2f} USDT ({total_rub_amount:.0f}₽)🖤"
    else:
        total_display = f"💜Итого: {total_amount:.0f} ₽🖤"

    # ЧИСТЫЙ ТЕКСТ (без форматирования Markdown)
    text = (f"{line}\n"
            f"💜Товар: {product['name']}🖤\n"
            f"💜Кол-во: {product_quantity}🖤\n"
            f"💜Заказ: {order_id}🖤\n"
            f"💜Время заказа: {now}🖤\n"
            f"{total_display}\n" 
            f"💜Способ оплаты: {PAYMENT_METHOD}🖤\n"
            f"{line}\n"
            f"💜Для оплаты заказа перейдите по ссылке!🖤\n"
            f"💜Время на оплату: {PAYMENT_DEADLINE_MINUTES} минут🖤\n"
            f"💜Необходимо оплатить до: {deadline}🖤\n"
            f"{line}")
            
    markup = InlineKeyboardMarkup([[InlineKeyboardButton("💜Перейти к оплате🖤", url=invoice_url)],[InlineKeyboardButton("💜Проверить оплату🖤", callback_data=f"check_{invoice_id}")], [InlineKeyboardButton("❌Отмена", callback_data=f"cancel_{order_id}")]])
    
    await q.edit_message_text(text, reply_markup=markup) 
    return ConversationHandler.END

async def check_payment(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    
    invoice_id_from_callback = q.data.replace("check_","")
    orders = load_orders()
    
    order = next((o for o in orders if o.get("invoice_id")==invoice_id_from_callback), None)
    
    if not order:
        return await q.answer(f"Заказ не найден (Invoice ID: {invoice_id_from_callback}).", show_alert=True) 

    order_id = order["order_id"] 
    current_message_text = q.message.text
    
    # 1. Проверяем, не был ли заказ уже обработан
    if order["status"] == "completed":
        return await q.answer("✅ ОПЛАЧЕНО!", show_alert=True) 
    if order["status"] == "cancelled":
        return await q.answer("Заказ отменен из-за истечения времени.", show_alert=True)

    # 2. Проверяем на просрочку
    order_time = datetime.strptime(order["timestamp"], "%Y-%m-%d %H:%M:%S")
    if datetime.now() > order_time + timedelta(minutes=PAYMENT_DEADLINE_MINUTES):
        # Дедлайн истек -> Отменяем заказ
        order["status"] = "cancelled"
        update_order(order)
        
        expired_text = current_message_text + "\n\n❌ Заказ отменен: Истекло время на оплату."
        
        await q.edit_message_text(expired_text, reply_markup=None)
        return await q.answer("Время на оплату истекло. Заказ отменен.", show_alert=True)

    # 3. Проверяем оплату через API
    paid = False
    
    if "Crypto Bot" in order["payment_method"]:
        paid = check_crypto_invoice(invoice_id_from_callback)
    elif "LOLZ_MERCHANT" in order["payment_method"]:
        paid = check_lzt_invoice(invoice_id_from_callback, order_id)
    
    
    if paid:
        # ✅ ОПЛАТА УСПЕШНА (Статус PAID)
        
        # --- ЛОГИКА ДОСТАВКИ ТОВАРА ---
        try:
            quantity_to_deliver = order["quantity"]
            # Вызов функции из stock_manager
            delivery_content, remaining_stock = stock_manager.deliver_products(quantity_to_deliver) 
            
            # 1. Отправляем файл пользователю
            file_in_memory = io.BytesIO(delivery_content.encode('utf-8'))
            file_in_memory.name = f"order_{order_id}_verblud_squad.txt"
            
            await context.bot.send_document(
                chat_id=q.from_user.id,
                document=InputFile(file_in_memory),
                caption=f"✅ Ваш заказ #{order_id} готов!"
            )
            
            # 2. Обновляем статус заказа
            order["status"] = "completed"
            order["paid"] = True
            update_order(order)
            
            success_text = current_message_text + "\n\n✅ ОПЛАЧЕНО! Товар доставлен в чат."
            
            # 3. Редактируем сообщение заказа
            await q.edit_message_text(success_text, reply_markup=None)
            
            # 4. Ответ пользователю
            return await q.answer("✅ ОПЛАЧЕНО!", show_alert=True)
            
        except ValueError as e:
            # Если не хватило стока (хотя это должно было быть проверено раньше)
            print(f"ERROR DELIVERY: {e}. Order {order_id}.")
            
            # Отправляем сообщение об ошибке и не меняем статус на 'completed'
            fail_text = current_message_text + "\n\n❌ ОШИБКА ДОСТАВКИ: Недостаточно товара. Обратитесь в поддержку."
            await q.edit_message_text(fail_text, reply_markup=None)
            return await q.answer("❌ Ошибка доставки: Недостаточно товара. Обратитесь в поддержку.", show_alert=True)
            
        except Exception as e:
            print(f"CRITICAL ERROR during delivery for order {order_id}: {e}")
            fail_text = current_message_text + "\n\n❌ КРИТИЧЕСКАЯ ОШИБКА ДОСТАВКИ. Обратитесь в поддержку."
            await q.edit_message_text(fail_text, reply_markup=None)
            return await q.answer("❌ Критическая ошибка доставки. Обратитесь в поддержку.", show_alert=True)
        # --- КОНЕЦ ЛОГИКИ ДОСТАВКИ ТОВАРА ---
        
    else:
        # ❌ ОПЛАТА НЕ ПОДТВЕРЖДЕНА (Статус NOT_PAID/PENDING)
        
        alert_text = (
            "❌️Кажется вы не оплатили товар. Если вы оплатили товар, но все еще видите это сообщение - обратитесь в поддержку."
        )
        
        # Выводим alert
        return await q.answer(alert_text, show_alert=True)
        
async def cancel_order_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    await q.answer()
    
    order_id_to_cancel = q.data.replace("cancel_", "")
    orders = load_orders()
    order = next((o for o in orders if o.get("order_id") == order_id_to_cancel), None)

    if not order:
        return await q.answer("Заказ для отмены не найден.", show_alert=True)

    if order["status"] == "completed":
        return await q.answer("Оплаченный заказ отменить нельзя.", show_alert=True)

    if order["status"] == "waiting":
        order["status"] = "cancelled"
        update_order(order)
        
        # Обновляем сообщение
        cancelled_text = q.message.text + "\n\n🚫 Заказ отменен пользователем."
        
        await q.edit_message_text(cancelled_text, reply_markup=None)
        return await q.answer(f"Заказ #{order_id_to_cancel} успешно отменен.", show_alert=True)
        
    return await q.answer("Заказ уже отменен.", show_alert=True)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Отмена.")
    return ConversationHandler.END

# ------------------------------
# 6. ЗАПУСК БОТА
# ------------------------------

def main():
    ensure_orderbase() 
    # >>> НОВЫЙ ВЫЗОВ: Гарантируем существование файла стока при запуске
    stock_manager.ensure_stock_file_exists() 
    
    if not TOKEN:
        print("Ошибка: TOKEN (Telegram Bot Token) не установлен в .env")
        return
    
    print("Bot started (PTB v20.6)")
    
    app = ApplicationBuilder().token(TOKEN).build()
    
    conv_handler = ConversationHandler(
        entry_points=[CallbackQueryHandler(button, pattern="^(product_verblud|back_main)$")], 
        states={
            CHOOSING_QUANTITY: [MessageHandler(filters.TEXT & ~filters.COMMAND, quantity)],
            WAITING_PAYMENT: [CallbackQueryHandler(payment, pattern="^pay_(crypto|lzt)$")]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(conv_handler)
    
    app.add_handler(MessageHandler(filters.Regex("^💜Профиль💜$"), profile))
    app.add_handler(MessageHandler(filters.Regex("^🖤Купить товар🖤$"), buy_menu))
    
    app.add_handler(CallbackQueryHandler(check_payment, pattern="^check_"))
    app.add_handler(CallbackQueryHandler(cancel_order_callback, pattern="^cancel_")) 
    
    app.run_polling()

if __name__=="__main__":
    main()
