import logging
import sqlite3
from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    LabeledPrice,
    Message,
    PreCheckoutQuery,
)

# الإعدادات الأساسية
TOKEN = "8994010775:AAG7G3WCglHe0yJlR3K8eOzc4lUvy0APk88"
ADMIN_USERNAME = "MrBotMaker1"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)
router = Router()

# ==================== قاعدة البيانات (SQLite) ====================
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    # جدول المستخدمين
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            balance REAL DEFAULT 0.0,
            referred_by INTEGER,
            points INTEGER DEFAULT 0
        )
    """)
    # جدول الخدمات والأسعار (التحكم الديناميكي للآدمن)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS services (
            service_id TEXT PRIMARY KEY,
            name TEXT,
            price REAL
        )
    """)
    # إدراج خدمات افتراضية لو مش موجودة
    default_services = [
        ("stars_50", "50 Telegram Stars", 1.0),
        ("pubg_60", "60 PUBG UC", 1.0),
        ("prem_1m", "Telegram Premium (1 Month)", 4.0)
    ]
    for s_id, name, price in default_services:
        cursor.execute("INSERT OR IGNORE INTO services (service_id, name, price) VALUES (?, ?, ?)", (s_id, name, price))
    
    conn.commit()
    conn.close()

init_db()

# حالات FSM لتواصل الآدمن أو شحن البانس
class AdminStates(StatesGroup):
    waiting_for_broadcast = State()
    waiting_for_user_id = State()
    waiting_for_balance = State()

class BuyStates(StatesGroup):
    confirming_purchase = State()

# ==================== الأزرار والقوائم ====================
def main_menu(is_admin: bool = False):
    keyboard = [
        [InlineKeyboardButton(text="💎 خدمات تليجرام وببجي", callback_data="services")],
        [InlineKeyboardButton(text="🎁 نظام الأصدقاء (الإحالة)", callback_data="referral")],
        [InlineKeyboardButton(text="👤 حسابي", callback_data="profile")]
    ]
    if is_admin:
        keyboard.append([InlineKeyboardButton(text="⚙️ لوحة تحكم الآدمن", callback_data="admin_panel")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard)

# ==================== الأوامر الرئيسية ====================
@router.message(CommandStart())
async def cmd_start(message: Message):
    user_id = message.from_user.id
    username = message.from_user.username or "NoUsername"
    
    # فحص الإحالة لو وجدت في الرابط
    args = message.text.split()
    referred_by = None
    if len(args) > 1 and args[1].isdigit():
        ref_id = int(args[1])
        if ref_id != user_id:
            referred_by = ref_id

    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        cursor.execute(
            "INSERT INTO users (user_id, username, referred_by) VALUES (?, ?, ?)",
            (user_id, username, referred_by)
        )
        if referred_by:
            # مكافأة المُحيل
            cursor.execute("UPDATE users SET points = points + 1 WHERE user_id = ?", (referred_by,))
            try:
                await bot.send_message(referred_by, "🎉 انضم شخص جديد عبر رابط إحالتك! حصلت على نقطة.")
            except:
                pass
        conn.commit()
    conn.close()

    is_admin = message.from_user.username == ADMIN_USERNAME
    await message.answer(
        f"مرحباً بك يا أخي في بوت الخدمات الرقمية والشحن المتكامل 🚀\n"
        f"اختر ما يناسبك من القائمة أدناه:",
        reply_markup=main_menu(is_admin)
    )

# ==================== الملف الشخصي والإحالة ====================
@router.callback_query(F.data == "profile")
async def profile_callback(callback: CallbackQuery):
    user_id = callback.from_user.id
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance, points FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()

    balance, points = row if row else (0.0, 0)
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={user_id}"

    text = (
        f"👤 **معلومات حسابك:**\n"
        f"🆔 الآيدي: `{user_id}`\n"
        f"💰 الرصيد الحالي: `{balance}` $\n"
        f"🎁 نقاط الإحالة: `{points}`\n\n"
        f"🔗 رابط الإحالة الخاص بك:\n`{ref_link}`"
    )
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="main_menu")]
    ])
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data == "referral")
async def referral_callback(callback: CallbackQuery):
    await profile_callback(callback)

@router.callback_query(F.data == "main_menu")
async def back_to_main(callback: CallbackQuery):
    is_admin = callback.from_user.username == ADMIN_USERNAME
    await callback.message.edit_text("القائمة الرئيسية:", reply_markup=main_menu(is_admin))

