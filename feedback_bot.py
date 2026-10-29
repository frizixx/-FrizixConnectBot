import asyncio
import logging
import sqlite3
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

# ================= CONFIGURATION =================
TOKEN = "9276476302:AAFdxdGBKwfwSi7U1WXXzDOY6Bg-H_HwVBQ"
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
    conn.commit()
    conn.close()

init_db()

def add_user_to_db(user_id: int, username: str, full_name: str):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("""
        INSERT OR IGNORE INTO users (user_id, username, full_name) VALUES (?, ?, ?)
    """, (user_id, username, full_name))
    conn.commit()
    conn.close()

# ================= FSM (STATES) =================
class UserState(StatesGroup):
    waiting_for_message = State()
    answering_user = State()

# ================= HANDLERS =================
@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    add_user_to_db(message.from_user.id, message.from_user.username, message.from_user.full_name)
    
    if message.from_user.id == ADMIN_ID:
        await message.answer("👋 Привет, Администратор! Панель управления активна.")
    else:
        await message.answer(
            "👋 Hello! Напишите сообщение, и я передам его владельцу.\n"
            "Владельцем данного бота является @frizixoff. Если у вас есть предложения, что добавить сюда, или вопросы – пишите. 🤗",
            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✍️ Написать сообщение", callback_data="send_feedback")]
            ])
        )

@router.callback_query(F.data == "send_feedback")
async def process_feedback_callback(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Напиши свое сообщение, и я отправлю его создателю:")
    await state.set_state(UserState.waiting_for_message)
    await callback.answer()

@router.message(UserState.waiting_for_message)
async def receive_user_message(message: Message, state: FSMContext):
    user_id = message.from_user.id
    username = f"@{message.from_user.username}" if message.from_user.username else "нет юзернейма"
    full_name = message.from_user.full_name

    # Кнопка для ответа администратору прямо из сообщения
    admin_markup = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💬 Ответить", callback_data=f"reply_{user_id}")]
    ])

    # Пересылаем админу
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
    await state.clear()

# Админ отвечает пользователю через инлайн-кнопку
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
async def admin_send_reply(message: Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID:
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
        await message.answer(f"❌ Не удалось отправить сообщение (возможно, пользователь заблокировал бота):\n`{e}`", parse_mode="Markdown")

    await state.clear()

# ================= MAIN =================
async def main():
    bot = Bot(token=TOKEN)
    dp = Dispatcher()
    dp.include_router(router)

    # Защита от конфликтов сессий
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Бот успешно запущен и ожидает сообщения...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
