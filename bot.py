import sqlite3
import asyncio
import os
from dotenv import load_dotenv
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup, BotCommand
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    filters, ContextTypes, ConversationHandler, CallbackQueryHandler
)
load_dotenv()
BOT_TOKEN = os.getenv("TOKEN")

# States untuk ConversationHandler
REGISTER_NAME, REGISTER_GENDER, REGISTER_AGE, REGISTER_INTEREST = range(4)
RATING = 4

# ───────────────────────────────────────────────
# DATABASE SETUP
# ───────────────────────────────────────────────

def init_db():
    conn = sqlite3.connect("matchbot.db")
    c = conn.cursor()

    c.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id     INTEGER PRIMARY KEY,
            username    TEXT,
            name        TEXT,
            gender      TEXT,
            age         INTEGER,
            interest    TEXT,
            rating      REAL DEFAULT 0,
            rating_count INTEGER DEFAULT 0,
            created_at  TEXT
        )
    """)

    c.execute("""
        CREATE TABLE IF NOT EXISTS matches (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            user1_id    INTEGER,
            user2_id    INTEGER,
            started_at  TEXT,
            ended_at    TEXT
        )
    """)

    conn.commit()
    conn.close()

def get_user(user_id):
    conn = sqlite3.connect("matchbot.db")
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    row = c.fetchone()
    conn.close()
    return row

def save_user(user_id, username, name, gender, age, interest):
    conn = sqlite3.connect("matchbot.db")
    c = conn.cursor()
    c.execute("""
        INSERT OR REPLACE INTO users 
        (user_id, username, name, gender, age, interest, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, (user_id, username, name, gender, age, interest, datetime.now().isoformat()))
    conn.commit()
    conn.close()

def update_rating(user_id, new_rating):
    conn = sqlite3.connect("matchbot.db")
    c = conn.cursor()
    c.execute("""
        UPDATE users 
        SET rating = (rating * rating_count + ?) / (rating_count + 1),
            rating_count = rating_count + 1
        WHERE user_id = ?
    """, (new_rating, user_id))
    conn.commit()
    conn.close()

def save_match(user1_id, user2_id):
    conn = sqlite3.connect("matchbot.db")
    c = conn.cursor()
    c.execute("""
        INSERT INTO matches (user1_id, user2_id, started_at)
        VALUES (?, ?, ?)
    """, (user1_id, user2_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()

# ───────────────────────────────────────────────
# STATE GLOBAL
# ───────────────────────────────────────────────

waiting_users = []   # [(user_id, gender, age, interest)]
matched_pairs = {}   # {user_id: partner_id}

# ───────────────────────────────────────────────
# HELPER
# ───────────────────────────────────────────────

def find_match(user_id, gender, age, interest):
    """Cari partner yang cocok dari waiting list"""
    for i, (wid, wgender, wage, winterest) in enumerate(waiting_users):
        if wid == user_id:
            continue
        same_interest = winterest == interest
        close_age = abs(wage - age) <= 5
        if same_interest or close_age:
            waiting_users.pop(i)
            return wid
    for i, (wid, _, _, _) in enumerate(waiting_users):
        if wid != user_id:
            waiting_users.pop(i)
            return wid
    return None

def stars(rating):
    full = int(rating)
    return "⭐" * full + f" ({rating:.1f})"

# ───────────────────────────────────────────────
# REGISTRASI
# ───────────────────────────────────────────────
# set Command 
async def set_command(app):
    await app.bot.set_my_commands([
        BotCommand("start", "Mulai bot"),
        BotCommand("daftar", "Daftar / update profil"),
        BotCommand("cari", "Cari teman ngobrol"),
        BotCommand("batal", "Keluar dari antrian"),
        BotCommand("stop", "Akhiri obrolan"),
        BotCommand("profil", "Lihat profil lo"),
        ])
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)

    if user:
        name, gender, age, interest, rating, rating_count = user[2], user[3], user[4], user[5], user[6], user[7]
        await update.message.reply_text(
            f"👋 Halo lagi, {name}!\n\n"
            f"📋 Profil lo:\n"
            f"• Gender: {gender}\n"
            f"• Umur: {age} tahun\n"
            f"• Minat: {interest}\n"
            f"• Rating: {stars(rating) if rating_count > 0 else 'Belum ada rating'}\n\n"
            "Ketik /cari untuk mulai matching!\n"
            "Ketik /profil untuk update profil."
        )
    else:
        await update.message.reply_text(
            "👋 Selamat datang di MatchBot!\n\n"
            "Sebelum mulai, gw perlu tau sedikit tentang lo.\n"
            "Ketik /daftar untuk registrasi!"
        )

async def daftar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📝 Registrasi\n\nSiapa nama lo?",
        reply_markup=ReplyKeyboardRemove()
    )
    return REGISTER_NAME

