#!/usr/bin/env python3
"""
ALPHA INVESTMENT — BingX Momentum Bot
بوت تداول آلي — 42 عملة على BingX مع تحكم عبر تيليجرام
Trailing Stop +1% → Breakeven (حماية رأس المال)

Deploy on Render, Railway, or any Python host.
"""
import asyncio
import logging
import os
import time
from datetime import datetime, timezone
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from config import (
    TELEGRAM_TOKEN,
    TELEGRAM_CHAT_ID,
    COINS,
    STATE_FILE,
    BINGX_API_KEY,
    BINGX_SECRET_KEY,
    SCAN_HOUR,
    SCAN_MINUTE,
)
from state import load as load_state, save as save_state, reset as reset_state
from bingx_api import BingX
from scanner import Scanner

# === Setup ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
log = logging.getLogger(__name__)

state = load_state()
bingx = BingX(
    state.get('bingx_api_key') or BINGX_API_KEY or "",
    state.get('bingx_secret_key') or BINGX_SECRET_KEY or "",
    0.05
)


# ========== HEALTH CHECK SERVER ==========
class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()
        self.wfile.write(b'OK\n')
    def log_message(self, format, *args):
        pass

def run_health_server():
    port = int(os.environ.get('PORT', '10000'))
    server = HTTPServer(('0.0.0.0', port), HealthHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    log.info(f"🔌 Health server running on port {port}")


# ========== COMMAND HANDLERS ==========

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TELEGRAM_CHAT_ID: return
    msg = (
        "╔══════════════════════════════╗\n"
        "║   🤖 ALPHA INVESTMENT 🤖   ║\n"
        "╚══════════════════════════════╝\n\n"
        "صنع بواسطة Abozaid™\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "BingX 🟢 ONLINE\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🎯 استراتيجية: Momentum Continuation\n"
        "⚡ الشرط: Pump ≥ 5% ← شراء فوري\n"
        "🎯 TP: +2% | 🛑 SL: -1%\n"
        "🔄 Trailing SL: +1% → Breakeven 🛡️\n"
        "💰 المخاطرة: 100% All-In\n"
        f"📊 المراقبة: {len(COINS)} عملة (BingX)\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📌 الأوامر:\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "💰 /balance ← رصيد المحفظة\n"
        "📈 /status ← الرصيد والحالة\n"
        "💼 /position ← الصفقة الحالية\n"
        "📋 /trades ← آخر الصفقات\n"
        "📊 /stats ← الإحصائيات\n"
        "🔍 /scan ← فحص يدوي\n"
        "⏯ /toggle ← تشغيل/إيقاف\n"
        "🔄 /reset ← تصفير البيانات\n"
        "🔑 /set_bingx ← ربط API\n"
        "📖 /help ← المساعدة\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "™ ALPHA INVESTMENT v2.0 — BingX\n"
        "© Powered by Abozaid"
    )
    await update.message.reply_text(msg, parse_mode=None)


async def status_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TELEGRAM_CHAT_ID: return
    st = load_state()
    live_bal = bingx.get_balance('USDT') if bingx.api_key else 0
    bal = live_bal if live_bal > 0 else st.get('balance', 0)
    start_bal = st.get('start_balance') or bal
    total_pnl = bal - start_bal
    total_pnl_pct = (bal / start_bal - 1) * 100 if start_bal else 0
    pos = st.get('position')
    trades = st.get('trades', [])
    wins = sum(1 for t in trades if t.get('pnl', 0) > 0)
    peak = st.get('peak_balance', bal)
    dd = (peak - bal) / peak * 100 if peak else 0

    msg = (f"📊 الحالة\n{'─'*30}\n"
           f"💰 الرصيد: `${bal:.2f}`\n"
           f"📈 إجمالي الربح: `{total_pnl:+.2f}` ({total_pnl_pct:+.1f}%)\n"
           f"📉 Max DD: `{dd:.1f}%`\n"
           f"✅ صفقات: {len(trades)} | ربح: {wins}\n"
           f"🔴 البوت: {'🟢 شغال' if st.get('is_active', True) else '⏸ متوقف'}\n"
           f"\n💼 الصفقة الحالية: ")
    if pos:
        trail = '🛡️مفعل' if pos.get('trail_activated') else '⏳بانتظار'
        msg += f"{pos['symbol']} | دخول: ${pos['entry_price']:.6f} | TP: ${pos['tp']:.6f} | SL: ${pos['sl']:.6f} | Trailing: {trail}"
    else:
        msg += "_لا توجد_"
    await update.message.reply_text(msg, parse_mode=None)


async def balance_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TELEGRAM_CHAT_ID: return
    
    if not bingx.api_key:
        await update.message.reply_text("💳 **المحفظة**\n\n⚠️ لم يتم ربط BingX API بعد.\nاستخدم `/set_bingx` للمتابعة", parse_mode=None)
        return
    
    st = load_state()
    
    # جرب نجيب الرصيد مباشر من API — أكثر من طريقة
    live_bal = bingx.get_balance('USDT')
    if live_bal > 0:
        bal = live_bal
    else:
        # طريقة ثانية: raw response
        bal = st.get('balance', 0)
        if bal == 0:
            raw = bingx._get("/openApi/spot/v1/account/balance", signed=True)
            if isinstance(raw, (list, dict)) and 'error' not in str(raw):
                items = raw if isinstance(raw, list) else raw.get('balances', [])
                for b in items:
                    if b.get('asset') == 'USDT' or b.get('coin') == 'USDT':
                        bal = float(b.get('free', b.get('balance', 0)))
                        break

    start_bal = st.get('start_balance') or bal or 1
    total_pnl = bal - start_bal
    total_pnl_pct = (bal / start_bal - 1) * 100 if start_bal and start_bal > 0 else 0
    pos = st.get('position')
    pos_value = 0
    pos_sym = ''
    if pos:
        price = bingx.get_price(pos['symbol'])
        pos_value = price * pos['qty']
        pos_sym = pos['symbol']
    available = bal - pos_value
    
    msg = (
        f"💳 **المحفظة**\n{'─'*30}\n\n"
        f"💰 **USDT المتاح:** `${available:.2f}`\n"
        f"📦 **المستثمر:** `${pos_value:.2f}` {f'({pos_sym})' if pos_sym else ''}\n"
        f"💵 **الإجمالي:** `${bal:.2f}`\n"
        f"📈 **إجمالي الربح:** `{total_pnl:+.2f}` ({total_pnl_pct:+.1f}%)\n"
    )
    if pos:
        pct_invested = (pos_value / bal) * 100 if bal and bal > 0 else 0
        msg += f"📊 **التوزيع:** `{pct_invested:.0f}%` مستثمر | `{100-pct_invested:.0f}%` متاح"
    await update.message.reply_text(msg, parse_mode=None)


async def trades_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TELEGRAM_CHAT_ID: return
    st = load_state()
    trades = list(reversed(st.get('trades', [])))[:10]
    if not trades:
        await update.message.reply_text("📭 لا توجد صفقات بعد")
        return
    lines = []
    for t in trades:
        icon = '✅' if t.get('pnl', 0) > 0 else ('🔄' if t.get('result') == 'BE' else '❌')
        lines.append(
            f"{icon} {t['symbol']} | {t['date']}\n"
            f"   دخل: ${t.get('entry_price', 0):.6f} | خرج: ${t.get('exit_price', 0):.6f}\n"
            f"   PnL: `${t.get('pnl', 0):+.2f}` ({t.get('pnl_pct', 0):+.2f}%) | {t.get('result', '?')}"
        )
    await update.message.reply_text(f"📋 آخر {len(lines)} صفقة\n\n" + "\n\n".join(lines), parse_mode=None)


async def position_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TELEGRAM_CHAT_ID: return
    st = load_state()
    pos = st.get('position')
    if not pos:
        await update.message.reply_text("📭 لا توجد صفقة مفتوحة حالياً")
        return
    price = bingx.get_price(pos['symbol'])
    pnl = (price - pos['entry_price']) * pos['qty']
    pnl_pct = (price / pos['entry_price'] - 1) * 100
    trail = '🛡️✅ مفعل (SL=سعر الدخول)' if pos.get('trail_activated') else '⏳ بانتظار +1% للتفعيل'
    msg = (
        f"💼 الصفقة الحالية\n{'─'*30}\n"
        f"🔹 العملة: `{pos['symbol']}`\n"
        f"📌 الدخول: `${pos['entry_price']:.6f}`\n"
        f"💵 السعر الحالي: `${price:.6f}`\n"
        f"📦 الكمية: `{pos['qty']:.6f}`\n"
        f"💰 المستثمر: `${pos['usdt_invested']:.2f}`\n"
        f"📈 PnL: `{pnl:+.2f}` ({pnl_pct:+.2f}%)\n"
        f"🎯 TP: `${pos['tp']:.6f}` | 🛑 SL: `${pos['sl']:.6f}`\n"
        f"🔄 Trailing: {trail}\n"
        f"📅 الدخول: `{pos.get('date', '?')}`"
    )
    await update.message.reply_text(msg, parse_mode=None)


async def toggle_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TELEGRAM_CHAT_ID: return
    st = load_state()
    st['is_active'] = not st.get('is_active', True)
    save_state(st)
    status = '🟢 شغال' if st['is_active'] else '⏸ متوقف'
    await update.message.reply_text(f"البوت الآن: {status}", parse_mode=None)


async def scan_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TELEGRAM_CHAT_ID: return
    msg = await update.message.reply_text("🔍 جاري الفحص اليدوي...")

    signals_daily = []
    signals_4h = []
    api_errors = 0
    first_sym = True

    for sym in COINS:
        raw_d = bingx.get_klines(sym, '1d', 3)
        if isinstance(raw_d, dict) and 'error' in raw_d:
            api_errors += 1
            if first_sym:
                signals_daily.append(f"⚠️ ERR ({sym}): {str(raw_d.get('msg', raw_d))[:100]}")
                first_sym = False
        elif raw_d and isinstance(raw_d, list) and len(raw_d) >= 2:
            try:
                yesterday = raw_d[-2]
                open_p = float(yesterday[1])
                close_p = float(yesterday[4])
                pump = (close_p - open_p) / open_p * 100
                if pump >= 5:
                    entry = float(raw_d[-1][1])
                    current = bingx.get_price(sym)
                    perf = (current / entry - 1) * 100
                    signals_daily.append(f"💎 {sym} | {pump:+.1f}% (أمس) | الآن {perf:+.1f}% | دخول ${entry:.6f}")
            except Exception:
                pass

        raw_4 = bingx.get_klines(sym, '4h', 5)
        if raw_4 and isinstance(raw_4, list) and len(raw_4) >= 2:
            try:
                last = raw_4[-2]
                open_4 = float(last[1])
                close_4 = float(last[4])
                pump_4 = (close_4 - open_4) / open_4 * 100
                if pump_4 >= 5:
                    entry_4 = float(raw_4[-1][1])
                    current_4 = bingx.get_price(sym)
                    perf_4 = (current_4 / entry_4 - 1) * 100
                    signals_4h.append(f"⚡ {sym} | 4h {pump_4:+.1f}% | الآن {perf_4:+.1f}% | دخول ${entry_4:.6f}")
            except Exception:
                pass
        time.sleep(0.06)

    lines = []
    if api_errors:
        lines.append(f"⚠️ **{api_errors}/{len(COINS)} عملة فشل اتصال API!**")
    lines.append("📆 **الفحص اليومي (أمس):**")
    lines.extend(signals_daily[:8] if signals_daily else ["— لا توجد إشارات"])
    lines.append("")
    lines.append("⚡ **الفحص السريع (4 ساعات):**")
    lines.extend(signals_4h[:8] if signals_4h else ["— لا توجد إشارات"])
    await msg.edit_text("🔍 **نتائج الفحص:**\n\n" + "\n".join(lines), parse_mode=None)


async def reset_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TELEGRAM_CHAT_ID: return
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ نعم، امسح", callback_data="reset_confirm"),
        InlineKeyboardButton("❌ إلغاء", callback_data="reset_cancel"),
    ]])
    await update.message.reply_text("⚠️ مسح كل البيانات؟", reply_markup=keyboard, parse_mode=None)


