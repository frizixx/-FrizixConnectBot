import asyncio
import html
import os
import sqlite3
import time

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ChatType
from aiogram.filters import CommandStart
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    ReplyParameters,
)

# Токен и ID берём из переменных окружения, а не из кода
TOKEN = os.environ["BOT_TOKEN"]
ADMIN_ID = int(os.environ["5226782090"])  # ваш Telegram ID (узнать: @userinfobot)

GREETING = "Привет! Напишите сообщение, и я передам его владельцу."
RECEIVED = "✅ Сообщение успешно передано владельцу. Ожидайте."

db = sqlite3.connect("bot.db")
db.execute(
    "CREATE TABLE IF NOT EXISTS msgs (admin_msg_id INTEGER PRIMARY KEY, user_id INTEGER, user_msg_id INTEGER)"
)
db.execute("CREATE TABLE IF NOT EXISTS banned (user_id INTEGER PRIMARY KEY)")
db.execute(
    "CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, full_name TEXT, username TEXT, first_seen INTEGER)"
)
db.commit()

dp = Dispatcher()


def save_user(user) -> None:
    """Запоминаем пользователя; дата первого обращения не перезаписывается."""
    db.execute(
        "INSERT INTO users VALUES (?, ?, ?, ?) "
        "ON CONFLICT(user_id) DO UPDATE SET full_name=excluded.full_name, username=excluded.username",
        (user.id, user.full_name, user.username, int(time.time())),
    )
    db.commit()


def days_ago(ts) -> str:
    if not ts:
        return "—"
    d = int((time.time() - ts) // 86400)
    if d == 0:
        return "сегодня"
    if 11 <= d % 100 <= 14:
        word = "дней"
    elif d % 10 == 1:
        word = "день"
    elif 2 <= d % 10 <= 4:
        word = "дня"
    else:
        word = "дней"
    return f"{d} {word} назад"


def is_banned(user_id: int) -> bool:
    return db.execute("SELECT 1 FROM banned WHERE user_id=?", (user_id,)).fetchone() is not None


def admin_keyboard(user_id: int, username: str | None = None) -> InlineKeyboardMarkup:
    ban_btn = (
        InlineKeyboardButton(text="✅ Разбан", callback_data=f"unban:{user_id}")
        if is_banned(user_id)
        else InlineKeyboardButton(text="🚫 Бан", callback_data=f"ban:{user_id}")
    )
    row = []
    # Кнопку профиля показываем только если есть username (иначе Telegram
    # может отклонить кнопку из-за настроек приватности пользователя)
    if username:
        row.append(InlineKeyboardButton(text="👤 Профиль", url=f"https://t.me/{username}"))
    row.append(InlineKeyboardButton(text="ℹ️ Инфо", callback_data=f"info:{user_id}"))
    row.append(ban_btn)
    return InlineKeyboardMarkup(inline_keyboard=[row])


@dp.message(CommandStart(), F.chat.type == ChatType.PRIVATE)
async def start(message: Message):
    await message.answer(GREETING)


# Сообщение от пользователя -> владельцу
@dp.message(F.chat.type == ChatType.PRIVATE, F.from_user.id != ADMIN_ID)
async def from_user(message: Message, bot: Bot):
    if is_banned(message.from_user.id):
        return

    save_user(message.from_user)

    copied = await bot.copy_message(
        chat_id=ADMIN_ID,
        from_chat_id=message.chat.id,
        message_id=message.message_id,
        reply_markup=admin_keyboard(message.from_user.id, message.from_user.username),
    )
    db.execute(
        "INSERT OR REPLACE INTO msgs VALUES (?, ?, ?)",
        (copied.message_id, message.from_user.id, message.message_id),
    )
    db.commit()

    # Ответ пользователю с цитатой его сообщения
    await message.reply(RECEIVED)


# Ответ владельца (reply на пересланное сообщение) -> пользователю
@dp.message(F.chat.id == ADMIN_ID, F.reply_to_message)
async def from_admin(message: Message, bot: Bot):
    row = db.execute(
        "SELECT user_id, user_msg_id FROM msgs WHERE admin_msg_id=?",
        (message.reply_to_message.message_id,),
    ).fetchone()
    if not row:
        await message.reply("Не нашёл, кому отвечать. Отвечайте на пересланное сообщение пользователя.")
        return

    user_id, user_msg_id = row
    try:
        await bot.copy_message(
            chat_id=user_id,
            from_chat_id=ADMIN_ID,
            message_id=message.message_id,
            reply_parameters=ReplyParameters(message_id=user_msg_id, allow_sending_without_reply=True),
        )
    except Exception as e:
        await message.reply(f"Не удалось отправить: {e}")


@dp.callback_query(F.from_user.id == ADMIN_ID, F.data.startswith("info:"))
async def user_info(call: CallbackQuery):
    uid = int(call.data.split(":")[1])
    row = db.execute(
        "SELECT full_name, username, first_seen FROM users WHERE user_id=?", (uid,)
    ).fetchone()
    full_name, username, first_seen = row if row else (None, None, None)

    text = (
        "<b>Пользователь</b>\n\n"
        f"ID: <code>{uid}</code>\n"
        f"ФИО: {html.escape(full_name) if full_name else '—'}\n"
        f"Username: {'@' + html.escape(username) if username else '—'}\n"
        "UTM-метки: —\n"
        "Мессенджер: Telegram\n"
        f"Создан: {days_ago(first_seen)}"
    )
    await call.message.reply(text, parse_mode="HTML")
    await call.answer()


@dp.callback_query(F.from_user.id == ADMIN_ID, F.data.startswith(("ban:", "unban:")))
async def ban_toggle(call: CallbackQuery):
    action, uid = call.data.split(":")
    uid = int(uid)
    if action == "ban":
        db.execute("INSERT OR IGNORE INTO banned VALUES (?)", (uid,))
    else:
        db.execute("DELETE FROM banned WHERE user_id=?", (uid,))
    db.commit()

    # достаём username из существующей кнопки профиля (если она была)
    username = None
    for row in call.message.reply_markup.inline_keyboard:
        for b in row:
            if b.url and b.url.startswith("https://t.me/"):
                username = b.url.removeprefix("https://t.me/")

    await call.message.edit_reply_markup(reply_markup=admin_keyboard(uid, username))
    await call.answer("Готово")


async def main():
    bot = Bot(TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
