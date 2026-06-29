"""
BingX Momentum Bot — Configuration from environment variables
"""
import os

# === BingX API (set via Telegram /set_bingx, or env vars) ===
BINGX_API_KEY = os.getenv('BINGX_API_KEY')
BINGX_SECRET_KEY = os.getenv('BINGX_SECRET_KEY')

# === Trading Params ===
MIN_PUMP = float(os.getenv('MIN_PUMP', '5.0'))          # Minimum pump % to trigger signal
TAKE_PROFIT = float(os.getenv('TAKE_PROFIT', '1.02'))    # +2%
STOP_LOSS = float(os.getenv('STOP_LOSS', '0.99'))        # -1%
RISK_PER_TRADE = float(os.getenv('RISK_PER_TRADE', '1.0'))  # 100% of balance
MAX_POSITIONS = int(os.getenv('MAX_POSITIONS', '1'))
FEE = float(os.getenv('FEE', '0.001'))                   # BingX spot fee (0.1%)

# === Coin Watchlist (from env, comma-separated, or default 42 BingX coins) ===
DEFAULT_COINS = [
    # — العملات الأساسية (من MEXC الأصلية، شغالة على BingX) —
    'ADA/USDT', 'ASTER/USDT', 'BEAT/USDT', 'BEL/USDT', 'BNB/USDT',
    'CHECK/USDT', 'CLO/USDT', 'DN/USDT', 'DOGE/USDT', 'DOT/USDT',
    'EIGEN/USDT', 'ETH/USDT', 'ETHFI/USDT', 'FIL/USDT', 'HYPE/USDT',
    'INJ/USDT', 'IO/USDT', 'LAB/USDT', 'LTC/USDT', 'MBG/USDT',
    'NEAR/USDT', 'SOL/USDT', 'SUI/USDT', 'TAO/USDT', 'TNSR/USDT',
    'TRX/USDT', 'VELVET/USDT', 'W/USDT', 'XPL/USDT', 'XRP/USDT',
    # — بدائل BingX (من الـ 44 الأصلية للباك تيست) —
    'GALA/USDT', 'FET/USDT', 'SAND/USDT', 'CHZ/USDT', 'GRT/USDT',
    'STORJ/USDT', 'ALICE/USDT', 'ANKR/USDT', 'BAT/USDT', 'ZIL/USDT',
    'WOO/USDT', 'MANA/USDT'
]

_coins_env = os.getenv('COINS')
if _coins_env:
    COINS = [c.strip() for c in _coins_env.split(',') if c.strip()]
else:
    COINS = DEFAULT_COINS

# === Telegram (REQUIRED: set TELEGRAM_TOKEN and TELEGRAM_CHAT_ID in env) ===
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN environment variable is required!")

TELEGRAM_CHAT_ID = int(os.getenv('TELEGRAM_CHAT_ID', '0'))
if not TELEGRAM_CHAT_ID:
    raise ValueError("TELEGRAM_CHAT_ID environment variable is required!")

# === Scanner Schedule ===
SCAN_HOUR = int(os.getenv('SCAN_HOUR', '0'))       # 00:00 UTC
SCAN_MINUTE = int(os.getenv('SCAN_MINUTE', '5'))   # :05

# === API Limits ===
REQUESTS_DELAY = float(os.getenv('REQUESTS_DELAY', '0.05'))

# === State file path ===
STATE_DIR = os.getenv('STATE_DIR', os.path.dirname(os.path.abspath(__file__)))
STATE_FILE = os.path.join(STATE_DIR, 'state.json')