async def button_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data == "reset_confirm":
        reset_state()
        await query.edit_message_text("✅ تم مسح جميع البيانات", parse_mode=None)
    elif query.data == "reset_cancel":
        await query.edit_message_text("❌ تم الإلغاء")


async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TELEGRAM_CHAT_ID: return
    msg = (
        "📖 **المساعدة — ALPHA INVESTMENT v2.0**\n"
        "═══════════════════════════════════\n\n"
        "💰 `/balance` ← رصيد المحفظة\n"
        "📈 `/status` ← الحالة العامة\n"
        "💼 `/position` ← الصفقة الحالية\n"
        "📋 `/trades` ← آخر الصفقات\n"
        "📊 `/stats` ← الإحصائيات\n"
        "🔍 `/scan` ← فحص الإشارات يدوياً\n"
        "⏯ `/toggle` ← تشغيل/إيقاف\n"
        "🔄 `/reset` ← تصفير البيانات\n"
        "🔐 `/set_bingx` ← ربط BingX API\n"
        "📖 `/help` ← هذه القائمة\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "🤖 صنع بواسطة **Abozaid**™\n"
        "© ALPHA INVESTMENT"
    )
    await update.message.reply_text(msg, parse_mode=None)


async def stats_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TELEGRAM_CHAT_ID: return
    st = load_state()
    trades = st.get('trades', [])
    if not trades:
        await update.message.reply_text("📭 لا توجد صفقات بعد")
        return
    wins = sum(1 for t in trades if t.get('pnl', 0) > 0)
    losses = sum(1 for t in trades if t.get('pnl', 0) <= 0)
    total_pnl = sum(t.get('pnl', 0) for t in trades)
    gp = sum(t['pnl'] for t in trades if t['pnl'] > 0)
    gl = abs(sum(t['pnl'] for t in trades if t['pnl'] < 0))
    pf = gp / max(gl, 0.001)
    lines = [f"📊 إحصائيات\n{'─'*30}"]
    lines.append(f"📊 صفقات: {len(trades)}")
    lines.append(f"✅ ربح: {wins} ({wins/len(trades)*100:.0f}%) | ❌ خسارة: {losses}")
    lines.append(f"💰 PnL: `{total_pnl:+.2f}` | 💹 PF: `{pf:.2f}`")
    await update.message.reply_text("\n".join(lines), parse_mode=None)


