#!/usr/bin/env python3
"""
MEXC Momentum Bot — Telegram Interface
Automated trading bot for MEXC exchange with Telegram control.

Deploy on Render, Railway, or any Python host.
"""
import asyncio
import logging
import time
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes

from config import (
    TELEGRAM_TOKEN,
    TELEGRAM_CHAT_ID,
    COINS,
    STATE_FILE,
    MEXC_API_KEY,
    MEXC_SECRET_KEY,
    SCAN_HOUR,
    SCAN_MINUTE,
)
from state import load as load_state, save as save_state, reset as reset_state
from mexc_api import MEXC
from scanner import Scanner

# === Setup ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
log = logging.getLogger(__name__)

state = load_state()
mexc = MEXC(
    state.get('mexc_api_key') or MEXC_API_KEY or "",
    state.get('mexc_secret_key') or MEXC_SECRET_KEY or "",
    0.05
)


# ========== COMMAND HANDLERS ==========

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TELEGRAM_CHAT_ID:
        return

    msg = (
        "╔══════════════════════════════╗\n"
        "║   🤖 ALPHA INVESTMENT 🤖   ║\n"
        "╚══════════════════════════════╝\n\n"
        "صنع بواسطة Abozaid™\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "BOT STATUS 🟢 ONLINE\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "🎯 استراتيجية: Momentum Continuation\n"
        "⚡ الشرط: Pump ≥ 5% ← شراء فوري\n"
        "🎯 TP: +2% | 🛑 SL: -1%\n"
        "💰 المخاطرة: 100% All-In\n"
        f"📊 المراقبة: {len(COINS)} عملة\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "📌 الأوامر:\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n\n"
        "📈 /status ← الرصيد والحالة\n"
        "💼 /position ← الصفقة الحالية\n"
        "📋 /trades ← آخر الصفقات\n"
        "📊 /stats ← الإحصائيات\n"
        "🔍 /scan ← فحص يدوي\n"
        "⏯ /toggle ← تشغيل/إيقاف\n"
        "🔄 /reset ← تصفير البيانات\n"
        "🔑 /set_mexc ← ربط API\n\n"
        "━━━━━━━━━━━━━━━━━━━━━━\n"
        "™ ALPHA INVESTMENT v1.0\n"
        "© Powered by Abozaid"
    )
    await update.message.reply_text(msg, parse_mode=None)


async def status_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TELEGRAM_CHAT_ID:
        return
    st = load_state()

    live_bal = mexc.get_balance('USDT') if mexc.api_key else 0
    bal = live_bal if live_bal > 0 else st.get('balance', 0)
    start_bal = st.get('start_balance') or bal
    total_pnl = bal - start_bal
    total_pnl_pct = (bal / start_bal - 1) * 100 if start_bal else 0

    pos = st.get('position')
    trades = st.get('trades', [])
    wins = sum(1 for t in trades if t.get('pnl', 0) > 0)
    peak = st.get('peak_balance', bal)
    dd = (peak - bal) / peak * 100 if peak else 0

    msg = (
        f"📊 الحالة\n"
        f"{'─'*30}\n"
        f"💰 الرصيد: `${bal:.2f}`\n"
        f"📈 إجمالي الربح: `{total_pnl:+.2f}` ({total_pnl_pct:+.1f}%)\n"
        f"📉 Max DD: `{dd:.1f}%`\n"
        f"✅ صفقات كلها: {len(trades)} | ربح: {wins}\n"
        f"🔴 البوت: {'🟢 شغال' if st.get('is_active', True) else '⏸ متوقف'}\n"
        f"\n💼 الصفقة الحالية: "
    )

    if pos:
        pnl = (bal - st.get('balance', 0) + (pos.get('usdt_invested', 0)))
        msg += (
            f"{pos['symbol']} | دخول: ${pos['entry_price']:.6f} "
            f"| TP: ${pos['tp']:.6f} | SL: ${pos['sl']:.6f}"
        )
    else:
        msg += "_لا توجد_"

    await update.message.reply_text(msg, parse_mode=None)


