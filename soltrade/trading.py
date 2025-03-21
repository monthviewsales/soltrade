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
    
    # Determine trend bias by comparing the current medium EMA to its previous value
    prev_ema_medium = df['close'].ewm(span=20, adjust=False).mean().iat[-2]
    trend_bias = ema_medium > prev_ema_medium

    # Retrieve the trading mode from config
    trading_mode = config().trading_mode

    # Determine thresholds based on trading mode
    if trading_mode.lower() == "degen":
        rsi_buy_threshold = config().degen_rsi_buy_threshold
        rsi_sell_threshold = config().degen_rsi_sell_threshold
        stoploss_multiplier = config().degen_stoploss_percent
        takeprofit_multiplier = config().degen_takeprofit_percent
    else:
        rsi_buy_threshold = config().rsi_buy_threshold
        rsi_sell_threshold = config().rsi_sell_threshold
        stoploss_multiplier = config().stoploss_percent
        takeprofit_multiplier = config().takeprofit_percent

    # Update current stoploss and takeprofit from market instance
    stoploss = mkt.sl
    takeprofit = mkt.tp

    # If in an open position, update the highest_price if the current price is higher
    if mkt.position:
        # If entry_price is available use it, otherwise default to highest_price.
        entry_price = getattr(mkt, 'entry_price', mkt.highest_price)
        percent_change = ((price - entry_price) / entry_price) * 100
        entry_info = f"Entry Price: {entry_price:6f} (Change: {percent_change:+.2f}%)"
    else:
        entry_info = "Entry Price: N/A"

    # If highest_price is not yet set, initialize it at the entry price.
    if not hasattr(mkt, 'highest_price') or mkt.highest_price == 0:
        mkt.highest_price = price
    elif price > mkt.highest_price:
        mkt.highest_price = price
        # Persist the new highest_price in position.json
        mkt.update_position(True, stoploss, takeprofit, highest_price=mkt.highest_price)

        # Calculate trailing stop using a trailing stop percent from config (default 5%)
        trailing_stop_percent = getattr(config(), 'trailing_stop_percent', 0.05)
        trailing_stop = mkt.highest_price * (1 - trailing_stop_percent)
    else:
        # When not in a position, highest_price is irrelevant.
        trailing_stop = 0

    # Trade conditions using configurable thresholds
    buy_condition1 = ema_short > ema_medium and price < lower_bb.iat[-1]
    buy_condition2 = rsi <= rsi_buy_threshold

    # ------------------------------
    # Trade Logic Overview
    # ------------------------------
    # Buy Logic:
    # - Degen Mode:
    #     * Requires all of the following:
    #         - Medium EMA trending upward
    #         - Price below lower Bollinger Band
    #         - RSI at or below configured threshold
    # - Retail Mode:
    #     * Requires EMA crossover and RSI threshold met
    #
    # Sell Logic:
    # - Exit if price hits stop loss or trailing stop
    # - Exit if overbought conditions are met (BB, EMA, or RSI)
    # ------------------------------

    # In degen mode, only buy if we're in an uptrend,
    # the price is under the lower Bollinger Band,
    # and RSI is below the dynamic threshold from config
    if trading_mode.lower() == "degen":
        final_buy_decision = trend_bias and price < lower_bb.iat[-1] and rsi <= rsi_buy_threshold
    else:
        final_buy_decision = buy_condition1 and buy_condition2

    # Revised sell conditions:
    # Instead of forcing a sale when price >= takeprofit,
    # we now sell if the price falls below the stoploss or the trailing stop.
    sell_condition1 = price <= stoploss or (mkt.position and price < trailing_stop)
    sell_condition2 = ema_short < ema_medium and price > upper_bb.iat[-1]
    sell_condition3 = rsi >= rsi_sell_threshold

    log_general.debug(f"""
Trade Conditions:
---------------------------------
Price: {price:6f} / {entry_info}
Short EMA: {ema_short}
Medium EMA: {ema_medium}
Upper BB: {upper_bb.iat[-1]}
Lower BB: {lower_bb.iat[-1]}
RSI: {rsi}
Stop Loss: {stoploss}
Take Profit: {takeprofit}
Highest Price: {mkt.highest_price if mkt.position else 'N/A'}
Trailing Stop: {trailing_stop if mkt.position else 'N/A'}
Market Position: {mkt.position}
Trading Mode: {trading_mode}
---------------------------------
Buy Conditions:
- EMA Short > EMA Medium OR Price < Lower BB: {buy_condition1}
- RSI <= {rsi_buy_threshold}: {buy_condition2}
Buy Decision Reason: {'Trend Up + BB Dip + RSI' if final_buy_decision and trading_mode.lower() == 'degen' else 'EMA Crossover + RSI' if final_buy_decision else 'No qualifying conditions met'}
Final Buy Decision: {final_buy_decision}
""")

    if mkt.position:
        log_general.debug(f"""
Sell Conditions:
- Price <= Stoploss OR Price < Trailing Stop: {sell_condition1}
- EMA Short < EMA Medium OR Price > Upper BB: {sell_condition2}
- RSI >= {rsi_sell_threshold}: {sell_condition3}
Sell Decision Reason: {'Stoploss/Trailing hit' if sell_condition1 else 'Overbought/Trend Reversal' if sell_condition2 and sell_condition3 else 'No qualifying conditions met'}
Final Sell Decision: {sell_condition1 or (sell_condition2 and sell_condition3)}
""")

    if not mkt.position:
        input_amount = find_balance(config().primary_mint)
        log_general.debug(f"Available Balance for Buying: {input_amount}")

        if final_buy_decision:
            log_transaction.info("Soltrade has detected a buy signal.")

            if input_amount <= 0:
                log_transaction.warning(f"Buy signal detected, but not enough {config().primary_mint_symbol} to trade.")
                return

            try:
                is_swapped = asyncio.run(perform_swap(input_amount, config().primary_mint))
                log_transaction.info(f"Buy Trade Execution Status: {is_swapped}")

                if is_swapped:
                    # Upon buying, set stoploss, takeprofit, and initialize highest_price to the entry price.
                    stoploss = mkt.sl = cl.iat[-1] * stoploss_multiplier
                    takeprofit = mkt.tp = cl.iat[-1] * takeprofit_multiplier
                    mkt.highest_price = cl.iat[-1]
                    mkt.entry_price = cl.iat[-1]  # Record the entry price
                    mkt.update_position(True, stoploss, takeprofit, highest_price=mkt.highest_price)
            except Exception as e:
                log_transaction.error(f"Buy trade execution failed: {e}")
            return
    else:
        input_amount = find_balance(config().secondary_mint)
        log_general.debug(f"Available Balance for Selling: {input_amount}")

        if sell_condition1 or (sell_condition2 or sell_condition3):
            log_transaction.info("Soltrade has detected a sell signal.")

            try:
                is_swapped = asyncio.run(perform_swap(input_amount, config().secondary_mint))
                log_transaction.info(f"Sell Trade Execution Status: {is_swapped}")

                if is_swapped:
                    # Reset values upon exiting the position.
                    stoploss = takeprofit = mkt.sl = mkt.tp = 0
                    mkt.highest_price = 0
                    mkt.update_position(False, stoploss, takeprofit, highest_price=mkt.highest_price)
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