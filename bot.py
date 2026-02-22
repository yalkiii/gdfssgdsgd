import asyncio
import sqlite3
import os
import re
from datetime import datetime
from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton, ReplyKeyboardRemove,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
)

# --- ЗАГРУЗКА НАСТРОЕК ИЗ .env ---
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Получаем ID обоих админов
ADMIN_YALKI = int(os.getenv("ADMIN_YALKI", 0))
ADMIN_HOPER = int(os.getenv("ADMIN_HOPER", 0))
ADMIN_IDS = [ADMIN_YALKI, ADMIN_HOPER]

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect('magic_scout.db')
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT,
            dob TEXT,
            english TEXT,
            cpu TEXT,
            gpu TEXT,
            internet_mic TEXT,
            phone TEXT,
            username TEXT,
            status TEXT,
            submit_date TEXT,
            referrer_id INTEGER DEFAULT 0,
            user_id INTEGER DEFAULT 0
        )
    ''')
    conn.commit()
    conn.close()

STATUSES = {
    "new": "🆕 Новая",
    "reject": "❌ Отказ",
    "interview": "💬 Собеседование",
    "training": "📚 На обучении",
    "working": "✅ Работает"
}

# --- СОСТОЯНИЯ АНКЕТЫ ---
class Questionnaire(StatesGroup):
    referrer = State()
    name = State()
    dob = State()
    english = State()
    cpu = State()
    gpu = State()
    internet_and_mic = State()
    phone = State()

# ==========================================
# ЧАСТЬ 1: АНКЕТИРОВАНИЕ И РЕФЕРАЛКИ
# ==========================================

@dp.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    # Извлекаем параметр start для рефералки
    command_args = message.text.split(maxsplit=1)
    referrer_id = 0
    if len(command_args) == 2 and command_args[1].startswith("ref_"):
        try:
            referrer_id = int(command_args[1].split("_")[1])
        except ValueError:
            pass

    # Если это админ - показываем его меню и ссылку
    if user_id in ADMIN_IDS:
        me = await bot.get_me()
        bot_username = me.username
        ref_link = f"https://t.me/{bot_username}?start=ref_{user_id}"
        
        # Определяем, кто именно пишет
        admin_name = "Ялки" if user_id == ADMIN_YALKI else "Хопер"
        
        await message.answer(
            f"👋 Привет, {admin_name}!\n\n"
            f"🔗 Твоя личная реферальная ссылка:\n`{ref_link}`\n\n"
            f"Твоя панель доступна по команде /admin",
            parse_mode="Markdown"
        )
        return

    # ПРОВЕРКА НА ДУБЛИКАТ ЗАЯВКИ
    conn = sqlite3.connect('magic_scout.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM applications WHERE user_id=?", (user_id,))
    existing_app = cursor.fetchone()
    conn.close()

    if existing_app:
        await message.answer("⚠️ Ты уже отправлял заявку! Пожалуйста, ожидай ответа от нашего менеджера.")
        return

    # Сохраняем ID рефовода в состояние
    await state.update_data(referrer=referrer_id)

    await message.answer(
        "👋 Привет! Добро пожаловать в бота Magic Scout.\n\n"
        "Мы ищем технического оператора трансляций. Давай проверим, подходим ли мы друг другу.\n\n"
        "Для начала напиши свои Имя и Фамилию:"
    )
    await state.set_state(Questionnaire.name)

@dp.message(Questionnaire.name)
async def process_name(message: Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Отлично. Напиши свою Дату рождения (например, 15.08.2001):")
    await state.set_state(Questionnaire.dob)

@dp.message(Questionnaire.dob)
async def process_dob(message: Message, state: FSMContext):
    await state.update_data(dob=message.text)
    await message.answer("Как ты оцениваешь свой уровень Английского языка? (Например: B1, средний)")
    await state.set_state(Questionnaire.english)

@dp.message(Questionnaire.english)
async def process_english(message: Message, state: FSMContext):
    await state.update_data(english=message.text)
    await message.answer("Переходим к технике 💻\nНапиши модель своего Процессора (Нам нужен Intel i5 10-го поколения или аналог AMD):")
    await state.set_state(Questionnaire.cpu)

@dp.message(Questionnaire.cpu)
async def process_cpu(message: Message, state: FSMContext):
    await state.update_data(cpu=message.text)
    await message.answer("Какая у тебя Видеокарта? (Напоминаем, минимум GTX 1060):")
    await state.set_state(Questionnaire.gpu)

@dp.message(Questionnaire.gpu)
async def process_gpu(message: Message, state: FSMContext):
    await state.update_data(gpu=message.text)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Да, всё есть"), KeyboardButton(text="Нет")]], resize_keyboard=True)
    await message.answer("Есть ли у тебя стабильный быстрый интернет и гарнитура с микрофоном?", reply_markup=kb)
    await state.set_state(Questionnaire.internet_and_mic)

@dp.message(Questionnaire.internet_and_mic)
async def process_internet_mic(message: Message, state: FSMContext):
    await state.update_data(internet_and_mic=message.text)
    kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📱 Отправить номер", request_contact=True)]], resize_keyboard=True)
    await message.answer("Последний шаг! Отправь номер телефона (нажми кнопку ниже или напиши цифрами).", reply_markup=kb)
    await state.set_state(Questionnaire.phone)

@dp.message(Questionnaire.phone)
async def process_phone(message: Message, state: FSMContext):
    if message.contact:
        phone = message.contact.phone_number
    else:
        text = message.text
        cleaned_phone = re.sub(r'[\s\-\(\)\+]', '', text)
        if not cleaned_phone.isdigit() or len(cleaned_phone) < 10 or len(cleaned_phone) > 15:
            await message.answer("⚠️ Пожалуйста, введи корректный номер телефона (только цифры, можно с плюсом) или воспользуйся кнопкой '📱 Отправить номер'.")
            return
        phone = text

    data = await state.get_data()
    user_id = message.from_user.id
    username = f"@{message.from_user.username}" if message.from_user.username else "Скрыт"
    submit_date = datetime.now().strftime("%d.%m.%Y")
    referrer_id = data.get('referrer', 0)
    
    conn = sqlite3.connect('magic_scout.db')
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO applications (name, dob, english, cpu, gpu, internet_mic, phone, username, status, submit_date, referrer_id, user_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (data['name'], data['dob'], data['english'], data['cpu'], data['gpu'], data['internet_and_mic'], phone, username, "new", submit_date, referrer_id, user_id))
    conn.commit()
    conn.close()
    
    await message.answer("✅ Твоя заявка успешно отправлена! Ожидай ответа.", reply_markup=ReplyKeyboardRemove())
    
    # Уведомляем ВСЕХ админов
    for admin in ADMIN_IDS:
        if admin != 0: # Защита, если ID не заполнен
            try:
                await bot.send_message(admin, f"🚨 Новая заявка от {data['name']}!\nПроверь меню /admin")
            except Exception:
                pass
            
    await state.clear()

# ==========================================
# ЧАСТЬ 2: АДМИН-ПАНЕЛЬ
# ==========================================

async def show_admin_menu(chat_id: int, message_to_edit: Message = None):
    keyboard = [
        [InlineKeyboardButton(text="📋 Все заявки", callback_data="show_all_apps")],
        [InlineKeyboardButton(text="👤 Рефералы Ялки", callback_data="show_refs_yalki")],
        [InlineKeyboardButton(text="👤 Рефералы Хопер", callback_data="show_refs_hoper")]
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    text = "🛠 **Панель управления**\nВыберите нужный раздел:"
    
    if message_to_edit:
        await message_to_edit.edit_text(text, reply_markup=markup, parse_mode="Markdown")
    else:
        await bot.send_message(chat_id, text, reply_markup=markup, parse_mode="Markdown")

@dp.message(Command("admin"))
async def admin_panel(message: Message):
    if message.from_user.id not in ADMIN_IDS:
        return
    await show_admin_menu(message.chat.id)

@dp.callback_query(F.data == "show_all_apps")
async def show_all_apps(callback: CallbackQuery):
    conn = sqlite3.connect('magic_scout.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, submit_date, status FROM applications ORDER BY id DESC")
    apps = cursor.fetchall()
    conn.close()

    if not apps:
        await callback.answer("📭 Заявок пока нет.", show_alert=True)
        return

    keyboard = []
    for app_id, name, date, status in apps:
        status_emoji = STATUSES.get(status, "❓").split()[0]
        btn_text = f"{name} | {date} | {status_emoji}"
        keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f"view_{app_id}")])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main_admin")])
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await callback.message.edit_text(f"📋 **Все заявки (Всего: {len(apps)}):**", reply_markup=markup, parse_mode="Markdown")

# Вспомогательная функция для вывода рефералов конкретного админа
async def render_referrals_list(callback: CallbackQuery, admin_id: int, admin_name: str):
    conn = sqlite3.connect('magic_scout.db')
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, submit_date, status FROM applications WHERE referrer_id=? ORDER BY id DESC", (admin_id,))
    apps = cursor.fetchall()
    conn.close()

    if not apps:
        await callback.answer(f"У {admin_name} пока нет рефералов.", show_alert=True)
        return

    keyboard = []
    for app_id, name, date, status in apps:
        status_emoji = STATUSES.get(status, "❓").split()[0]
        btn_text = f"{name} | {date} | {status_emoji}"
        keyboard.append([InlineKeyboardButton(text=btn_text, callback_data=f"view_{app_id}")])
    
    keyboard.append([InlineKeyboardButton(text="🔙 Назад", callback_data="back_to_main_admin")])
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await callback.message.edit_text(f"👥 **Рефералы {admin_name} (Всего: {len(apps)}):**", reply_markup=markup, parse_mode="Markdown")

@dp.callback_query(F.data == "show_refs_yalki")
async def show_refs_yalki_handler(callback: CallbackQuery):
    await render_referrals_list(callback, ADMIN_YALKI, "Ялки")

@dp.callback_query(F.data == "show_refs_hoper")
async def show_refs_hoper_handler(callback: CallbackQuery):
    await render_referrals_list(callback, ADMIN_HOPER, "Хопер")

@dp.callback_query(F.data == "back_to_main_admin")
async def back_to_main_admin(callback: CallbackQuery):
    await show_admin_menu(callback.message.chat.id, callback.message)

@dp.callback_query(F.data.startswith("view_"))
async def view_application(callback: CallbackQuery):
    app_id = callback.data.split("_")[1]
    
    conn = sqlite3.connect('magic_scout.db')
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM applications WHERE id=?", (app_id,))
    app = cursor.fetchone()
    conn.close()

    if not app:
        await callback.answer("Заявка не найдена или была удалена!")
        return

    # Определяем, чей это реферал для красивого отображения
    referrer_id = app[11]
    ref_text = "Нет (Органика)"
    if referrer_id == ADMIN_YALKI:
        ref_text = "Ялки"
    elif referrer_id == ADMIN_HOPER:
        ref_text = "Хопер"
    elif referrer_id != 0:
        ref_text = f"Неизвестный ID ({referrer_id})"
    
    text = (
        f"📄 **ЗАЯВКА #{app[0]}**\n"
        f"Текущий статус: {STATUSES.get(app[9], 'Неизвестно')}\n"
        f"Дата подачи: {app[10]}\n"
        f"Чей реферал: **{ref_text}**\n\n"
        f"👤 **Имя:** {app[1]}\n"
        f"📅 **ДР:** {app[2]}\n"
        f"🇬🇧 **Англ:** {app[3]}\n\n"
        f"💻 **ЖЕЛЕЗО:**\n"
        f"Процессор: {app[4]}\n"
        f"Видеокарта: {app[5]}\n"
        f"Инет/Микро: {app[6]}\n\n"
        f"📞 **КОНТАКТЫ:**\n"
        f"Телефон: {app[7]}\n"
        f"Telegram: {app[8]}"
    )

    keyboard = [
        [InlineKeyboardButton(text="❌ Отказ", callback_data=f"status_{app_id}_reject"),
         InlineKeyboardButton(text="💬 Собеседование", callback_data=f"status_{app_id}_interview")],
        [InlineKeyboardButton(text="📚 На обучении", callback_data=f"status_{app_id}_training"),
         InlineKeyboardButton(text="✅ Работает", callback_data=f"status_{app_id}_working")],
        [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_app_{app_id}")],
        [InlineKeyboardButton(text="🔙 В главное меню", callback_data="back_to_main_admin")]
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await callback.message.edit_text(text, reply_markup=markup, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("status_"))
async def change_status(callback: CallbackQuery):
    _, app_id, new_status = callback.data.split("_")
    
    conn = sqlite3.connect('magic_scout.db')
    cursor = conn.cursor()
    cursor.execute("UPDATE applications SET status=? WHERE id=?", (new_status, app_id))
    conn.commit()
    conn.close()

    await callback.answer(f"Статус изменен на: {STATUSES[new_status]}", show_alert=True)
    await view_application(callback)

@dp.callback_query(F.data.startswith("delete_app_"))
async def ask_delete_confirmation(callback: CallbackQuery):
    app_id = callback.data.split("_")[2]
    
    keyboard = [
        [InlineKeyboardButton(text="⚠️ ДА, УДАЛИТЬ", callback_data=f"confirm_delete_{app_id}")],
        [InlineKeyboardButton(text="Отмена", callback_data=f"view_{app_id}")]
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await callback.message.edit_text(f"❗️ **Удалить заявку #{app_id}?**\nЭто нельзя отменить.", reply_markup=markup, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("confirm_delete_"))
async def execute_delete(callback: CallbackQuery):
    app_id = callback.data.split("_")[2]
    
    conn = sqlite3.connect('magic_scout.db')
    cursor = conn.cursor()
    cursor.execute("DELETE FROM applications WHERE id=?", (app_id,))
    conn.commit()
    conn.close()

    await callback.answer(f"Заявка #{app_id} удалена.", show_alert=True)
    await show_admin_menu(callback.message.chat.id, callback.message)

# --- ЗАПУСК ---
async def main():
    init_db()
    print("Бот Magic Scout запущен! Панель для Ялки и Хопера готова.")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())