#!/usr/bin/env python3
import yfinance as yf
from datetime import datetime, timedelta

end_date = datetime.now()
start_date = end_date - timedelta(days=365)

ticker = 'BTC-USD'
data = yf.download(ticker, start=start_date.strftime('%Y-%m-%d'), 
                   end=end_date.strftime('%Y-%m-%d'), progress=False)

print(f"Data type: {type(data)}")
print(f"Data shape: {data.shape}")
print(f"Columns: {data.columns.tolist()}")
print(f"\nFirst 3 rows:")
print(data.head(3))

if 'Close' in data.columns:
    close = data['Close']
    print(f"\nClose type: {type(close)}")
    print(f"Close shape: {close.shape}")
    print(f"First value: {close.iloc[0]}, type: {type(close.iloc[0])}")
