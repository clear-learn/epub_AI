#!/bin/bash
# 로컬에서 EC2로 직접 배포하는 스크립트

set -e

EC2_HOST="ec2-3-38-101-46.ap-northeast-2.compute.amazonaws.com"
EC2_USER="ubuntu"
SSH_KEY="../ec2-research-data-key.pem"
REMOTE_DIR="~/ai-epub-api"

echo "🚀 EC2로 직접 배포 시작..."
echo "📡 대상: ${EC2_USER}@${EC2_HOST}"
echo ""

# 1. 로컬에서 Git 커밋 (변경사항이 있을 경우)
if ! git diff-index --quiet HEAD -- 2>/dev/null; then
    echo "📝 로컬 변경사항 커밋 중..."
    git add .
    TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")
    git commit -m "Update: ${TIMESTAMP}" || true
    echo "✅ 커밋 완료"
    echo ""
fi

# 2. rsync로 파일 동기화 (빠르고 효율적)
echo "📦 파일 동기화 중..."
rsync -avz --delete \
    --exclude='.git' \
    --exclude='__pycache__' \
    --exclude='*.pyc' \
    --exclude='.env' \
    --exclude='venv/' \
    --exclude='logs/' \
    --exclude='.pytest_cache/' \
    --exclude='.DS_Store' \
    --exclude='*.pem' \
    -e "ssh -i ${SSH_KEY} -o StrictHostKeyChecking=no" \
    ./ ${EC2_USER}@${EC2_HOST}:${REMOTE_DIR}/

echo "✅ 파일 동기화 완료"
echo ""

# 3. EC2에서 의존성 설치 및 서비스 재시작
echo "🔧 EC2에서 의존성 설치 및 서비스 재시작 중..."
ssh -i ${SSH_KEY} -o StrictHostKeyChecking=no ${EC2_USER}@${EC2_HOST} << 'EOF'
    cd ~/ai-epub-api

    # 가상환경 활성화
    source venv/bin/activate

    # 의존성 설치
    pip install -r requirements.txt -q

    # 서비스 재시작
    sudo systemctl restart ai-epub-api.service 2>/dev/null || echo "⚠️  서비스 재시작 실패 (수동으로 확인 필요)"

    echo "✅ EC2 설정 완료"
EOF

echo ""
echo "🎉 배포 완료!"
echo "📊 서비스 상태 확인: ssh -i ${SSH_KEY} ${EC2_USER}@${EC2_HOST} 'sudo systemctl status ai-epub-api.service'"