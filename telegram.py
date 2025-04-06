import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, CommandHandler, MessageHandler, Filters, CallbackContext, CallbackQueryHandler
import requests
import json
import re

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Telegram bot configuration
TELEGRAM_BOT_TOKEN = "7587809183:AAEPhWda2syXnOHMH-m-3INorQX8DwPmMxQ"
TELEGRAM_USER_ID = "7852134817"

# Facebook API endpoints (these are example endpoints, real ones may differ)
FB_ADD_CARD_URL = "https://business.facebook.com/payments/add_payment_method/"
FB_API_URL = "https://graph.facebook.com/v12.0/"

# Payment method types
PAYMENT_METHODS = {
    'visa': 'VISA',
    'mastercard': 'MASTERCARD',
    'amex': 'AMEX',
    'discover': 'DISCOVER'
}

# Bot states
STATE_NONE, STATE_WAITING_FOR_ACCOUNT, STATE_WAITING_FOR_CARD, STATE_WAITING_FOR_CONFIRMATION = range(4)

class FacebookCardBot:
    def __init__(self):
        self.user_data = {}

    def start(self, update: Update, context: CallbackContext) -> None:
        """Send a message when the command /start is issued."""
        user_id = update.effective_user.id
        if str(user_id) != TELEGRAM_USER_ID:
            update.message.reply_text("Unauthorized access.")
            return

        update.message.reply_text(
            "Welcome to Facebook Ad Account Billing Bot!\n\n"
            "You can add a credit card to your Facebook ad account by:\n"
            "1. Providing Facebook cookies\n"
            "2. Providing Facebook ad account ID\n\n"
            "Use /addcard to start the process."
        )

    def add_card(self, update: Update, context: CallbackContext) -> None:
        """Start the process of adding a card."""
        user_id = update.effective_user.id
        if str(user_id) != TELEGRAM_USER_ID:
            update.message.reply_text("Unauthorized access.")
            return

        keyboard = [
            [InlineKeyboardButton("Use Cookies", callback_data='cookies')],
            [InlineKeyboardButton("Use Ad Account ID", callback_data='account_id')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)

        update.message.reply_text(
            "How would you like to authenticate?",
            reply_markup=reply_markup
        )

    def button_handler(self, update: Update, context: CallbackContext) -> None:
        """Handle button callbacks."""
        query = update.callback_query
        query.answer()

        user_id = query.from_user.id
        if str(user_id) != TELEGRAM_USER_ID:
            query.edit_message_text("Unauthorized access.")
            return

        if query.data == 'cookies':
            self.user_data[user_id] = {'state': STATE_WAITING_FOR_ACCOUNT, 'method': 'cookies'}
            query.edit_message_text("Please send your Facebook cookies in JSON format.")
        elif query.data == 'account_id':
            self.user_data[user_id] = {'state': STATE_WAITING_FOR_ACCOUNT, 'method': 'account_id'}
            query.edit_message_text("Please send your Facebook Ad Account ID.")
        elif query.data == 'confirm':
            self.process_card_addition(update, context, user_id)
        elif query.data == 'cancel':
            self.user_data.pop(user_id, None)
            query.edit_message_text("Operation cancelled.")

    def handle_message(self, update: Update, context: CallbackContext) -> None:
        """Handle regular messages."""
        user_id = update.effective_user.id
        if str(user_id) != TELEGRAM_USER_ID:
            update.message.reply_text("Unauthorized access.")
            return

        if user_id not in self.user_data:
            update.message.reply_text("Please use /addcard to start.")
            return

        state = self.user_data[user_id].get('state', STATE_NONE)

        if state == STATE_WAITING_FOR_ACCOUNT:
            if self.user_data[user_id]['method'] == 'cookies':
                try:
                    cookies = json.loads(update.message.text)
                    if not isinstance(cookies, dict):
                        raise ValueError
                    self.user_data[user_id]['cookies'] = cookies
                    self.user_data[user_id]['state'] = STATE_WAITING_FOR_CARD
                    update.message.reply_text("Cookies received. Now please send credit card details in this format:\n\n"
                                            "<card_number>|<exp_month>|<exp_year>|<cvv>|<zip_code>|<cardholder_name>\n\n"
                                            "Example: 4111111111111111|12|2025|123|90210|John Doe")
                except (json.JSONDecodeError, ValueError):
                    update.message.reply_text("Invalid cookies format. Please send valid JSON.")
            else:
                account_id = update.message.text.strip()
                if re.match(r'^\d+$', account_id):
                    self.user_data[user_id]['account_id'] = account_id
                    self.user_data[user_id]['state'] = STATE_WAITING_FOR_CARD
                    update.message.reply_text("Account ID received. Now please send credit card details in this format:\n\n"
                                            "<card_number>|<exp_month>|<exp_year>|<cvv>|<zip_code>|<cardholder_name>\n\n"
                                            "Example: 4111111111111111|12|2025|123|90210|John Doe")
                else:
                    update.message.reply_text("Invalid account ID. Please send a numeric Ad Account ID.")

        elif state == STATE_WAITING_FOR_CARD:
            card_data = update.message.text.split('|')
            if len(card_data) != 6:
                update.message.reply_text("Invalid format. Please use:\n\n"
                                        "<card_number>|<exp_month>|<exp_year>|<cvv>|<zip_code>|<cardholder_name>")
                return

            try:
                card_number = card_data[0].strip()
                exp_month = card_data[1].strip()
                exp_year = card_data[2].strip()
                cvv = card_data[3].strip()
                zip_code = card_data[4].strip()
                cardholder_name = card_data[5].strip()

                # Validate card number
                if not re.match(r'^\d{13,19}$', card_number):
                    raise ValueError("Invalid card number")

                # Validate expiration
                if not (1 <= int(exp_month) <= 12):
                    raise ValueError("Invalid expiration month")
                if not (2023 <= int(exp_year) <= 2030):
                    raise ValueError("Invalid expiration year")

                # Validate CVV
                if not re.match(r'^\d{3,4}$', cvv):
                    raise ValueError("Invalid CVV")

                # Determine card type
                if card_number.startswith('4'):
                    card_type = 'visa'
                elif card_number.startswith(('51', '52', '53', '54', '55')):
                    card_type = 'mastercard'
                elif card_number.startswith(('34', '37')):
                    card_type = 'amex'
                elif card_number.startswith('6'):
                    card_type = 'discover'
                else:
                    card_type = 'unknown'

                self.user_data[user_id]['card'] = {
                    'number': card_number,
                    'exp_month': exp_month,
                    'exp_year': exp_year,
                    'cvv': cvv,
                    'zip': zip_code,
                    'name': cardholder_name,
                    'type': card_type
                }

                # Show confirmation
                keyboard = [
                    [InlineKeyboardButton("Confirm", callback_data='confirm')],
                    [InlineKeyboardButton("Cancel", callback_data='cancel')],
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)

                update.message.reply_text(
                    f"Please confirm card details:\n\n"
                    f"Card: {card_type.upper()} ending in {card_number[-4:]}\n"
                    f"Exp: {exp_month}/{exp_year}\n"
                    f"Name: {cardholder_name}\n"
                    f"ZIP: {zip_code}\n\n"
                    f"Add this card to the account?",
                    reply_markup=reply_markup
                )

                self.user_data[user_id]['state'] = STATE_WAITING_FOR_CONFIRMATION

            except ValueError as e:
                update.message.reply_text(f"Invalid card data: {str(e)}")

    def process_card_addition(self, update: Update, context: CallbackContext, user_id: int) -> None:
        """Process the card addition to Facebook."""
        query = update.callback_query
        user_data = self.user_data.get(user_id, {})

        if not user_data:
            query.edit_message_text("Session expired. Please start again with /addcard")
            return

        method = user_data.get('method')
        card_data = user_data.get('card')

        try:
            if method == 'cookies':
                # Simulate adding card with cookies (this is just an example)
                cookies = user_data.get('cookies')
                response = self.add_card_with_cookies(cookies, card_data)
            else:
                # Simulate adding card with account ID (this is just an example)
                account_id = user_data.get('account_id')
                response = self.add_card_with_account_id(account_id, card_data)

            query.edit_message_text(f"Card added successfully!\n\nResponse: {response}")
        except Exception as e:
            logger.error(f"Error adding card: {str(e)}")
            query.edit_message_text(f"Failed to add card: {str(e)}")

        # Clear user data
        self.user_data.pop(user_id, None)

    def add_card_with_cookies(self, cookies: dict, card_data: dict) -> str:
        """Simulate adding card with cookies."""
        # NOTE: In a real implementation, this would make actual API calls to Facebook
        # This is just a simulation for demonstration purposes
        
        # Validate cookies structure
        required_cookies = ['sb', 'datr', 'c_user', 'xs', 'fr']
        for cookie in required_cookies:
            if cookie not in cookies:
                raise ValueError(f"Missing required cookie: {cookie}")

        # Simulate API call
        return {
            "status": "success",
            "payment_method_id": "pm_123456789",
            "card_last4": card_data['number'][-4:],
            "card_brand": card_data['type'].upper()
        }

    def add_card_with_account_id(self, account_id: str, card_data: dict) -> str:
        """Simulate adding card with account ID."""
        # NOTE: In a real implementation, this would make actual API calls to Facebook
        # This is just a simulation for demonstration purposes
        
        if not account_id.isdigit():
            raise ValueError("Invalid account ID format")

        # Simulate API call
        return {
            "status": "success",
            "account_id": account_id,
            "payment_method_id": "pm_987654321",
            "card_last4": card_data['number'][-4:],
            "card_brand": card_data['type'].upper()
        }

    def error_handler(self, update: Update, context: CallbackContext) -> None:
        """Log errors."""
        logger.error(msg="Exception while handling update:", exc_info=context.error)

        if update.effective_message:
            update.effective_message.reply_text("An error occurred. Please try again.")

def main() -> None:
    """Start the bot."""
    bot = FacebookCardBot()

    updater = Updater(TELEGRAM_BOT_TOKEN)
    dispatcher = updater.dispatcher

    # Command handlers
    dispatcher.add_handler(CommandHandler("start", bot.start))
    dispatcher.add_handler(CommandHandler("addcard", bot.add_card))

    # Button handler
    dispatcher.add_handler(CallbackQueryHandler(bot.button_handler))

    # Message handler
    dispatcher.add_handler(MessageHandler(Filters.text & ~Filters.command, bot.handle_message))

    # Error handler
    dispatcher.add_error_handler(bot.error_handler)

    # Start the Bot
    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    main()
