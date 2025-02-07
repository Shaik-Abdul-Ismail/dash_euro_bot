import os
import time
import requests
import hmac
import hashlib
import json
import logging
from flask import Flask  # Import Flask for the web server

# Configure logging to log messages to both a file and the console
logging.basicConfig(
    level=logging.INFO,  # Set the logging level to INFO
    format='%(asctime)s - %(levelname)s - %(message)s',  # Define the log format
    handlers=[
        logging.FileHandler("bot.log"),  # Log to a file named "bot.log"
        logging.StreamHandler()  # Also print logs to the console
    ]
)

# Constants for API and trading parameters
API_URL = "https://payeer.com/api/trade"
API_KEY = os.getenv('API_KEY')  # Fetch API key from environment variables
API_SECRET = os.getenv('API_SECRET')  # Fetch API secret from environment variables
SYMBOL = "POL_EUR"  # Trading pair
BUY_PRICE = 0.3  # Buy POL at this price
SELL_PRICE = 2.8  # Sell POL at this price
INVESTMENT_AMOUNT = 0.2  # Fixed investment amount in EUR
BALANCE_THRESHOLD = 0.001  # Minimum balance threshold for trading

# Initialize Flask app for health checks
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def generate_signature(method, params):
    """
    Generate HMAC-SHA256 signature for API requests.
    """
    params_json = json.dumps(params, separators=(',', ':'), ensure_ascii=False)
    H = hmac.new(API_SECRET.encode('utf-8'), digestmod=hashlib.sha256)
    H.update((method + params_json).encode('utf-8'))
    return H.hexdigest()

def get_balances():
    """
    Fetch account balances from the exchange.
    """
    method = "account"
    payload = {'ts': int(time.time() * 1000)}
    headers = {
        'Content-Type': 'application/json',
        'API-ID': API_KEY,
        'API-SIGN': generate_signature(method, payload)
    }
    response = requests.post(f"{API_URL}/{method}", headers=headers, json=payload)
    return response.json() if response.status_code == 200 else {}

def place_order(order_type, amount, price):
    """
    Place a buy or sell order on the exchange.
    """
    method = "order_create"
    payload = {
        'ts': int(time.time() * 1000),
        'pair': SYMBOL,
        'type': order_type,
        'amount': amount,
        'price': price
    }
    headers = {
        'Content-Type': 'application/json',
        'API-ID': API_KEY,
        'API-SIGN': generate_signature(method, payload)
    }
    response = requests.post(f"{API_URL}/{method}", headers=headers, json=payload)
    return response.json() if response.status_code == 200 else {}

def get_current_price():
    """
    Fetch the current market price for the trading pair.
    """
    method = "ticker"
    payload = {'ts': int(time.time() * 1000), 'pair': SYMBOL}
    headers = {
        'Content-Type': 'application/json',
        'API-ID': API_KEY,
        'API-SIGN': generate_signature(method, payload)
    }
    response = requests.post(f"{API_URL}/{method}", headers=headers, json=payload)
    data = response.json() if response.status_code == 200 else {}
    return float(data['pairs'][SYMBOL]['last']) if data.get('success') else None

def main():
    logging.info("Starting Simple Auto Trading Bot...")
    last_buy_price = None
    pol_bought = False
    while True:
        try:
            current_price = get_current_price()
            if current_price is None:
                logging.error("Failed to fetch market price. Retrying...")
                time.sleep(10)
                continue

            logging.info(f"Current Price: {current_price} EUR")
            balances = get_balances()
            eur_balance = float(balances.get('EUR', {}).get('total', 0.0))
            pol_balance = float(balances.get('POL', {}).get('total', 0.0))

            if not pol_bought and current_price <= BUY_PRICE and eur_balance >= INVESTMENT_AMOUNT:
                buy_amount = INVESTMENT_AMOUNT / current_price
                logging.info(f"Placing BUY order at {current_price} EUR for {buy_amount} POL")
                place_order('buy', buy_amount, current_price)
                last_buy_price = current_price
                pol_bought = True

            if pol_bought and current_price >= SELL_PRICE and pol_balance > BALANCE_THRESHOLD:
                logging.info(f"Selling all POL at {current_price} EUR")
                place_order('sell', pol_balance, current_price)
                logging.info("Buy and sell completed. Stopping the bot.")
                break

            logging.info("Running successfully")
            time.sleep(60)
        except Exception as e:
            logging.error(f"An error occurred: {e}")
            logging.error("Not running")
            time.sleep(10)

if __name__ == "__main__":
    import threading
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=8000)).start()
    main()
