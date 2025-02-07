import os
import time
import requests
import hmac
import hashlib
import json
import logging

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
SELL_PRICE_INCREASE_PERCENT = 0.02  # Sell when the price increases by 2%
BALANCE_THRESHOLD = 0.001  # Minimum balance threshold for trading

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
    last_buy_price = None  # Track the last buy price
    trailing_stop = None  # Initialize trailing stop

    while True:
        try:
            # Fetch the current market price
            current_price = get_current_price()
            if current_price is None:
                logging.error("Failed to fetch market price. Retrying...")  # Log failure
                time.sleep(10)
                continue

            logging.info(f"Current Price: {current_price} EUR")  # Log the current price

            # Fetch account balances
            balances = get_balances()
            eur_balance = float(balances.get('EUR', {}).get('total', 0.0))
            pol_balance = float(balances.get('POL', {}).get('total', 0.0))

            # Buy POL at 0.31 EUR if conditions are met
            if current_price <= BUY_PRICE and eur_balance > BALANCE_THRESHOLD:
                buy_amount = eur_balance / current_price  # Use all available EUR to buy POL
                logging.info(f"Placing BUY order at {current_price} EUR for {buy_amount} POL")  # Log buy order
                place_order('buy', buy_amount, current_price)
                last_buy_price = current_price  # Update last buy price

            # Implement trailing stop-loss for sell orders
            if last_buy_price and pol_balance > BALANCE_THRESHOLD:
                target_sell_price = last_buy_price * (1 + SELL_PRICE_INCREASE_PERCENT)
                if trailing_stop is None or current_price > trailing_stop:
                    trailing_stop = current_price * (1 - SELL_PRICE_INCREASE_PERCENT)
                    logging.info(f"Updated trailing stop to {trailing_stop} EUR")  # Log trailing stop update

                if current_price >= target_sell_price:
                    logging.info(f"Selling all POL at {current_price} EUR due to price increase")  # Log sell order
                    place_order('sell', pol_balance, current_price)
                    trailing_stop = None
                    last_buy_price = None

            logging.info("Running successfully")  # Log that the bot is running successfully
            time.sleep(60)  # Wait for 60 seconds before the next iteration

        except Exception as e:
            logging.error(f"An error occurred: {e}")  # Log any errors
            logging.error("Not running")  # Log that the bot is not running
            time.sleep(10)  # Wait for 10 seconds before retrying

if __name__ == "__main__":
    main()
