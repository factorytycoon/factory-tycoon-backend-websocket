
import redis
from dotenv import load_dotenv
import os
import time
import asyncio
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from contextlib import asynccontextmanager
import uvicorn
from threading import Thread
import json

load_dotenv()
REDIS_HOST       = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT       = int(os.getenv('REDIS_PORT', 6379))
REDIS_PASSWORD   = os.getenv('REDIS_PASSWORD', None)
REDIS_CHANNEL    = os.getenv('REDIS_CHANNEL', 'sensor_data')  # Pub/Sub 채널로 변경
WEBSOCKET_PATH   = os.getenv('WEBSOCKET_PATH', '/ws')
WEBSOCKET_HOST   = os.getenv('WEBSOCKET_HOST', '0.0.0.0')
WEBSOCKET_PORT   = int(os.getenv('WEBSOCKET_PORT', 8000))


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass


class RedisPubSubReader:
    def __init__(self, manager: ConnectionManager):
        self.client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, decode_responses=True)
        self.manager = manager
        self.pubsub = self.client.pubsub()

    async def listen(self):
        print(f"Subscribing to Redis Pub/Sub channel '{REDIS_CHANNEL}'...")
        loop = asyncio.get_event_loop()
        
        # 채널 구독 (블로킹 없이)
        await loop.run_in_executor(None, self.pubsub.subscribe, REDIS_CHANNEL)
        print(f"Subscribed to channel '{REDIS_CHANNEL}'")
        
        while True:
            try:
                # get_message()를 비동기로 실행
                message = await loop.run_in_executor(
                    None,
                    lambda: self.pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
                )
                
                if message and message['type'] == 'message':
                    data = message['data']
                    print(f"Received: {data}")
                    await self.manager.broadcast(data)
                else:
                    # 메시지가 없으면 잠시 대기
                    await asyncio.sleep(0.01)
                    
            except Exception as e:
                print(f"Error: {e}")
                await asyncio.sleep(2)



# FastAPI lifespan 이벤트 핸들러로 Redis 리스너 등록
@asynccontextmanager
async def lifespan(app: FastAPI):
    loop = asyncio.get_event_loop()
    loop.create_task(reader.listen())
    yield

app = FastAPI(lifespan=lifespan)
manager = ConnectionManager()
reader = RedisStreamReader(manager)

@app.get("/")
async def root():
    return {"status": "ok"}

@app.websocket(WEBSOCKET_PATH)
async def websPubSubendpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            try:
                # 클라이언트 메시지 대기 (30초 타임아웃)
                # 메시지가 오면 즉시 처리, 없으면 타임아웃 후 연결 유지
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # 연결 유지를 위한 ping 전송
                await websocket.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        manager.disconnect(websocket)



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=WEBSOCKET_HOST, port=WEBSOCKET_PORT)
