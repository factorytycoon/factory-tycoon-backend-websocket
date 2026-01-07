# Factory Tycoon Backend WebSocket

Redis Pub/Sub 기반 실시간 센서 데이터 WebSocket 서버

## 기술 스택

- Python 3.11
- FastAPI
- WebSocket
- Redis (Pub/Sub)
- Uvicorn
- Docker

## 주요 기능

- **Redis Pub/Sub 구독**: Redis 채널에서 센서 데이터 수신
- **WebSocket 브로드캐스트**: 연결된 모든 클라이언트에게 실시간 데이터 전송
- **연결 관리**: 다중 클라이언트 WebSocket 연결 관리
- **비동기 처리**: asyncio 기반 효율적인 이벤트 처리

## 실행 방법

### 로컬 실행

```bash
# 환경 변수 설정 (.env 파일 생성)
# REDIS_HOST, REDIS_PORT, REDIS_PASSWORD
# REDIS_CHANNEL (기본값: sensor_data)
# WEBSOCKET_HOST, WEBSOCKET_PORT

# 의존성 설치
$ pip install -r requirements.txt

# 서버 실행
$ uvicorn main:app --host 0.0.0.0 --port 8000
```

### Docker 실행

```bash
# 이미지 빌드
$ docker build -t factory-tycoon-websocket .

# 실행
$ docker run -p 8000:8000 factory-tycoon-websocket
```

## WebSocket 연결

```javascript
// 클라이언트 연결 예시
const ws = new WebSocket('ws://localhost:8000/ws');

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log('센서 데이터:', data);
};
```

## 데이터 흐름

```
IoT Sensor → Redis Pub/Sub → WebSocket Server → 브라우저 클라이언트
```

1. IoT 센서가 Redis 채널에 데이터 발행
2. WebSocket 서버가 Redis 채널 구독
3. 수신된 데이터를 모든 WebSocket 클라이언트에게 브로드캐스트