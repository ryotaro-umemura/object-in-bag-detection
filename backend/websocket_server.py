"""
WebSocket サーバーモジュール

物体通過イベントを WebSocket 経由でクライアントに送信する。
"""

import asyncio
import json
from typing import Set
import websockets
from websockets.server import WebSocketServerProtocol

# 接続中のクライアントを保持
connected_clients: Set[WebSocketServerProtocol] = set()

# イベントキュー（メインスレッドからイベントを受け取る）
event_queue: asyncio.Queue = None


async def handler(websocket: WebSocketServerProtocol):
    """WebSocket 接続ハンドラ"""
    connected_clients.add(websocket)
    print(f"WebSocket クライアント接続: {websocket.remote_address}")
    try:
        # 接続を維持（クライアントからのメッセージは無視）
        async for _ in websocket:
            pass
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        connected_clients.discard(websocket)
        print(f"WebSocket クライアント切断: {websocket.remote_address}")


async def broadcast(message: dict):
    """全クライアントにメッセージをブロードキャスト"""
    if connected_clients:
        message_json = json.dumps(message, ensure_ascii=False)
        await asyncio.gather(
            *[client.send(message_json) for client in connected_clients],
            return_exceptions=True
        )


async def event_broadcaster():
    """イベントキューからメッセージを取り出してブロードキャスト"""
    global event_queue
    while True:
        event = await event_queue.get()
        await broadcast(event)


async def start_server(host: str = "localhost", port: int = 8765):
    """WebSocket サーバーを起動"""
    global event_queue
    event_queue = asyncio.Queue()
    
    # イベントブロードキャスタを起動
    asyncio.create_task(event_broadcaster())
    
    async with websockets.serve(handler, host, port):
        print(f"WebSocket サーバー起動: ws://{host}:{port}")
        await asyncio.Future()  # 永続待機


def send_crossing_event(object_id: int, object_name: str, crossing_count: int):
    """
    物体通過イベントをキューに追加（同期関数）
    
    メインスレッドから呼び出して使用する。
    """
    if event_queue is None:
        return
    
    event = {
        "type": "crossing",
        "object_id": object_id,
        "object_name": object_name,
        "crossing_count": crossing_count,
        "timestamp": asyncio.get_event_loop().time()
    }
    
    try:
        event_queue.put_nowait(event)
    except Exception:
        pass  # キューが満杯の場合は無視
