import os
import time
import requests
import hmac
import hashlib
import json
import logging
from flask import Flask

# Configure logging to log messages to both a file and the console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler()
    ]
)

# Constants for API and trading parameters
API_URL = "https://payeer.com/api/trade"
API_KEY = os.getenv('API_KEY')  # Fetch API key from environment variables
API_SECRET = os.getenv('API_SECRET')  # Fetch API secret from environment variables
SYMBOL = "DASH_EUR"  # Trading pair
FIXED_INVESTMENT_AMOUNT = 0.2  # Fixed investment amount in EUR
BALANCE_THRESHOLD = 0.001  # Minimum balance threshold for trading
PRICE_PRECISION = 2  # Price precision (2 decimal places)
AMOUNT_PRECISION = 4  # Amount precision (4 decimal places)

# Initialize Flask app for health checks
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def generate_signature(method, params):
    """
    Generate HMAC-SHA256 signature for API requests.
    :param method: The API method (e.g., 'account', 'order_create')
    :param params: The payload parameters for the request
    :return: Hex-encoded HMAC signature
    """
    params_json = json.dumps(params, separators=(',', ':'), ensure_ascii=False)
    H = hmac.new(API_SECRET.encode('utf-8'), digestmod=hashlib.sha256)
    H.update((method + params_json).encode('utf-8'))
    return H.hexdigest()

def get_balances():
    """
    Fetch account balances from the exchange.
    :return: JSON response containing account balances
    """
    method = "account"
    payload = {'ts': int(time.time() * 1000)}  # Current timestamp in milliseconds
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
    :param order_type: 'buy' or 'sell'
    :param amount: Amount of asset to buy/sell
    :param price: Price at which to execute the order
    :return: JSON response containing order details
    """
    method = "order_create"
    payload = {
        'ts': int(time.time() * 1000),
        'pair': SYMBOL,
        'type': order_type,
        'amount': round(amount, AMOUNT_PRECISION),  # Ensure amount meets precision
        'price': round(price, PRICE_PRECISION)  # Ensure price meets precision
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
    :return: Current market price as a float, or None if the request fails
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
    logging.info("Starting Simple Buy-and-Sell Bot...")  # Log when the bot starts

    try:
        # Fetch the current market price
        current_price = get_current_price()
        if current_price is None:
            logging.error("Failed to fetch market price.")
            return

        logging.info(f"Current Price: {current_price:.2f} EUR")

        # Fetch account balances
        balances = get_balances()
        eur_balance = float(balances.get('EUR', {}).get('total', 0.0))
        dash_balance = float(balances.get('DASH', {}).get('total', 0.0))

        # Check if there's enough EUR balance to place a buy order
        if eur_balance < FIXED_INVESTMENT_AMOUNT:
            logging.error(f"Not enough EUR balance. Required: {FIXED_INVESTMENT_AMOUNT}, Available: {eur_balance}")
            return

        # Calculate the amount of DASH to buy with 0.2 EUR
        buy_amount = FIXED_INVESTMENT_AMOUNT / current_price
        logging.info(f"Placing BUY order at {current_price:.2f} EUR for {buy_amount:.4f} DASH")
        place_order('buy', buy_amount, current_price)

        # Wait for a short moment to ensure the buy order is processed
        time.sleep(5)

        # Fetch updated balances after the buy order
        updated_balances = get_balances()
        dash_balance = float(updated_balances.get('DASH', {}).get('total', 0.0))

        # Place a SELL order for all the DASH bought
        if dash_balance > BALANCE_THRESHOLD:
            logging.info(f"Placing SELL order at {current_price:.2f} EUR for {dash_balance:.4f} DASH")
            place_order('sell', dash_balance, current_price)
        else:
            logging.error("Not enough DASH balance to place a sell order.")
            return

        logging.info("Buy and sell completed. Stopping the bot.")

    except Exception as e:
        logging.error(f"An error occurred: {e}")
        logging.error("Not running")

if __name__ == "__main__":
    # Start the Flask web server in a separate thread
    import threading
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=8000)).start()

    # Run the bot's main function
    main()