async def trades_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TELEGRAM_CHAT_ID:
        return
    st = load_state()
    trades = list(reversed(st.get('trades', [])))[:10]

    if not trades:
        await update.message.reply_text("📭 لا توجد صفقات بعد")
        return

    lines = []
    for t in trades:
        icon = '✅' if t.get('pnl', 0) > 0 else '❌'
        lines.append(
            f"{icon} {t['symbol']} | {t['date']}\n"
            f"   دخل: ${t.get('entry_price', 0):.6f} | خرج: ${t.get('exit_price', 0):.6f}\n"
            f"   PnL: `${t.get('pnl', 0):+.2f}` ({t.get('pnl_pct', 0):+.2f}%) | {t.get('result', '?')}"
        )

    await update.message.reply_text(
        f"📋 آخر {len(lines)} صفقة\n\n" + "\n\n".join(lines),
        parse_mode=None
    )


async def position_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TELEGRAM_CHAT_ID:
        return
    st = load_state()
    pos = st.get('position')

    if not pos:
        await update.message.reply_text("📭 لا توجد صفقة مفتوحة حالياً")
        return

    price = mexc.get_price(pos['symbol'])
    pnl = (price - pos['entry_price']) * pos['qty']
    pnl_pct = (price / pos['entry_price'] - 1) * 100

    msg = (
        f"💼 الصفقة الحالية\n"
        f"{'─'*30}\n"
        f"🔹 العملة: `{pos['symbol']}`\n"
        f"📌 الدخول: `${pos['entry_price']:.6f}`\n"
        f"💵 السعر الحالي: `${price:.6f}`\n"
        f"📦 الكمية: `{pos['qty']:.6f}`\n"
        f"💰 المستثمر: `${pos['usdt_invested']:.2f}`\n"
        f"📈 PnL: `{pnl:+.2f}` ({pnl_pct:+.2f}%)\n"
        f"🎯 TP: `${pos['tp']:.6f}` | SL: `${pos['sl']:.6f}`\n"
        f"📅 الدخول: `{pos.get('date', '?')}`"
    )

    await update.message.reply_text(msg, parse_mode=None)


async def toggle_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TELEGRAM_CHAT_ID:
        return
    st = load_state()
    st['is_active'] = not st.get('is_active', True)
    save_state(st)
    status = '🟢 شغال' if st['is_active'] else '⏸ متوقف'
    await update.message.reply_text(f"البوت الآن: {status}", parse_mode=None)


async def scan_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TELEGRAM_CHAT_ID:
        return
    msg = await update.message.reply_text("🔍 جاري الفحص اليدوي...")

    signals_daily = []
    signals_4h = []

    for sym in COINS:
        # Daily scan
        raw_d = mexc.get_klines(sym, '1d', 3)
        if raw_d and isinstance(raw_d, list) and len(raw_d) >= 2:
            try:
                yesterday = raw_d[-2]
                open_p = float(yesterday[1])
                close_p = float(yesterday[4])
                pump = (close_p - open_p) / open_p * 100
                if pump >= 5:
                    entry = float(raw_d[-1][1])
                    current = mexc.get_price(sym)
                    perf = (current / entry - 1) * 100
                    signals_daily.append(
                        f"💎 {sym} | {pump:+.1f}% (أمس) | الآن {perf:+.1f}% | دخول ${entry:.6f}"
                    )
            except Exception:
                pass

        # 4h scan
        raw_4 = mexc.get_klines(sym, '4h', 5)
        if raw_4 and isinstance(raw_4, list) and len(raw_4) >= 2:
            try:
                last = raw_4[-2]
                open_4 = float(last[1])
                close_4 = float(last[4])
                pump_4 = (close_4 - open_4) / open_4 * 100
                if pump_4 >= 5:
                    entry_4 = float(raw_4[-1][1])
                    current_4 = mexc.get_price(sym)
                    perf_4 = (current_4 / entry_4 - 1) * 100
                    signals_4h.append(
                        f"⚡ {sym} | 4h {pump_4:+.1f}% | الآن {perf_4:+.1f}% | دخول ${entry_4:.6f}"
                    )
            except Exception:
                pass

        time.sleep(0.06)

    lines = []
    lines.append("📆 **الفحص اليومي (أمس):**")
    lines.extend(signals_daily[:8] if signals_daily else ["— لا توجد إشارات"])
    lines.append("")
    lines.append("⚡ **الفحص السريع (4 ساعات):**")
    lines.extend(signals_4h[:8] if signals_4h else ["— لا توجد إشارات"])

    await msg.edit_text(
        "🔍 **نتائج الفحص:**\n\n" + "\n".join(lines),
        parse_mode=None
    )


