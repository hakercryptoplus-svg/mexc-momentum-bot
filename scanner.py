"""
Scanner — Check for pump signals and execute trades
"""
import time
from datetime import datetime, timezone
from config import MIN_PUMP, MAX_PUMP, COINS, FEE

class Scanner:
    def __init__(self, exchange, state, notify_func=None):
        self.m = exchange
        self.state = state
        self.notify = notify_func
        self.coins_to_check = 0

    def scan(self):
        """Scan all coins for pump signals. Returns signal or None."""
        today = datetime.now(timezone.utc).strftime('%Y-%m-%d')
        signals = []

        # ── فلتر رموز API ──────────────────────────────────────────────────
        # نجلب من BingX قائمة الرموز المسموحة للتداول عبر API (apiStateBuy=1)
        # مرة واحدة قبل المسح لتجنب خطأ 100421 عند محاولة الشراء.
        # إذا فشل الطلب → tradeable_set = None → نتجاهل الفلتر (آمن).
        tradeable_set = self.m.get_api_tradeable_symbols()
        skipped = []

        for sym in COINS:
            # تخطّى الرموز الممنوعة من API مع تسجيل اسمها
            if tradeable_set is not None and sym not in tradeable_set:
                skipped.append(sym)
                continue

            raw = self.m.get_klines(sym, '1d', 3)
            if not raw or 'error' in raw or not isinstance(raw, list) or len(raw) < 2:
                continue

            df = self.m.parse_klines(raw)
            if len(df) < 2: continue

            yesterday = df[-2]
            pump = (yesterday['close'] - yesterday['open']) / yesterday['open'] * 100

            if MIN_PUMP <= pump <= MAX_PUMP:
                today_candle = df[-1]
                entry_price = today_candle['open']

                signals.append({
                    'symbol': sym,
                    'pump': round(pump, 2),
                    'entry': entry_price,
                    'date': today
                })

            time.sleep(0.08)

        if skipped:
            import logging
            logging.info(f"[Scanner] تم تخطّى {len(skipped)} رمز ممنوع من API: {', '.join(skipped)}")

        if not signals:
            return None

        signals.sort(key=lambda x: x['pump'], reverse=True)
        return signals   # ترجّع القائمة كاملة مرتبة (الأقوى أولاً)

    def execute_trade(self, signal, balance):
        """Place market buy with 100% of balance"""
        sym = signal['symbol']
        entry = signal['entry']

        actual_balance = self.m.get_balance('USDT')
        if actual_balance < 1:
            return None, "الرصيد أقل من 1 USDT"

        invest = actual_balance * 0.995   # اترك 0.5% هامش للعمولة والتقريب

        result = self.m.market_buy(sym, invest)
        if 'error' in result:
            err_code = result.get('error')
            # 100421 = رمز ممنوع من API — ليس خطأ حقيقياً، فقط تخطّاه
            if err_code == 100421:
                return None, f"__SKIP_100421__{sym}"
            return None, f"فشل الشراء: {result.get('msg', result)}"

        # ── استخراج السعر والكمية من استجابة BingX ──
        # BingX لا يرجع fills مثل Binance — يستخدم executedQty و cummulativeQuoteQty
        fills = result.get('fills', [])
        if fills:
            # حساب المتوسط الموزون من fills (إذا وُجدت)
            qty = sum(float(f['qty']) for f in fills)
            avg_price = (
                sum(float(f['price']) * float(f['qty']) for f in fills) / qty
                if qty > 0 else 0
            )
        else:
            # استجابة BingX الاعتيادية
            qty = float(result.get('executedQty') or result.get('origQty') or 0)
            quote_spent = float(result.get('cummulativeQuoteQty') or 0)
            if qty > 0 and quote_spent > 0:
                avg_price = quote_spent / qty
            else:
                # آخر حل: السعر الحالي من السوق
                avg_price = self.m.get_price(sym)

        # حماية: إذا السعر لا يزال صفر، أرجع خطأ
        if avg_price <= 0:
            return None, f"تعذّر تحديد سعر الدخول بعد الشراء (executedQty={qty})"

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

        # ── احجز OCO فوراً بعد الشراء: TP +2% / SL -1% ──
        # الأسماء والمسارات هنا مؤكدة من توثيق BingX الرسمي (انظر تعليقات
        # place_oco في bingx_api.py) — وليست تخميناً.
        # ⚠️ العمولة على الشراء في BingX سبوت تُخصم من العملة المشتراة نفسها،
        # وليس من USDT. يعني الرصيد الحر الفعلي بعد الشراء أقل من executedQty.
        # نجيب الرصيد الحر الحقيقي قبل ما نحجز OCO، لأن حجزه بكمية أكبر من
        # المتاح يرفضه BingX (insufficient balance) ويفشل الـ OCO بالكامل.
        asset = sym.split('/')[0]
        time.sleep(1)  # مهلة بسيطة حتى يتحدّث الرصيد بعد الشراء
        free_qty = self.m._get_asset_balance(asset)
        sell_qty = min(qty, free_qty) if free_qty > 0 else qty * (1 - FEE)
        adjusted_qty = self.m.adjust_qty(sym, sell_qty)
        tp_price = avg_price * 1.02          # +2%
        sl_trigger = avg_price * 0.99        # -1% (سعر التفعيل)
        sl_limit = avg_price * 0.985         # هامش بسيط تحت التفعيل لضمان التنفيذ

        oco_result = self.m.place_oco(sym, adjusted_qty, tp_price, sl_trigger, sl_limit)

        orders = oco_result.get('orders') if isinstance(oco_result, dict) else None
        order_ids = [o.get('orderId') for o in orders if o.get('orderId')] if orders else []
        order_list_id = oco_result.get('orderListId') if isinstance(oco_result, dict) else None

        if 'error' in oco_result or not order_list_id or len(order_ids) < 2:
            # فشل حجز OCO أو استجابة غير مكتملة — نرجع للمراقبة اليدوية (polling) كخطة بديلة
            import logging
            logging.warning(f"[OCO] فشل حجز الأمر لـ {sym}: {oco_result} — سيتم الاعتماد على المراقبة اليدوية")
            trade['oco_id'] = None
            trade['oco_order_ids'] = []
            trade['oco_active'] = False
        else:
            # خزّن orderListId (للاستعلام) + orderId لكل ساق (Limit=TP و Stop-Limit=SL)
            # عشان نقدر نتحقق من حالة كل ساق ونلغي المجموعة لاحقاً عند الترلينغ
            trade['oco_id'] = order_list_id
            trade['oco_order_ids'] = order_ids
            trade['oco_active'] = True

        return trade, None

    def check_tp_sl(self, trade):
        """Check if TP or SL is hit. Returns 'TP', 'SL', 'BE', 'TRAIL', or 'HOLD'

        يستخدم السعر الحالي فقط (lastPrice) — وليس highPrice/lowPrice من الـ 24h ticker
        لأن الـ 24h high/low يتضمن حركة أمس (قبل دخولنا) وسيُفعّل TP/SL بشكل خاطئ.

        TRAILING LOGIC:
        - إذا السعر لمس +1% من سعر الدخول ← SL يتحرك لسعر الدخول (Breakeven)
        - بعدها ننتظر TP أو Breakeven — لا خسارة بعد التفعيل
        """
        sym = trade['symbol']
        ticker = self.m.get_ticker(sym)
        if 'error' in ticker:
            return 'HOLD'

        try:
            current = float(ticker.get('lastPrice', 0))
        except:
            return 'HOLD'

        if current <= 0:
            return 'HOLD'

        tp = trade['tp']
        entry = trade['entry_price']
        trail_trigger = trade.get('trail_trigger', entry * 1.01)
        sl_trailed = trade.get('sl_trailed', entry)
        trail_activated = trade.get('trail_activated', False)

        # === TRAILING: هل السعر لمس +1%؟ ===
        if not trail_activated and current >= trail_trigger:
            trade['trail_activated'] = True
            trade['sl'] = sl_trailed        # حرك SL لسعر الدخول (Breakeven)
            trade['trail_time'] = datetime.now(timezone.utc).isoformat()
            trail_activated = True
            return 'TRAIL'                  # أعلم bot.py أن يحفظ الحالة ويرسل تنبيه

        sl = trade['sl']

        if current <= sl:
            return 'BE' if trail_activated else 'SL'

        if current >= tp:
            return 'TP'

        return 'HOLD'

    def close_trade(self, trade, reason='TP'):
        """Sell position"""
        sym = trade['symbol']
        qty = trade['qty']

        asset = sym.split('/')[0]
        actual_qty = self._get_asset_balance(asset)

        filters = self.m.get_symbol_filters(sym)
        min_qty = filters['minQty'] if filters else 0

        # ⚠️ الرصيد فعلياً صفر أو أقل من أدنى كمية بيع مسموحة — يعني العملة
        # خرجت من المحفظة خارج مسار البوت (بيع يدوي على المنصة، أو صفقة أُغلقت
        # فعلاً في محاولة سابقة ولم يُحفظ ذلك بالحالة). لا يوجد شيء نبيعه، فلا
        # نستدعي market_sell (BingX ترفضه بخطأ quantity<=0) ولا نكرر المحاولة
        # للأبد — نسجّل الإغلاق بأفضل تقدير للسعر الحالي حتى تتحرر الصفقة.
        if actual_qty <= 0 or (min_qty and actual_qty < min_qty):
            exit_price = self.m.get_price(sym)
            if exit_price <= 0:
                return None, f"لا يوجد كمية من العملة والسعر الحالي غير متاح (balance={actual_qty})"
            buy_fee = trade['usdt_invested'] * FEE
            sell_rev = exit_price * qty * (1 - FEE)
            pnl = sell_rev - trade['usdt_invested'] - buy_fee
            pnl_pct = (exit_price / trade['entry_price'] - 1) * 100
            return {
                'exit_price': exit_price,
                'pnl': round(pnl, 2),
                'pnl_pct': round(pnl_pct, 2),
                'result': reason,
                'exit_time': datetime.now(timezone.utc).isoformat(),
                'closed_externally': True,   # بيع سابق (يدوي أو OCO) لم يُسجَّل بالحالة
            }, None

        adjusted = self.m.adjust_qty(sym, actual_qty)
        if adjusted <= 0:
            # actual_qty كان أكبر من الصفر ومن minQty، لكن التقريب لـ stepSize
            # أنزله لصفر (حالة نادرة) — نبيع الكمية الأصلية غير المقرّبة بدل
            # إرسال 0 لـ BingX.
            adjusted = actual_qty

        result = self.m.market_sell(sym, adjusted)
        if 'error' in result:
            return None, f"فشل البيع: {result.get('msg', result)}"

        # ── استخراج سعر البيع من استجابة BingX (نفس منطق الشراء) ──
        fills = result.get('fills', [])
        if fills:
            total_qty = sum(float(f['qty']) for f in fills)
            avg_price = (
                sum(float(f['price']) * float(f['qty']) for f in fills) / total_qty
                if total_qty > 0 else 0
            )
        else:
            sold_qty  = float(result.get('executedQty') or 0)
            quote_got = float(result.get('cummulativeQuoteQty') or 0)
            if sold_qty > 0 and quote_got > 0:
                avg_price = quote_got / sold_qty
            else:
                avg_price = self.m.get_price(sym)   # آخر حل

        if avg_price <= 0:
            return None, f"تعذّر تحديد سعر الخروج (executedQty={result.get('executedQty')})"

        # PnL صافي بعد عمولة الشراء والبيع
        buy_fee  = trade['usdt_invested'] * FEE
        sell_rev = avg_price * adjusted * (1 - FEE)
        pnl      = sell_rev - trade['usdt_invested'] - buy_fee
        pnl_pct  = (avg_price / trade['entry_price'] - 1) * 100

        return {
            'exit_price': avg_price,
            'pnl': round(pnl, 2),
            'pnl_pct': round(pnl_pct, 2),
            'result': reason,
            'exit_time': datetime.now(timezone.utc).isoformat()
        }, None

    def _get_asset_balance(self, asset):
        """Get balance of a specific asset using the exchange balance method"""
        # Get balance for the asset — try exchange-specific method first
        try:
            return self.m._get_asset_balance(asset)
        except:
            pass
        # Fallback: get full balance
        bal = self.m.get_balance(asset)
        if bal > 0: return bal
        return 0.0
