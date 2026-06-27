#!/usr/bin/env bash
# ============================================
# 📦 Auto-deploy MEXC Momentum Bot to GitHub
# ============================================
# Usage: bash deploy.sh GITHUB_TOKEN
# ============================================

set -e

if [ -z "$1" ]; then
    echo "❌ يرجى تمرير GitHub Token!"
    echo "   استخدم: bash deploy.sh ghp_xxxxxxxxxxxxxxxxxxxx"
    echo ""
    echo "   👉 أنشئ token هنا: https://github.com/settings/tokens"
    echo "      (حدد صلاحية: repo)"
    exit 1
fi

TOKEN="$1"
USER="abozaid005"
REPO="mexc-momentum-bot"
DIR="/root/.openclaw/workspace/mexc-bot-deploy"

echo "🚀 إنشاء المستودع $REPO على GitHub..."

# Create repo via API
CREATE_RESP=$(curl -s -X POST \
    -H "Authorization: token $TOKEN" \
    -H "Accept: application/vnd.github.v3+json" \
    -d "{\"name\":\"$REPO\",\"description\":\"🤖 بوت تداول آلي MEXC + تحكم تيليجرام\",\"public\":true,\"has_issues\":true}" \
    "https://api.github.com/user/repos")

if echo "$CREATE_RESP" | grep -q "\"id\":"; then
    echo "✅ تم إنشاء المستودع!"
elif echo "$CREATE_RESP" | grep -q "already_exists"; then
    echo "⚠️ المستودع موجود مسبقاً، سنحدثه..."
else
    echo "❌ فشل إنشاء المستودع:"
    echo "$CREATE_RESP" | head -3
    exit 1
fi

cd "$DIR"

echo "📦 تهيئة Git..."
rm -rf .git
git init -b main
git add -A
git commit -m "🎉 Initial release: MEXC Momentum Bot v1.0

Automated trading bot for MEXC exchange with Telegram control.
- Momentum Continuation strategy (pump ≥ 5%)
- TP +2% / SL -1%
- 42 coins watchlist
- Telegram commands in Arabic
- Deployable on Render, Railway, Docker"

echo "☁️ رفع إلى GitHub..."
git remote add origin "https://abozaid005:${TOKEN}@github.com/${USER}/${REPO}.git"
git push -u origin main

echo ""
echo "═══════════════════════════════════════════"
echo "  ✅ تم الرفع بنجاح!"
echo "  📍 https://github.com/$USER/$REPO"
echo "═══════════════════════════════════════════"
echo ""
echo "▶️ للنشر على Render.com:"
echo "   1. افتح https://dashboard.render.com"
echo "   2. New → Worker"
echo "   3. Connect your GitHub repo: $USER/$REPO"
echo "   4. أضف المتغيرات: TELEGRAM_TOKEN و TELEGRAM_CHAT_ID"
echo "   5. Deploy 🚀"
echo ""
echo "▶️ للنشر على Railway:"
echo "   1. افتح https://railway.app"
echo "   2. New Project → Deploy from GitHub"
echo "   3. اختر $USER/$REPO"
echo "   4. أضف Environment Variables"
echo "   5. Deploy 🚀"
