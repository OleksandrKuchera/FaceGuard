import { useEffect, useRef, useState } from 'react';
import Layout from '@/components/Layout';
import { getCameras, getValidAccessToken, refreshAccessToken } from '@/api/client';
import type { Camera, WsMessage, WsFace } from '@/types';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Separator } from '@/components/ui/separator';
import { toast } from 'sonner';
import { Wifi, WifiOff, AlertTriangle, RefreshCw } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { useAlertStore } from '@/store/alertStore';

const WS_BASE = import.meta.env.VITE_WS_URL || `ws://${window.location.host}`;

interface FaceEvent {
  ts: string;
  faces: WsFace[];
}

function CameraStream({ camera }: { camera: Camera }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [fps, setFps] = useState(0);
  const [events, setEvents] = useState<FaceEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const [reconnecting, setReconnecting] = useState(false);
  const addAlert = useAlertStore(s => s.addAlert);

  const connect = async () => {
    const token = await getValidAccessToken();
    if (!token) {
      toast.error('Сесія авторизації недійсна. Увійдіть повторно.');
      window.location.href = '/login';
      return;
    }

    const ws = new WebSocket(`${WS_BASE}/ws/camera/${camera.id}/?token=${token}`);
    wsRef.current = ws;

    ws.onopen = () => { setConnected(true); setReconnecting(false); };
    ws.onclose = async (event) => {
      setConnected(false);
      setFps(0);

      if (event.code === 4001) {
        const refreshedToken = await refreshAccessToken();
        if (refreshedToken) {
          const retryWs = new WebSocket(`${WS_BASE}/ws/camera/${camera.id}/?token=${refreshedToken}`);
          wsRef.current = retryWs;
          retryWs.onopen = ws.onopen;
          retryWs.onclose = ws.onclose;
          retryWs.onmessage = ws.onmessage;
          return;
        }

        toast.error(`Сесію для "${camera.name}" завершено. Потрібен повторний вхід.`);
        window.location.href = '/login';
      }
    };

    ws.onmessage = (e) => {
      const data = JSON.parse(e.data as string) as WsMessage;

      if (data.type === 'frame') {
        setFps(data.fps);
        const img = new Image();
        img.onload = () => {
          const ctx = canvasRef.current?.getContext('2d');
          const canvas = canvasRef.current;
          if (!ctx || !canvas) return;
          canvas.width = img.width;
          canvas.height = img.height;
          ctx.drawImage(img, 0, 0);

          data.faces?.forEach((face) => {
            const { top, right, bottom, left } = face.bbox;
            const color = face.is_warming_up
              ? '#6b7280'
              : face.is_in_cooldown ? '#38bdf8'
              : face.is_spoofing ? '#ef4444'
              : face.is_known ? '#10b981'
              : '#f59e0b';
            ctx.strokeStyle = color;
            ctx.lineWidth = 2;
            ctx.strokeRect(left, top, right - left, bottom - top);
            ctx.fillStyle = color;
            ctx.font = 'bold 13px Inter, sans-serif';
            let label = face.is_warming_up
              ? '⏳ Warming up...'
              : face.is_in_cooldown
                ? '⏸ Cooldown'
                : (face.person_name ?? 'Unknown');
            if (face.track_id != null) label += ` #${face.track_id}`;
            if (!face.is_warming_up && !face.is_in_cooldown && face.confidence != null) label += ` ${face.confidence.toFixed(0)}%`;
            if (face.is_spoofing) {
              const reason = face.texture_is_spoof
                ? `texture tx:${face.texture_score.toFixed(2)}`
                : face.liveness_is_spoofing
                  ? 'liveness'
                  : `combined tx:${face.texture_score.toFixed(2)}`;
              label = `⚠ SPOOF (${reason})`;
            } else if (face.liveness_state === 'INSUFFICIENT_DATA') {
              label = '… Insufficient data';
            }
            ctx.fillText(label, left, top > 20 ? top - 6 : top + 18);
          });

          if (data.faces?.length) {
            setEvents(prev => [{
              ts: new Date().toLocaleTimeString('uk-UA'),
              faces: data.faces,
            }, ...prev].slice(0, 8));
          }
        };
        img.src = data.frame;
      }

      if (data.type === 'alert') {
        toast.error(`🚨 ${camera.name}: ${data.message}`, {
          description: new Date(data.timestamp).toLocaleString('uk-UA'),
          duration: 8000,
        });
        addAlert({
          id: `${data.event_id ?? Date.now()}`,
          level: data.alert_level,
          message: `${camera.name}: ${data.message}`,
          camera_id: data.camera_id,
          event_id: data.event_id,
          timestamp: data.timestamp,
        });
      }

      if (data.type === 'camera_status' && data.status === 'offline') {
        toast.warning(`Камера "${camera.name}" відключилась`);
        setConnected(false);
      }
    };
  };

  useEffect(() => {
    void connect();
    return () => { wsRef.current?.close(); };
  }, [camera.id]);

  const handleReconnect = () => {
    wsRef.current?.close();
    setReconnecting(true);
    setTimeout(() => { void connect(); }, 500);
  };

  return (
    <div className="camera-tile">
      <div className="camera-header">
        <div className="flex flex-col gap-0.5">
          <span className="camera-name">{camera.name}</span>
          <span className="text-xs text-white/40">{camera.location}</span>
        </div>
        <div className="flex items-center gap-2">
          {connected ? (
            <Badge className="bg-emerald-500/20 text-emerald-400 border-0 gap-1">
              <Wifi size={10} />LIVE
            </Badge>
          ) : (
            <Badge className="bg-gray-500/20 text-gray-400 border-0 gap-1">
              <WifiOff size={10} />Офлайн
            </Badge>
          )}
          {!connected && (
            <Button variant="ghost" size="icon-xs" onClick={handleReconnect} title="Перепідключити">
              <RefreshCw size={12} className={reconnecting ? 'animate-spin' : ''} />
            </Button>
          )}
          <span className="fps-badge">{fps.toFixed(1)} FPS</span>
        </div>
      </div>

      <div className="camera-canvas-wrap">
        <canvas ref={canvasRef} />
        {!connected && (
          <div className="absolute inset-0 flex flex-col items-center justify-center bg-black/60 gap-2">
            <WifiOff size={32} className="text-white/30" />
            <span className="text-white/40 text-sm">Немає з'єднання</span>
          </div>
        )}
      </div>

      <ScrollArea className="face-events">
        {events.length === 0 ? (
          <div className="text-center text-xs text-white/30 py-4">Очікування подій...</div>
        ) : (
          events.map((ev, i) => (
            <div className="face-event" key={i}>
              <span className="text-white/30 min-w-[60px] text-[11px]">{ev.ts}</span>
              <div className="flex flex-wrap gap-1">
                {ev.faces.map((f, j) => (
                  <Badge
                    key={j}
                    className={`text-[10px] border-0 ${
                      f.is_warming_up
                        ? 'bg-gray-500/20 text-gray-400'
                        : f.is_spoofing
                          ? 'bg-red-500/20 text-red-400'
                          : f.is_known
                            ? 'bg-emerald-500/20 text-emerald-400'
                            : 'bg-amber-500/20 text-amber-400'
                    }`}
                  >
                    {f.is_spoofing && <AlertTriangle size={9} />}
                    {f.is_warming_up
                      ? '⏳ Warming up'
                      : f.is_spoofing
                        ? `SPOOF ${
                          f.texture_is_spoof
                            ? `texture tx:${f.texture_score.toFixed(2)}`
                            : f.liveness_is_spoofing
                              ? 'liveness'
                              : `combined tx:${f.texture_score.toFixed(2)}`
                        }`
                        : `${f.person_name ?? 'Unknown'}${f.track_id != null ? ` #${f.track_id}` : ''}${f.confidence != null ? ` ${f.confidence.toFixed(0)}%` : ''}`
                    }
                  </Badge>
                ))}
              </div>
            </div>
          ))
        )}
      </ScrollArea>
    </div>
  );
}

