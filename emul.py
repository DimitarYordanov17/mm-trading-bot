import requests
import random
import time
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# ================= SETTINGS =================
# Your Telegram Bot API token (from BotFather)
API_TOKEN = os.getenv("TELEGRAM_API_TOKEN")  # Get token from .env file
# Your Telegram chat ID (the chat where messages will be sent)
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")  # Get chat ID from .env file

# Function to send a message to Telegram
def send_telegram_message(message):
    url = f"https://api.telegram.org/bot{API_TOKEN}/sendMessage"
    payload = {
        'chat_id': CHAT_ID,  # The correct chat ID goes here
        'text': message
    }
    response = requests.post(url, data=payload)
    return response

# ================= EMULATED SIGNAL FUNCTION =================
def simulate_signal():
    # Randomly simulate a "buy" or "sell" signal
    trade_type = random.choice(["buy", "sell"])
    price = round(random.uniform(1400, 1500), 2)  # Random price between 1400 and 1500

    # Simulate sending a Telegram message about the trade
    if trade_type == "buy":
        send_telegram_message(f"⚡️ EXPERIMENTAL: Buy Signal at {price}")
    elif trade_type == "sell":
        send_telegram_message(f"⚡️ EXPERIMENTAL: Sell Signal at {price}")

# ================= TEST LOOP =================
while True:
    simulate_signal()  # Simulate a trade signal
    time.sleep(5)  # Wait for 5 seconds before simulating another trade
