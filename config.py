"""
MEXC Momentum Bot — Configuration from environment variables
"""
import os

# === MEXC API (set via Telegram /set_mexc, or env vars) ===
MEXC_API_KEY = os.getenv('MEXC_API_KEY')
MEXC_SECRET_KEY = os.getenv('MEXC_SECRET_KEY')

# === Trading Params ===
MIN_PUMP = float(os.getenv('MIN_PUMP', '5.0'))          # Minimum pump % to trigger signal
TAKE_PROFIT = float(os.getenv('TAKE_PROFIT', '1.02'))    # +2%
STOP_LOSS = float(os.getenv('STOP_LOSS', '0.99'))        # -1%
RISK_PER_TRADE = float(os.getenv('RISK_PER_TRADE', '1.0'))  # 100% of balance
MAX_POSITIONS = int(os.getenv('MAX_POSITIONS', '1'))
FEE = float(os.getenv('FEE', '0.001'))                   # Binance spot fee (0.1%)

# === Coin Watchlist (from env, comma-separated, or default 42 coins) ===
DEFAULT_COINS = [
    'ALICE/USDT', 'CELR/USDT', 'CKB/USDT', 'COTI/USDT', 'DUSK/USDT',
    'IOST/USDT', 'IOTX/USDT', 'LRC/USDT', 'NKN/USDT', 'ONT/USDT',
    'RSR/USDT', 'RVN/USDT', 'SLP/USDT', 'STORJ/USDT', 'UMA/USDT',
    'WOO/USDT', 'YGG/USDT', 'ZIL/USDT', 'ZRX/USDT', 'ANKR/USDT',
    'ARPA/USDT', 'BAT/USDT', 'ENJ/USDT', 'FET/USDT', 'GALA/USDT',
    'FLOW/USDT', 'HIVE/USDT', 'KAVA/USDT', 'KSM/USDT', 'LPT/USDT',
    'MANA/USDT', 'FARM/USDT', 'BEL/USDT', 'RLC/USDT', 'MAGIC/USDT',
    'RARE/USDT', 'GRT/USDT', 'GTC/USDT', 'XNO/USDT', 'SXP/USDT',
    'TRU/USDT', 'PENDLE/USDT', 'PEOPLE/USDT', 'STX/USDT'
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
