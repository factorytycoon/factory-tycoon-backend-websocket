# Deployment Guide

GitHub Actions를 통한 자동 배포 프로세스

## 배포 트리거

`main` 브랜치에 모든 파일 변경 시 자동 배포

## 배포 프로세스

1. **코드 체크아웃** - 최신 코드 가져오기
2. **AWS 인증** - ECR 접근 권한 설정
3. **Docker 이미지 빌드** - 멀티 플랫폼 빌드 (linux/amd64)
4. **ECR 푸시** - 이미지 태그: `latest`, `{git-sha}`
5. **Helm 차트 업데이트** - K8s 배포를 위한 이미지 태그 변경
6. **ArgoCD 자동 배포** - Helm 차트 변경 감지 및 클러스터 배포

## 필요한 GitHub Secrets

```
AWS_ACCESS_KEY_ID       # AWS 액세스 키
AWS_SECRET_ACCESS_KEY   # AWS 시크릿 키
AWS_REGION             # AWS 리전 (예: ap-northeast-2)
GH_PAT                 # GitHub Personal Access Token (K8s 레포 업데이트용)
```

## ECR 이미지 태그

- `latest` - 최신 배포 버전
- `{git-sha}` - 커밋 해시 기반 버전

## 배포 확인

```bash
# ECR 이미지 확인
aws ecr describe-images --repository-name sf-backend-websocket

# K8s Pod 상태 확인
kubectl get pods -n default -l app=factory-tycoon-websocket

# 배포 로그 확인
kubectl logs -n default -l app=factory-tycoon-websocket

# WebSocket 연결 테스트
wscat -c ws://<service-url>/ws
```

## 롤백

문제 발생 시 이전 버전으로 롤백:
```bash
# Helm 차트에서 이전 이미지 태그로 변경
cd factory-tycoon-k8s/helm/factory-tycoon-websocket
# values-prod.yaml의 tag를 이전 커밋 해시로 변경
git commit -m "Rollback to {previous-sha}"
git push
```

## 환경 변수

K8s ConfigMap/Secret에서 관리:
- `REDIS_HOST` - Redis 서버 호스트
- `REDIS_CHANNEL` - 구독할 Pub/Sub 채널명
- `WEBSOCKET_PATH` - Websocket path
