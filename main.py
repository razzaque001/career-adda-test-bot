import os
import json
import random
import glob
import logging
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes
)

# Load .env
load_dotenv()

# Logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)

TESTS_DIR = "tests"

# Create tests folder
os.makedirs(TESTS_DIR, exist_ok=True)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args

    if args:
        test_name = args[0]
        test_path = os.path.join(TESTS_DIR, f"{test_name}.json")

        if not os.path.exists(test_path):
            await update.message.reply_text("❌ Test not found.")
            return

        try:
            with open(test_path, "r", encoding="utf-8") as f:
                questions = json.load(f)

        except json.JSONDecodeError:
            await update.message.reply_text("❌ Corrupted test file.")
            return

        if not questions:
            await update.message.reply_text("❌ Empty test.")
            return

        random.shuffle(questions)

        # Store quiz data
        context.user_data['quiz'] = questions
        context.user_data['current_idx'] = 0
        context.user_data['score'] = 0
        context.user_data['test_name'] = test_name
        context.user_data['skipped_questions'] = []
        context.user_data['original_total'] = len(questions)

        await update.message.reply_text(
            f"🚀 *{test_name.upper()} TEST STARTED*\n\n"
            f"📝 Total Questions: {len(questions)}\n"
            f"⏭ You can skip difficult questions.\n"
            f"✅ You can submit anytime.",
            parse_mode='Markdown'
        )

        await send_question(update, context)

    else:
        msg = (
            "🎓 *Welcome to Career Adda Test Bot*\n\n"
            "📚 /tests - View available tests\n"
            "ℹ️ /help - Help section"
        )

        await update.message.reply_text(
            msg,
            parse_mode='Markdown'
        )


async def list_tests(update: Update, context: ContextTypes.DEFAULT_TYPE):
    test_files = glob.glob(os.path.join(TESTS_DIR, "*.json"))

    if not test_files:
        await update.message.reply_text(
            "❌ No tests available."
        )
        return

    msg = "📚 *Available Tests*\n\n"

    for file in test_files:
        filename = os.path.basename(file).replace(".json", "")
        bot_username = context.bot.username

        link = f"https://t.me/{bot_username}?start={filename}"

        msg += (
            f"🔹 {filename.capitalize()}\n"
            f"🔗 [Start Test]({link})\n\n"
        )

    await update.message.reply_text(
        msg,
        parse_mode='Markdown',
        disable_web_page_preview=True
    )


async def send_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = context.user_data['current_idx']
    quiz = context.user_data['quiz']

    # Prevent crash
    if idx >= len(quiz):
        await finish_test(update, context)
        return

    question_data = quiz[idx]

    options = question_data['options'].copy()
    random.shuffle(options)

    context.user_data['current_options'] = options

    keyboard = []

    for i, option in enumerate(options):
        callback_data = f"q_{idx}_opt_{i}"

        keyboard.append([
            InlineKeyboardButton(
                option,
                callback_data=callback_data
            )
        ])

    # Skip button
    keyboard.append([
        InlineKeyboardButton(
            "⏭ Skip",
            callback_data=f"skip_{idx}"
        )
    ])

    # Submit button
    keyboard.append([
        InlineKeyboardButton(
            "✅ Submit Test",
            callback_data="submit_test"
        )
    ])

    reply_markup = InlineKeyboardMarkup(keyboard)

    question_text = (
        f"📝 *Question {idx + 1}/{context.user_data['original_total']}*\n\n"
        f"{question_data['question']}"
    )

    if update.callback_query:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=question_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )

    else:
        await update.message.reply_text(
            question_text,
            reply_markup=reply_markup,
            parse_mode='Markdown'
        )


