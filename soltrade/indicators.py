import pandas as pd
from typing import Tuple

def calculate_ema(dataframe: pd.DataFrame, length: int) -> int:
    """
    Calculate the Exponential Moving Average (EMA) for the 'close' column in the DataFrame.

    Args:
        dataframe (pd.DataFrame): DataFrame containing the 'close' price data.
        length (int): The span for the EMA.

    Returns:
        int: The last computed EMA value.

    Raises:
        ValueError: If the DataFrame does not have enough data points.
    """
    if len(dataframe) < length:
        raise ValueError("DataFrame does not have enough data points to compute EMA.")
    
    ema = dataframe['close'].ewm(span=length, adjust=False).mean()
    return ema.iat[-1]

def calculate_bbands(dataframe: pd.DataFrame, length: int) -> Tuple[pd.Series, pd.Series]:
    """
    Calculate Bollinger Bands (upper and lower) using a simple moving average (SMA) for the 'close' column in the DataFrame.

    Args:
        dataframe (pd.DataFrame): DataFrame containing the 'close' price data.
        length (int): The window length for the moving average and standard deviation.

    Returns:
        Tuple[pd.Series, pd.Series]: The upper and lower Bollinger Bands as pd.Series.

    Raises:
        ValueError: If the DataFrame does not have enough data points.
    """
    if len(dataframe) < length:
        raise ValueError("DataFrame does not have enough data points to compute Bollinger Bands.")
    
    sma = dataframe['close'].rolling(length).mean()
    std = dataframe['close'].rolling(length).std()
    upper_bband = sma + std * 2
    lower_bband = sma - std * 2
    return upper_bband, lower_bband

def calculate_rsi(dataframe: pd.DataFrame, length: int) -> int:
    """
    Calculate the Relative Strength Index (RSI) using a custom EMA approach for gains and losses on the 'close' column.

    Args:
        dataframe (pd.DataFrame): DataFrame containing the 'close' price data.
        length (int): The window length for the RSI calculation.

    Returns:
        int: The last computed RSI value.

    Raises:
        ValueError: If the DataFrame does not have enough data points.
    """
    if len(dataframe) < length:
        raise ValueError("DataFrame does not have enough data points to compute RSI.")
    
    delta = dataframe['close'].diff()
    up = delta.clip(lower=0)
    down = delta.clip(upper=0).abs()
    upper_ema = up.ewm(com=length - 1, adjust=False, min_periods=length).mean()
    lower_ema = down.ewm(com=length - 1, adjust=False, min_periods=length).mean()
    
    # Adding epsilon to avoid division by zero
    epsilon = 1e-10
    rsi_ratio = upper_ema / (lower_ema + epsilon)
    rsi = 100 - (100 / (1 + rsi_ratio))
    return rsi.iat[-1]