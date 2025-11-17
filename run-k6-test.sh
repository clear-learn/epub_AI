#!/bin/bash
# EC2에서 k6 테스트 실행 후 결과를 로컬에 자동 저장

set -e

EC2_HOST="ec2-3-38-101-46.ap-northeast-2.compute.amazonaws.com"
EC2_USER="ubuntu"
SSH_KEY="../ec2-research-data-key.pem"
LOCAL_DOWNLOAD_DIR="/Users/yimhaksoon/Downloads"

echo "🚀 EC2에서 k6 부하 테스트 실행 중..."
echo ""

# EC2에서 k6 실행 (원본 명령어와 동일)
ssh -i ${SSH_KEY} ${EC2_USER}@${EC2_HOST} << 'EOF'
cd ~/ai-epub-api/.sample

# 이전 결과 파일 삭제
rm -f result.json

# k6 테스트 실행 (원본 명령어)
k6 run k6_test.js -e TENANTS=tenant-a,tenant-b,tenant-c,tenant-d

echo ""
echo "✅ 테스트 완료! 결과 파일 생성됨"
ls -lh result.json
EOF

echo ""
echo "📥 결과 파일을 로컬로 다운로드 중..."

# 타임스탬프 생성
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")

# 결과 파일 다운로드
scp -i ${SSH_KEY} \
  ${EC2_USER}@${EC2_HOST}:~/ai-epub-api/.sample/result.json \
  ${LOCAL_DOWNLOAD_DIR}/k6_result_${TIMESTAMP}.json

echo ""
echo "✅ 다운로드 완료!"
echo "📁 저장 위치: ${LOCAL_DOWNLOAD_DIR}/k6_result_${TIMESTAMP}.json"
echo ""

# 간단한 결과 출력
echo "📊 테스트 결과:"
cat ${LOCAL_DOWNLOAD_DIR}/k6_result_${TIMESTAMP}.json