async def reset_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TELEGRAM_CHAT_ID:
        return
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("✅ نعم، امسح", callback_data="reset_confirm"),
        InlineKeyboardButton("❌ إلغاء", callback_data="reset_cancel"),
    ]])
    await update.message.reply_text(
        "⚠️ مسح كل البيانات؟ سيتم حذف جميع الصفقات والحالة.",
        reply_markup=keyboard,
        parse_mode=None
    )


async def stats_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TELEGRAM_CHAT_ID:
        return
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

    monthly = {}
    for t in trades:
        m = t.get('date', '?')[:7]
        if m not in monthly:
            monthly[m] = {'n': 0, 'pnl': 0, 'w': 0}
        monthly[m]['n'] += 1
        monthly[m]['pnl'] += t.get('pnl', 0)
        if t.get('pnl', 0) > 0:
            monthly[m]['w'] += 1

    lines = [f"📊 إحصائيات عامة\n{'─'*30}"]
    lines.append(f"📅 الفترة: {trades[0].get('date','?')} → {trades[-1].get('date','?')}")
    lines.append(f"📊 إجمالي الصفقات: {len(trades)}")
    lines.append(f"✅ ربح: {wins} ({wins/len(trades)*100:.0f}%) | ❌ خسارة: {losses}")
    lines.append(f"💰 إجمالي PnL: `{total_pnl:+.2f}`")
    lines.append(f"💹 PF: `{pf:.2f}`")
    lines.append(f"\n📆 شهرياً:")
    for m in sorted(monthly.keys()):
        d = monthly[m]
        lines.append(
            f"  {m}: {d['n']} صفقات | {d['w']/max(d['n'],1)*100:.0f}% | PnL: `{d['pnl']:+.2f}`"
        )

    await update.message.reply_text("\n".join(lines), parse_mode=None)


# ========== CALLBACK ==========

