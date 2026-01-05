
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
REDIS_STREAM_KEY = os.getenv('REDIS_STREAM_KEY', 'mystream')
CONSUMER_GROUP   = os.getenv('CONSUMER_GROUP', 'mygroup')
CONSUMER_NAME    = os.getenv('CONSUMER_NAME', 'sensor-reader-1')
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


class RedisStreamReader:
    def __init__(self, manager: ConnectionManager):
        self.client = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, password=REDIS_PASSWORD, decode_responses=True)
        self.manager = manager
        self._create_consumer_group()

    def _create_consumer_group(self):
        try:
            self.client.xgroup_create(name=REDIS_STREAM_KEY, groupname=CONSUMER_GROUP, id='0', mkstream=True)
        except redis.exceptions.ResponseError as e:
            if 'BUSYGROUP' in str(e):
                print("already exists consumer group")
                pass  # 이미 그룹이 있으면 무시
            else:
                raise

    async def listen(self):
        print(f"Listening to Redis stream '{REDIS_STREAM_KEY}' as group '{CONSUMER_GROUP}'...")
        loop = asyncio.get_event_loop()
        while True:
            try:
                # 블로킹 호출을 스레드로 실행
                messages = await loop.run_in_executor(
                    None,
                    lambda: self.client.xreadgroup(
                        groupname=CONSUMER_GROUP,
                        consumername=CONSUMER_NAME,
                        streams={REDIS_STREAM_KEY: '>'},
                        count=10,
                        block=1000
                    )
                )
                for stream, msgs in messages:
                    for msg_id, msg in msgs:
                        print(f"Received: {msg}")
                        await self.manager.broadcast(json.dumps(msg))
                        self.client.xack(REDIS_STREAM_KEY, CONSUMER_GROUP, msg_id)
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
async def websocket_endpoint(websocket: WebSocket):
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
