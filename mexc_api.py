"""
MEXC API wrapper — Private & Public endpoints
"""
import hashlib
import hmac
import time
import requests
from urllib.parse import urlencode

MEXC_BASE = "https://api.mexc.com"

class MEXC:
    def __init__(self, api_key, secret_key, delay=0.05):
        self.api_key = api_key
        self.secret = secret_key
        self.delay = delay
        self._last_call = 0

    def _rate_limit(self):
        elapsed = time.time() - self._last_call
        if elapsed < self.delay:
            time.sleep(self.delay - elapsed)

    def _sign(self, params):
        query = urlencode(sorted(params.items()))
        return hmac.new(self.secret.encode(), query.encode(), hashlib.sha256).hexdigest()

    def _get(self, path, params=None, signed=False):
        self._rate_limit()
        url = f"{MEXC_BASE}{path}"
        headers = {'X-MEXC-APIKEY': self.api_key} if signed and self.api_key else {}
        if signed:
            params = params or {}
            params['timestamp'] = int(time.time() * 1000)
            params['signature'] = self._sign(params)
        try:
            r = requests.get(url, params=params, headers=headers, timeout=15)
            return r.json() if r.status_code == 200 else {'error': r.status_code, 'msg': r.text[:200]}
        except Exception as e:
            return {'error': -1, 'msg': str(e)}

    def _post(self, path, params=None):
        self._rate_limit()
        params = params or {}
        params['timestamp'] = int(time.time() * 1000)
        params['signature'] = self._sign(params)
        headers = {'X-MEXC-APIKEY': self.api_key}
        try:
            r = requests.post(f"{MEXC_BASE}{path}", params=params, headers=headers, timeout=15)
            return r.json() if r.status_code == 200 else {'error': r.status_code, 'msg': r.text[:200]}
        except Exception as e:
            return {'error': -1, 'msg': str(e)}

    def _delete(self, path, params=None):
        self._rate_limit()
        params = params or {}
        params['timestamp'] = int(time.time() * 1000)
        params['signature'] = self._sign(params)
        headers = {'X-MEXC-APIKEY': self.api_key}
        try:
            r = requests.delete(f"{MEXC_BASE}{path}", params=params, headers=headers, timeout=15)
            return r.json() if r.status_code == 200 else {'error': r.status_code, 'msg': r.text[:200]}
        except Exception as e:
            return {'error': -1, 'msg': str(e)}

    # ========= Public =========
    def get_klines(self, symbol, interval='1d', limit=500):
        s = symbol.replace('/', '')
        return self._get("/api/v3/klines", {'symbol': s, 'interval': interval, 'limit': limit})

    def get_ticker(self, symbol):
        s = symbol.replace('/', '')
        return self._get("/api/v3/ticker/24hr", {'symbol': s})

    def get_price(self, symbol):
        s = symbol.replace('/', '')
        r = self._get("/api/v3/ticker/price", {'symbol': s})
        return float(r.get('price', 0)) if isinstance(r, dict) and 'price' in r else 0

    # ========= Account =========
    def get_balance(self, asset='USDT'):
        r = self._get("/api/v3/account", signed=True)
        if 'error' in r: return 0.0
        for b in r.get('balances', []):
            if b['asset'] == asset:
                return float(b.get('free', 0))
        return 0.0

    def get_open_orders(self, symbol=None):
        params = {}
        if symbol: params['symbol'] = symbol.replace('/', '')
        return self._get("/api/v3/openOrders", params, signed=True)

    # ========= Trading =========
    def market_buy(self, symbol, quote_qty):
        s = symbol.replace('/', '')
        return self._post("/api/v3/order", {
            'symbol': s, 'side': 'BUY', 'type': 'MARKET',
            'quoteOrderQty': str(round(quote_qty, 5))
        })

    def market_sell(self, symbol, qty):
        s = symbol.replace('/', '')
        return self._post("/api/v3/order", {
            'symbol': s, 'side': 'SELL', 'type': 'MARKET',
            'quantity': str(round(qty, 8))
        })

    def limit_sell(self, symbol, qty, price):
        s = symbol.replace('/', '')
        return self._post("/api/v3/order", {
            'symbol': s, 'side': 'SELL', 'type': 'LIMIT_MAKER',
            'quantity': str(round(qty, 8)), 'price': str(round(price, 8))
        })

    def cancel_order(self, symbol, order_id):
        s = symbol.replace('/', '')
        return self._delete("/api/v3/order", {'symbol': s, 'orderId': order_id})

    def parse_klines(self, data):
        if not data or not isinstance(data, list):
            return []
        rows = []
        for row in data:
            rows.append({
                'ts': row[0], 'open': float(row[1]), 'high': float(row[2]),
                'low': float(row[3]), 'close': float(row[4]), 'vol': float(row[5]),
                'date_s': time.strftime('%Y-%m-%d', time.gmtime(row[0]/1000)),
                'date_dt': row[0]
            })
        return rows

    def get_precision(self, symbol):
        s = symbol.replace('/', '')
        r = self._get("/api/v3/exchangeInfo", {'symbol': s})
        if 'error' in r: return 4, 4
        try:
            sym = r['symbols'][0]
            return int(sym['baseAssetPrecision']), int(sym['quotePrecision'])
        except:
            return 4, 4

    def get_symbol_filters(self, symbol):
        s = symbol.replace('/', '')
        r = self._get("/api/v3/exchangeInfo", {'symbol': s})
        if 'error' in r: return None
        try:
            sym = r['symbols'][0]
            for f in sym.get('filters', []):
                if f['filterType'] in ('LOT_SIZE', 'MARKET_LOT_SIZE'):
                    return {
                        'minQty': float(f['minQty']),
                        'maxQty': float(f['maxQty']),
                        'stepSize': float(f['stepSize'])
                    }
        except:
            pass
        return None

    def adjust_qty(self, symbol, qty):
        filters = self.get_symbol_filters(symbol)
        if not filters: return qty
        step = filters['stepSize']
        prec = len(str(step).split('.')[-1]) if '.' in str(step) else 0
        adjusted = int(qty / step) * step
        return round(adjusted, prec)

    def check_symbol(self, symbol):
        s = symbol.replace('/', '')
        r = self._get("/api/v3/exchangeInfo", {'symbol': s})
        if 'error' in r: return False
        try:
            return r['symbols'][0]['status'] == '1'
        except:
            return False