# ========== SCHEDULED SCAN ==========

async def scheduled_scan(ctx: ContextTypes.DEFAULT_TYPE):
    st = load_state()
    if not st.get('is_active', True):
        log.info("Scan skipped: bot inactive")
        return
    today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    if st.get('last_scan_date') == today:
        log.info(f"Scan skipped: already scanned {today}")
        return
    if st.get('position') is not None:
        log.info("Scan skipped: position already open")
        return
    if not bingx.api_key:
        log.error("Scan failed: API key not configured")
        return
    log.info(f"🔍 Scanning for signals...")
    scanner = Scanner(bingx, st)
    live_bal = bingx.get_balance('USDT')
    if live_bal < 1:
        log.warning(f"Balance too low: ${live_bal}")
        # فحص الإشارات أولاً (بدون شراء) عشان ننبش لو في فرصة ضايعة
        scanner = Scanner(bingx, st)
        signals = scanner.scan()
        if signals:
            signal = signals[0]
            await _notify(ctx, f"💰 تم العثور على إشارة!\n"
                               f"🔹 {signal['symbol']} | Pump: {signal['pump']:+.1f}%\n"
                               f"⚠️ لكن الرصيد `$0.00` — تعذر الشراء\n"
                               f"💵 ارسل USDT لحساب BingX عشان البوت يبدأ 🚀")
        else:
            log.info("No signals found (balance: $0)")
        return
    signals = scanner.scan()
    if not signals:
        st['last_scan_date'] = today
        save_state(st)
        log.info(f"No signals found for {today}")
        return

    # جرّب الإشارات بالترتيب (الأقوى أولاً) — لو فشلت وحدة، انتقل للي بعدها
    trade = None
    skipped_syms = []
    for signal in signals:
        log.info(f"Trying signal: {signal['symbol']} pump={signal['pump']}%")
        trade, error = scanner.execute_trade(signal, live_bal)

        if not error:
            break   # نجحت الصفقة — اطلع من اللوب

        # الرمز ممنوع من API (100421) → تخطّاه بصمت وجرّب التالي
        if error.startswith("__SKIP_100421__"):
            blocked_sym = error.replace("__SKIP_100421__", "")
            log.warning(f"Skipped API-blocked symbol: {blocked_sym} (100421)")
            skipped_syms.append(blocked_sym)
            trade = None
            continue

        # أي خطأ آخر → سجّله وجرّب التالي بدل ما توقف اليوم كله
        log.error(f"Trade failed on {signal['symbol']}: {error} — trying next")
        skipped_syms.append(signal['symbol'])
        trade = None
        continue

    # لو ما نجحت أي صفقة بعد تجربة كل الإشارات
    if trade is None:
        st['last_scan_date'] = today
        save_state(st)
        if skipped_syms:
            log.warning(f"All {len(skipped_syms)} signals failed/skipped today: {', '.join(skipped_syms)}")
        return
    st['balance'] = live_bal
    st['position'] = trade
    st['last_scan_date'] = today
    if st.get('start_balance') is None:
        st['start_balance'] = live_bal
    if live_bal > st.get('peak_balance', 0):
        st['peak_balance'] = live_bal
    save_state(st)
    # نسبة الاستثمار من الرصيد قبل الشراء (live_bal) — لا من الرصيد بعده (يكون قريب من صفر)
    pct_used = min((trade['usdt_invested'] / live_bal) * 100, 100) if live_bal else 100
    msg = (
        f"🚀 **صفقة جديدة!**\n{'─'*25}\n"
        f"🔹 **العملة:** `{trade['symbol']}`\n"
        f"📊 **Pump:** `{signal['pump']:+.1f}%`\n"
        f"📌 **الدخول:** `${trade['entry_price']:.6f}`\n"
        f"📦 **الكمية:** `{trade['qty']:.6f}` {trade['symbol'].split('/')[0]}\n"
        f"💰 **المستثمر:** `${trade['usdt_invested']:.2f}` ({pct_used:.0f}% من الرصيد)\n"
        f"🎯 **TP:** `${trade['tp']:.6f}` (+2%)\n"
        f"🛑 **SL أولي:** `${trade['entry_price']*0.99:.6f}` (-1%)\n"
        f"🔄 **Trailing:** +1% → Breakeven 🛡️\n\n"
        f"⏳ **مراقبة:** كل 5 دقائق"
    )
    await _notify(ctx, msg)
    log.info(f"Trade executed: {trade['symbol']} @ ${trade['entry_price']:.6f}")


