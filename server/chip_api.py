#!/usr/bin/env python3
"""
个股筹码分析 API
提供给前端调用的接口
"""
import sys
import json
from pathlib import Path

# 添加筹码分析系统路径
chip_dir = Path(__file__).parent.parent / '独立股票的筹码分析系统'
sys.path.insert(0, str(chip_dir))

from chip_analyzer import ChipAnalyzer
from data_source import get_daily, get_moneyflow, get_stock_name
from ifind_enricher import get_fundamentals


def analyze_stock(ts_code: str, days: int = 60) -> dict:
    """
    分析个股筹码
    返回 JSON 格式结果
    """
    try:
        stock_name = get_stock_name(ts_code)
        df_daily = get_daily(ts_code, days=days)
        
        if df_daily is None or len(df_daily) == 0:
            return {'success': False, 'error': '无法获取行情数据'}
        
        analyzer = ChipAnalyzer(price_step=0.1)
        chip = analyzer.analyze(df_daily)
        
        df_money = get_moneyflow(ts_code, days=20)
        
        # 资金流
        moneyflow = {
            'main_net_5d': None,
            'main_net_10d': None,
        }
        if df_money is not None and len(df_money) > 0 and 'main_net' in df_money.columns:
            moneyflow['main_net_5d'] = float(df_money.tail(5)['main_net'].sum()) if len(df_money) >= 1 else None
            moneyflow['main_net_10d'] = float(df_money.tail(10)['main_net'].sum()) if len(df_money) >= 1 else None
        
        # 基本面
        last = df_daily.iloc[-1]
        basics = {
            'pe_ttm': round(float(last['pe_ttm']), 2) if 'pe_ttm' in df_daily.columns and last['pe_ttm'] is not None and str(last['pe_ttm']) != 'nan' else None,
            'pb': round(float(last['pb']), 2) if 'pb' in df_daily.columns and last['pb'] is not None and str(last['pb']) != 'nan' else None,
            'total_mv': float(last['total_mv']) if 'total_mv' in df_daily.columns and last['total_mv'] is not None and str(last['total_mv']) != 'nan' else None,
        }
        
        # 数据区间
        start_date = df_daily.iloc[0]['trade_date'].strftime('%Y-%m-%d')
        end_date = df_daily.iloc[-1]['trade_date'].strftime('%Y-%m-%d')
        date_range = f"{start_date} ~ {end_date}"
        actual_trade_days = int(len(df_daily))

        # iFind 基本面增强
        fundamentals = get_fundamentals(ts_code, stock_name)
        
        def _f(v):
            """安全转 float"""
            if v is None:
                return None
            try:
                f = float(v)
                return round(f, 2) if abs(f) < 1e12 else f
            except (TypeError, ValueError):
                return None

        return {
            'success': True,
            'ts_code': ts_code,
            'stock_name': stock_name,
            'date_range': date_range,
            'start_date': start_date,
            'end_date': end_date,
            'lookback_days': days,
            'actual_trade_days': actual_trade_days,
            'chip': {
                'current_price': _f(chip.get('current_price')),
                'avg_cost': _f(chip.get('avg_cost')),
                'median_cost': _f(chip.get('median_cost')),
                'peak_price': _f(chip.get('peak_price')),
                'range_70': [_f(chip['range_70'][0]), _f(chip['range_70'][1])] if chip.get('range_70') else None,
                'range_90': [_f(chip['range_90'][0]), _f(chip['range_90'][1])] if chip.get('range_90') else None,
                'profit_ratio': _f(chip.get('profit_ratio')),
                'locked_ratio': _f(chip.get('locked_ratio')),
                'peak_distance': _f(chip.get('peak_distance')),
            },
            'moneyflow': moneyflow,
            'basics': basics,
            'fundamentals': fundamentals,
        }
    except Exception as e:
        return {'success': False, 'error': str(e)}


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(json.dumps({'success': False, 'error': '缺少股票代码参数'}))
        sys.exit(1)
    
    code = sys.argv[1].upper()
    result = analyze_stock(code)
    print(json.dumps(result, ensure_ascii=False))
