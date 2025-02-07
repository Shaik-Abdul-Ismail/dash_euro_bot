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
SYMBOL = "DASH_EUR"  # Trading pair
BALANCE_THRESHOLD = 0.001  # Minimum balance threshold for trading
RISK_PER_TRADE = 0.01  # Risk 1% of total balance per trade
TRAILING_STOP_PERCENT = 0.02  # Trailing stop at 2% below current price
INITIAL_GRID_BUY_LEVELS = [18.0, 15.0, 16.0, 17.0, 19.0, 20.0, 21.0, 22.5, 23.0, 23.5, 24.0, 24.1]  # Buy grid levels
INITIAL_GRID_SELL_LEVELS = [
    150.0, 100.0, 120.0, 80.0, 70.0, 60.0, 50.0, 45.0, 42.0, 41.0,
    39.0, 38.0, 37.0, 36.0, 35.0, 34.0, 33.0, 32.0, 31.0, 30.0, 28.0, 27.0
]  # Sell grid levels

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

def calculate_position_size(balance, risk_percentage, price):
    """
    Calculate the position size based on the risk percentage.
    :param balance: Total balance available for trading
    :param risk_percentage: Percentage of balance to risk per trade
    :param price: Current market price
    :return: Position size (amount of asset to trade)
    """
    return (balance * risk_percentage) / price

def adjust_grid_levels(current_price, initial_levels, compression_factor=1.0):
    """
    Dynamically adjust grid levels based on the current price and volatility.
    :param current_price: Current market price
    :param initial_levels: Initial grid levels (buy or sell)
    :param compression_factor: Factor to reduce the distance between levels in volatile markets
    :return: Adjusted grid levels sorted in ascending order
    """
    adjusted_levels = [
        current_price + (level - current_price) * compression_factor
        for level in initial_levels
    ]
    return sorted(adjusted_levels)

def detect_trend(prices, short_window=10, long_window=50):
    """
    Detect market trend using Simple Moving Average (SMA) crossover.
    :param prices: List of historical prices
    :param short_window: Short-term SMA window size
    :param long_window: Long-term SMA window size
    :return: 'up', 'down', or 'neutral' based on the trend
    """
    if len(prices) < long_window:
        return 'neutral'  # Not enough data to determine trend
    short_sma = sum(prices[-short_window:]) / short_window
    long_sma = sum(prices[-long_window:]) / long_window
    if short_sma > long_sma:
        return 'up'
    elif short_sma < long_sma:
        return 'down'
    else:
        return 'neutral'

def main():
    logging.info("Starting Advanced Auto Trading Bot...")  # Log when the bot starts
    trailing_stop = None  # Initialize trailing stop
    last_buy_price = None  # Track the last buy price
    historical_prices = []  # Store historical prices for trend detection
    grid_buy_levels = INITIAL_GRID_BUY_LEVELS  # Initialize buy grid levels
    grid_sell_levels = INITIAL_GRID_SELL_LEVELS  # Initialize sell grid levels

    while True:
        try:
            # Fetch the current market price
            current_price = get_current_price()
            if current_price is None:
                logging.error("Failed to fetch market price. Retrying...")  # Log failure
                time.sleep(10)
                continue
            logging.info(f"Current Price: {current_price} EUR")  # Log the current price
            historical_prices.append(current_price)
            # Keep only the last 100 prices for trend analysis
            if len(historical_prices) > 100:
                historical_prices.pop(0)
            # Detect the current market trend
            trend = detect_trend(historical_prices)
            logging.info(f"Detected Trend: {trend}")  # Log the detected trend
            # Dynamically adjust grid levels based on the current price
            grid_buy_levels = adjust_grid_levels(current_price, INITIAL_GRID_BUY_LEVELS, compression_factor=0.9)
            grid_sell_levels = adjust_grid_levels(current_price, INITIAL_GRID_SELL_LEVELS, compression_factor=0.9)
            # Fetch account balances
            balances = get_balances()
            eur_balance = float(balances.get('EUR', {}).get('total', 0.0))
            dash_balance = float(balances.get('DASH', {}).get('total', 0.0))
            # Calculate maximum buy amount based on risk percentage
            max_buy_amount = calculate_position_size(eur_balance, RISK_PER_TRADE, current_price)
            # Place dynamic buy orders in an uptrend or neutral market
            if trend != 'down':  # Only buy in an uptrend or neutral market
                for level in sorted(grid_buy_levels):
                    if current_price <= level and eur_balance > BALANCE_THRESHOLD:
                        buy_amount = min(max_buy_amount, eur_balance / current_price)
                        logging.info(f"Placing BUY order at {current_price} EUR for {buy_amount} DASH")  # Log buy order
                        place_order('buy', buy_amount, current_price)
                        last_buy_price = current_price
                        break
            # Implement trailing stop-loss for sell orders
            if last_buy_price and dash_balance > BALANCE_THRESHOLD:
                if trailing_stop is None or current_price > trailing_stop:
                    trailing_stop = current_price * (1 - TRAILING_STOP_PERCENT)
                    logging.info(f"Updated trailing stop to {trailing_stop} EUR")  # Log trailing stop update
                if current_price <= trailing_stop:
                    logging.info(f"Selling all DASH at {current_price} EUR due to trailing stop")  # Log sell order
                    place_order('sell', dash_balance, current_price)
                    trailing_stop = None
                    last_buy_price = None
            # Place dynamic sell orders in a downtrend or neutral market
            if trend != 'up':  # Only sell in a downtrend or neutral market
                for level in sorted(grid_sell_levels, reverse=True):
                    if current_price >= level and dash_balance > BALANCE_THRESHOLD:
                        logging.info(f"Placing SELL order at {current_price} EUR for {dash_balance} DASH")  # Log sell order
                        place_order('sell', dash_balance, current_price)
                        trailing_stop = None
                        last_buy_price = None
                        break
            logging.info("Running successfully")  # Log that the bot is running successfully
            time.sleep(60)  # Wait for 60 seconds before the next iteration
        except Exception as e:
            logging.error(f"An error occurred: {e}")  # Log any errors
            logging.error("Not running")  # Log that the bot is not running
            time.sleep(10)  # Wait for 10 seconds before retrying

if __name__ == "__main__":
    # Start the Flask web server in a separate thread
    import threading
    threading.Thread(target=lambda: app.run(host='0.0.0.0', port=8000)).start()
    # Run the bot's main function
    main()