async def check_positions(ctx: ContextTypes.DEFAULT_TYPE):
    st = load_state()
    if not st.get('is_active', True): return
    if not st.get('position'): return
    if not bingx.api_key: return

    scanner = Scanner(bingx, st)
    trade = st['position']
    sym = trade['symbol']
    oco_id = trade.get('oco_id')

    # ══════════════════════════════════════════════════
    # الحالة أ: عندنا OCO نشط على المنصة → استعلم عن حالته
    # ══════════════════════════════════════════════════
    if oco_id and trade.get('oco_active'):
        oco_status = bingx.query_oco(oco_id)

        # تحقق: هل تنفذ أي أمر (TP أو SL)؟
        # ⚠️ عدّل قراءة الحالة حسب شكل استجابة BingX الفعلي
        filled = False
        exit_reason = None
        exit_price = None

        if isinstance(oco_status, dict) and 'error' not in oco_status:
            orders = oco_status.get('orders', []) or oco_status.get('data', [])
            for o in orders:
                if str(o.get('status', '')).upper() == 'FILLED':
                    filled = True
                    exit_price = float(o.get('price') or o.get('avgPrice') or 0)
                    # لو سعر التنفيذ قريب من TP = ربح، غير كذا = وقف خسارة
                    exit_reason = 'TP' if exit_price >= trade['entry_price'] else 'SL'
                    break

        if filled:
            # الصفقة أُغلقت على المنصة — سجّلها وأبلغ المستخدم
            pnl_pct = (exit_price / trade['entry_price'] - 1) * 100
            buy_fee = trade['usdt_invested'] * 0.001
            sell_rev = exit_price * trade['qty'] * (1 - 0.001)
            pnl = sell_rev - trade['usdt_invested'] - buy_fee

            trade.update({
                'exit_price': exit_price,
                'pnl': round(pnl, 2),
                'pnl_pct': round(pnl_pct, 2),
                'result': exit_reason,
                'exit_time': datetime.now(timezone.utc).isoformat(),
                'status': 'CLOSED',
            })
            st.setdefault('trades', []).append(trade)
            st['position'] = None
            live_bal = bingx.get_balance('USDT')
            st['balance'] = live_bal
            if live_bal > st.get('peak_balance', 0):
                st['peak_balance'] = live_bal
            save_state(st)

            icon = '✅' if pnl > 0 else '❌'
            label = '🎯 جني أرباح (TP)' if exit_reason == 'TP' else '🛑 وقف خسارة (SL)'
            await _notify(ctx,
                f"{icon} **صفقة مقفلة — {label}**\n{'─'*25}\n"
                f"🔹 **العملة:** `{sym}`\n"
                f"📌 **الدخول:** `${trade['entry_price']:.6f}`\n"
                f"🔄 **الخروج:** `${exit_price:.6f}`\n"
                f"📊 **النتيجة:** `{pnl:+.2f} USDT` ({pnl_pct:+.2f}%)\n"
                f"💵 **الرصيد:** `${live_bal:.2f}`\n"
                f"🤖 نُفّذ تلقائياً على المنصة (OCO)"
            )
            log.info(f"OCO filled: {sym} {exit_reason} pnl={pnl:+.2f}")
            return

        # ── الترلينغ: هل السعر لمس +1%؟ ننقل الـ SL لنقطة الدخول ──
        if not trade.get('trail_activated'):
            current = bingx.get_price(sym)
            trail_trigger = trade['entry_price'] * 1.01
            if current >= trail_trigger:
                # 1) ألغِ الـ OCO القديم
                cancel_res = bingx.cancel_oco(sym, oco_id)
                if 'error' in cancel_res:
                    log.error(f"فشل إلغاء OCO للترلينغ: {cancel_res.get('msg')}")
                    return  # نجرب المرة الجاية

                # 2) حط OCO جديد: نفس الـ TP، بس الـ SL على نقطة الدخول (Breakeven)
                adjusted_qty = bingx.adjust_qty(sym, trade['qty'])
                new_tp = trade['entry_price'] * 1.02
                new_sl_trigger = trade['entry_price']            # Breakeven
                new_sl_limit = trade['entry_price'] * 0.998       # هامش تنفيذ بسيط

                new_oco = bingx.place_oco(sym, adjusted_qty, new_tp, new_sl_trigger, new_sl_limit)
                if 'error' in new_oco:
                    log.error(f"فشل حجز OCO الجديد للترلينغ: {new_oco.get('msg')}")
                    # حالة حرجة: لا OCO الآن — فعّل مراقبة يدوية طوارئ
                    trade['oco_active'] = False
                    trade['oco_id'] = None
                    st['position'] = trade
                    save_state(st)
                    return

                trade['oco_id'] = new_oco.get('orderListId') or new_oco.get('orderListID')
                trade['trail_activated'] = True
                trade['sl'] = new_sl_trigger
                trade['trail_time'] = datetime.now(timezone.utc).isoformat()
                st['position'] = trade
                save_state(st)

                await _notify(ctx,
                    f"🛡️ **Trailing Stop مفعّل!**\n{'─'*25}\n"
                    f"🔹 **العملة:** `{sym}`\n"
                    f"✅ السعر لمس +1% — وقف الخسارة تحرّك لسعر الدخول\n"
                    f"🛑 **SL الجديد:** `${new_sl_trigger:.6f}` (Breakeven)\n"
                    f"🎯 **TP:** `${new_tp:.6f}` (+2%)\n"
                    f"🔒 رأس المال محمي — إما ربح أو تعادل"
                )
                log.info(f"Trailing activated via OCO swap: {sym}")
        return

    # ══════════════════════════════════════════════════
    # الحالة ب: ما فيه OCO (فشل حجزه) → مراقبة يدوية (الكود القديم)
    # ══════════════════════════════════════════════════
    action = scanner.check_tp_sl(trade)

    if action == 'TRAIL':
        st['position'] = trade
        save_state(st)
        await _notify(ctx, f"🛡️ Trailing مفعّل (يدوي): {sym}")
        return

    if action == 'HOLD':
        return

    # إغلاق يدوي (TP/SL/BE)
    close_data, error = scanner.close_trade(trade, action)
    if error:
        log.error(f"Close failed: {error}")
        await _notify(ctx, f"⚠️ فشل إغلاق الصفقة\n{sym}: {error}")
        return

    trade.update(close_data)
    trade['status'] = 'CLOSED'
    st.setdefault('trades', []).append(trade)
    st['position'] = None
    live_bal = bingx.get_balance('USDT')
    st['balance'] = live_bal
    if live_bal > st.get('peak_balance', 0):
        st['peak_balance'] = live_bal
    save_state(st)

    icon = '🔄' if action == 'BE' else ('✅' if close_data['pnl'] > 0 else '❌')
    await _notify(ctx,
        f"{icon} **صفقة مقفلة (يدوي)**\n{'─'*25}\n"
        f"🔹 {sym} | خروج: `${close_data['exit_price']:.6f}`\n"
        f"📊 `{close_data['pnl']:+.2f} USDT` ({close_data['pnl_pct']:+.2f}%)\n"
        f"💵 الرصيد: `${live_bal:.2f}`"
    )
    log.info(f"Position closed (manual): {sym} pnl={close_data['pnl']:+.2f}")


