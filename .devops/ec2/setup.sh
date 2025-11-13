#!/bin/bash
# EC2 초기 설정 스크립트
# 사용법: bash setup.sh

set -e

echo "🚀 EC2 서버 초기 설정을 시작합니다..."

# 1. 시스템 패키지 업데이트
echo "📦 시스템 패키지 업데이트 중..."
sudo apt-get update
sudo apt-get upgrade -y

# 2. Python 및 필수 패키지 설치
echo "🐍 Python 및 필수 패키지 설치 중..."
sudo apt-get install -y python3 python3-pip python3-venv git

# 3. 프로젝트 디렉토리 생성
echo "📁 프로젝트 디렉토리 설정 중..."
cd ~
if [ ! -d "ai-epub-api" ]; then
    echo "⚠️  GitHub 저장소 URL을 입력하세요:"
    read -r REPO_URL
    git clone "$REPO_URL" ai-epub-api
fi

cd ~/ai-epub-api

# 4. Python 가상환경 생성
echo "🔧 Python 가상환경 생성 중..."
python3 -m venv venv
source venv/bin/activate

# 5. 의존성 설치
echo "📚 의존성 설치 중..."
pip install --upgrade pip
pip install -r requirements.txt

# 6. 환경 변수 파일 생성
if [ ! -f ".env" ]; then
    echo "⚙️  환경 변수 파일 생성 중..."
    if [ -f "sample.env" ]; then
        cp sample.env .env
        echo "✅ .env 파일이 생성되었습니다. 파일을 수정하여 실제 값을 입력하세요."
    else
        echo "⚠️  sample.env 파일이 없습니다. 수동으로 .env 파일을 생성하세요."
    fi
fi

# 7. systemd 서비스 파일 생성
echo "🔧 systemd 서비스 설정 중..."
sudo bash -c "cat > /etc/systemd/system/ai-epub-api.service" << 'EOF'
[Unit]
Description=AI EPUB API Service
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/ai-epub-api
Environment="PATH=/home/ubuntu/ai-epub-api/venv/bin"
ExecStart=/home/ubuntu/ai-epub-api/venv/bin/gunicorn -c gunicorn.conf.py app:app
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

# 8. systemd 서비스 활성화
echo "🚀 서비스 활성화 중..."
sudo systemctl daemon-reload
sudo systemctl enable ai-epub-api.service
sudo systemctl start ai-epub-api.service

# 9. 상태 확인
echo "✅ 서비스 상태 확인 중..."
sudo systemctl status ai-epub-api.service --no-pager

echo ""
echo "✅ EC2 초기 설정이 완료되었습니다!"
echo ""
echo "다음 단계:"
echo "1. .env 파일을 수정하여 실제 환경 변수를 입력하세요: nano ~/ai-epub-api/.env"
echo "2. 서비스 재시작: sudo systemctl restart ai-epub-api.service"
echo "3. 로그 확인: sudo journalctl -u ai-epub-api.service -f"