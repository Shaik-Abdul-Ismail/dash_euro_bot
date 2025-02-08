import time
import json
import hmac
import hashlib
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry

# Configuration
API_ID = "d3245bd8-5bd6-474c-8ff7-f6913cd11f1b"
API_SECRET = "DSj7irD5v7QBANpE"
BASE_URL = "https://payeer.com/api/trade/"
PAIR = "POL_EUR"  # Change this to your desired pair
STOP_LOSS_PERCENTAGE = 5  # Stop loss percentage
PROFIT_TARGET_PERCENTAGE = 10  # Profit target percentage
MAX_RETRIES = 5  # Maximum retries for API calls
RETRY_BACKOFF_FACTOR = 2  # Exponential backoff factor

# Helper Functions
def generate_signature(method, req_body):
    """Generate HMAC-SHA256 signature."""
    req_body_str = json.dumps(req_body)
    message = method + req_body_str
    return hmac.new(API_SECRET.encode(), message.encode(), hashlib.sha256).hexdigest()

def make_request(method, endpoint, data=None):
    """Make a POST request to the Payeer API with retry logic."""
    url = BASE_URL + endpoint
    ts = int(time.time() * 1000)
    req_body = {"ts": ts}
    if data:
        req_body.update(data)

    headers = {
        "Content-Type": "application/json",
        "API-ID": API_ID,
        "API-SIGN": generate_signature(endpoint, req_body),
    }

    # Configure retry strategy
    retry_strategy = Retry(
        total=MAX_RETRIES,
        backoff_factor=RETRY_BACKOFF_FACTOR,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["POST"],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session = requests.Session()
    session.mount("https://", adapter)

    try:
        response = session.post(url, headers=headers, data=json.dumps(req_body))
        response.raise_for_status()
        result = response.json()
        if result.get("success"):
            return result
        else:
            print(f"Error: {result}")
            return None
    except requests.exceptions.RequestException as e:
        print(f"Request failed: {e}")
        return None

def get_balance():
    """Fetch account balance."""
    response = make_request("POST", "account")
    if response:
        return response.get("balances", {})
    return {}

def place_order(pair, action, amount, price=None, order_type="limit"):
    """Place a new order."""
    data = {
        "pair": pair,
        "type": order_type,
        "action": action,
        "amount": str(amount),
    }
    if price:
        data["price"] = str(price)
    response = make_request("POST", "order_create", data)
    if response:
        return response.get("order_id")
    return None

def get_order_status(order_id):
    """Get the status of an order."""
    data = {"order_id": order_id}
    response = make_request("POST", "order_status", data)
    if response:
        return response.get("order", {})
    return {}

def cancel_order(order_id):
    """Cancel an order."""
    data = {"order_id": order_id}
    response = make_request("POST", "order_cancel", data)
    if response and response.get("success"):
        print(f"Order {order_id} canceled successfully.")
    else:
        print(f"Failed to cancel order {order_id}.")

def get_ticker(pair):
    """Get ticker information for a pair."""
    data = {"pair": pair}
    response = make_request("POST", "ticker", data)
    if response:
        return response.get("pairs", {}).get(pair, {})
    return {}

def get_pair_limits(pair):
    """Fetch minimum amount and value for a specific pair."""
    response = make_request("POST", "info", {"pair": pair})
    if response and response.get("success"):
        pair_info = response["pairs"][pair]
        return {
            "min_amount": float(pair_info["min_amount"]),
            "min_value": float(pair_info["min_value"]),
        }
    return None

def monitor_orders(buy_order_id, sell_order_id, buy_price, sell_price):
    """Monitor orders and implement stop-loss/profit-target logic."""
    while True:
        buy_order = get_order_status(buy_order_id)
        sell_order = get_order_status(sell_order_id)

        # Check if buy order is filled
        if buy_order.get("status") == "success":
            print("Buy order filled. Monitoring sell order...")
            break

        # Check if sell order is filled
        if sell_order.get("status") == "success":
            print("Sell order filled. Exiting...")
            return

        # Calculate current price (you can replace this with live ticker data)
        current_price = float(get_ticker(PAIR)["last"])

        # Stop-loss logic
        if current_price <= buy_price * (1 - STOP_LOSS_PERCENTAGE / 100):
            print("Stop-loss triggered. Canceling orders...")
            cancel_order(buy_order_id)
            cancel_order(sell_order_id)
            return

        # Profit target logic
        if current_price >= sell_price:
            print("Profit target reached. Waiting for sell order to fill...")
            break

        time.sleep(10)  # Poll every 10 seconds

# Main Bot Logic
def trading_bot():
    global BUY_AMOUNT  # Declare BUY_AMOUNT as global to modify it
    try:
        print("Fetching balance...")
        balance = get_balance()
        print(f"Balance: {balance}")

        # Fetch ticker data
        ticker = get_ticker(PAIR)
        last_price = float(ticker.get("last", 0))
        print(f"Last price for {PAIR}: {last_price}")

        # Fetch pair limits
        pair_limits = get_pair_limits(PAIR)
        if not pair_limits:
            print(f"Failed to fetch limits for {PAIR}. Exiting...")
            return

        min_amount = pair_limits["min_amount"]
        min_value = pair_limits["min_value"]

        # Adjust BUY_AMOUNT to meet both min_amount and min_value
        BUY_AMOUNT = max(min_amount, min_value / last_price)
        print(f"Adjusted BUY_AMOUNT to {BUY_AMOUNT} to meet minimum requirements.")

        # Calculate buy and sell prices
        buy_price = last_price * 0.99  # Buy at 1% below current price
        sell_price = last_price * 1.01  # Sell at 1% above current price

        # Verify available balance
        quote_currency = PAIR.split("_")[1]  # Extract quote currency (e.g., EUR)
        available_balance = float(balance.get(quote_currency, {}).get("available", 0))
        total_buy_value = BUY_AMOUNT * buy_price

        if available_balance < total_buy_value:
            print(
                f"Insufficient balance in {quote_currency}. Available: {available_balance}, Required: {total_buy_value}"
            )
            return

        print(f"Placing buy order at {buy_price}...")
        buy_order_id = place_order(PAIR, "buy", BUY_AMOUNT, buy_price)
        if not buy_order_id:
            print("Failed to place buy order.")
            return

        print(f"Placing sell order at {sell_price}...")
        sell_order_id = place_order(PAIR, "sell", BUY_AMOUNT, sell_price)
        if not sell_order_id:
            print("Failed to place sell order.")
            cancel_order(buy_order_id)
            return

        print(f"Monitoring orders: Buy ID={buy_order_id}, Sell ID={sell_order_id}")
        monitor_orders(buy_order_id, sell_order_id, buy_price, sell_price)

    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    trading_bot()