async def register_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["name"] = update.message.text.strip()
    keyboard = [["Laki-laki", "Perempuan"]]
    await update.message.reply_text(
        "Gender lo?",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    )
    return REGISTER_GENDER

async def register_gender(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.text not in ["Laki-laki", "Perempuan"]:
        await update.message.reply_text("Pilih: Laki-laki atau Perempuan")
        return REGISTER_GENDER
    context.user_data["gender"] = update.message.text
    await update.message.reply_text(
        "Umur lo? (angka aja)",
        reply_markup=ReplyKeyboardRemove()
    )
    return REGISTER_AGE

async def register_age(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        age = int(update.message.text.strip())
        if age < 13 or age > 99:
            raise ValueError
    except ValueError:
        await update.message.reply_text("Masukkin umur yang valid (13-99)")
        return REGISTER_AGE

    context.user_data["age"] = age
    keyboard = [["Teknologi", "Musik"], ["Gaming", "Olahraga"], ["Film", "Seni"], ["Lainnya"]]
    await update.message.reply_text(
        "Minat/hobi lo?",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    )
    return REGISTER_INTEREST

async def register_interest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["interest"] = update.message.text.strip()

    user = update.effective_user
    data = context.user_data

    save_user(
        user.id, user.username,
        data["name"], data["gender"],
        data["age"], data["interest"]
    )

    await update.message.reply_text(
        f"✅ Registrasi selesai!\n\n"
        f"👤 Nama: {data['name']}\n"
        f"⚧ Gender: {data['gender']}\n"
        f"🎂 Umur: {data['age']} tahun\n"
        f"🎯 Minat: {data['interest']}\n\n"
        "Ketik /cari untuk mulai matching!",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("❌ Dibatalin.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

# ───────────────────────────────────────────────
# MATCHING
# ───────────────────────────────────────────────

async def cari(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)

    if not user:
        await update.message.reply_text("❗ Lo belum daftar. Ketik /daftar dulu!")
        return

    if user_id in matched_pairs:
        await update.message.reply_text("❗ Lo udah dalam obrolan. Ketik /stop dulu.")
        return

    if any(w[0] == user_id for w in waiting_users):
        await update.message.reply_text("⏳ Masih nyari teman buat lo, sabar ya...")
        return

    name, gender, age, interest = user[2], user[3], user[4], user[5]
    partner_id = find_match(user_id, gender, age, interest)

    if partner_id:
        partner = get_user(partner_id)
        matched_pairs[user_id] = partner_id
        matched_pairs[partner_id] = user_id
        save_match(user_id, partner_id)


        await context.bot.send_message(
            partner_id,
            f"✅ Ketemu teman ngobrol!\n\n"
            f"👤 {name} | {gender} | {age} thn | {interest}\n\n"
            "Mulai ngobrol sekarang! Ketik /stop untuk berhenti."
        )


        p_name, p_gender, p_age, p_interest = partner[2], partner[3], partner[4], partner[5]
        await update.message.reply_text(
            f"✅ Ketemu teman ngobrol!\n\n"
            f"👤 {p_name} | {p_gender} | {p_age} thn | {p_interest}\n\n"
            "Mulai ngobrol sekarang! Ketik /stop untuk berhenti."
        )
    else:
        waiting_users.append((user_id, gender, age, interest))
        await update.message.reply_text(
            "🔍 Lagi nyari teman yang cocok buat lo...\n"
            "Tunggu sebentar ya! Ketik /batal untuk keluar antrian."
        )

async def batal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    for i, (wid, _, _, _) in enumerate(waiting_users):
        if wid == user_id:
            waiting_users.pop(i)
            await update.message.reply_text("✅ Lo udah keluar dari antrian.")
            return
    await update.message.reply_text("Lo lagi ga dalam antrian.")

# ───────────────────────────────────────────────
# FORWARD PESAN
# ───────────────────────────────────────────────

async def forward_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in matched_pairs:
        await update.message.reply_text("❗ Lo belum terhubung. Ketik /cari dulu.")
        return

    partner_id = matched_pairs[user_id]
    user = get_user(user_id)
    name = user[2] if user else "Partner"

    if update.message.text:
        await context.bot.send_message(partner_id, f"💬 {name}: {update.message.text}")
    elif update.message.photo:
        photo = update.message.photo[-1].file_id
        caption = update.message.caption or ""
        await context.bot.send_photo(partner_id, photo, caption=f"📷 {name}: {caption}")
    elif update.message.sticker:
        await context.bot.send_sticker(partner_id, update.message.sticker.file_id)
    elif update.message.voice:
        await context.bot.send_voice(partner_id, update.message.voice.file_id)

# ───────────────────────────────────────────────
# STOP + RATING
# ───────────────────────────────────────────────

async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id

    if user_id not in matched_pairs:
        await update.message.reply_text("Lo lagi ga dalam obrolan.")
        return

    partner_id = matched_pairs.pop(user_id)
    matched_pairs.pop(partner_id, None)

    # rating
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("⭐ 1", callback_data=f"rate_{partner_id}_1"),
            InlineKeyboardButton("⭐ 2", callback_data=f"rate_{partner_id}_2"),
            InlineKeyboardButton("⭐ 3", callback_data=f"rate_{partner_id}_3"),
            InlineKeyboardButton("⭐ 4", callback_data=f"rate_{partner_id}_4"),
            InlineKeyboardButton("⭐ 5", callback_data=f"rate_{partner_id}_5"),
        ]
    ])

    await context.bot.send_message(
        partner_id,
        "❌ Partner lo udah ninggalin obrolan.\n\nKasih rating buat dia:"
        , reply_markup=keyboard
    )
    await update.message.reply_text(
        "👋 Obrolan selesai!\n\nKasih rating buat partner lo:",
        reply_markup=keyboard
    )

async def handle_rating(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, partner_id, rating = query.data.split("_")
    update_rating(int(partner_id), int(rating))

    await query.edit_message_text(f"✅ Thanks! Lo kasih ⭐ {rating} buat partner lo.")

# ───────────────────────────────────────────────
# PROFIL
# ───────────────────────────────────────────────

async def profil(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = get_user(user_id)

    if not user:
        await update.message.reply_text("❗ Lo belum daftar. Ketik /daftar!")
        return

    name, gender, age, interest, rating, rating_count = user[2], user[3], user[4], user[5], user[6], user[7]
    await update.message.reply_text(
        f"👤 Profil Lo\n\n"
        f"• Nama: {name}\n"
        f"• Gender: {gender}\n"
        f"• Umur: {age} tahun\n"
        f"• Minat: {interest}\n"
        f"• Rating: {stars(rating) if rating_count > 0 else 'Belum ada rating'}\n"
        f"• Total dinilai: {rating_count}x\n\n"
        "Ketik /daftar untuk update profil."
    )

# ───────────────────────────────────────────────
# MAIN
# ───────────────────────────────────────────────

def main():
    init_db()

    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.post_init = set_command
    # Conversation handler untuk registrasi
    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("daftar", daftar),
            CommandHandler("profil_update", daftar)
        ],
        states={
            REGISTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_name)],
            REGISTER_GENDER: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_gender)],
            REGISTER_AGE: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_age)],
            REGISTER_INTEREST: [MessageHandler(filters.TEXT & ~filters.COMMAND, register_interest)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )

    app.add_handler(conv_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("cari", cari))
    app.add_handler(CommandHandler("batal", batal))
    app.add_handler(CommandHandler("stop", stop))
    app.add_handler(CommandHandler("profil", profil))
    app.add_handler(CallbackQueryHandler(handle_rating, pattern=r"^rate_"))
    app.add_handler(MessageHandler(
        (filters.TEXT | filters.PHOTO | filters.Sticker.ALL | filters.VOICE) & ~filters.COMMAND,
        forward_message
    ))

    print("✅ MatchBot jalan!")
    app.run_polling()

if __name__ == "__main__":
    main()