# ==================== الخدمات والشراء ====================
@router.callback_query(F.data == "services")
async def services_callback(callback: CallbackQuery):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT service_id, name, price FROM services")
    services = cursor.fetchall()
    conn.close()

    keyboard = []
    for s_id, name, price in services:
        keyboard.append([InlineKeyboardButton(text=f"{name} - {price}$", callback_data=f"buy_{s_id}")])
    
    keyboard.append([InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="main_menu")])
    await callback.message.edit_text("اختر الخدمة المطلوبة للشراء:", reply_markup=InlineKeyboardMarkup(inline_keyboard=keyboard))

@router.callback_query(F.data.startswith("buy_"))
async def process_buy(callback: CallbackQuery):
    s_id = callback.data.split("_", 1)[1]
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT name, price FROM services WHERE service_id = ?", (s_id,))
    service = cursor.fetchone()
    conn.close()

    if not service:
        await callback.answer("الخدمة غير متوفرة حالياً.", show_alert=True)
        return

    name, price = service
    
    # دعم الدفع عبر نجوم تليجرام أو الرصيد
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"⭐️ الدفع بـ Telegram Stars", callback_data=f"pay_stars_{s_id}")],
        [InlineKeyboardButton(text="🔙 رجوع", callback_data="services")]
    ])
    
    await callback.message.edit_text(
        f"🛒 تفاصيل الطلب:\n- الخدمة: **{name}**\n- السعر: **{price} $**\n\nاختر وسيلة الدفع:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

@router.callback_query(F.data.startswith("pay_stars_"))
async def pay_with_stars(callback: CallbackQuery):
    s_id = callback.data.split("_", 2)[2]
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT name, price FROM services WHERE service_id = ?", (s_id,))
    service = cursor.fetchone()
    conn.close()

    if not service:
        return

    name, price = service
    # تحويل السعر لـ Stars (مثلاً كل 1 دولار = 50 نجمة افتراضياً للتوضيح)
    stars_amount = int(price * 50)

    prices = [LabeledPrice(label=name, amount=stars_amount)]
    await bot.send_invoice(
        chat_id=callback.message.chat.id,
        title=name,
        description=f"شراء {name} عبر نجوم تليجرام الرسمية",
        payload=f"bot_order_{s_id}",
        currency="XTR",
        prices=prices
    )

@router.pre_checkout_query()
async def pre_checkout(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

@router.message(F.successful_payment)
async def successful_payment(message: Message):
    await message.answer("🎉 تم دفع المبلغ بنجاح! يتم تنفيذ طلبك الآن والتواصل معك قريباً.")
    # إشعار الآدمن بعملية شراء جديدة
    for admin_id in [message.from_user.id]: # أو يوزرنيم الآدمن
        pass

# ==================== لوحة تحكم الآدمن ====================
@router.callback_query(F.data == "admin_panel")
async def admin_panel(callback: CallbackQuery):
    if callback.from_user.username != ADMIN_USERNAME:
        await callback.answer("هذا الزر مخصص للآدمن فقط!", show_alert=True)
        return

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 إرسال رسالة للجميع", callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="💰 تعديل رصيد مستخدم", callback_data="admin_set_balance")],
        [InlineKeyboardButton(text="🔙 القائمة الرئيسية", callback_data="main_menu")]
    ])
    await callback.message.edit_text("⚙️ **لوحة تحكم الآدمن:**", reply_markup=keyboard, parse_mode="Markdown")

@router.callback_query(F.data == "admin_broadcast")
async def admin_broadcast(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.username != ADMIN_USERNAME:
        return
    await state.set_state(AdminStates.waiting_for_broadcast)
    await callback.message.answer("أرسل الآن النص أو الرسالة المراد إذاعتها لجميع المستخدمين:")

@router.message(AdminStates.waiting_for_broadcast)
async def execute_broadcast(message: Message, state: FSMContext):
    if message.from_user.username != ADMIN_USERNAME:
        return
    
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    conn.close()

    count = 0
    for (u_id,) in users:
        try:
            await message.copy_to(chat_id=u_id)
            count += 1
        except:
            pass

    await state.clear()
    await message.answer(f"✅ تم إرسال الإذاعة بنجاح إلى {count} مستخدم.")

# تشغيل البوت
async def main():
    dp.include_router(router)
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