async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query

    await query.answer()

    data = query.data

    # Prevent expired clicks
    if 'quiz' not in context.user_data:
        await query.edit_message_reply_markup(reply_markup=None)

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⚠️ Test session expired."
        )

        return

    # Submit test manually
    if data == "submit_test":

        await query.edit_message_reply_markup(reply_markup=None)

        await finish_test(update, context)

        return

    # Handle skip
    if data.startswith("skip_"):
        parts = data.split("_")
        q_idx = int(parts[1])

        if q_idx != context.user_data['current_idx']:
            await query.edit_message_reply_markup(reply_markup=None)
            return

        await query.edit_message_reply_markup(reply_markup=None)

        skipped_question = context.user_data['quiz'][q_idx]

        context.user_data['skipped_questions'].append(
            skipped_question
        )

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⏭ Question skipped."
        )

        context.user_data['current_idx'] += 1

        if context.user_data['current_idx'] < len(
            context.user_data['quiz']
        ):
            await send_question(update, context)

        else:
            # Reattempt skipped questions
            if context.user_data['skipped_questions']:
                context.user_data['quiz'] = context.user_data[
                    'skipped_questions'
                ]

                context.user_data['skipped_questions'] = []

                context.user_data['current_idx'] = 0

                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text="📌 Reattempt skipped questions now."
                )

                await send_question(update, context)

            else:
                await finish_test(update, context)

        return

    # Normal answers
    if not data.startswith("q_"):
        return

    parts = data.split("_")

    q_idx = int(parts[1])
    opt_idx = int(parts[3])

    if q_idx != context.user_data['current_idx']:
        await query.edit_message_reply_markup(reply_markup=None)

        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="⚠️ Question already answered."
        )

        return

    await query.edit_message_reply_markup(reply_markup=None)

    quiz = context.user_data['quiz']

    current_question = quiz[q_idx]

    selected_option = context.user_data[
        'current_options'
    ][opt_idx]

    correct_answer = current_question['answer']

    if selected_option == correct_answer:
        context.user_data['score'] += 1

        result_text = "✅ *Correct!*"

    else:
        result_text = (
            f"❌ *Incorrect!*\n"
            f"✅ Correct Answer: {correct_answer}"
        )

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=result_text,
        parse_mode='Markdown'
    )

    context.user_data['current_idx'] += 1

    if context.user_data['current_idx'] < len(quiz):
        await send_question(update, context)

    else:
        # Reattempt skipped
        if context.user_data['skipped_questions']:
            context.user_data['quiz'] = context.user_data[
                'skipped_questions'
            ]

            context.user_data['skipped_questions'] = []

            context.user_data['current_idx'] = 0

            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="📌 Reattempt skipped questions now."
            )

            await send_question(update, context)

        else:
            await finish_test(update, context)


async def finish_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    score = context.user_data['score']

    total = context.user_data['original_total']

    attempted = score + len(
        context.user_data['skipped_questions']
    )

    percentage = (score / total) * 100

    username = (
        update.effective_user.username or
        update.effective_user.first_name
    )

    summary = (
        f"🏁 *TEST COMPLETED*\n\n"
        f"👤 {username}\n"
        f"✅ Correct: {score}\n"
        f"❌ Wrong/Skipped: {total - score}\n"
        f"📝 Attempted: {attempted}/{total}\n"
        f"🎯 Final Score: {score}/{total}\n"
        f"📈 Percentage: {percentage:.1f}%"
    )

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=summary,
        parse_mode='Markdown'
    )

    # Clear session
    context.user_data.clear()

    # Show tests again
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="📚 Choose your next test:"
    )

    await list_tests(update, context)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "💡 *How to use this bot:*\n\n"
        "1. Type /tests\n"
        "2. Open any test\n"
        "3. Answer questions\n"
        "4. Skip difficult ones\n"
        "5. Submit anytime"
    )

    await update.message.reply_text(
        help_text,
        parse_mode='Markdown'
    )


def main():
    TOKEN = os.getenv("TOKEN")

    if not TOKEN:
        logger.error("TOKEN not found in .env")
        return

    application = Application.builder().token(TOKEN).build()

    application.add_handler(
        CommandHandler("start", start)
    )

    application.add_handler(
        CommandHandler("tests", list_tests)
    )

    application.add_handler(
        CommandHandler("help", help_command)
    )

    application.add_handler(
        CallbackQueryHandler(handle_answer)
    )

    logger.info("✅ Bot started successfully...")

    application.run_polling(
        allowed_updates=Update.ALL_TYPES
    )


if __name__ == "__main__":
    main()