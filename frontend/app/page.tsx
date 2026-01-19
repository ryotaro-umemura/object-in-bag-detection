'use client';

import { useState, useEffect, useRef } from 'react';

interface CrossingEvent {
  type: string;
  object_id: number;
  object_name: string;
  crossing_count: number;
  timestamp: number;
}

type ConnectionStatus = 'connecting' | 'connected' | 'disconnected';

export default function Home() {
  const [events, setEvents] = useState<CrossingEvent[]>([]);
  const [status, setStatus] = useState<ConnectionStatus>('connecting');
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    const connect = () => {
      const ws = new WebSocket('ws://localhost:8765');
      wsRef.current = ws;

      ws.onopen = () => {
        setStatus('connected');
        console.log('WebSocket 接続完了');
      };

      ws.onmessage = (event) => {
        try {
          const data: CrossingEvent = JSON.parse(event.data);
          if (data.type === 'crossing') {
            setEvents((prev) => [data, ...prev].slice(0, 50)); // 最新50件を保持
          }
        } catch (e) {
          console.error('メッセージ解析エラー:', e);
        }
      };

      ws.onclose = () => {
        setStatus('disconnected');
        console.log('WebSocket 切断 - 3秒後に再接続');
        reconnectTimeoutRef.current = setTimeout(connect, 3000);
      };

      ws.onerror = (error) => {
        console.error('WebSocket エラー:', error);
        ws.close();
      };
    };

    connect();

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
      }
    };
  }, []);

  const statusColors: Record<ConnectionStatus, string> = {
    connecting: 'bg-yellow-500',
    connected: 'bg-green-500',
    disconnected: 'bg-red-500',
  };

  const statusText: Record<ConnectionStatus, string> = {
    connecting: '接続中...',
    connected: '接続済み',
    disconnected: '切断 (再接続中...)',
  };

  return (
    <div className="min-h-screen bg-white p-8">
      <div className="max-w-2xl mx-auto">
        {/* Header */}
        <div className="text-center mb-8">
          <h1 className="text-4xl font-bold text-black mb-2 tracking-tight">
            物体通過モニター
          </h1>
          <p className="text-slate-500">
            赤い枠を通過した物体をリアルタイムで表示
          </p>
        </div>

        {/* Connection Status */}
        <div className="flex items-center justify-center gap-3 mb-8">
          <span
            className={`w-3 h-3 rounded-full ${statusColors[status]} animate-pulse`}
          />
          <span className="text-black">{statusText[status]}</span>
        </div>

        {/* Events List */}
        <div className="space-y-4">
          {events.length === 0 ? (
            <div className="text-center py-16 text-slate-500">
              <div className="text-6xl mb-4">📦</div>
              <p>物体の通過を待っています...</p>
            </div>
          ) : (
            events.map((event, index) => (
              <div
                key={`${event.object_id}-${event.timestamp}-${index}`}
                className="bg-slate-50 rounded-2xl p-6 border border-slate-200 shadow-sm"
                style={{
                  animation: index === 0 ? 'slideIn 0.3s ease-out' : undefined,
                }}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className="w-12 h-12 bg-blue-500 rounded-lg flex items-center justify-center text-white font-bold text-lg">
                      {event.object_id}
                    </div>
                    <div>
                      <div className="text-lg font-semibold text-black">
                        {event.object_name}
                      </div>
                      <div className="text-slate-500 text-sm">
                        ID: {event.object_id}
                      </div>
                    </div>
                  </div>
                  <div className="text-right">
                    <div className="text-2xl font-bold text-orange-500">
                      ×{event.crossing_count}
                    </div>
                    <div className="text-slate-400 text-xs">回</div>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>

        {/* Stats */}
        {events.length > 0 && (
          <div className="mt-8 text-center text-slate-500">
            表示中: {events.length} 件
          </div>
        )}
      </div>

      <style jsx>{`
        @keyframes slideIn {
          from {
            opacity: 0;
            transform: translateY(-20px);
          }
          to {
            opacity: 1;
            transform: translateY(0);
          }
        }
      `}</style>
    </div>
  );
}