async def button_callback(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "reset_confirm":
        reset_state()
        await query.edit_message_text("✅ تم مسح جميع البيانات", parse_mode=None)
    elif query.data == "reset_cancel":
        await query.edit_message_text("❌ تم الإلغاء")


# ========== SCHEDULED SCAN ==========

async def scheduled_scan(ctx: ContextTypes.DEFAULT_TYPE):
    """Daily scan — runs at configured time"""
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

    if not mexc.api_key:
        log.error("Scan failed: API key not configured")
        return

    log.info(f"🔍 Scanning for signals...")
    scanner = Scanner(mexc, st)

    live_bal = mexc.get_balance('USDT')
    if live_bal < 1:
        log.warning(f"Balance too low: ${live_bal}")
        return

    signal = scanner.scan()
    if not signal:
        st['last_scan_date'] = today
        save_state(st)
        log.info(f"No signals found for {today}")
        return

    log.info(f"Signal detected: {signal['symbol']} pump={signal['pump']}%")

    trade, error = scanner.execute_trade(signal, live_bal)
    if error:
        log.error(f"Trade failed: {error}")
        await _notify(ctx, f"❌ فشل التداول\n{signal['symbol']}: {error}")
        return

    st['balance'] = live_bal
    st['position'] = trade
    st['last_scan_date'] = today
    if st.get('start_balance') is None:
        st['start_balance'] = live_bal
    if live_bal > st.get('peak_balance', 0):
        st['peak_balance'] = live_bal
    save_state(st)

    msg = (
        f"🚀 صفقة جديدة!\n"
        f"{'─'*25}\n"
        f"🔹 العملة: `{trade['symbol']}`\n"
        f"📊 Pump: `{signal['pump']:+.1f}%`\n"
        f"📌 الدخول: `${trade['entry_price']:.6f}`\n"
        f"💰 المستثمر: `${trade['usdt_invested']:.2f}`\n"
        f"🎯 TP: `${trade['tp']:.6f}`\n"
        f"🛑 SL: `${trade['sl']:.6f}`"
    )
    await _notify(ctx, msg)
    log.info(f"Trade executed: {trade['symbol']} @ ${trade['entry_price']:.6f}")


async def check_positions(ctx: ContextTypes.DEFAULT_TYPE):
    """Check open positions for TP/SL every 5 minutes"""
    st = load_state()
    if not st.get('is_active', True):
        return
    if not st.get('position'):
        return
    if not mexc.api_key:
        return

    scanner = Scanner(mexc, st)
    trade = st['position']
    action = scanner.check_tp_sl(trade)

    if action == 'HOLD':
        return

    log.info(f"Closing position: {trade['symbol']} -> {action}")
    close_data, error = scanner.close_trade(trade, action)
    if error:
        log.error(f"Close failed: {error}")
        return

    trade.update(close_data)
    trade['status'] = 'CLOSED'

    st.setdefault('trades', []).append(trade)
    st['position'] = None

    live_bal = mexc.get_balance('USDT')
    st['balance'] = live_bal
    if live_bal > st.get('peak_balance', 0):
        st['peak_balance'] = live_bal
    save_state(st)

    if action == 'BE':
        icon = '🔄'  # Breakeven — neutral
    else:
        icon = '✅' if close_data['pnl'] > 0 else '❌'

    msg = (
        f"{icon} صفقة مقفلة\n"
        f"{'─'*25}\n"
        f"🔹 {trade['symbol']} → {action}\n"
        f"📌 الدخول: `${trade['entry_price']:.6f}`\n"
        f"🔄 الخروج: `${close_data['exit_price']:.6f}`\n"
        f"📊 PnL: `{close_data['pnl']:+.2f}` ({close_data['pnl_pct']:+.2f}%)\n"
        f"💰 الرصيد: `${live_bal:.2f}`"
    )
    await _notify(ctx, msg)
    log.info(f"Position closed: {trade['symbol']} pnl={close_data['pnl']:+.2f}")


async def _notify(ctx, msg):
    """Send message to the user"""
    try:
        await ctx.bot.send_message(TELEGRAM_CHAT_ID, msg, parse_mode=None)
    except Exception as e:
        log.error(f"Notify failed: {e}")


# ========== SETUP / CONFIG ==========

async def config_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TELEGRAM_CHAT_ID:
        return
    await update.message.reply_text(
        "🔑 الإعدادات\n\n"
        "لتحديث مفاتيح API:\n"
        "`/set_mexc API_KEY SECRET_KEY`\n\n"
        "لتحديث توكن التليجرام:\n"
        "`/set_telegram TOKEN`",
        parse_mode=None
    )


async def set_mexc(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != TELEGRAM_CHAT_ID:
        return
    args = ctx.args
    if len(args) < 2:
        await update.message.reply_text(
            "⚠️ الأمر: `/set_mexc API_KEY SECRET`",
            parse_mode=None
        )
        return

    mexc.api_key = args[0]
    mexc.secret = args[1]

    bal = mexc.get_balance('USDT')
    if isinstance(bal, float) and bal >= 0:
        st = load_state()
        st['mexc_api_key'] = args[0]
        st['mexc_secret_key'] = args[1]
        save_state(st)
        await update.message.reply_text(
            f"✅ تم ربط API! الرصيد: `${bal:.2f}`",
            parse_mode=None
        )
    else:
        await update.message.reply_text(
            "⚠️ المفاتيح تبدو غير صالحة، تأكد منها"
        )


# ========== MAIN ==========

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()

    # Commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("trades", trades_cmd))
    app.add_handler(CommandHandler("position", position_cmd))
    app.add_handler(CommandHandler("toggle", toggle_cmd))
    app.add_handler(CommandHandler("scan", scan_cmd))
    app.add_handler(CommandHandler("reset", reset_cmd))
    app.add_handler(CommandHandler("stats", stats_cmd))
    app.add_handler(CommandHandler("config", config_cmd))
    app.add_handler(CommandHandler("set_mexc", set_mexc))
    app.add_handler(CallbackQueryHandler(button_callback))

    # Scheduler
    app.job_queue.run_daily(
        scheduled_scan,
        time=datetime.strptime(f"{SCAN_HOUR:02d}:{SCAN_MINUTE:02d}", "%H:%M").time()
    )
    app.job_queue.run_repeating(check_positions, interval=300, first=30)

    log.info("🤖 Bot started! Press Ctrl+C to stop")
    app.run_polling()


if __name__ == "__main__":
    main()
