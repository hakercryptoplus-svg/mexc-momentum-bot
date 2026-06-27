"""
Scanner — Check for pump signals and execute trades
"""
import time
from datetime import datetime, timezone
from config import MIN_PUMP, COINS, FEE

class Scanner:
    def __init__(self, mexc, state, notify_func=None):
        self.m = mexc
        self.state = state
        self.notify = notify_func
        self.coins_to_check = 0

    def scan(self):
        """Scan all coins for pump signals. Returns signal or None."""
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        signals = []

        for sym in COINS:
            raw = self.m.get_klines(sym, '1d', 3)
            if not raw or 'error' in raw or not isinstance(raw, list) or len(raw) < 2:
                continue

            df = self.m.parse_klines(raw)
            if len(df) < 2: continue

            yesterday = df[-2]
            pump = (yesterday['close'] - yesterday['open']) / yesterday['open'] * 100

            if pump >= MIN_PUMP:
                today_candle = df[-1]
                entry_price = today_candle['open']

                signals.append({
                    'symbol': sym,
                    'pump': round(pump, 2),
                    'entry': entry_price,
                    'date': today
                })

            time.sleep(0.08)

        if not signals:
            return None

        signals.sort(key=lambda x: x['pump'], reverse=True)
        return signals[0]

    def execute_trade(self, signal, balance):
        """Place market buy with 100% of balance"""
        sym = signal['symbol']
        entry = signal['entry']

        actual_balance = self.m.get_balance('USDT')
        if actual_balance < 1:
            return None, "الرصيد أقل من 1 USDT"

        invest = actual_balance

        result = self.m.market_buy(sym, invest)
        if 'error' in result:
            return None, f"فشل الشراء: {result.get('msg', result)}"

        fills = result.get('fills', [])
        qty = sum(float(f['qty']) for f in fills)
        avg_price = sum(float(f['price']) for f in fills) / max(len(fills), 1)

        trade = {
            'symbol': sym,
            'entry_price': avg_price,
            'qty': qty,
            'usdt_invested': invest,
            'date': signal['date'],
            'entry_time': datetime.now(timezone.utc).isoformat(),
            'tp': avg_price * 1.02,           # +2%
            'sl': avg_price * 0.99,            # -1% أصلي
            'trail_trigger': avg_price * 1.01, # +1% → يفعل التريلنغ
            'sl_trailed': avg_price,           # بعد التفعيل = سعر الدخول
            'trail_activated': False,          # لسه ما تفعل
            'status': 'OPEN'
        }

        return trade, None

    def check_tp_sl(self, trade):
        """Check if TP or SL is hit. Returns 'TP', 'SL', 'BE', or 'HOLD'
        
        TRAILING LOGIC:
        - إذا السعر لمس +1% من سعر الدخول ← الـ SL يتحرك لسعر الدخول (Breakeven)
        - بعدها ننتظر TP أو Breakeven — لا خسارة بعد التفعيل
        """
        sym = trade['symbol']
        ticker = self.m.get_ticker(sym)
        if 'error' in ticker:
            return 'HOLD'

        try:
            high = float(ticker.get('highPrice', 0))
            low = float(ticker.get('lowPrice', 0))
            current = float(ticker.get('lastPrice', 0))
        except:
            return 'HOLD'

        tp = trade['tp']
        entry = trade['entry_price']
        trail_trigger = trade.get('trail_trigger', entry * 1.01)
        sl_trailed = trade.get('sl_trailed', entry)
        trail_activated = trade.get('trail_activated', False)

        # === TRAILING: هل السعر لمس +1%؟ ===
        if not trail_activated:
            if high >= trail_trigger or current >= trail_trigger:
                trade['trail_activated'] = True
                trade['sl'] = sl_trailed  # حرك الـ SL لسعر الدخول
                trade['trail_time'] = datetime.now(timezone.utc).isoformat()
                trail_activated = True

        sl = trade['sl']

        if low <= sl:
            if trail_activated:
                return 'BE'
            return 'SL'
        if high >= tp:
            return 'TP'
        if current <= sl:
            if trail_activated:
                return 'BE'
            return 'SL'
        if current >= tp:
            return 'TP'

        return 'HOLD'

    def close_trade(self, trade, reason='TP'):
        """Sell position"""
        sym = trade['symbol']
        qty = trade['qty']

        asset = sym.split('/')[0]
        actual_qty = self._get_asset_balance(asset)

        if actual_qty <= 0:
            return None, "لا يوجد كمية من العملة"

        adjusted = self.m.adjust_qty(sym, actual_qty)

        result = self.m.market_sell(sym, adjusted)
        if 'error' in result:
            return None, f"فشل البيع: {result.get('msg', result)}"

        fills = result.get('fills', [])
        avg_price = sum(float(f['price']) for f in fills) / max(len(fills), 1)

        pnl = (avg_price - trade['entry_price']) * trade['qty'] - (trade['usdt_invested'] + avg_price * trade['qty']) * FEE
        pnl_pct = (avg_price / trade['entry_price'] - 1) * 100

        return {
            'exit_price': avg_price,
            'pnl': round(pnl, 2),
            'pnl_pct': round(pnl_pct, 2),
            'result': reason,
            'exit_time': datetime.now(timezone.utc).isoformat()
        }, None

    def _get_asset_balance(self, asset):
        acct = self.m._get("/api/v3/account", signed=True)
        if 'error' in acct:
            return 0.0
        for b in acct.get('balances', []):
            if b['asset'] == asset:
                return float(b.get('free', 0))
        return 0.0
