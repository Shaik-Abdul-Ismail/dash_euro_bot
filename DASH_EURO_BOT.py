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
API_KEY = os.getenv('API_KEY')
API_SECRET = os.getenv('API_SECRET')
SYMBOL = "DASH_EUR"

# Trading constraints
PRICE_PRECISION = 2  # Price precision (2 decimal places)
MIN_PRICE = 4375.74  # Minimum price for creating an order
MAX_PRICE = 83139.00  # Maximum price for creating an order
MIN_AMOUNT = 0.0001  # Minimum amount to create an order
MIN_VALUE = 0.5  # Minimum value to create an order

BALANCE_THRESHOLD = 0.001  # Minimum balance threshold for trading
RISK_PER_TRADE = 0.01  # Risk 1% of total balance per trade
TRAILING_STOP_PERCENT = 0.02  # Trailing stop at 2% below current price

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
        'amount': round(amount, 4),  # Ensure amount meets MIN_AMOUNT precision
        'price': round(price, PRICE_PRECISION)  # Ensure price meets PRICE_PRECISION
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

def calculate_position_size(balance, risk_percentage, price):
    """
    Calculate the position size based on the risk percentage.
    :param balance: Total balance available for trading
    :param risk_percentage: Percentage of balance to risk per trade
    :param price: Current market price
    :return: Position size (amount of asset to trade)
    """
    max_buy_amount = (balance * risk_percentage) / price
    # Ensure the calculated amount meets MIN_AMOUNT and MIN_VALUE constraints
    min_required_amount = max(MIN_AMOUNT, MIN_VALUE / price)
    return max(min_required_amount, max_buy_amount)

def main():
    logging.info("Starting Advanced Auto Trading Bot...")  # Log when the bot starts

    trailing_stop = None  # Initialize trailing stop
    last_buy_price = None  # Track the last buy price
    historical_prices = []  # Store historical prices for trend detection

    while True:
        try:
            # Fetch the current market price
            current_price = get_current_price()
            if current_price is None:
                logging.error("Failed to fetch market price. Retrying...")
                time.sleep(10)
                continue

            # Ensure the price is within allowed limits
            if current_price < MIN_PRICE or current_price > MAX_PRICE:
                logging.error(f"Price {current_price} EUR is out of bounds. Skipping iteration.")
                time.sleep(60)
                continue

            logging.info(f"Current Price: {current_price} EUR")
            historical_prices.append(current_price)

            # Keep only the last 100 prices for trend analysis
            if len(historical_prices) > 100:
                historical_prices.pop(0)

            # Fetch account balances
            balances = get_balances()
            eur_balance = float(balances.get('EUR', {}).get('total', 0.0))
            dash_balance = float(balances.get('DASH', {}).get('total', 0.0))

            # Calculate maximum buy amount based on risk percentage
            max_buy_amount = calculate_position_size(eur_balance, RISK_PER_TRADE, current_price)

            # Place a BUY order if conditions are met
            if eur_balance > BALANCE_THRESHOLD and max_buy_amount >= MIN_AMOUNT:
                buy_amount = min(max_buy_amount, eur_balance / current_price)
                buy_price = current_price
                logging.info(f"Placing BUY order at {buy_price:.2f} EUR for {buy_amount:.4f} DASH")
                place_order('buy', buy_amount, buy_price)
                last_buy_price = current_price

            # Implement trailing stop-loss for sell orders
            if last_buy_price and dash_balance > BALANCE_THRESHOLD:
                if trailing_stop is None or current_price > trailing_stop:
                    trailing_stop = current_price * (1 - TRAILING_STOP_PERCENT)
                    logging.info(f"Updated trailing stop to {trailing_stop:.2f} EUR")

                if current_price <= trailing_stop:
                    logging.info(f"Selling all DASH at {current_price:.2f} EUR due to trailing stop")
                    place_order('sell', dash_balance, current_price)
                    trailing_stop = None
                    last_buy_price = None

            logging.info("Running successfully")
            time.sleep(60)

        except Exception as e:
            logging.error(f"An error occurred: {e}")
            logging.error("Not running")
            time.sleep(10)

if __name__ == "__main__":
    # Start the Flask web server in a separate thread
    import threading
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=8000)).start()

    # Run the bot's main function
    main()