async def _notify(ctx, msg):
    try:
        await ctx.bot.send_message(TELEGRAM_CHAT_ID, msg, parse_mode=None)
    except Exception as e:
        log.error(f"Notify failed: {e}")


async def config_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TELEGRAM_CHAT_ID: return
    await update.message.reply_text(
        "🔑 الإعدادات\n\n"
        "لتحديث مفاتيح BingX API:\n"
        "`/set_bingx API_KEY SECRET_KEY`\n\n"
        "لتحديث توكن التليجرام:\n"
        "`/set_telegram TOKEN`", parse_mode=None
    )


async def set_bingx(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TELEGRAM_CHAT_ID: return
    args = ctx.args
    if len(args) < 2:
        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("🔗 فتح BingX API", url="https://bingx.com/en-us/user/security/api"),
        ]])
        await update.message.reply_text(
            "🔐 **ربط BingX API**\n"
            "═══════════════════\n\n"
            "**📌 الخطوات:**\n"
            "1️⃣ افتح [BingX API](https://bingx.com/en-us/user/security/api)\n"
            "2️⃣ أنشئ API Key جديد **للـ Spot فقط**\n"
            "3️⃣ انسخ المفتاح والمفتاح السري\n"
            "4️⃣ أرسل: `/set_bingx API_KEY SECRET_KEY`\n\n"
            "⚠️ مثال:\n"
            "`/set_bingx abcdef123456 xyz789secret`",
            parse_mode=None, reply_markup=kb
        )
        return
    bingx.api_key = args[0]
    bingx.secret = args[1]
    
    # اختبار 1: هل Public API يشتغل (تأكيد اتصال)
    test_ticker = bingx.get_ticker('BTC/USDT')
    ticker_ok = isinstance(test_ticker, dict) and 'lastPrice' in test_ticker
    
    # اختبار 2: جيب الرصيد (يحتاج توقيع)
    bal = bingx.get_balance('USDT')
    
    # اختبار 3: إذا فشل، جرب نجيب الخطأ الحقيقي من API
    error_detail = ""
    if not ticker_ok:
        error_detail = "🌐 فشل الاتصال بـ BingX — تأكد من الإنترنت"
    elif isinstance(bal, float) and bal == 0.0:
        # جرب نشوف الـ raw response عشان نعرف السبب الحقيقي
        import json as _json
        raw = bingx._get("/openApi/spot/v1/account/balance", signed=True)
        if isinstance(raw, dict) and 'error' in raw:
            err_code = raw.get('error', '?')
            err_msg = raw.get('msg', '')[:100]
            if err_code == 100413:
                error_detail = f"❌ خطأ {err_code}: المفاتيح غير صالحة أو منتهية الصلاحية"
            elif err_code == 100419:
                error_detail = f"⚠️ API صحيح لكن الرصيد $0.00 — الحساب فاضي"
            elif err_code == 100435:
                error_detail = f"⚠️ المفتاح للقراءة فقط — ارجع لـ BingX واختار صلاحية تداول"
            else:
                error_detail = f"⚠️ خطأ {err_code}: {err_msg}"
        else:
            error_detail = f"💸 تم الاتصال لكن الرصيد $0.00 — الحساب فاضي أو API ما عنده صلاحية"
    
    # نتائج الاختبار
    if isinstance(bal, float) and bal > 0:
        st = load_state()
        st['bingx_api_key'] = args[0]
        st['bingx_secret_key'] = args[1]
        save_state(st)
        await update.message.reply_text(
            f"✅ **تم ربط BingX API بنجاح!**\n{'─'*25}\n"
            f"💰 الرصيد: `${bal:.2f}`\n"
            f"🔑 الحالة: 🟢 متصل\n\n"
            f"📌 استخدم `/balance` لعرض تفاصيل المحفظة", parse_mode=None
        )
    else:
        await update.message.reply_text(
            f"❌ **فشل ربط BingX API**\n{'─'*25}\n"
            f"{error_detail}\n\n"
            f"📌 **الحل:**\n"
            f"1️⃣ امسح API Key القديم: https://bingx.com/en/account/api\n"
            f"2️⃣ سو API **جديد** ✅\n"
            f"3️⃣ ⚠️ انسخ **API Key** و **Secret Key** فوراً قبل قفل الصفحة\n"
            f"4️⃣ أرسلهم لي وأنا أختبرهم", parse_mode=None
        )


