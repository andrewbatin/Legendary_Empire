import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, CallbackQueryHandler, ConversationHandler, MessageHandler, Filters, CallbackContext
import sqlite3
import random

# Настройка логирования
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Соединяемся с базой данных SQLite
conn = sqlite3.connect('legendary_empire.db', check_same_thread=False)
cursor = conn.cursor()

# Инициализируем таблицу пользователей
def init_db():
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            game_id TEXT UNIQUE,
            nickname TEXT,
            registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            map_state TEXT,
            resources TEXT,
            castle_built BOOLEAN DEFAULT FALSE
        );
    ''')
    conn.commit()

# Генерируем уникальную карту
def generate_map():
    tiles = ['🌳', '🏜️', '🏔️', '🌋', '🌊', '🌱']  # Элементы карты
    size = 10
    return [[random.choice(tiles) for _ in range(size)] for _ in range(size)]

# Сохраняем состояние карты
def save_map_state(user_id, map_state):
    cursor.execute("UPDATE users SET map_state=? WHERE user_id=?", (repr(map_state), user_id))
    conn.commit()

# Получаем сохранённое состояние карты
def load_map_state(user_id):
    cursor.execute("SELECT map_state FROM users WHERE user_id=?", (user_id,))
    state = cursor.fetchone()
    return eval(state[0]) if state else None

# Получаем начальные ресурсы
def get_start_resources():
    return {'stones': 20, 'coins': 50, 'trees': 20, 'diamonds': 1}

# Основные команды и реакции бота

# Начало игры (/start)
def start(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    cursor.execute("SELECT COUNT(*) FROM users WHERE user_id=?", (user_id,))
    count = cursor.fetchone()[0]
    if count > 0:
        update.message.reply_text("Вы уже зарегистрированы!")
    else:
        buttons = [[InlineKeyboardButton("Начать ⭐", callback_data="start_game")]]
        markup = InlineKeyboardMarkup(buttons)
        update.message.reply_text("Добро пожаловать в легендарную империю!\nНачнем приключение?", reply_markup=markup)

# Выбор игрового имени
def set_nickname(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    nickname = update.message.text.strip()
    if len(nickname) < 2 or len(nickname) > 15:
        update.message.reply_text("Имя должно быть длиной от 2 до 15 символов. Повторите попытку.")
        return
    cursor.execute("UPDATE users SET nickname=? WHERE user_id=?", (nickname, user_id))
    conn.commit()
    update.message.reply_text(f"Приветствуем тебя, {nickname}, начинай исследовать мир!")

# Отображаем карту
def show_map(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    map_state = load_map_state(user_id)
    if not map_state:
        map_state = generate_map()
        save_map_state(user_id, map_state)
    keyboard = []
    for i in range(len(map_state)):
        row_buttons = []
        for j in range(len(map_state[i])):
            button_text = f'{i}-{j}'
            row_buttons.append(InlineKeyboardButton(button_text, callback_data=f'cell_{button_text}'))
        keyboard.append(row_buttons)
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text("Это твоя карта 🗺️. Нажми на клетку, чтобы сделать ход.", reply_markup=reply_markup)

# Обрабатываем выбор клетки на карте
def select_cell(update: Update, context: CallbackContext):
    query = update.callback_query
    user_id = query.from_user.id
    coords = query.data.split('_')[-1].split('-')
    x, y = int(coords[0]), int(coords[1])
    map_state = load_map_state(user_id)
    terrain_type = map_state[x][y]
    results = {
        '🌳': "Поздравляю 🥳! Вы построили замок 🏰.",
        '🏜️': "Вы умерли от странной раны от кактуса 🌵.",
        '🏔️': "Вы погибли, упав с высоты горы 🏔️.",
        '🌋': "Вы сгорели в лаве 🌋.",
        '🌊': "Вы утонули в океане 🌊.",
        '🌱': "Вас съел маленький росток 🌱."
    }
    response = results.get(terrain_type, "Что-то пошло не так 😕")
    query.answer(response)
    query.edit_message_text(response)

# Администрирование (показ статистики)
def admin_stats(update: Update, context: CallbackContext):
    user_id = update.effective_user.id
    if user_id != 8304713213  # Замените YOUR_ADMIN_USER_ID вашим настоящим ID
        update.message.reply_text("Только администраторы имеют доступ.")
        return
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    update.message.reply_text(f"Количество зарегистрированных пользователей: {total_users}")

# Конструктор бота
def main():
    TOKEN = "8066566128:AAGu7ipZd21dF7Bpqw7w6N8YuDWzRDbhL14"  # Здесь вставьте токен вашего бота
    updater = Updater(token=TOKEN, use_context=True)
    dp = updater.dispatcher

    # Командные хэндлеры
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(MessageHandler(Filters.text & (~Filters.command), set_nickname))  # Установка имени
    dp.add_handler(CommandHandler("show_map", show_map))  # Показать карту
    dp.add_handler(CallbackQueryHandler(select_cell, pattern=r'^cell_[0-9]+-[0-9]+$'))  # Обработка выбора клетки
    dp.add_handler(CommandHandler("stats", admin_stats))  # Статистика для администратора

    # Логирование и запуск
    logger.info("Bot started successfully.")
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    init_db()  # Инициализация базы данных перед запуском
    main()
