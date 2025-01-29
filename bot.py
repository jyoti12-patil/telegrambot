import logging
import pymongo
from telegram import Update, KeyboardButton, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters
import google.generativeai as genai
import requests
import time

# Setup logging
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.INFO)
logger = logging.getLogger(__name__)

# MongoDB setup
client = pymongo.MongoClient("mongodb://localhost:27017")
db = client['telegram_bot']
users_collection = db['users']
chat_history_collection = db['chat_history']

# Google Gemini API setup
genai.configure(api_key="AIzaSyA7PInwlsDzzGhrPAx4TUpSgFi_KdCCZOY")  

# Telegram Bot setup
telegram_bot_token = "7288397212:AAE1vmPd8F2T0UCiZsgWuOzUabo3e637B-A"  

async def start(update: Update, context) -> None:
    """Handles the /start command, registers users, and asks for contact."""
    user = update.message.from_user
    chat_id = user.id

    # Check if user is already registered
    existing_user = users_collection.find_one({"chat_id": chat_id})

    if not existing_user:
        # Register new user
        users_collection.insert_one({
            "first_name": user.first_name,
            "username": user.username,
            "chat_id": chat_id
        })
        await update.message.reply_text(
            f"Hello, {user.first_name}! Please share your phone number to complete registration.",
            reply_markup=ReplyKeyboardMarkup(
                [[KeyboardButton("Share Contact", request_contact=True)]],
                one_time_keyboard=True
            )
        )
    else:
        await update.message.reply_text("Welcome back! How can I assist you today?")

async def handle_contact(update: Update, context) -> None:
    """Handles the contact sharing and updates the user's phone number."""
    phone_number = update.message.contact.phone_number
    chat_id = update.message.from_user.id

    # Update user with phone number
    users_collection.update_one({"chat_id": chat_id}, {"$set": {"phone_number": phone_number}})

    await update.message.reply_text("Thank you for sharing your phone number! You can now interact with the bot.")

async def gemini_query(query: str) -> str:
    """Handles communication with the Google Gemini AI model."""
    model = genai.GenerativeModel("gemini-pro")
    response = model.generate_content(query)
    
    return response.text if response and hasattr(response, "text") else "Sorry, I couldn't generate a response."

async def handle_text_message(update: Update, context) -> None:
    """Handles user messages and provides AI responses."""
    user_input = update.message.text
    user_id = update.message.from_user.id
    timestamp = time.time()

    # Get Gemini response
    bot_response = await gemini_query(user_input)

    # Save chat history
    chat_history_collection.insert_one({
        "user_id": user_id,
        "user_input": user_input,
        "bot_response": bot_response,
        "timestamp": timestamp
    })

    # Send bot response
    await update.message.reply_text(bot_response)

async def handle_file(update: Update, context) -> None:
    """Handles file uploads and analyzes them using Gemini AI."""
    file = update.message.document or update.message.photo[-1]
    file_id = file.file_id
    file_name = file.file_name if hasattr(file, "file_name") else "unknown"

    new_file = await context.bot.get_file(file_id)
    file_url = new_file.file_path

    # Download file content
    file_content = requests.get(file_url).content

    # Analyze file content with Gemini API
    analysis = await gemini_query(f"Analyze the following file content: {file_content[:100]}")

    # Save file metadata
    chat_history_collection.insert_one({
        "file_name": file_name,
        "file_analysis": analysis,
        "timestamp": time.time()
    })

    await update.message.reply_text(f"File analyzed: {analysis}")

async def web_search(update: Update, context) -> None:
    """Handles web search queries and provides AI-generated summaries."""
    query = " ".join(context.args)
    search_url = f"https://www.google.com/search?q={query}"

    # Call Gemini to summarize search results
    summary = await gemini_query(f"Summarize the top results for: {query} at {search_url}")

    await update.message.reply_text(summary)

def main() -> None:
    """Main function to start the bot."""
    app = ApplicationBuilder().token(telegram_bot_token).build()

    # Command Handlers
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("websearch", web_search))

    # Message Handlers
    app.add_handler(MessageHandler(filters.CONTACT, handle_contact))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file))

    # Start the bot
    app.run_polling()

if __name__ == '__main__':
    main()
