#!/bin/bash
# 자동 커밋 및 배포 스크립트
# 파일 변경을 감지하여 자동으로 git commit & push

echo "🤖 자동 배포 모드 시작..."
echo "📁 감시 디렉토리: $(pwd)"
echo "🔄 파일 변경 시 자동으로 commit & push 합니다."
echo "⏹️  중지하려면 Ctrl+C를 누르세요."
echo ""

# 마지막 커밋 해시
LAST_COMMIT=$(git rev-parse HEAD 2>/dev/null || echo "")

while true; do
    # Git 상태 확인
    if git diff-index --quiet HEAD -- 2>/dev/null; then
        # 변경사항 없음
        sleep 5
        continue
    fi

    echo "📝 변경 감지! 자동 커밋 및 푸시 중..."

    # 변경된 파일 목록
    CHANGED_FILES=$(git status --short | head -5)
    echo "변경된 파일:"
    echo "$CHANGED_FILES"
    echo ""

    # 타임스탬프 생성
    TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")

    # Git add
    git add .

    # 커밋 메시지 생성
    COMMIT_MSG="Auto-deploy: $(date +"%Y-%m-%d %H:%M:%S")

🤖 자동 배포 시스템이 변경사항을 감지하여 배포합니다.

Co-Authored-By: Claude <noreply@anthropic.com>"

    # 커밋
    git commit -m "$COMMIT_MSG" 2>&1 | grep -v "^#"

    # 푸시
    echo "🚀 GitHub에 푸시 중..."
    if git push origin main 2>&1; then
        echo "✅ 푸시 완료! GitHub Actions가 EC2에 자동 배포합니다."
        echo "📊 배포 상태: https://github.com/clear-learn/epub_AI/actions"
    else
        echo "❌ 푸시 실패. 인터넷 연결을 확인하세요."
    fi

    echo ""
    echo "⏳ 다음 변경사항 감시 중... (5초마다 체크)"
    echo ""

    # 5초 대기
    sleep 5
done