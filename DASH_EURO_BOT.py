# Constants for API and trading parameters
API_URL = "https://payeer.com/api/trade"
API_KEY = os.getenv('API_KEY')
API_SECRET = os.getenv('API_SECRET')
SYMBOL = "DASH_EUR"

# Trading constraints
PRICE_PRECISION = 2  # Price precision (2 decimal places)
MIN_PRICE = 20.0  # Minimum price for creating an order
MAX_PRICE = 50.0  # Maximum price for creating an order
MIN_AMOUNT = 0.0001  # Minimum amount to create an order
MIN_VALUE = 0.5  # Minimum value to create an order

BALANCE_THRESHOLD = 0.001  # Minimum balance threshold for trading
RISK_PER_TRADE = 0.01  # Risk 1% of total balance per trade
TRAILING_STOP_PERCENT = 0.02  # Trailing stop at 2% below current price

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

            logging.info(f"Fetched Current Price: {current_price} EUR")

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

            logging.info("Running successfully")  # Log that the bot is running successfully
            time.sleep(60)  # Wait for 60 seconds before the next iteration

        except Exception as e:
            logging.error(f"An error occurred: {e}")  # Log any errors
            logging.error("Not running")  # Log that the bot is not running
            time.sleep(10)  # Wait for 10 seconds before retrying
