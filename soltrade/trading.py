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
    # Set buy logic mode based on trading mode
    buy_logic_mode = 'loose' if trading_mode.lower() == 'degen' else 'strict'

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

    # Add margin variables for more flexible buy/sell triggers
    buy_margin = getattr(config(), 'buy_margin_percent', 0)
    sell_margin = getattr(config(), 'sell_margin_percent', 0)

    # Precompute margin-adjusted targets so they're always available
    bb_target = lower_bb.iat[-1] * (1 + buy_margin)
    rsi_target = rsi_buy_threshold * (1 + buy_margin)

    # Update current stoploss and takeprofit from market instance
    stoploss = mkt.sl
    takeprofit = mkt.tp

    # Recalculate the expected stoploss and takeprofit based on current config values
    if mkt.position and hasattr(mkt, 'entry_price') and mkt.entry_price > 0:
        expected_stoploss = mkt.entry_price * stoploss_multiplier
        expected_takeprofit = mkt.entry_price * takeprofit_multiplier

        if abs(mkt.sl - expected_stoploss) > 0.000001 or abs(mkt.tp - expected_takeprofit) > 0.000001:
            log_general.info(f"Updated stoploss or takeprofit from .env: SL {mkt.sl:.6f} → {expected_stoploss:.6f}, TP {mkt.tp:.6f} → {expected_takeprofit:.6f}")
            mkt.sl = expected_stoploss
            mkt.tp = expected_takeprofit
            stoploss = expected_stoploss
            takeprofit = expected_takeprofit
            mkt.update_position(True, stoploss, takeprofit, highest_price=mkt.highest_price)

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
    ema_target = ema_medium * (1 - buy_margin)
    ema_crossover = ema_short >= ema_target
    buy_condition1 = ema_crossover or price <= bb_target

    # ------------------------------
    # Margin logic:
    # BUY_MARGIN_PERCENT allows buy triggers to activate slightly before crossing exact thresholds (BB, RSI).
    # SELL_MARGIN_PERCENT allows sell triggers like RSI to hit slightly early.
    # These are configurable in the .env file and default to 0 if not set.
    # ------------------------------
    
    # In degen mode, only buy if we're in an uptrend,
    # the price is under the lower Bollinger Band,
    # and RSI is below the dynamic threshold from config
    if trading_mode.lower() == "degen":
        # Logic mode handling for buy decision
        if buy_logic_mode == "loose":
            # Loose mode: Buy if trend is up and either BB dip OR RSI dip
            final_buy_decision = trend_bias and (price <= bb_target or rsi <= rsi_target)
        else:
            # Strict mode: Buy only if all conditions are met
            final_buy_decision = trend_bias and price <= bb_target and rsi <= rsi_target
    else:
        final_buy_decision = buy_condition1 and (rsi <= rsi_buy_threshold)

    # Revised sell conditions:
    # Instead of forcing a sale when price >= takeprofit,
    # we now sell if the price falls below the stoploss or the trailing stop.
    ema_sell_target = ema_medium * (1 + sell_margin)
    ema_reversal = ema_short <= ema_sell_target
    sell_condition1 = price <= stoploss or (mkt.position and price < trailing_stop)
    sell_condition2 = ema_reversal or price > upper_bb.iat[-1]
    rsi_sell_target = rsi_sell_threshold * (1 - sell_margin)
    sell_condition3 = rsi >= rsi_sell_target

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
- EMA Short >= EMA Medium (with margin) OR Price < Lower BB: {buy_condition1}
- RSI <= {rsi_buy_threshold}: {rsi <= rsi_buy_threshold}
Buy Decision Reason: {'Trend + (BB or RSI)' if final_buy_decision and buy_logic_mode == 'loose' else 'Trend + BB + RSI' if final_buy_decision else 'No qualifying conditions met'}
Final Buy Decision: {final_buy_decision}
""")

    if mkt.position:
        log_general.debug(f"""
Sell Conditions:
- Price <= Stoploss OR Price < Trailing Stop: {sell_condition1}
- EMA Short <= EMA Medium (with margin) OR Price > Upper BB: {sell_condition2}
- RSI >= {rsi_sell_target}: {sell_condition3}
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

        if sell_condition1 or (sell_condition2 and sell_condition3):
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