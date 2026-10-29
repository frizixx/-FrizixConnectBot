import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

# ================= CONFIGURATION =================
TOKEN = "9276476302:AAFkse2mksE-inswPuFiUptN5DmjoLY8ovE"
ADMIN_ID = 5226782090  # Твой числовой Telegram ID

logging.basicConfig(level=logging.INFO)
router = Router()

# ================= DATABASE SETUP =================
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            full_name TEXT
        )
    """)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    conn.commit()
    conn.close()

init_db()

def get_bot_status() -> str:
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT value FROM settings WHERE key = 'bot_status'")
    row = cursor.fetchone()
    conn.close()
    if not row:
        return "active"
    return row[0]

def set_bot_status(status: str):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('bot_status', ?)", (status,))
    conn.commit()
    conn.close()

def add_user_to_db(user_id: int, username: str, full_name: str):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)
    """, (user_id, username, full_name))
    conn.commit()
    conn.close()

def get_all_users():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = [row[0] for row in cursor.fetchall()]
    conn.close()
    return users

def get_users_count():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    conn.close()
    return count

# ================= FSM (STATES) =================
class UserState(StatesGroup):
    waiting_for_message = State()
    answering_user = State()
    broadcast_message = State()

# ================= HANDLERS =================
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    user_id = message.from_user.id
    
    if user_id == ADMIN_ID:
        set_bot_status("active")  # Админ командой /start включает бота обратно
        await message.answer(
            "👋 Привет, Администратор!\n"
            "🟢 Бот снова **включен** для всех пользователей.\n"
            "Используй /admin для панели управления или /stop для отключения."
        )
        return

    # Проверка глобального статуса для обычных пользователей
    if get_bot_status() == "disabled":
        await message.answer("В данный момент бот отключен владельцем. Ожидайте!")
        return

    add_user_to_db(user_id, message.from_user.username, message.from_user.full_name)
    await message.answer(
        "👋 Hello! Напишите сообщение, и я передам его владельцу.\n"
        "Владельцем данного бота является @frizixoff. Если у вас есть предложения, что добавить сюда, или вопросы – пишите. 🤗\n\n"
        "✍️ **Просто отправьте ваш текст следующим сообщением в чат:**"
    )
    await state.set_state(UserState.waiting_for_message)

@router.message(Command("admin"))
async def cmd_admin(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return
    
    await state.clear()
    admin_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")],
        [InlineKeyboardButton(text="📢 Сделать рассылку", callback_data="admin_broadcast")]
    ])
    await message.answer("⚙️ **Панель администратора:**", reply_markup=admin_markup, parse_mode="Markdown")

@router.message(Command("stop"))
async def cmd_stop(message: Message, state: FSMContext):
    user_id = message.from_user.id
    
    if user_id == ADMIN_ID:
        set_bot_status("disabled")  # Жестко отключаем бота для всех
        await state.clear()
        await message.answer("🔴 Бот полностью **отключен** для всех пользователей.\nЧтобы включить его обратно, отправьте команду /start.")
    else:
        await state.clear()
        if get_bot_status() == "disabled":
            await message.answer("В данный момент бот отключен владельцем. Ожидайте!")
        else:
            await message.answer("❌ Действие отменено.")

# --- Управление админ-панелью ---
@router.callback_query(F.data == "admin_stats")
async def admin_stats_callback(callback: CallbackQuery):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("У вас нет прав!", show_alert=True)
        return
    
    count = get_users_count()
    status = "🟢 Включен" if get_bot_status() == "active" else "🔴 Отключен"
    await callback.message.answer(f"📊 **Статистика бота:**\n\n👥 Пользователей в базе: `{count}`\n⚙️ Статус: {status}", parse_mode="Markdown")
    await callback.answer()

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast_callback(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("У вас нет прав!", show_alert=True)
        return

    await callback.message.answer("📢 Введите текст для рассылки всем пользователям:")
    await state.set_state(UserState.broadcast_message)
    await callback.answer()

@router.message(UserState.broadcast_message)
async def execute_broadcast(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    if message.text and message.text.startswith("/"):
        return

    users = get_all_users()
    success = 0
    blocked = 0

    status_msg = await message.answer(f"⏳ Рассылка началась... Всего получателей: {len(users)}")

    for uid in users:
        try:
            await message.bot.send_message(uid, message.text)
            success += 1
            await asyncio.sleep(0.04)
        except Exception:
            blocked += 1

    await status_msg.edit_text(
        f"✅ **Рассылка завершена!**\n\n"
        f"📤 Успешно доставлено: `{success}`\n"
        f"❌ Ошибок / заблокировали: `{blocked}`",
        parse_mode="Markdown"
    )
    await state.clear()

# --- Прием сообщений от пользователей ---
@router.message(UserState.waiting_for_message)
async def receive_user_message(message: Message, state: FSMContext):
    user_id = message.from_user.id

    if get_bot_status() == "disabled":
        await message.answer("В данный момент бот отключен владельцем. Ожидайте!")
        return

    if message.text and message.text.startswith("/"):
        return

    username = f"@{message.from_user.username}" if message.from_user.username else "нет юзернейма"
    full_name = message.from_user.full_name

    admin_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Ответить", callback_data=f"reply_{user_id}")]
    ])

    await message.bot.send_message(
        ADMIN_ID,
        f"📩 **Новое сообщение!**\n\n"
        f"От: {full_name} ({username})\n"
        f"ID: `{user_id}`\n\n"
        f"Текст:\n{message.text}",
        reply_markup=admin_markup,
        parse_mode="Markdown"
    )

    await message.answer("✅ Твое сообщение успешно отправлено администратору!")

# --- Ответ администратора пользователю ---
@router.callback_query(F.data.startswith("reply_"))
async def admin_start_reply(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id != ADMIN_ID:
        await callback.answer("У вас нет прав!", show_alert=True)
        return

    target_user_id = int(callback.data.split("_")[1])
    await state.update_data(target_user_id=target_user_id)
    
    await callback.message.answer(f"Введите текст ответа для пользователя (`ID: {target_user_id}`):", parse_mode="Markdown")
    await state.set_state(UserState.answering_user)
    await callback.answer()

@router.message(UserState.answering_user)
async def admin_send_reply(message: Message, state: FsmContext if 'FsmContext' in globals() else FSMContext):
    if message.from_user.id != ADMIN_ID:
        return

    if message.text and message.text.startswith("/"):
        return

    data = await state.get_data()
    target_user_id = data.get("target_user_id")

    try:
        await message.bot.send_message(
            target_user_id,
            f"💌 **Ответ от администратора:**\n\n{message.text}",
            parse_mode="Markdown"
        )
        await message.answer("✅ Ответ успешно отправлен пользователю!")
    except Exception as e:
        await message.answer(f"❌ Не удалось отправить сообщение:\n`{e}`", parse_mode="Markdown")

    await state.clear()

# Универсальный перехватчик для всех остальных сообщений
@router.message()
async def global_fallback_handler(message: Message):
    if message.from_user.id == ADMIN_ID:
        return
    
    if get_bot_status() == "disabled":
        await message.answer("В данный момент бот отключен владельцем. Ожидайте!")

# ================= MAIN =================
async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Бот успешно запущен и ожидает сообщения...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
