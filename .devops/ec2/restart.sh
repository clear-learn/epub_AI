#!/bin/bash
# 서비스 재시작 스크립트

echo "🔄 AI EPUB API 서비스 재시작 중..."
sudo systemctl restart ai-epub-api.service

echo "✅ 서비스 상태:"
sudo systemctl status ai-epub-api.service --no-pager

echo ""
echo "📋 최근 로그:"
sudo journalctl -u ai-epub-api.service -n 50 --no-pager