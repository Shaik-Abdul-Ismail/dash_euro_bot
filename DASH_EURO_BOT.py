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
        'ts': int(time.time() * 1000),  # Current timestamp in milliseconds
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
    logging.info("Starting Simple Auto Trading Bot...")  # Log when the bot starts

    try:
        # Fetch the current market price
        current_price = get_current_price()
        if current_price is None:
            logging.error("Failed to fetch market price.")  # Log failure
            return

        logging.info(f"Current Price: {current_price} EUR")  # Log the current price

        # Fetch account balances
        balances = get_balances()
        eur_balance = float(balances.get('EUR', {}).get('total', 0.0))
        pol_balance = float(balances.get('POL', {}).get('total', 0.0))

        # Place a BUY order at the current market price
        if eur_balance >= INVESTMENT_AMOUNT:
            buy_amount = INVESTMENT_AMOUNT / current_price  # Use 0.2 EUR to buy POL
            logging.info(f"Placing BUY order at {current_price} EUR for {buy_amount} POL")  # Log buy order
            place_order('buy', buy_amount, current_price)
        else:
            logging.error("Not enough EUR balance to place a buy order.")
            return

        # Wait for a short moment to ensure the buy order is processed
        time.sleep(5)

        # Place a SELL order at the current market price
        updated_balances = get_balances()
        pol_balance = float(updated_balances.get('POL', {}).get('total', 0.0))
        if pol_balance > BALANCE_THRESHOLD:
            logging.info(f"Placing SELL order at {current_price} EUR for {pol_balance} POL")  # Log sell order
            place_order('sell', pol_balance, current_price)
        else:
            logging.error("Not enough POL balance to place a sell order.")
            return

        logging.info("Buy and sell completed. Stopping the bot.")  # Log completion

    except Exception as e:
        logging.error(f"An error occurred: {e}")  # Log any errors
        logging.error("Not running")  # Log that the bot is not running

if __name__ == "__main__":
    # Start the Flask web server in a separate thread
    import threading
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=8000)).start()

    # Run the bot's main function
    main()
