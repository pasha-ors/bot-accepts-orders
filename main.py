from data import DATA

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
    ContextTypes
)
import aiosqlite
import nest_asyncio

# Apply nest_asyncio to allow using an event loop that's already running
nest_asyncio.apply()

# Global dictionary to temporarily store user orders
user_orders = {}

def format_menu():
    """Format the menu text message."""
    text = "🍣 *Our Sushi Menu* 🍣\n\n"
    for key, item in DATA.items():
        text += f"*{item['name']}* - ${item['price']}\n_{item['description']}_\n\n"
    text += "Please select a roll from the menu below 👇"
    return text

def get_menu_keyboard():
    """Return an inline keyboard with the menu items."""
    keyboard = [
        [InlineKeyboardButton(item["name"], callback_data=key)]
        for key, item in DATA.items()
    ]
    return InlineKeyboardMarkup(keyboard)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the /start command by showing the menu."""
    user_id = update.message.from_user.id
    # Reset any previous order data for the user
    user_orders.pop(user_id, None)
    await update.message.reply_text(
        format_menu(),
        reply_markup=get_menu_keyboard(),
        parse_mode="Markdown"
    )

async def button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the menu item selection via inline keyboard."""
    query = update.callback_query
    await query.answer()
    item = DATA.get(query.data)
    user_id = query.from_user.id
    if user_id not in user_orders:
        user_orders[user_id] = {"items": "", "address": ""}
    # Append the selected item to the order
    current_items = user_orders[user_id].get("items", "")
    new_items = item["name"] if not current_items else f"{current_items}, {item['name']}"
    user_orders[user_id]["items"] = new_items
    await query.edit_message_text(
        f"You added: {item['name']}.\n"
        "You can add more items or enter your delivery address:"
    )

async def address_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the address input and show order confirmation options."""
    user_id = update.message.from_user.id
    address = update.message.text

    if user_id not in user_orders or not user_orders[user_id].get("items"):
        await update.message.reply_text("Please select at least one item from the menu first by using /start.")
        return

    user_orders[user_id]["address"] = address
    order_details = user_orders[user_id]
    confirm_text = (
        f"Please confirm your order:\n\n"
        f"Items: {order_details['items']}\n"
        f"Address: {order_details['address']}"
    )
    keyboard = [
        [
            InlineKeyboardButton("✅ Confirm Order", callback_data="confirm_yes"),
            InlineKeyboardButton("❌ Cancel Order", callback_data="confirm_no")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(confirm_text, reply_markup=reply_markup)

async def order_confirmation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle order confirmation or cancellation."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    order = user_orders.get(user_id)
    if not order or not order.get("items") or not order.get("address"):
        await query.edit_message_text("No order details found. Please start again with /start.")
        return

    if query.data == "confirm_yes":
        # Insert the order into the database with confirmed = 1
        async with aiosqlite.connect("orders.db") as db:
            await db.execute(
                "INSERT INTO orders (user_id, items, address, confirmed) VALUES (?, ?, ?, 1)",
                (user_id, order["items"], order["address"])
            )
            await db.commit()
        # Ask the user if they want to order more items
        keyboard = [
            [
                InlineKeyboardButton("🛍️ Yes, I want more!", callback_data="order_again"),
                InlineKeyboardButton("🚪 No, that's all", callback_data="order_end")
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "✅ Your order has been confirmed!\nDo you want to order something else?",
            reply_markup=reply_markup
        )
    elif query.data == "confirm_no":
        await query.edit_message_text("❌ Your order has been cancelled.")
        user_orders.pop(user_id, None)

async def order_again_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the 'order again' or 'order end' response."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    if query.data == "order_again":
        # Clear previous order data and show the menu for a new order
        user_orders.pop(user_id, None)
        await query.edit_message_text("Alright! Let's order more!")
        await query.message.reply_text(
            format_menu(),
            reply_markup=get_menu_keyboard(),
            parse_mode="Markdown"
        )
    elif query.data == "order_end":
        # End the ordering session and show a Start button
        user_orders.pop(user_id, None)
        keyboard = [
            [InlineKeyboardButton("Start", callback_data="start_command")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text("Thank you! See you next time.", reply_markup=reply_markup)

async def start_command_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle the Start button to begin a new order."""
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    user_orders.pop(user_id, None)
    await query.edit_message_text(
        format_menu(),
        reply_markup=get_menu_keyboard(),
        parse_mode="Markdown"
    )

async def init_db():
    """Initialize the database and create the orders table if it doesn't exist."""
    async with aiosqlite.connect("orders.db") as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                items TEXT,
                address TEXT,
                confirmed BOOLEAN DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        await db.commit()

async def main():
    # Initialize the database
    await init_db()

    app = ApplicationBuilder().token("7375700832:AAHUgSz4Offvap41aKtdS3w6lGuKisv_AfU").build()

    # Handlers
    app.add_handler(CommandHandler("start", start))
    # Handler for menu buttons (callback_data that does not start with "confirm_", "order_", or "start_command")
    app.add_handler(CallbackQueryHandler(button, pattern="^(?!confirm_|order_|start_command).+"))
    # Handler for address input
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, address_handler))
    # Handler for order confirmation/cancellation
    app.add_handler(CallbackQueryHandler(order_confirmation_handler, pattern="^confirm_"))
    # Handler for ordering more or finishing the session
    app.add_handler(CallbackQueryHandler(order_again_handler, pattern="^order_"))
    # Handler for the Start button
    app.add_handler(CallbackQueryHandler(start_command_handler, pattern="^start_command$"))

    print("Bot is running...")
    await app.run_polling()

if __name__ == "__main__":
    import asyncio
    asyncio.get_event_loop().run_until_complete(main())