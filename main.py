from typing import Final
from telegram import Update, BotCommand
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler
from openai import AsyncOpenAI
import configparser

# Initialize configparser
config = configparser.ConfigParser()
config.read('config.ini')

# Retrieve keys and tokens from config file
OPENAI_API_KEY = config['Keys']['OPENAI_API_KEY']
TELEGRAM_TOKEN = config['Keys']['TELEGRAM_TOKEN']

# Initialize the OpenAI client
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# Your Telegram bot token
TOKEN = TELEGRAM_TOKEN
BOT_USERNAME = '@NutriTrack_bot'

# In-memory storage for user meals (use a database in a real application)
user_meals = {}

# Define states
TRACKING, CONFIRMING_DELETE = range(2)


# Commands
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        'Hello! I am NutriTrack bot. I can help you track your nutrition. '
        'Type /help to see the list of commands.'
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        'List of commands:\n'
        '/start - Start the bot\n'
        '/help - Show this message\n'
        '/track - Track your meal\n'
        '/view - View your meal history\n'
        '/delete - Delete your meal history\n'
        '/cancel - Cancel the current operation'
    )


async def track_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('What did you eat? Please describe your meal.')
    return TRACKING


async def view_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat.id
    meals = user_meals.get(user_id, [])
    if not meals:
        await update.message.reply_text('You have not tracked any meals yet.')
    else:
        await update.message.reply_text('Your meal history:\n' + '\n'.join(meals))


async def delete_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat.id
    if user_id in user_meals and user_meals[user_id]:
        await update.message.reply_text('Are you sure you want to delete your meal history? Type "yes" to confirm.')
        return CONFIRMING_DELETE
    else:
        await update.message.reply_text('You have no meal history to delete.')
        return ConversationHandler.END


async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text('Operation cancelled.')
    return ConversationHandler.END


async def confirm_delete(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat.id
    if update.message.text.lower() == 'yes':
        user_meals[user_id] = []
        await update.message.reply_text('Your meal history has been deleted.')
    else:
        await update.message.reply_text('Delete operation cancelled.')
    return ConversationHandler.END


async def handle_track(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.chat.id
    text: str = update.message.text

    if user_id not in user_meals:
        user_meals[user_id] = []
    user_meals[user_id].append(text)
    await update.message.reply_text('Meal tracked successfully.')

    # Provide nutritional advice using OpenAI
    try:
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a helpful nutrition assistant."},
                {"role": "user", "content": f"I ate {text}. Please provide nutritional advice."}
            ]
        )
        advice = response.choices[0].message.content.strip()
        await update.message.reply_text(advice)
    except Exception as e:
        print(f"Error from OpenAI API: {str(e)}")
        await update.message.reply_text('Meal tracked, but unable to fetch nutritional advice at the moment.')

    return ConversationHandler.END


async def handle_response(text: str) -> str:
    processed: str = text.lower()

    if 'hello' in processed:
        return 'Hello There!'

    if 'how are you' in processed:
        try:
            response = await client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "How are you?"}
                ]
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"Error from OpenAI API: {str(e)}")
            return "I am fine, thank you!"  # Default response if OpenAI fails

    if 'bye' in processed:
        return 'Goodbye!'

    return 'I do not understand that command'


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text: str = update.message.text
    response: str = await handle_response(text)
    await update.message.reply_text(response)


async def error(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f'Update {update} caused error {context.error}')


if __name__ == '__main__':
    print('Starting Bot...')
    app = Application.builder().token(TOKEN).build()


    # Conversation handler for tracking meals
    track_conversation_handler = ConversationHandler(
        entry_points=[CommandHandler('track', track_command)],
        states={
            TRACKING: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_track)],
        },
        fallbacks=[CommandHandler('cancel', cancel_command)]
    )

    # Conversation handler for deleting meals
    delete_conversation_handler = ConversationHandler(
        entry_points=[CommandHandler('delete', delete_command)],
        states={
            CONFIRMING_DELETE: [MessageHandler(filters.TEXT & ~filters.COMMAND, confirm_delete)],
        },
        fallbacks=[CommandHandler('cancel', cancel_command)]
    )

    # Commands
    app.add_handler(CommandHandler('start', start_command))
    app.add_handler(CommandHandler('help', help_command))
    app.add_handler(CommandHandler('view', view_command))
    app.add_handler(track_conversation_handler)
    app.add_handler(delete_conversation_handler)
    app.add_handler(CommandHandler('cancel', cancel_command))

    # Messages
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Error
    app.add_error_handler(error)

    # Polls the bot
    app.run_polling(poll_interval=1)