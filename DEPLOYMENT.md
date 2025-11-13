# 🚀 EC2 배포 가이드

이 가이드는 로컬에서 코드를 수정하고 EC2 서버에 자동으로 배포하는 CI/CD 파이프라인 설정 방법을 설명합니다.

## 📋 목차
1. [사전 준비](#1-사전-준비)
2. [GitHub 저장소 설정](#2-github-저장소-설정)
3. [EC2 서버 초기 설정](#3-ec2-서버-초기-설정)
4. [GitHub Actions Secrets 설정](#4-github-actions-secrets-설정)
5. [배포 테스트](#5-배포-테스트)
6. [문제 해결](#6-문제-해결)

---

## 1. 사전 준비

### 필요한 것들
- ✅ GitHub 계정
- ✅ EC2 인스턴스 (Ubuntu)
- ✅ SSH 키 (ec2-research-data-key.pem)
- ✅ EC2 보안 그룹에서 포트 8000 오픈

### EC2 정보
```
호스트: ec2-3-38-101-46.ap-northeast-2.compute.amazonaws.com
사용자: ubuntu
프로젝트 경로: /home/ubuntu/ai-epub-api
```

---

## 2. GitHub 저장소 설정

### 2.1 GitHub에서 새 저장소 생성
1. GitHub에 로그인
2. 우측 상단 `+` → `New repository` 클릭
3. 저장소 이름 입력 (예: `ai-epub-api`)
4. `Private` 선택 (권장)
5. `Create repository` 클릭

### 2.2 로컬 코드를 GitHub에 푸시
```bash
# Git 원격 저장소 추가
git remote add origin https://github.com/YOUR_USERNAME/ai-epub-api.git

# 초기 커밋
git add .
git commit -m "Initial commit: AI EPUB API with CI/CD"

# main 브랜치로 푸시
git branch -M main
git push -u origin main
```

---

## 3. EC2 서버 초기 설정

### 3.1 EC2에 SSH 접속
```bash
# 로컬에서 실행
ssh -i ec2-research-data-key.pem ubuntu@ec2-3-38-101-46.ap-northeast-2.compute.amazonaws.com
```

### 3.2 초기 설정 스크립트 실행
```bash
# EC2 서버에서 실행

# 1. 설정 스크립트 다운로드
wget https://raw.githubusercontent.com/YOUR_USERNAME/ai-epub-api/main/.devops/ec2/setup.sh

# 2. 실행 권한 부여
chmod +x setup.sh

# 3. 스크립트 실행 (GitHub 저장소 URL 입력 필요)
bash setup.sh
```

### 3.3 환경 변수 설정
```bash
# .env 파일 편집
nano ~/ai-epub-api/.env

# 필요한 환경 변수 입력 (sample.env 참고)
# 예시:
# AWS_REGION=ap-northeast-2
# S3_BUCKET_NAME=your-bucket-name
# OPENAI_API_KEY=your-api-key
# ...

# 저장: Ctrl+O, Enter
# 종료: Ctrl+X
```

### 3.4 서비스 시작 확인
```bash
# 서비스 상태 확인
sudo systemctl status ai-epub-api.service

# 로그 확인
sudo journalctl -u ai-epub-api.service -f

# 서비스가 정상 동작하지 않으면
sudo systemctl restart ai-epub-api.service
```

---

## 4. GitHub Actions Secrets 설정

GitHub 저장소에 EC2 접속 정보를 안전하게 저장합니다.

### 4.1 SSH 키 내용 복사
```bash
# 로컬에서 실행
cat ec2-research-data-key.pem
```
출력된 전체 내용을 복사합니다 (-----BEGIN ... END----- 포함).

### 4.2 GitHub Secrets 추가
1. GitHub 저장소 페이지로 이동
2. `Settings` → `Secrets and variables` → `Actions` 클릭
3. `New repository secret` 클릭하여 다음 3개 추가:

#### Secret 1: EC2_HOST
```
Name: EC2_HOST
Value: ec2-3-38-101-46.ap-northeast-2.compute.amazonaws.com
```

#### Secret 2: EC2_USER
```
Name: EC2_USER
Value: ubuntu
```

#### Secret 3: EC2_SSH_KEY
```
Name: EC2_SSH_KEY
Value: (ec2-research-data-key.pem 파일의 전체 내용 붙여넣기)
```

---

## 5. 배포 테스트

### 5.1 코드 수정 및 푸시
```bash
# 로컬에서 코드 수정 (예: README.md 수정)
echo "# Test deployment" >> README.md

# Git 커밋
git add .
git commit -m "Test: CI/CD deployment"

# GitHub에 푸시 (자동 배포 시작)
git push origin main
```

### 5.2 배포 진행 상황 확인
1. GitHub 저장소 → `Actions` 탭 클릭
2. 최근 워크플로우 실행 상태 확인
3. 녹색 체크 표시가 나오면 배포 성공! ✅

### 5.3 EC2에서 결과 확인
```bash
# EC2에 접속
ssh -i ec2-research-data-key.pem ubuntu@ec2-3-38-101-46.ap-northeast-2.compute.amazonaws.com

# 최신 코드가 반영되었는지 확인
cd ~/ai-epub-api
git log -1

# 서비스가 정상 동작하는지 확인
sudo systemctl status ai-epub-api.service
```

---

## 6. 문제 해결

### 배포가 실패하는 경우

#### 1. SSH 연결 실패
```bash
# GitHub Actions 로그에서 확인할 내용:
# - EC2_HOST, EC2_USER, EC2_SSH_KEY가 올바르게 설정되었는지
# - EC2 보안 그룹에서 SSH 포트(22)가 열려있는지

# 로컬에서 테스트
ssh -i ec2-research-data-key.pem ubuntu@ec2-3-38-101-46.ap-northeast-2.compute.amazonaws.com
```

#### 2. Git pull 실패
```bash
# EC2에서 Git 저장소 상태 확인
cd ~/ai-epub-api
git status

# 충돌이 있으면 초기화
git fetch origin
git reset --hard origin/main
```

#### 3. 서비스 재시작 실패
```bash
# EC2에서 로그 확인
sudo journalctl -u ai-epub-api.service -n 100 --no-pager

# 수동으로 재시작
sudo systemctl restart ai-epub-api.service

# 서비스 파일 재로드
sudo systemctl daemon-reload
sudo systemctl restart ai-epub-api.service
```

#### 4. 의존성 설치 실패
```bash
# EC2에서 수동 설치 시도
cd ~/ai-epub-api
source venv/bin/activate
pip install -r requirements.txt
```

### 유용한 명령어

```bash
# 서비스 상태 확인
sudo systemctl status ai-epub-api.service

# 실시간 로그 확인
sudo journalctl -u ai-epub-api.service -f

# 서비스 재시작
sudo systemctl restart ai-epub-api.service

# 서비스 중지
sudo systemctl stop ai-epub-api.service

# 서비스 시작
sudo systemctl start ai-epub-api.service

# 최근 로그 100줄 확인
sudo journalctl -u ai-epub-api.service -n 100 --no-pager
```

---

## 🎉 완료!

이제 로컬에서 코드를 수정하고 `git push`만 하면 자동으로 EC2에 배포됩니다!

**워크플로우:**
```
로컬 수정 → git commit → git push → GitHub Actions → EC2 배포 완료
```

**배포 시간:** 약 1-2분

---

## 📚 추가 리소스

- [GitHub Actions 문서](https://docs.github.com/en/actions)
- [systemd 서비스 관리](https://www.freedesktop.org/software/systemd/man/systemctl.html)
- [EC2 보안 그룹 설정](https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-security-groups.html)

---

**문제가 있으면 Issue를 열어주세요!** 🙏