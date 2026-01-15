
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
# 필터링 모드: 'filter' = 필터링 활성화, 'broadcast' = 모든 클라이언트에게 전송 (테스트용)
ALERT_FILTER_MODE = os.getenv('ALERT_FILTER_MODE', 'broadcast')  # 기본값은 모든 클라이언트에게 전송


class ConnectionManager:
    def __init__(self, name: str = "default"):
        self.name = name
        self.active_connections: dict[WebSocket, dict] = {}  # WebSocket -> 구독 정보

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections[websocket] = {
            "factoryId": None,
            "equipmentIds": set()
        }
        print(f"[{self.name}] Client connected. Total: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            del self.active_connections[websocket]
            print(f"[{self.name}] Client disconnected. Total: {len(self.active_connections)}")

    async def subscribe(self, websocket: WebSocket, factoryId: int = None, equipmentIds: list = None):
        """클라이언트의 구독 정보 업데이트"""
        if websocket in self.active_connections:
            self.active_connections[websocket]["factoryId"] = factoryId
            if equipmentIds:
                # 모든 equipmentId를 int로 변환하여 set에 저장
                try:
                    self.active_connections[websocket]["equipmentIds"] = {int(eid) for eid in equipmentIds}
                    print(f"[{self.name}] Subscription updated - factory={factoryId}, equipment IDs (as int)={self.active_connections[websocket]['equipmentIds']}")
                except (ValueError, TypeError) as e:
                    print(f"[{self.name}] Error converting equipment IDs to int: {e}, storing as-is")
                    self.active_connections[websocket]["equipmentIds"] = set(equipmentIds)
            else:
                print(f"[{self.name}] No equipment IDs provided, subscription for factory={factoryId} only")

    async def broadcast(self, message: str):
        """모든 클라이언트에게 브로드캐스트"""
        for connection in self.active_connections.keys():
            try:
                await connection.send_text(message)
            except Exception:
                pass

    async def broadcast_filtered(self, message: str, equipment_id: int = None):
        """필터링된 브로드캐스트 (특정 설비/공장만)"""
        try:
            data = json.loads(message)
            msg_equipment_id = data.get("equipmentId")
            
            print(f"[{self.name}] ===== FILTERING BROADCAST =====")
            print(f"[{self.name}] Message equipmentId: {msg_equipment_id} (type: {type(msg_equipment_id)})")
            print(f"[{self.name}] Full message data: {data}")
            print(f"[{self.name}] Active connections: {len(self.active_connections)}")
            
            # 연결이 없으면 로깅만 하고 종료
            if not self.active_connections:
                print(f"[{self.name}] No active connections to send to")
                return
            
            sent_count = 0
            
            for connection, subscription in self.active_connections.items():
                try:
                    # 구독 정보 디버깅 출력
                    print(f"[{self.name}] Checking connection:")
                    print(f"  - factoryId: {subscription['factoryId']}")
                    print(f"  - equipmentIds: {subscription['equipmentIds']} (type: {type(subscription['equipmentIds'])})")
                    
                    # 구독 정보가 없으면 모든 메시지 수신 (하위 호환성)
                    # OR 구독한 설비 목록이 있고 msg_equipment_id가 그 중에 있으면 전송
                    should_send = False
                    
                    if not subscription["factoryId"] and not subscription["equipmentIds"]:
                        # 구독 정보 없음 = 모든 메시지 수신
                        print(f"[{self.name}] No subscription info, sending to all")
                        should_send = True
                    elif subscription["equipmentIds"]:
                        # 구독한 설비 목록이 있음
                        # 타입 변환하여 비교 (int로 통일)
                        try:
                            msg_eq_id_int = int(msg_equipment_id) if msg_equipment_id is not None else None
                            subscription_ids_int = {int(eid) for eid in subscription["equipmentIds"]}
                            
                            print(f"[{self.name}] Comparing: {msg_eq_id_int} in {subscription_ids_int}")
                            
                            if msg_eq_id_int and msg_eq_id_int in subscription_ids_int:
                                print(f"[{self.name}] ✓ Equipment {msg_eq_id_int} MATCHES subscription!")
                                should_send = True
                            else:
                                print(f"[{self.name}] ✗ Equipment {msg_eq_id_int} NOT in {subscription_ids_int}")
                        except (ValueError, TypeError) as e:
                            print(f"[{self.name}] Type conversion error: {e}, checking with original types")
                            # 타입 변환 실패 시 원본으로 비교
                            if msg_equipment_id in subscription["equipmentIds"]:
                                print(f"[{self.name}] ✓ Equipment {msg_equipment_id} MATCHES (original type)!")
                                should_send = True
                    
                    if should_send:
                        await connection.send_text(message)
                        sent_count += 1
                        print(f"[{self.name}] ✓ Message sent successfully")
                    else:
                        print(f"[{self.name}] ✗ Message NOT sent (no match)")
                        
                except Exception as e:
                    print(f"[{self.name}] Error sending to connection: {e}")
                    import traceback
                    traceback.print_exc()
                    
            print(f"[{self.name}] ===== SENT TO {sent_count}/{len(self.active_connections)} CONNECTIONS =====")
                    
        except json.JSONDecodeError as e:
            print(f"[{self.name}] JSON decode error: {e}, broadcasting to all")
            # JSON 파싱 실패 시 모든 클라이언트에게 브로드캐스트
            await self.broadcast(message)


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
                        print(f"[ALERT] Filter mode: {ALERT_FILTER_MODE}")
                        # 필터링 모드에 따라 다르게 처리
                        if ALERT_FILTER_MODE == 'filter':
                            # 필터링된 브로드캐스트 (설비별로 필터링)
                            await self.alert_manager.broadcast_filtered(data)
                        else:
                            # 모든 클라이언트에게 브로드캐스트 (필터링 없음)
                            print(f"[ALERT] Broadcasting to all clients (no filtering)")
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
    print(f"[ALERT] New alert websocket connection")
    try:
        while True:
            try:
                # 클라이언트 메시지 대기 (30초 타임아웃)
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                print(f"[ALERT] Received from client: {data}")
                
                # 구독 정보 처리
                try:
                    msg = json.loads(data)
                    if msg.get("type") == "subscribe":
                        factoryId = msg.get("factoryId")
                        equipmentIds = msg.get("equipmentIds", [])
                        await alert_manager.subscribe(websocket, factoryId, equipmentIds)
                        print(f"[ALERT] Subscribed: factoryId={factoryId}, equipmentIds={equipmentIds}")
                        # 구독 확인 메시지 전송
                        await websocket.send_text(json.dumps({
                            "type": "subscription_confirmed",
                            "factoryId": factoryId,
                            "equipmentIds": equipmentIds
                        }))
                except json.JSONDecodeError as e:
                    print(f"[ALERT] JSON decode error: {e}")
                    
            except asyncio.TimeoutError:
                # 연결 유지를 위한 ping 전송
                await websocket.send_text(json.dumps({"type": "ping"}))
    except WebSocketDisconnect:
        alert_manager.disconnect(websocket)
        print(f"[ALERT] Client disconnected")



if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=WEBSOCKET_HOST, port=WEBSOCKET_PORT)
