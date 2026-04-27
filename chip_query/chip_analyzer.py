#!/usr/bin/env python3
"""
筹码分布核心算法
"""
import numpy as np
import pandas as pd


class ChipAnalyzer:
    def __init__(self, price_step: float = 0.1):
        self.price_step = price_step

    def _build_price_grid(self, df: pd.DataFrame):
        min_price = max(0.01, df['low'].min() * 0.95)
        max_price = df['high'].max() * 1.05
        return np.arange(min_price, max_price + self.price_step, self.price_step)

    def _triangular_distribution(self, low: float, high: float, avg_price: float, price_grid):
        if high <= low:
            dist = np.zeros_like(price_grid)
            idx = np.argmin(np.abs(price_grid - avg_price))
            if idx < len(dist):
                dist[idx] = 1.0
            return dist
        
        dist = np.zeros_like(price_grid)
        mask = (price_grid >= low) & (price_grid <= high)
        
        if avg_price <= low:
            avg_price = low + 0.01
        if avg_price >= high:
            avg_price = high - 0.01
        
        left_mask = mask & (price_grid < avg_price)
        right_mask = mask & (price_grid >= avg_price)
        
        if left_mask.any():
            dist[left_mask] = (price_grid[left_mask] - low) / (avg_price - low)
        if right_mask.any():
            dist[right_mask] = (high - price_grid[right_mask]) / (high - avg_price)
        
        total = dist.sum()
        if total > 0:
            dist /= total
        
        return dist

    def analyze(self, df: pd.DataFrame) -> dict:
        df = df.sort_values('trade_date').reset_index(drop=True)
        price_grid = self._build_price_grid(df)
        chips = np.zeros_like(price_grid)
        
        for i, row in df.iterrows():
            turnover = row['turnover_rate'] / 100.0
            if turnover > 1.0:
                turnover = 1.0
            
            avg_price = (row['open'] + row['high'] + row['low'] + row['close']) / 4.0
            today_dist = self._triangular_distribution(row['low'], row['high'], avg_price, price_grid)
            
            chips = chips * (1 - turnover) + today_dist * turnover
        
        total = chips.sum()
        if total > 0:
            chips /= total
        
        current_price = df.iloc[-1]['close']
        avg_cost = np.sum(price_grid * chips)
        
        cumsum = np.cumsum(chips)
        median_idx = np.searchsorted(cumsum, 0.5)
        median_cost = price_grid[median_idx] if median_idx < len(price_grid) else avg_cost
        
        peak_idx = np.argmax(chips)
        peak_price = price_grid[peak_idx]
        
        profit_ratio = chips[price_grid < current_price].sum()
        locked_ratio = 1.0 - profit_ratio
        
        idx_70_low = np.searchsorted(cumsum, 0.15)
        idx_70_high = np.searchsorted(cumsum, 0.85)
        range_70 = (round(price_grid[idx_70_low], 2), round(price_grid[idx_70_high], 2))
        
        idx_90_low = np.searchsorted(cumsum, 0.05)
        idx_90_high = np.searchsorted(cumsum, 0.95)
        range_90 = (round(price_grid[idx_90_low], 2), round(price_grid[idx_90_high], 2))
        
        peak_distance = round((current_price / peak_price - 1) * 100, 2)
        
        return {
            'price_grid': price_grid,
            'chips': chips,
            'avg_cost': round(avg_cost, 2),
            'median_cost': round(median_cost, 2),
            'peak_price': round(peak_price, 2),
            'current_price': round(current_price, 2),
            'profit_ratio': round(profit_ratio, 4),
            'locked_ratio': round(locked_ratio, 4),
            'range_70': range_70,
            'range_90': range_90,
            'peak_distance': peak_distance,
        }
