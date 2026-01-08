
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
REDIS_USERNAME   = os.getenv('REDIS_USERNAME', None)
RAW_REDIS_PASSWORD = os.getenv('REDIS_PASSWORD', None)
REDIS_PASSWORD   = RAW_REDIS_PASSWORD if RAW_REDIS_PASSWORD and RAW_REDIS_PASSWORD.strip() else None
REDIS_CHANNEL    = os.getenv('REDIS_CHANNEL', 'sensor_data')  # 센서 데이터 채널
REDIS_ALERT_CHANNEL = os.getenv('REDIS_ALERT_CHANNEL', 'alert_notifications')  # 알람 채널
WEBSOCKET_PATH   = os.getenv('WEBSOCKET_PATH', '/ws')
WEBSOCKET_HOST   = os.getenv('WEBSOCKET_HOST', '0.0.0.0')
WEBSOCKET_PORT   = int(os.getenv('WEBSOCKET_PORT', 8000))


class ConnectionManager:
    def __init__(self, name: str = "default"):
        self.name = name
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        print(f"[{self.name}] Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            print(f"[{self.name}] Client disconnected. Total: {len(self.active_connections)}")

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            try:
                await connection.send_text(message)
            except Exception:
                pass


class RedisPubSubReader:
    def __init__(self, sensor_manager: ConnectionManager, alert_manager: ConnectionManager):
        client_kwargs = {
            "host": REDIS_HOST,
            "port": REDIS_PORT,
            "decode_responses": True,
        }
        if REDIS_USERNAME:
            client_kwargs["username"] = REDIS_USERNAME
        if REDIS_PASSWORD:
            client_kwargs["password"] = REDIS_PASSWORD
        self.client = redis.Redis(**client_kwargs)
        self.sensor_manager = sensor_manager
        self.alert_manager = alert_manager
        self.pubsub = self.client.pubsub()

    async def listen(self):
        print(f"Subscribing to Redis Pub/Sub channel '{REDIS_CHANNEL}'...")
        loop = asyncio.get_event_loop()
        
        # 채널 구독 (센서 데이터 + 알람)
        await loop.run_in_executor(None, self.pubsub.subscribe, REDIS_CHANNEL, REDIS_ALERT_CHANNEL)
        print(f"Subscribed to channels: '{REDIS_CHANNEL}', '{REDIS_ALERT_CHANNEL}'")
        
        while True:
            try:
                # get_message()를 비동기로 실행
                message = await loop.run_in_executor(
                    None,
                    lambda: self.pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
                )
                
                if message and message['type'] == 'message':
                    channel = message['channel']
                    data = message['data']
                    
                    # 채널에 따라 적절한 ConnectionManager로 브로드캐스트 (원본 데이터 그대로)
                    if channel == REDIS_ALERT_CHANNEL:
                        print(f"[ALERT] {data}")
                        await self.alert_manager.broadcast(data)
                    else:  # sensor_data 채널
                        print(f"[SENSOR] {data}")
                        await self.sensor_manager.broadcast(data)
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
sensor_manager = ConnectionManager("sensor")
alert_manager = ConnectionManager("alert")
reader = RedisPubSubReader(sensor_manager, alert_manager)

@app.get("/")
async def root():
    return {"status": "ok"}

@app.websocket("/ws/sensor")
async def sensor_websocket(websocket: WebSocket):
    await sensor_manager.connect(websocket)
    try:
        while True:
            try:
                # 클라이언트 메시지 대기 (30초 타임아웃)
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # 연결 유지를 위한 ping 전송
                await websocket.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        sensor_manager.disconnect(websocket)

@app.websocket("/ws/alert")
async def alert_websocket(websocket: WebSocket):
    await alert_manager.connect(websocket)
    try:
        while True:
            try:
                # 클라이언트 메시지 대기 (30초 타임아웃)
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # 연결 유지를 위한 ping 전송
                await websocket.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        alert_manager.disconnect(websocket)



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=WEBSOCKET_HOST, port=WEBSOCKET_PORT)
