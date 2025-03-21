import requests
import asyncio
import pandas as pd

from apscheduler.schedulers.background import BlockingScheduler

from soltrade.transactions import perform_swap, market
from soltrade.indicators import calculate_ema, calculate_rsi, calculate_bbands
from soltrade.wallet import find_balance
from soltrade.log import log_general, log_transaction
from soltrade.config import config

stoploss = 0
takeprofit = 0

market('position.json')

# Pulls the candlestick information in fifteen minute intervals
def fetch_candlestick() -> dict:
    url = "https://min-api.cryptocompare.com/data/v2/histominute"
    headers = {'authorization': config().api_key}
    params = {'tsym': config().primary_mint_symbol, 'fsym': config().secondary_mint_symbol, 'limit': 50, 'aggregate': config().trading_interval_minutes}
    
    response = requests.get(url, headers=headers, params=params)
    response_json = response.json()
    
    # Log only the API status code instead of full response
    if response.status_code != 200:
        log_general.error(f"API Error: {response.status_code} {response.reason}")
        exit()
    
    log_general.debug(f"API Response: {response.status_code} {response.reason}")
    return response_json

# Analyzes the current market variables and determines trades
def perform_analysis():
    global stoploss, takeprofit
    log_general.debug("Soltrade is analyzing the market; no trade has been executed.")

    mkt = market()  # Use a single market instance to keep state
    mkt.load_position()
    
    # Fetch and prepare candlestick data for analysis
    candle_json = fetch_candlestick()
    candle_dict = candle_json["Data"]["Data"]

    # Create DataFrame for manipulation
    columns = ['close', 'high', 'low', 'open', 'time', 'VF', 'VT']
    df = pd.DataFrame(candle_dict, columns=columns)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    cl = df['close']

    # Technical analysis values
    price = cl.iat[-1]
    ema_short = calculate_ema(dataframe=df, length=5)
    ema_medium = calculate_ema(dataframe=df, length=20)
    rsi = calculate_rsi(dataframe=df, length=14)
    upper_bb, lower_bb = calculate_bbands(dataframe=df, length=14)
    
    # Retrieve stoploss and takeprofit multipliers from config
    stoploss_multiplier = config().stoploss_percent
    takeprofit_multiplier = config().takeprofit_percent
    
    # Update current stoploss and takeprofit from market instance
    stoploss = mkt.sl
    takeprofit = mkt.tp

    # Get RSI thresholds from config (.env file)
    rsi_buy_threshold = config().rsi_buy_threshold
    rsi_sell_threshold = config().rsi_sell_threshold

    # Trade conditions using configurable RSI thresholds
    buy_condition1 = ema_short > ema_medium or price < lower_bb.iat[-1]
    buy_condition2 = rsi <= rsi_buy_threshold
    sell_condition1 = price <= stoploss or price >= takeprofit
    sell_condition2 = ema_short < ema_medium or price > upper_bb.iat[-1]
    sell_condition3 = rsi >= rsi_sell_threshold

    log_general.debug(f"""
Trade Conditions:
---------------------------------
Price: {price}
Short EMA: {ema_short}
Medium EMA: {ema_medium}
Upper BB: {upper_bb.iat[-1]}
Lower BB: {lower_bb.iat[-1]}
RSI: {rsi}
Stop Loss: {stoploss}
Take Profit: {takeprofit}
Market Position: {mkt.position}
---------------------------------
Buy Conditions:
- EMA Short > EMA Medium OR Price < Lower BB: {buy_condition1}
- RSI <= {rsi_buy_threshold}: {buy_condition2}
Final Buy Decision: {buy_condition1 and buy_condition2}

Sell Conditions:
- Price <= Stoploss OR Price >= Takeprofit: {sell_condition1}
- EMA Short < EMA Medium OR Price > Upper BB: {sell_condition2}
- RSI >= {rsi_sell_threshold}: {sell_condition3}
Final Sell Decision: {sell_condition1 or (sell_condition2 and sell_condition3)}
""")

    # Trade execution logic
    if not mkt.position:
        input_amount = find_balance(config().primary_mint)
        log_general.debug(f"Available Balance for Buying: {input_amount}")

        if buy_condition1 and buy_condition2:
            log_transaction.info("Soltrade has detected a buy signal.")
            if input_amount <= 0:
                log_transaction.warning(f"Buy signal detected, but not enough {config().primary_mint_symbol} to trade.")
                return

            try:
                is_swapped = asyncio.run(perform_swap(input_amount, config().primary_mint))
                log_transaction.info(f"Buy Trade Execution Status: {is_swapped}")

                if is_swapped:
                    # Use multipliers from the .env config to calculate stoploss and takeprofit
                    stoploss = mkt.sl = cl.iat[-1] * stoploss_multiplier
                    takeprofit = mkt.tp = cl.iat[-1] * takeprofit_multiplier
                    mkt.update_position(True, stoploss, takeprofit)
            except Exception as e:
                log_transaction.error(f"Buy trade execution failed: {e}")
            return
    else:
        input_amount = find_balance(config().secondary_mint)
        log_general.debug(f"Available Balance for Selling: {input_amount}")

        if sell_condition1 or (sell_condition2 and sell_condition3):
            log_transaction.info("Soltrade has detected a sell signal.")
            try:
                is_swapped = asyncio.run(perform_swap(input_amount, config().secondary_mint))
                log_transaction.info(f"Sell Trade Execution Status: {is_swapped}")

                if is_swapped:
                    stoploss = takeprofit = mkt.sl = mkt.tp = 0
                    mkt.update_position(False, stoploss, takeprofit)
            except Exception as e:
                log_transaction.error(f"Sell trade execution failed: {e}")
            return

# This starts the trading function on a timer
def start_trading():
    log_general.info("Soltrade has now initialized the trading algorithm.")

    trading_sched = BlockingScheduler()
    trading_sched.add_job(perform_analysis, 'interval', seconds=config().price_update_seconds, max_instances=1)
    trading_sched.start()
    perform_analysis()