import sqlite3
import re
import os
from datetime import datetime, timedelta
from typing import Optional, Tuple, List

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler, CallbackQueryHandler
)
from telegram.request import HTTPXRequest

TOKEN = "8791934705:AAFklC8iQkrb2FMcFH_rCUQVTfAqI_Tzk-E"
CONNECT_TIMEOUT = 30.0
READ_TIMEOUT = 30.0
WRITE_TIMEOUT = 30.0

RECIPE_NAME, RECIPE_INGREDIENTS, RECIPE_STEPS = range(3)

DB_PATH = os.path.join(os.path.dirname(__file__), 'recipes.db')

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS recipes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE,
        ingredients TEXT,
        steps TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS reminders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        chat_id INTEGER,
        text TEXT,
        remind_time TEXT,
        interval_days INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        username TEXT PRIMARY KEY,
        user_id INTEGER,
        chat_id INTEGER,
        first_seen TIMESTAMP
    )''')
    conn.commit()
    conn.close()
    print("✅ База данных готова")

def save_user(username: str, user_id: int, chat_id: int):
    username = username.lower()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT OR REPLACE INTO users (username, user_id, chat_id, first_seen) VALUES (?, ?, ?, ?)",
              (username, user_id, chat_id, datetime.now()))
    conn.commit()
    conn.close()

def get_user_chat_id(username: str) -> Optional[int]:
    username = username.lower()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT chat_id FROM users WHERE username = ?", (username,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def get_user_id(username: str) -> Optional[int]:
    username = username.lower()
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT user_id FROM users WHERE username = ?", (username,))
    result = c.fetchone()
    conn.close()
    return result[0] if result else None

def add_recipe_to_db(name: str, ingredients: str, steps: str) -> bool:
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("INSERT INTO recipes (name, ingredients, steps) VALUES (?, ?, ?)",
                  (name.lower(), ingredients, steps))
        conn.commit()
        conn.close()
        return True
    except sqlite3.IntegrityError:
        return False

def find_recipe(name: str) -> Optional[Tuple]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, ingredients, steps FROM recipes WHERE name LIKE ? LIMIT 1",
              (f"%{name.lower()}%",))
    result = c.fetchone()
    conn.close()
    return result

def get_random_recipe() -> Optional[Tuple]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name, ingredients, steps FROM recipes ORDER BY RANDOM() LIMIT 1")
    result = c.fetchone()
    conn.close()
    return result

def get_all_recipes_names() -> List[str]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT name FROM recipes")
    result = [row[0] for row in c.fetchall()]
    conn.close()
    return result

def add_reminder_db(user_id: int, chat_id: int, text: str, remind_time: datetime, interval_days: int = 0):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO reminders (user_id, chat_id, text, remind_time, interval_days) VALUES (?, ?, ?, ?, ?)",
              (user_id, chat_id, text, remind_time.strftime("%Y-%m-%d %H:%M"), interval_days))
    conn.commit()
    conn.close()

def get_active_reminders(user_id: int) -> List[Tuple]:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, text, remind_time, interval_days FROM reminders WHERE user_id = ? AND is_active = 1 ORDER BY remind_time",
              (user_id,))
    result = c.fetchall()
    conn.close()
    return result

def delete_reminder(reminder_id: int, user_id: int) -> bool:
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE reminders SET is_active = 0 WHERE id = ? AND user_id = ?", (reminder_id, user_id))
    affected = c.rowcount
    conn.commit()
    conn.close()
    return affected > 0

def get_due_reminders() -> List[Tuple]:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT id, user_id, chat_id, text, remind_time, interval_days FROM reminders WHERE is_active = 1 AND remind_time <= ?", (now,))
    result = c.fetchall()
    conn.close()
    return result

def reschedule_reminder(reminder_id: int, interval_days: int, old_time_str: str):
    if interval_days <= 0:
        return False
    old_time = datetime.strptime(old_time_str, "%Y-%m-%d %H:%M")
    new_time = old_time + timedelta(days=interval_days)
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("UPDATE reminders SET remind_time = ? WHERE id = ?", (new_time.strftime("%Y-%m-%d %H:%M"), reminder_id))
    conn.commit()
    conn.close()
    return True

# ========== РЕЦЕПТЫ ==========
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.username:
        save_user(update.effective_user.username, update.effective_user.id, update.effective_chat.id)
    await update.message.reply_text(
        "👨‍🍳 Бытовой помощник\n\n"
        "📖 Рецепты:\n/add_recipe - добавить рецепт\n/find <название> - найти рецепт\n"
        "/random - случайный рецепт\n/all - все рецепты\n\n"
        "⏰ Напоминания:\n/remind - создать напоминание\n/mytasks - мои напоминания\n"
        "/done <номер> - удалить напоминание\n\n"
        "🎮 Меню задач:\n/task - выбрать задачу\n\n"
        "📝 Пример: /task"
    )

async def add_recipe_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🍽 Название блюда:")
    return RECIPE_NAME

async def recipe_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['recipe_name'] = update.message.text
    await update.message.reply_text("📝 Ингредиенты:")
    return RECIPE_INGREDIENTS

async def recipe_ingredients(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['recipe_ingredients'] = update.message.text
    await update.message.reply_text("👨‍🍳 Приготовление:")
    return RECIPE_STEPS

async def recipe_steps(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = context.user_data['recipe_name']
    if add_recipe_to_db(name, context.user_data['recipe_ingredients'], update.message.text):
        await update.message.reply_text(f"✅ Рецепт {name} сохранён!")
    else:
        await update.message.reply_text(f"❌ Рецепт {name} уже существует!")
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ Отменено.")
    return ConversationHandler.END

async def find_recipe_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("🔍 Пример: /find борщ")
        return
    recipe = find_recipe(" ".join(context.args))
    if recipe:
        name, ingredients, steps = recipe
        await update.message.reply_text(f"🍳 {name.title()}\n\n📦 {ingredients}\n\n👨‍🍳 {steps}")
    else:
        await update.message.reply_text("😕 Не найден")

async def random_recipe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    recipe = get_random_recipe()
    if recipe:
        name, ingredients, steps = recipe
        await update.message.reply_text(f"🎲 {name.title()}\n\n📦 {ingredients}\n\n👨‍🍳 {steps}")
    else:
        await update.message.reply_text("📭 Нет рецептов")

async def list_all_recipes(update: Update, context: ContextTypes.DEFAULT_TYPE):
    names = get_all_recipes_names()
    if not names:
        await update.message.reply_text("📭 Нет рецептов")
        return
    await update.message.reply_text("📖 Мои рецепты:\n" + "\n".join([f"• {n.title()}" for n in names]))

# ========== НАПОМИНАНИЯ ==========
USERS = ["hald1rka", "nady_sali"]
temp_remind = {}

async def remind_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton("👤 Мне", callback_data="remind_me")]]
    for u in USERS:
        keyboard.append([InlineKeyboardButton(f"👤 @{u}", callback_data=f"remind_user_{u}")])
    keyboard.append([InlineKeyboardButton("❌ Отмена", callback_data="cancel_remind")])
    await update.message.reply_text("⏰ Кому отправить напоминание?", reply_markup=InlineKeyboardMarkup(keyboard))

async def remind_recipient_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "cancel_remind":
        await query.edit_message_text("❌ Отменено")
        return
    recipient = "me" if query.data == "remind_me" else query.data.replace("remind_user_", "")
    temp_remind[query.from_user.id] = {"recipient": recipient}
    await query.edit_message_text("📝 Напишите текст напоминания:\n(или /cancel)")

async def handle_remind_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in temp_remind:
        await update.message.reply_text("❌ Начните с /remind")
        return
    temp_remind[user_id]["text"] = update.message.text
    # Изменённые кнопки: "Сейчас" и "Через 10 минут"
    keyboard = [
        [InlineKeyboardButton("⏰ Сейчас", callback_data="time_now")],
        [InlineKeyboardButton("⏰ Через 10 минут", callback_data="time_10min")],
        [InlineKeyboardButton("⏰ Через 30 минут", callback_data="time_30min")],
        [InlineKeyboardButton("⏰ Через 1 час", callback_data="time_1hour")],
        [InlineKeyboardButton("⏰ Через 2 часа", callback_data="time_2hour")],
        [InlineKeyboardButton("📅 Завтра в 09:00", callback_data="time_tomorrow9")],
        [InlineKeyboardButton("❌ Отмена", callback_data="cancel_remind")]
    ]
    await update.message.reply_text(f"✅ Текст: {update.message.text}\n\n⏰ Выберите время:", reply_markup=InlineKeyboardMarkup(keyboard))

async def remind_time_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if user_id not in temp_remind:
        await query.edit_message_text("❌ Ошибка. Начните заново с /remind")
        return
    if query.data == "cancel_remind":
        temp_remind.pop(user_id, None)
        await query.edit_message_text("❌ Отменено")
        return
    now = datetime.now()
    if query.data == "time_now":
        remind_time = now  # сразу
    elif query.data == "time_10min":
        remind_time = now + timedelta(minutes=10)
    elif query.data == "time_30min":
        remind_time = now + timedelta(minutes=30)
    elif query.data == "time_1hour":
        remind_time = now + timedelta(hours=1)
    elif query.data == "time_2hour":
        remind_time = now + timedelta(hours=2)
    elif query.data == "time_tomorrow9":
        remind_time = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
    else:
        await query.edit_message_text("❌ Неизвестное время")
        return
    await finalize_reminder(query, user_id, remind_time, context.bot)

async def finalize_reminder(query, user_id, remind_time, bot):
    data = temp_remind.pop(user_id, None)
    if not data:
        await query.edit_message_text("❌ Ошибка: данные не найдены")
        return
    recipient, text = data["recipient"], data["text"]
    admin = query.from_user.username or "админ"
    if recipient == "me":
        add_reminder_db(query.from_user.id, query.message.chat_id, f"🔔 {text}", remind_time, 0)
        await query.edit_message_text(f"✅ Напоминание создано!\n📝 {text}\n⏰ {remind_time.strftime('%d.%m.%Y %H:%M')}")
    else:
        target_uid, target_cid = get_user_id(recipient), get_user_chat_id(recipient)
        if target_uid and target_cid:
            add_reminder_db(target_uid, target_cid, f"🔔 От @{admin}: {text}", remind_time, 0)
            try:
                await bot.send_message(
                    chat_id=target_cid,
                    text=f"🔔 Напоминание от @{admin}\n📝 {text}\n⏰ {remind_time.strftime('%H:%M')}"
                )
                await query.edit_message_text(f"✅ Напоминание для @{recipient} создано и отправлено!\n📝 {text}\n⏰ {remind_time.strftime('%d.%m.%Y %H:%M')}")
            except Exception:
                await query.edit_message_text(f"✅ Напоминание для @{recipient} создано, но не удалось отправить уведомление.\n📝 {text}\n⏰ {remind_time.strftime('%d.%m.%Y %H:%M')}")
        else:
            await query.edit_message_text(f"⚠️ @{recipient} не запускал бота, напоминание сохранено.\n📝 {text}\n⏰ {remind_time.strftime('%d.%m.%Y %H:%M')}")

async def list_my_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    reminders = get_active_reminders(update.effective_user.id)
    if not reminders:
        await update.message.reply_text("📭 Нет активных напоминаний.")
        return
    text = "⏰ Ваши напоминания:\n"
    for rid, rtext, rtime, interval in reminders:
        dt = datetime.strptime(rtime, "%Y-%m-%d %H:%M")
        text += f"{rid}. {rtext}\n   🕒 {dt.strftime('%d.%m %H:%M')}"
        if interval > 0:
            text += " (повтор)"
        text += "\n\n"
    await update.message.reply_text(text + "🗑 /done номер")

async def done_reminder(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not context.args:
        await update.message.reply_text("❌ Пример: /done 3")
        return
    try:
        rid = int(context.args[0])
        if delete_reminder(rid, update.effective_user.id):
            await update.message.reply_text(f"✅ Задача #{rid} удалена")
        else:
            await update.message.reply_text("❌ Не найдена")
    except ValueError:
        await update.message.reply_text("❌ Нужно число")

# ========== МЕНЮ ЗАДАЧ ==========
TASKS = {
    "food": {"name": "🍽 Еда готова", "text": "Помыть посуду", "delay": 20},
    "trash": {"name": "🗑 Вынести мусор", "text": "Вынести мусор", "delay": 0},
    "order": {"name": "📦 Забрать заказ", "text": "Забрать заказ", "delay": 0},
    "clean": {"name": "🪠 Черкаш", "text": "Почистить унитаз", "delay": 0},
}
pending_orders = {}

async def task_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [[InlineKeyboardButton(t["name"], callback_data=f"task_{k}")] for k, t in TASKS.items()]
    await update.message.reply_text("📋 Выберите задачу:", reply_markup=InlineKeyboardMarkup(keyboard))

async def task_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    task_key = query.data.replace("task_", "")
    context.user_data['selected_task'] = task_key
    keyboard = [[InlineKeyboardButton(f"👤 @{u}", callback_data=f"user_{task_key}_{u}")] for u in USERS]
    await query.edit_message_text(f"👥 Выберите получателя для {TASKS[task_key]['name']}:", reply_markup=InlineKeyboardMarkup(keyboard))

async def user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    parts = query.data.split("_", 2)
    if len(parts) < 3:
        await query.edit_message_text("❌ Ошибка")
        return
    task_key, target = parts[1], parts[2]
    task = TASKS.get(task_key)
    if not task:
        await query.edit_message_text("❌ Задача не найдена")
        return
    admin = query.from_user.username or "админ"

    if task_key == "order":
        pending_orders[query.from_user.id] = {"target": target, "admin": admin}
        await query.edit_message_text(f"📸 Отправьте ФОТО заказа для @{target}\n(просто отправьте фото)")
        return

    target_lower = target.lower()
    target_cid = get_user_chat_id(target_lower)
    target_uid = get_user_id(target_lower)

    if task["delay"] == 0:
        if target_cid:
            try:
                await context.bot.send_message(
                    chat_id=target_cid,
                    text=f"🔔 {task['text']}\n✉️ От @{admin}"
                )
                await query.edit_message_text(f"✅ Задача мгновенно отправлена @{target}: {task['text']}")
            except Exception:
                await query.edit_message_text(f"⚠️ Не удалось отправить уведомление @{target}.\nЗадача не сохранена.")
        else:
            await query.edit_message_text(f"⚠️ @{target} не запускал бота. Задача не может быть отправлена.\nПопросите его написать /start")
    else:
        if not target_uid or not target_cid:
            await query.edit_message_text(f"⚠️ @{target} не запускал бота. Задача не сохранена.")
            return
        remind_time = datetime.now() + timedelta(minutes=task["delay"])
        add_reminder_db(target_uid, target_cid, f"🔔 Задача от @{admin}: {task['text']}", remind_time, 0)
        await query.edit_message_text(f"✅ Задача для @{target} создана.\n📝 {task['text']}\n⏰ Напомню через {task['delay']} минут (в {remind_time.strftime('%H:%M')})")

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in pending_orders:
        await update.message.reply_text("❌ Нет активного заказа. Используйте /task и выберите 'Забрать заказ'")
        return
    data = pending_orders.pop(user_id)
    target, admin = data["target"], data["admin"]
    target_lower = target.lower()
    target_cid = get_user_chat_id(target_lower)
    if not target_cid:
        await update.message.reply_text(f"⚠️ @{target} не запускал бота, фото не может быть отправлено.")
        return
    if not update.message.photo:
        await update.message.reply_text("❌ Отправьте фото")
        return
    photo = update.message.photo[-1]
    caption = f"📦 ЗАКАЗ ДЛЯ @{target}\n✉️ От @{admin}\n\n🔔 Нужно забрать!"
    try:
        await context.bot.send_photo(chat_id=target_cid, photo=photo.file_id, caption=caption)
        await update.message.reply_text(f"✅ Фото заказа отправлено @{target}!")
        remind_time = datetime.now() + timedelta(minutes=30)
        add_reminder_db(update.effective_user.id, update.effective_chat.id, f"📦 Напомнить о заказе для @{target}", remind_time, 0)
    except Exception as e:
        await update.message.reply_text(f"❌ Не удалось отправить фото: {e}")

# ========== ПЛАНИРОВЩИК ==========
async def send_reminders(context: ContextTypes.DEFAULT_TYPE):
    for rid, uid, cid, text, tstr, interval in get_due_reminders():
        try:
            await context.bot.send_message(chat_id=cid, text=f"🔔 {text}")
            if interval > 0:
                reschedule_reminder(rid, interval, tstr)
            else:
                delete_reminder(rid, uid)
        except Exception as e:
            print(f"Ошибка отправки: {e}")

# ========== ЗАПУСК ==========
def main():
    print("🚀 Запуск бота...")
    init_db()
    app = Application.builder().token(TOKEN).request(
        HTTPXRequest(connect_timeout=CONNECT_TIMEOUT, read_timeout=READ_TIMEOUT, write_timeout=WRITE_TIMEOUT)
    ).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("random", random_recipe))
    app.add_handler(CommandHandler("find", find_recipe_command))
    app.add_handler(CommandHandler("all", list_all_recipes))
    app.add_handler(ConversationHandler(
        entry_points=[CommandHandler("add_recipe", add_recipe_start)],
        states={
            RECIPE_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, recipe_name)],
            RECIPE_INGREDIENTS: [MessageHandler(filters.TEXT & ~filters.COMMAND, recipe_ingredients)],
            RECIPE_STEPS: [MessageHandler(filters.TEXT & ~filters.COMMAND, recipe_steps)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    ))

    app.add_handler(CommandHandler("remind", remind_command))
    app.add_handler(CallbackQueryHandler(remind_recipient_callback, pattern="^(remind_|cancel_remind)"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_remind_text, block=False))
    app.add_handler(CallbackQueryHandler(remind_time_callback, pattern="^time_"))

    app.add_handler(CommandHandler("mytasks", list_my_tasks))
    app.add_handler(CommandHandler("done", done_reminder))

    app.add_handler(CommandHandler("task", task_command))
    app.add_handler(CallbackQueryHandler(task_callback, pattern="^task_"))
    app.add_handler(CallbackQueryHandler(user_callback, pattern="^user_"))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))

    if app.job_queue:
        app.job_queue.run_repeating(send_reminders, interval=60, first=10)

    print("✅ БОТ УСПЕШНО ЗАПУЩЕН!")
    print("📱 Напишите /start в Telegram")
    print("💡 Для выбора задачи используйте /task")
    app.run_polling()

if __name__ == "__main__":
    main()