export default function Monitor() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getCameras()
      .then(r => setCameras((r.data as { results?: Camera[] }).results ?? (r.data as Camera[])))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const activeCameras = cameras.filter(c => c.status === 'active');

  return (
    <Layout title="Live Monitor">
      <div className="page-header">
        <div>
          <h1>Live Monitor</h1>
          <div className="page-subtitle">Real-time відеопотік з усіх активних камер</div>
        </div>
        <div className="flex items-center gap-2">
          <Badge variant="outline" className="text-white/50 border-white/20">
            {activeCameras.length} камер активно
          </Badge>
          <Button variant="ghost" size="sm" onClick={() => {
            setLoading(true);
            getCameras()
              .then(r => setCameras((r.data as { results?: Camera[] }).results ?? (r.data as Camera[])))
              .catch(() => {})
              .finally(() => setLoading(false));
          }}>
            <RefreshCw size={14} />
            Оновити
          </Button>
        </div>
      </div>

      <Separator className="mb-6 bg-white/10" />

      {loading ? (
        <div className="spinner" />
      ) : activeCameras.length === 0 ? (
        <div className="empty-state">
          <WifiOff size={40} className="mx-auto mb-3 text-white/20" />
          <p>Активних камер не знайдено.</p>
          <p className="text-xs mt-1">Додайте та запустіть камеру в розділі «Камери».</p>
        </div>
      ) : (
        <div className="cameras-grid">
          {activeCameras.map(cam => (
            <CameraStream key={cam.id} camera={cam} />
          ))}
        </div>
      )}
    </Layout>
  );
}
