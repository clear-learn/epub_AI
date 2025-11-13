#!/bin/bash
# 파일 변경 감지 → GitHub + EC2 동시 자동 배포

echo "🤖 완전 자동 배포 모드 시작..."
echo "📁 감시 디렉토리: $(pwd)"
echo ""
echo "🔄 파일 변경 시 자동으로:"
echo "   1️⃣  GitHub에 커밋/푸시"
echo "   2️⃣  EC2에 배포"
echo ""
echo "⏹️  중지하려면 Ctrl+C를 누르세요."
echo ""

# 마지막 배포 시간
LAST_DEPLOY=0

while true; do
    # 파일 변경 감지
    if git diff-index --quiet HEAD -- 2>/dev/null; then
        # 변경사항 없음
        sleep 3
        continue
    fi

    # 현재 시간
    CURRENT_TIME=$(date +%s)

    # 마지막 배포로부터 5초 이상 경과했는지 확인
    if [ $((CURRENT_TIME - LAST_DEPLOY)) -lt 5 ]; then
        sleep 3
        continue
    fi

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📝 변경 감지! 자동 배포 시작... ($(date +"%H:%M:%S"))"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # 변경된 파일 목록
    echo ""
    echo "📋 변경된 파일:"
    git status --short | head -5
    echo ""

    # 1. GitHub에 커밋/푸시
    echo "1️⃣  GitHub에 업로드 중..."
    git add .

    TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")
    COMMIT_MSG="Auto-update: ${TIMESTAMP}

🤖 자동 배포 시스템

Co-Authored-By: Claude <noreply@anthropic.com>"

    if git commit -m "$COMMIT_MSG" 2>&1 | grep -v "^#" && \
       git push origin main 2>&1 | grep -v "^$"; then
        echo "   ✅ GitHub 업로드 완료"
    else
        echo "   ⚠️  GitHub 업로드 실패 (무시하고 계속)"
    fi

    echo ""

    # 2. EC2에 배포
    echo "2️⃣  EC2에 배포 중..."
    if ./deploy-to-ec2.sh 2>&1 | grep -E "(동기화|완료|✅)" ; then
        echo "   ✅ EC2 배포 완료"
    else
        echo "   ⚠️  EC2 배포 실패"
    fi

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "✅ 배포 완료! ($(date +"%H:%M:%S"))"
    echo "   📦 GitHub: https://github.com/clear-learn/epub_AI"
    echo "   🚀 EC2: ubuntu@ec2-3-38-101-46.ap-northeast-2.compute.amazonaws.com"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "⏳ 다음 변경사항 감시 중..."
    echo ""

    LAST_DEPLOY=$(date +%s)
    sleep 3
done