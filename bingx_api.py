"""
BingX API wrapper — Spot trading
صنع خصيصاً لبوت ALPHA INVESTMENT — 42 عملة
"""
import hashlib
import hmac
import time
import requests
from urllib.parse import urlencode

BINGX_BASE = "https://open-api.bingx.com"

class BingX:
    def __init__(self, api_key, secret_key, delay=0.05):
        self.api_key = api_key
        self.secret = secret_key
        self.delay = delay
        self._last_call = 0

    def _rate_limit(self):
        elapsed = time.time() - self._last_call
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

    def _sign(self, query_string):
        """توقيع HMAC-SHA256 على query string جاهز (مرتّب مسبقاً)"""
        return hmac.new(
            self.secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256
        ).hexdigest()

    def _fmt(self, symbol):
        """Convert X/USDT -> X-USDT for BingX"""
        return symbol.replace('/', '-')

    def _get(self, path, params=None, signed=False):
        self._rate_limit()
        self._last_call = time.time()
        headers = {}
        if signed and self.api_key:
            headers['X-BX-APIKEY'] = self.api_key
            params = params or {}
            params['timestamp'] = int(time.time() * 1000)
            # بناء query string مرتّب أبجدياً → يُوقَّع ويُرسَل بنفس الترتيب
            query = urlencode(sorted(params.items()))
            sig = self._sign(query)
            url = f"{BINGX_BASE}{path}?{query}&signature={sig}"
            params = None  # موجودة في URL مباشرة
        else:
            url = f"{BINGX_BASE}{path}"
        try:
            r = requests.get(url, params=params, headers=headers, timeout=15)
            data = r.json()
            if data.get('code') == 0:
                return data.get('data') or data
            return {'error': data.get('code', r.status_code), 'msg': str(data)[:200]}
        except Exception as e:
            return {'error': -1, 'msg': str(e)}

    def _post(self, path, params=None):
        self._rate_limit()
        self._last_call = time.time()
        params = params or {}
        params['timestamp'] = int(time.time() * 1000)
        params['recvWindow'] = 10000  # 10 ثواني — يحل فرق التوقيت
        # بناء query string مرتّب أبجدياً → يُوقَّع ويُرسَل بنفس الترتيب
        query = urlencode(sorted(params.items()))
        sig = self._sign(query)
        url = f"{BINGX_BASE}{path}?{query}&signature={sig}"
        headers = {'X-BX-APIKEY': self.api_key}
        try:
            r = requests.post(url, headers=headers, timeout=15)
            data = r.json()
            if data.get('code') == 0:
                return data.get('data') or data
            return {'error': data.get('code', r.status_code), 'msg': str(data)[:300]}
        except Exception as e:
            return {'error': -1, 'msg': str(e)}

    def _delete(self, path, params=None):
        self._rate_limit()
        self._last_call = time.time()
        params = params or {}
        params['timestamp'] = int(time.time() * 1000)
        params['recvWindow'] = 10000
        query = urlencode(sorted(params.items()))
        sig = self._sign(query)
        url = f"{BINGX_BASE}{path}?{query}&signature={sig}"
        headers = {'X-BX-APIKEY': self.api_key}
        try:
            r = requests.delete(url, headers=headers, timeout=15)
            data = r.json()
            if data.get('code') == 0:
                return data.get('data') or data
            return {'error': data.get('code', r.status_code), 'msg': str(data)[:200]}
        except Exception as e:
            return {'error': -1, 'msg': str(e)}

    # ========= Public =========
    def get_klines(self, symbol, interval='1d', limit=500):
        s = self._fmt(symbol)
        r = self._get("/openApi/spot/v1/market/kline", {
            'symbol': s, 'interval': interval, 'limit': limit
        })
        # BingX returns data as array of arrays [ts,o,h,l,c,vol,...]
        if isinstance(r, list):
            return r
        if isinstance(r, dict) and 'data' in r:
            return r['data']
        return r  # error dict

    def get_ticker(self, symbol):
        s = self._fmt(symbol)
        r = self._get("/openApi/spot/v1/ticker/24hr", {'symbol': s})
        if isinstance(r, list) and len(r) > 0:
            return r[0]
        if isinstance(r, dict) and 'error' not in r:
            return r
        return {'error': -1, 'msg': str(r)}

    def get_price(self, symbol):
        """Get current price using ticker 24hr endpoint"""
        t = self.get_ticker(symbol)
        if 'error' in t:
            return 0.0
        return float(t.get('lastPrice', 0))

    # ========= Account =========
    def get_balance(self, asset='USDT'):
        r = self._get("/openApi/spot/v1/account/balance", signed=True)
        if 'error' in r:
            return 0.0
        balances = r if isinstance(r, list) else r.get('balances', [])
        for b in balances:
            if b.get('asset') == asset or b.get('coin') == asset:
                return float(b.get('free', b.get('balance', 0)))
        return 0.0

    def get_open_orders(self, symbol=None):
        params = {}
        if symbol: params['symbol'] = self._fmt(symbol)
        return self._get("/openApi/spot/v1/trade/openOrders", params, signed=True)

    # ========= Trading =========
    def market_buy(self, symbol, quote_qty):
        s = self._fmt(symbol)
        return self._post("/openApi/spot/v1/trade/order", {
            'symbol': s, 'side': 'BUY', 'type': 'MARKET',
            'quoteOrderQty': str(round(quote_qty, 5))
        })

    def market_sell(self, symbol, qty):
        s = self._fmt(symbol)
        return self._post("/openApi/spot/v1/trade/order", {
            'symbol': s, 'side': 'SELL', 'type': 'MARKET',
            'quantity': str(qty)
        })

    def cancel_order(self, symbol, order_id):
        s = self._fmt(symbol)
        return self._delete("/openApi/spot/v1/trade/order", {'symbol': s, 'orderId': order_id})

    def parse_klines(self, data):
        """Parse raw klines array of arrays into list of dicts"""
        if not data or not isinstance(data, list):
            return []
        rows = []
        for row in data:
            if not isinstance(row, (list, tuple)) or len(row) < 6:
                continue
            rows.append({
                'ts': row[0], 'open': float(row[1]), 'high': float(row[2]),
                'low': float(row[3]), 'close': float(row[4]), 'vol': float(row[5]),
                'date_s': time.strftime('%Y-%m-%d', time.gmtime(row[0]/1000)),
                'date_dt': row[0]
            })
        return rows

    def get_symbol_filters(self, symbol):
        """Get LOT_SIZE filter (stepSize) for quantity rounding"""
        s = self._fmt(symbol)
        r = requests.get(f"{BINGX_BASE}/openApi/spot/v1/common/symbols", timeout=10)
        if r.status_code != 200: return None
        data = r.json()
        for sym in data.get('data', {}).get('symbols', []):
            if sym['symbol'] == s:
                return {
                    'minQty': float(sym['minQty']),
                    'maxQty': float(sym['maxQty']),
                    'stepSize': float(sym['stepSize']),
                    'tickSize': float(sym['tickSize'])
                }
        return None

    def get_api_tradeable_symbols(self):
        """
        Returns a set of symbols (X/USDT format) where both apiStateBuy and
        apiStateSell are enabled (=1).  Used to skip restricted symbols before
        placing orders — avoids error 100421.
        """
        try:
            r = requests.get(
                f"{BINGX_BASE}/openApi/spot/v1/common/symbols", timeout=15
            )
            if r.status_code != 200:
                return None   # None → caller will skip the filter
            data = r.json()
            tradeable = set()
            for sym in data.get('data', {}).get('symbols', []):
                # apiStateBuy / apiStateSell: 1 = allowed, 0 = blocked
                if (int(sym.get('apiStateBuy', 0)) == 1 and
                        int(sym.get('apiStateSell', 0)) == 1):
                    # Convert BingX format  X-USDT  →  X/USDT
                    tradeable.add(sym['symbol'].replace('-', '/'))
            return tradeable
        except Exception:
            return None   # on any error → skip the filter (safe fallback)

    def adjust_qty(self, symbol, qty):
        """Round quantity to exchange precision"""
        filters = self.get_symbol_filters(symbol)
        if not filters: return qty
        step = filters['stepSize']
        prec = len(str(step).split('.')[-1]) if '.' in str(step) else 0
        adjusted = int(qty / step) * step
        return round(adjusted, prec)

    def check_symbol(self, symbol):
        """Verify symbol exists on BingX"""
        s = self._fmt(symbol)
        r = requests.get(f"{BINGX_BASE}/openApi/spot/v1/ticker/price", params={'symbol': s}, timeout=10)
        return r.status_code == 200 and r.json().get('code') == 0

    def _get_asset_balance(self, asset):
        """Get balance of a specific asset"""
        r = self._get("/openApi/spot/v1/account/balance", signed=True)
        if 'error' in r: return 0.0
        balances = r if isinstance(r, list) else r.get('balances', [])
        for b in balances:
            if b.get('asset') == asset or b.get('coin') == asset:
                return float(b.get('free', b.get('balance', 0)))
        return 0.0