# ========== TEST COMMAND ==========

async def test_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    """اختبار شامل لكل خطوات الصفقة الحقيقية — بدون تنفيذ شراء"""
    if update.effective_user.id != TELEGRAM_CHAT_ID: return

    msg = await update.message.reply_text("🔬 جاري الاختبار الشامل...", parse_mode=None)
    lines = ["🔬 نتائج الاختبار\n" + "─" * 30]

    # ── 1. اتصال عام (Public API) ──
    ticker = bingx.get_ticker('BTC/USDT')
    if isinstance(ticker, dict) and 'lastPrice' in ticker:
        btc = float(ticker['lastPrice'])
        lines.append(f"✅ 1. اتصال BingX: سعر BTC = ${btc:,.0f}")
    else:
        lines.append(f"❌ 1. اتصال BingX فشل: {str(ticker)[:80]}")
        await msg.edit_text("\n".join(lines), parse_mode=None)
        return

    # ── 2. توقيع GET — جلب الرصيد ──
    if not bingx.api_key:
        lines.append("⚠️ 2. لا يوجد API Key — استخدم /set_bingx أولاً")
        await msg.edit_text("\n".join(lines), parse_mode=None)
        return

    raw_bal = bingx._get("/openApi/spot/v1/account/balance", signed=True)
    if isinstance(raw_bal, dict) and 'error' in raw_bal:
        code = raw_bal.get('error')
        lines.append(f"❌ 2. توقيع GET فشل (كود {code}): {raw_bal.get('msg','')[:80]}")
        if code == 100001:
            lines.append("   ↳ مشكلة Signature — تأكد من Secret Key")
        elif code == 100413:
            lines.append("   ↳ API Key غير صالح أو منتهي الصلاحية")
        await msg.edit_text("\n".join(lines), parse_mode=None)
        return

    bal = bingx.get_balance('USDT')
    lines.append(f"✅ 2. توقيع GET: رصيد USDT = ${bal:.2f}")

    # ── 3. توقيع POST — محاولة أمر وهمي ($0.01) ──
    # BingX سترفضه بـ "أقل من الحد الأدنى" — لكن إذا وصل لهذا الخطأ
    # يعني التوقيع صح (كود 100001 = signature خطأ)
    test_order = bingx._post("/openApi/spot/v1/trade/order", {
        'symbol': 'BTC-USDT', 'side': 'BUY', 'type': 'MARKET',
        'quoteOrderQty': '0.01'
    })
    post_code = test_order.get('error') if isinstance(test_order, dict) else None

    if post_code == 100001:
        lines.append(f"❌ 3. توقيع POST فشل (Signature mismatch) — الإصلاح لم يطبّق بعد!")
        lines.append("   ↳ أعد نشر الكود على Render وانتظر دقيقة")
        await msg.edit_text("\n".join(lines), parse_mode=None)
        return
    elif post_code is not None:
        # أي كود آخر = التوقيع وصل لـ BingX وهي رفضته لسبب تجاري (مقبول)
        msg_text = test_order.get('msg', '')[:100]
        lines.append(f"✅ 3. توقيع POST: صحيح ✔ (BingX رفضت بكود {post_code}: {msg_text[:60]})")
        lines.append("   ↳ رفض تجاري طبيعي — التوقيع وصل سليم")
    else:
        lines.append("✅ 3. توقيع POST: تم القبول (غير متوقع — راجع الرصيد)")

    # ── 4. جلب الشمعات (نفس ما يستخدمه /scan) ──
    test_sym = COINS[0] if COINS else 'BTC/USDT'
    klines = bingx.get_klines(test_sym, '1d', 3)
    if isinstance(klines, list) and len(klines) >= 2:
        yesterday = klines[-2]
        try:
            pump = (float(yesterday[4]) - float(yesterday[1])) / float(yesterday[1]) * 100
            lines.append(f"✅ 4. الشمعات: {test_sym} أمس {pump:+.2f}%")
        except:
            lines.append(f"✅ 4. الشمعات: {test_sym} — {len(klines)} شمعة")
    else:
        lines.append(f"❌ 4. الشمعات فشل: {str(klines)[:80]}")

    # ── الخلاصة ──
    lines.append("\n" + "─" * 30)
    if all("✅" in l for l in lines if l.startswith(("✅", "❌"))):
        lines.append("🟢 كل شيء شغال — البوت جاهز للصفقة!")
    else:
        lines.append("🔴 في مشاكل — راجع السطور اللي عندها ❌")

    await msg.edit_text("\n".join(lines), parse_mode=None)


# ========== MAIN ==========
def main():
    run_health_server()
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("trades", trades_cmd))
    app.add_handler(CommandHandler("position", position_cmd))
    app.add_handler(CommandHandler("toggle", toggle_cmd))
    app.add_handler(CommandHandler("scan", scan_cmd))
    app.add_handler(CommandHandler("reset", reset_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("balance", balance_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("config", config_cmd))
    app.add_handler(CommandHandler("set_bingx", set_bingx))
    app.add_handler(CommandHandler("test", test_cmd))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.job_queue.run_daily(scheduled_scan, time=datetime.strptime(f"{SCAN_HOUR:02d}:{SCAN_MINUTE:02d}", "%H:%M").time())
    app.job_queue.run_repeating(check_positions, interval=300, first=30)
    log.info("🤖 BingX Bot started! Press Ctrl+C to stop")
    app.run_polling()

if __name__ == "__main__":
    main()
