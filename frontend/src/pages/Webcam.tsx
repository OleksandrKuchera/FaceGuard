import { useEffect, useRef, useState, useCallback } from 'react';
import Layout from '@/components/Layout';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { ScrollArea } from '@/components/ui/scroll-area';
import { getValidAccessToken, refreshAccessToken } from '@/api/client';
import { toast } from 'sonner';
import { Link, Navigate, useParams } from 'react-router-dom';
import type { WsFace } from '@/types';
import {
  Video, VideoOff, Camera as CameraIcon,
  Wifi, WifiOff, AlertTriangle,
  Settings2, ArrowLeft,
} from 'lucide-react';
import { getDemoCameraById } from '@/utils/demoCameras';

const WS_BASE = import.meta.env.VITE_WS_URL || `ws://${window.location.host}`;

interface FaceEvent {
  key: string;
  ts: string;
  faces: WsFace[];
  count: number;
}

const EVENT_LOG_COOLDOWN_MS = 5000;

function fmt(value: number | null | undefined, digits = 3) {
  if (typeof value === 'number') return value.toFixed(digits);
  if (value === null) return 'not_available';
  return 'not_provided';
}

function fmtText(value: string | null | undefined) {
  if (typeof value === 'string' && value.length > 0) return value;
  if (value === null) return 'not_available';
  return 'not_provided';
}

function fmtBool(value: boolean | null | undefined) {
  if (value === true) return 'true';
  if (value === false) return 'false';
  if (value === null) return 'not_available';
  return 'not_provided';
}

function debugLines(face: WsFace) {
  const baseline = face.open_eye_baseline != null
    ? fmt(face.open_eye_baseline)
    : face.baseline_required_frames != null
      ? `collecting ${face.baseline_buffer_size ?? 0}/${face.baseline_required_frames}`
      : '—';
  return [
    `Liveness: ${face.final_status ?? face.liveness_state ?? '—'}`,
    `Reason: ${fmtText(face.final_reason_code)}`,
    `Blinks: ${face.blink_count ?? 0}/${face.min_blinks_required ?? 1}`,
    `Eye: ${fmtText(face.eye_state)}`,
    `EAR: ${fmt(face.current_ear_avg)}`,
    `Base: ${baseline}`,
    `Drop/Rec ratios: ${fmt(face.drop_ratio)}/${fmt(face.recovery_ratio)}`,
    `Dn/Rc thr: ${face.blink_down_threshold != null ? fmt(face.blink_down_threshold) : 'wait'}/${face.blink_recovery_threshold != null ? fmt(face.blink_recovery_threshold) : 'wait'}`,
    `Texture: ${fmtText(face.texture_combined_status)}`,
    `Quality: ${fmtText(face.face_quality_status)}`,
  ];
}

function getFaceLogKey(face: WsFace) {
  if (face.is_warming_up) {
    return `warming:${face.track_id ?? 'na'}`;
  }
  if (face.is_spoofing) {
    return `spoof:${face.track_id ?? 'na'}`;
  }
  if (face.person_id != null) {
    return `person:${face.person_id}`;
  }
  return `unknown:${face.track_id ?? 'na'}`;
}

function buildEventKey(faces: WsFace[]) {
  return faces
    .map(getFaceLogKey)
    .sort()
    .join('|');
}

// Кольори для різних зон обличчя
const LANDMARK_COLORS: Record<string, string> = {
  chin: '#00bcd4',          // контур обличчя — бірюзовий
  left_eyebrow: '#ff9800',  // ліва брова — помаранчевий
  right_eyebrow: '#ff9800', // права брова — помаранчевий
  nose_bridge: '#4caf50',   // перенісся — зелений
  nose_tip: '#4caf50',      // кінчик носа — зелений
  left_eye: '#2196f3',      // ліве око — синій
  right_eye: '#2196f3',     // праве око — синій
  top_lip: '#e91e63',       // верхня губа — рожевий
  bottom_lip: '#e91e63',    // нижня губа — рожевий
};

function drawLandmarks(
  ctx: CanvasRenderingContext2D,
  landmarks: Record<string, [number, number][]>,
  colorOverride?: string,
) {
  for (const [region, points] of Object.entries(landmarks)) {
    const color = colorOverride || LANDMARK_COLORS[region] || '#ffffff';
    ctx.fillStyle = color;
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.5;

    for (const [x, y] of points) {
      // Точка
      ctx.beginPath();
      ctx.arc(x, y, 2.5, 0, 2 * Math.PI);
      ctx.fill();
    }

    // З'єднуємо точки лінією для контуру
    if (points.length > 2) {
      ctx.beginPath();
      ctx.moveTo(points[0][0], points[0][1]);
      for (let i = 1; i < points.length; i++) {
        ctx.lineTo(points[i][0], points[i][1]);
      }
      ctx.globalAlpha = 0.4;
      ctx.stroke();
      ctx.globalAlpha = 1.0;
    }
  }
}

function mirrorBBox(
  bbox: { top: number; right: number; bottom: number; left: number },
  width: number,
) {
  return {
    top: bbox.top,
    bottom: bbox.bottom,
    left: width - bbox.right,
    right: width - bbox.left,
  };
}

function mirrorLandmarks(
  landmarks: Record<string, [number, number][]>,
  width: number,
) {
  const mirrored: Record<string, [number, number][]> = {};
  for (const [region, points] of Object.entries(landmarks)) {
    mirrored[region] = points.map(([x, y]) => [width - x, y] as [number, number]);
  }
  return mirrored;
}

export default function Webcam() {
  const params = useParams();
  const cameraId = Number(params.id);
  const camera = Number.isFinite(cameraId) ? getDemoCameraById(cameraId) : null;

  const videoRef = useRef<HTMLVideoElement>(null);
  const displayCanvasRef = useRef<HTMLCanvasElement>(null);
  const captureCanvasRef = useRef<HTMLCanvasElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const frameInFlightRef = useRef(false);
  const wsConnectedRef = useRef(false);
  const lastEventAtRef = useRef<Map<string, number>>(new Map());

  const [streamActive, setStreamActive] = useState(false);
  const [wsConnected, setWsConnected] = useState(false);
  const [fps, setFps] = useState(0);
  const [processingMs, setProcessingMs] = useState(0);
  const [events, setEvents] = useState<FaceEvent[]>([]);
  const [faces, setFaces] = useState<WsFace[]>([]);
  const [frameRate, setFrameRate] = useState(30);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [videoReady, setVideoReady] = useState(false);

  if (!camera) {
    return <Navigate to="/cameras" replace />;
  }

  // ── Camera ────────────────────────────────────────────────────────

  const startCamera = useCallback(async () => {
    try {
      setCameraError(null);
      setVideoReady(false);
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 1280 },
          height: { ideal: 720 },
          facingMode: 'user',
        },
        audio: false,
      });
      streamRef.current = stream;
      setStreamActive(true);
      toast.success('Камеру підключено');
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Unknown error';
      setCameraError(msg);
      toast.error(`Помилка камери: ${msg}`);
    }
  }, []);

  useEffect(() => {
    if (!streamActive) return;

    const video = videoRef.current;
    const stream = streamRef.current;
    if (!video || !stream) return;

    let cancelled = false;
    let timeoutId: ReturnType<typeof setTimeout> | null = null;

    const tryPlay = async () => {
      try {
        await video.play();
        if (!cancelled) {
          setVideoReady(true);
        }
      } catch (err) {
        if (!cancelled) {
          console.warn('[Webcam] video.play() retry pending:', err);
        }
      }
    };

    video.srcObject = stream;
    video.muted = true;
    video.playsInline = true;

    const onReady = () => {
      void tryPlay();
    };

    video.addEventListener('loadedmetadata', onReady);
    video.addEventListener('canplay', onReady);
    void tryPlay();

    timeoutId = window.setTimeout(() => {
      if (!cancelled && video.videoWidth > 0 && video.videoHeight > 0) {
        setVideoReady(true);
        return;
      }
      if (!cancelled) {
        setCameraError('Camera did not become ready in time');
      }
    }, 5000);

    return () => {
      cancelled = true;
      if (timeoutId) window.clearTimeout(timeoutId);
      video.removeEventListener('loadedmetadata', onReady);
      video.removeEventListener('canplay', onReady);
    };
  }, [streamActive]);

  const stopCamera = useCallback(() => {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach(t => t.stop());
      streamRef.current = null;
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }
    setStreamActive(false);
    setWsConnected(false);
    setVideoReady(false);
    setEvents([]);
    wsConnectedRef.current = false;
    frameInFlightRef.current = false;
    lastEventAtRef.current.clear();
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    toast.info('Камеру вимкнено');
  }, []);

  // ── WebSocket ─────────────────────────────────────────────────────

  const connectWs = useCallback(async () => {
    const token = await getValidAccessToken();
    if (!token) {
      toast.error('Сесія авторизації недійсна. Увійдіть повторно.');
      window.location.href = '/login';
      return;
    }

    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }

    const ws = new WebSocket(`${WS_BASE}/ws/webcam/?token=${token}&camera_id=${camera.id}`);
    wsRef.current = ws;

    ws.onopen = () => {
      console.log('[Webcam] WS connected');
      setWsConnected(true);
      wsConnectedRef.current = true;
      toast.success('З\'єднання з сервером встановлено');
    };

    ws.onclose = async (event) => {
      console.log('[Webcam] WS closed');
      setWsConnected(false);
      wsConnectedRef.current = false;
      setFps(0);
      frameInFlightRef.current = false;

      if (event.code === 4001) {
        const refreshedToken = await refreshAccessToken();
        if (refreshedToken) {
          const retryWs = new WebSocket(`${WS_BASE}/ws/webcam/?token=${refreshedToken}&camera_id=${camera.id}`);
          wsRef.current = retryWs;
          retryWs.onopen = ws.onopen;
          retryWs.onclose = ws.onclose;
          retryWs.onerror = ws.onerror;
          retryWs.onmessage = ws.onmessage;
          return;
        }

        toast.error('Сесію завершено. Потрібен повторний вхід.');
        window.location.href = '/login';
      }
    };

    ws.onerror = (e) => {
      console.error('[Webcam] WS error:', e);
      toast.error('Помилка WebSocket з\'єднання');
    };

    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data as string);

        if (data.type === 'result') {
          frameInFlightRef.current = false;
          setFps(data.fps ?? 0);
          setProcessingMs(data.processing_ms ?? 0);
          setFaces((data.faces as WsFace[]) ?? []);

          const canvas = displayCanvasRef.current;
          const video = videoRef.current;
          if (!canvas || !video) return;

          const vw = video.videoWidth;
          const vh = video.videoHeight;
          if (vw === 0 || vh === 0) return;

          canvas.width = vw;
          canvas.height = vh;
          const ctx = canvas.getContext('2d');
          if (!ctx) return;

          ctx.clearRect(0, 0, canvas.width, canvas.height);

          // Draw landmarks for each face
          data.faces?.forEach((face: WsFace) => {
            const color = face.is_warming_up
              ? '#6b7280'
              : face.is_in_cooldown
                ? '#38bdf8'
              : face.is_spoofing ? '#ef4444'
              : face.is_known ? '#10b981'
              : '#f59e0b';

            const mirroredBBox = mirrorBBox(face.bbox, canvas.width);
            const mirroredLandmarks = face.landmarks && Object.keys(face.landmarks).length > 0
              ? mirrorLandmarks(face.landmarks, canvas.width)
              : null;

            ctx.strokeStyle = color;
            ctx.lineWidth = 2;
            ctx.strokeRect(
              mirroredBBox.left,
              mirroredBBox.top,
              mirroredBBox.right - mirroredBBox.left,
              mirroredBBox.bottom - mirroredBBox.top,
            );

            // 68 landmarks points
            if (mirroredLandmarks) {
              drawLandmarks(ctx, mirroredLandmarks, color);
            }

            // Label
            let label = face.is_warming_up
              ? '⏳ Warming up...'
              : face.is_in_cooldown
                ? '⏸ Cooldown'
                : (face.person_name ?? 'Unknown');
            if (face.track_id != null) label += ` #${face.track_id}`;
            if (!face.is_warming_up && !face.is_in_cooldown && face.confidence != null) label += ` ${face.confidence.toFixed(0)}%`;
            if (face.is_spoofing) {
              label = `⚠ SPOOF (${face.liveness_reason ?? 'blink check failed'})`;
            } else if (face.liveness_state === 'INSUFFICIENT_DATA') {
              label = '… Insufficient data';
            }

            // Position label near the face
            const labelX = (mirroredBBox.left + mirroredBBox.right) / 2;
            const labelY = mirroredBBox.top > 30 ? mirroredBBox.top - 10 : mirroredBBox.bottom + 20;

            ctx.font = 'bold 14px Inter, sans-serif';
            const metrics = ctx.measureText(label);
            const labelW = metrics.width + 16;
            const labelH = 24;

            ctx.fillStyle = 'rgba(0,0,0,0.75)';
            ctx.beginPath();
            ctx.roundRect(labelX - labelW / 2, labelY - labelH, labelW, labelH, 4);
            ctx.fill();

            ctx.fillStyle = color;
            ctx.textAlign = 'center';
            ctx.fillText(label, labelX, labelY - 6);
            ctx.textAlign = 'start';

            if (face.debug_enabled || face.current_ear_avg !== undefined || face.current_ear_avg === null) {
              const lines = debugLines(face);
              const overlayX = mirroredBBox.left;
              const overlayY = mirroredBBox.bottom + 8;
              const lineHeight = 12;
              const panelWidth = 170;
              const panelHeight = (lines.length * lineHeight) + 10;
              ctx.fillStyle = 'rgba(0,0,0,0.68)';
              ctx.fillRect(overlayX, overlayY, panelWidth, panelHeight);
              ctx.fillStyle = '#ffffff';
              ctx.font = '11px monospace';
              lines.forEach((line, idx) => {
                ctx.fillText(line, overlayX + 6, overlayY + 14 + (idx * lineHeight));
              });
            }
          });

          // Log events
          if (data.faces?.length) {
            const activeFaces = (data.faces as WsFace[]).filter(
              face => !face.is_warming_up && !face.is_in_cooldown && face.liveness_state !== 'INSUFFICIENT_DATA',
            );
            if (activeFaces.length > 0) {
              const now = Date.now();
              const eventKey = buildEventKey(activeFaces);
              const lastEventAt = lastEventAtRef.current.get(eventKey) ?? 0;

              setEvents(prev => {
                if (now - lastEventAt < EVENT_LOG_COOLDOWN_MS) {
                  return prev.map(event =>
                    event.key === eventKey
                      ? {
                          ...event,
                          ts: new Date().toLocaleTimeString('uk-UA'),
                          faces: activeFaces,
                          count: event.count + 1,
                        }
                      : event
                  );
                }

                lastEventAtRef.current.set(eventKey, now);
                return [{
                  key: eventKey,
                  ts: new Date().toLocaleTimeString('uk-UA'),
                  faces: activeFaces,
                  count: 1,
                }, ...prev].slice(0, 20);
              });
            }
          }
        }

        if (data.type === 'error') {
          frameInFlightRef.current = false;
          toast.error(`Сервер: ${data.message}`);
        }
      } catch (err) {
        console.error('[Webcam] WS message parse error:', err);
      }
    };
  }, [camera.id]);

  const disconnectWs = useCallback(() => {
    if (wsRef.current) {
      wsRef.current.close();
      wsRef.current = null;
    }
    setWsConnected(false);
    wsConnectedRef.current = false;
  }, []);

  // ── Effects ───────────────────────────────────────────────────────

  useEffect(() => {
    if (streamActive && !wsConnected) {
      void connectWs();
    }
    return () => {
      if (!streamActive) disconnectWs();
    };
  }, [streamActive, wsConnected, connectWs, disconnectWs]);

  useEffect(() => {
    if (intervalRef.current) {
      clearInterval(intervalRef.current);
      intervalRef.current = null;
    }

    if (streamActive && wsConnectedRef.current) {
      const ms = 1000 / frameRate;
      intervalRef.current = setInterval(() => {
        const video = videoRef.current;
        const ws = wsRef.current;
        const canvas = captureCanvasRef.current;
        if (!video || !ws || !canvas) return;
        if (ws.readyState !== WebSocket.OPEN) return;
        if (frameInFlightRef.current) return;
        if (video.readyState < 2) return;
        if (video.videoWidth === 0 || video.videoHeight === 0) return;

        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        frameInFlightRef.current = true;

        ctx.drawImage(video, 0, 0);
        const dataUrl = canvas.toDataURL('image/jpeg', 0.85);
        ws.send(JSON.stringify({ action: 'frame', frame: dataUrl }));
      }, ms);
    }

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [streamActive, wsConnected, frameRate]);

  useEffect(() => {
    return () => {
      if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop());
      if (wsRef.current) wsRef.current.close();
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, []);

  // ── Render ────────────────────────────────────────────────────────

  return (
    <Layout title={camera.name}>
      <div className="page-header">
        <div>
          <div className="mb-3">
            <Button asChild variant="ghost" size="sm" className="text-white/60 hover:text-white px-0">
              <Link to="/cameras">
                <ArrowLeft size={14} />
                Назад до камер
              </Link>
            </Button>
          </div>
          <h1>{camera.name}</h1>
          <div className="page-subtitle">
            {camera.location} • Розпізнавання, spoofing-аналіз і події в реальному часі
          </div>
        </div>
        <div className="flex items-center gap-2">
          {streamActive ? (
            <Badge className="bg-emerald-500/20 text-emerald-400 border-0 gap-1">
              <Video size={12} /> Камера активна
            </Badge>
          ) : (
            <Badge className="bg-gray-500/20 text-gray-400 border-0 gap-1">
              <VideoOff size={12} /> Камера вимкнена
            </Badge>
          )}
          {wsConnected && (
            <Badge className="bg-blue-500/20 text-blue-400 border-0 gap-1">
              <Wifi size={10} /> Сервер
            </Badge>
          )}
        </div>
      </div>

      <Separator className="mb-6 bg-white/10" />

        <div className="flex flex-wrap items-center gap-3 mb-6">
        {!streamActive ? (
          <Button onClick={startCamera} className="gap-2">
            <CameraIcon size={16} />
            Увімкнути {camera.name}
          </Button>
        ) : (
          <Button variant="destructive" onClick={stopCamera} className="gap-2">
            <VideoOff size={16} />
            Вимкнути камеру
          </Button>
        )}

        {streamActive && (
          <>
            {!wsConnected ? (
              <Button variant="outline" onClick={connectWs} className="gap-2">
                <Wifi size={14} />
                Підключитись до сервера
              </Button>
            ) : (
              <Button variant="outline" onClick={disconnectWs} className="gap-2">
                <WifiOff size={14} />
                Відключитись
              </Button>
            )}

            <div className="flex items-center gap-2 ml-auto">
              <Settings2 size={14} className="text-white/40" />
              <label className="text-xs text-white/60">FPS:</label>
              <select
                value={frameRate}
                onChange={e => setFrameRate(Number(e.target.value))}
                className="bg-[var(--fg-surface)] border border-white/10 rounded px-2 py-1 text-xs text-white"
              >
                <option value={1}>1</option>
                <option value={2}>2</option>
                <option value={4}>4</option>
                <option value={8}>8</option>
                <option value={15}>15</option>
                <option value={30}>30</option>
              </select>
            </div>
          </>
        )}
      </div>

      {cameraError && (
        <div className="mb-4 p-4 rounded-lg bg-red-500/10 border border-red-500/20">
          <p className="text-red-400 text-sm">⚠ Не вдалося підключити камеру: {cameraError}</p>
          <p className="text-white/40 text-xs mt-1">
            Перевірте System Settings → Privacy & Security → Camera
          </p>
        </div>
      )}

      {!streamActive ? (
        <div className="empty-state">
          <CameraIcon size={48} className="mx-auto mb-3 text-white/20" />
          <p>{camera.name} ще не підключена.</p>
          <p className="text-xs mt-1">Натисніть «Увімкнути {camera.name}» для початку розпізнавання.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          <div className="lg:col-span-2">
            <div className="relative rounded-lg overflow-hidden border border-white/10" style={{ aspectRatio: '16/9' }}>
              <video
                ref={videoRef}
                autoPlay
                playsInline
                muted
                className="absolute inset-0 w-full h-full object-cover bg-black"
                style={{ transform: 'scaleX(-1)' }}
              />

              <canvas
                ref={displayCanvasRef}
                className="absolute inset-0 w-full h-full object-cover"
                style={{ display: streamActive ? 'block' : 'none', pointerEvents: 'none' }}
              />

              <div className="absolute top-3 left-3 flex gap-2">
                {wsConnected ? (
                  <Badge className="bg-emerald-500/80 text-white border-0 text-[10px]">
                    <Wifi size={8} className="mr-1" /> LIVE
                  </Badge>
                ) : (
                  <Badge className="bg-gray-500/80 text-white border-0 text-[10px]">
                    <WifiOff size={8} className="mr-1" /> NO SERVER
                  </Badge>
                )}
                <Badge className="bg-black/60 text-white border-0 text-[10px]">
                  {fps.toFixed(1)} FPS
                </Badge>
                <Badge className="bg-black/60 text-white border-0 text-[10px]">
                  {processingMs.toFixed(0)}ms
                </Badge>
              </div>
              {!videoReady && (
                <div className="absolute inset-0 flex items-center justify-center bg-black/50 text-white/60 text-sm">
                  Завантаження камери...
                </div>
              )}
            </div>

            {/* Legend */}
            <div className="flex flex-wrap gap-3 mt-3 text-xs text-white/50">
              <span className="flex items-center gap-1">
                <span className="w-3 h-3 rounded-full bg-emerald-500 inline-block" />
                Відома особа
              </span>
              <span className="flex items-center gap-1">
                <span className="w-3 h-3 rounded-full bg-amber-500 inline-block" />
                Невідома особа
              </span>
              <span className="flex items-center gap-1">
                <span className="w-3 h-3 rounded-full bg-red-500 inline-block" />
                Спуфінг
              </span>
              <span className="flex items-center gap-1">
                <span className="w-3 h-3 rounded-full bg-gray-500 inline-block" />
                Warming up
              </span>
              <span className="ml-auto flex items-center gap-1">
                <span className="w-3 h-3 rounded-full bg-[#00bcd4] inline-block" />
                Контур обличчя
              </span>
              <span className="flex items-center gap-1">
                <span className="w-3 h-3 rounded-full bg-[#ff9800] inline-block" />
                Брови
              </span>
              <span className="flex items-center gap-1">
                <span className="w-3 h-3 rounded-full bg-[#4caf50] inline-block" />
                Ніс
              </span>
              <span className="flex items-center gap-1">
                <span className="w-3 h-3 rounded-full bg-[#2196f3] inline-block" />
                Очі
              </span>
              <span className="flex items-center gap-1">
                <span className="w-3 h-3 rounded-full bg-[#e91e63] inline-block" />
                Рот
              </span>
            </div>
          </div>

          <div className="lg:col-span-1">
            <div className="rounded-lg border border-white/10 bg-[var(--fg-surface)] overflow-hidden mb-4">
              <div className="px-4 py-3 border-b border-white/10 flex items-center justify-between gap-2">
                <h3 className="text-sm font-semibold text-white/80">Liveness Diagnostics</h3>
                <Badge className={`${faces.some(face => face.debug_enabled) ? 'bg-cyan-500/20 text-cyan-300' : 'bg-white/10 text-white/40'} border-0`}>
                  {faces.some(face => face.debug_enabled) ? 'DEBUG ON' : 'DEBUG OFF'}
                </Badge>
              </div>
              <ScrollArea className="h-[240px]">
                <div className="p-3 space-y-3">
                  {!faces.length && (
                    <div className="text-center text-xs text-white/30 py-8">
                      Очікування liveness cycle...
                    </div>
                  )}
                  {faces.map((face, idx) => (
                    <div key={`${face.track_id ?? 'na'}-${idx}`} className="rounded-lg border border-white/10 bg-black/20 p-3">
                      <div className="flex items-center justify-between gap-2 mb-2">
                        <div className="text-xs text-white/80">
                          Track #{face.track_id ?? '—'} • {face.final_status ?? face.liveness_state ?? '—'}
                        </div>
                        <Badge className="bg-white/10 text-white/70 border-0 text-[10px]">
                          {face.final_module_name ?? '—'}
                        </Badge>
                      </div>
                      {!face.debug_enabled && (
                        <div className="mb-2 rounded bg-amber-500/10 border border-amber-500/20 px-2 py-1 text-[11px] text-amber-200">
                          DEBUG OFF. {face.debug_hint ?? 'Set LIVENESS_DEBUG_OVERLAY=True for raw debug object and structured logs.'}
                        </div>
                      )}
                      <div className="grid grid-cols-2 gap-2 text-[11px] text-white/70">
                        <div>Liveness: {fmtText(face.liveness_state)}</div>
                        <div>Final: {fmtText(face.final_status)}</div>
                        <div>Reason: {fmtText(face.final_reason_code)}</div>
                        <div>Module: {fmtText(face.final_module_name)}</div>
                        <div>Blinks: {face.blink_count ?? 0}/{face.min_blinks_required ?? 1}</div>
                        <div>Blink status: {fmtText(face.blink_liveness_status)}</div>
                        <div>Eye: {fmtText(face.eye_state)}</div>
                        <div>EAR avg: {fmt(face.current_ear_avg)}</div>
                        <div>EAR L/R: {fmt(face.current_ear_left)}/{fmt(face.current_ear_right)}</div>
                        <div>Smoothed: {fmt(face.smoothed_ear)}</div>
                        <div>
                          Baseline: {face.open_eye_baseline != null
                            ? fmt(face.open_eye_baseline)
                            : face.baseline_required_frames != null
                              ? `collecting ${face.baseline_buffer_size ?? 0}/${face.baseline_required_frames}`
                              : '—'}
                        </div>
                        <div>Drop ratio: {fmt(face.drop_ratio)}</div>
                        <div>Recovery ratio: {fmt(face.recovery_ratio)}</div>
                        <div>
                          Down threshold: {face.blink_down_threshold != null ? fmt(face.blink_down_threshold) : 'waiting_for_baseline'}
                        </div>
                        <div>
                          Recovery threshold: {face.blink_recovery_threshold != null ? fmt(face.blink_recovery_threshold) : 'waiting_for_baseline'}
                        </div>
                        <div>Baseline state: {fmtText(face.baseline_state)}</div>
                        <div>Blink state: {fmtText(face.blink_internal_state)}</div>
                        <div>Closed/Open frames: {face.frames_closed_count ?? '—'}/{face.frames_open_count ?? '—'}</div>
                        <div>Valid/Missing EAR: {face.valid_ear_frames_count ?? '—'}/{face.missing_landmarks_count ?? '—'}</div>
                        <div>Min/Max EAR: {fmt(face.min_ear_seen_during_warmup)}/{fmt(face.max_ear_seen_during_warmup)}</div>
                        <div>Prev eye: {fmtText(face.previous_eye_state)}</div>
                        <div>Warmup: {fmt(face.warmup_elapsed_seconds, 2)}s / rem {fmt(face.warmup_remaining_seconds, 2)}s</div>
                        <div>Cooldown rem: {fmt(face.cooldown_remaining_seconds, 2)}s</div>
                        <div>Texture: {fmtText(face.texture_combined_status)}</div>
                        <div>LBP/Sobel/FFT: {fmtText(face.texture_lbp_status)}/{fmtText(face.texture_sobel_status)}/{fmtText(face.texture_fft_status)}</div>
                        <div>Face quality: {fmtText(face.face_quality_status)}</div>
                        <div>Score: {fmt(face.texture_score)}</div>
                        <div>Detector called: {fmtBool(face.blink_detector_called)}</div>
                        <div>Landmarks found: {fmtBool(face.landmarks_found)}</div>
                        <div>Reason code: {fmtText(face.blink_reason_code)}</div>
                      </div>
                    </div>
                  ))}
                </div>
              </ScrollArea>
            </div>
            <div className="rounded-lg border border-white/10 bg-[var(--fg-surface)] overflow-hidden">
              <div className="px-4 py-3 border-b border-white/10">
                <h3 className="text-sm font-semibold text-white/80">Події розпізнавання</h3>
              </div>
              <ScrollArea className="h-[500px]">
                <div className="p-3 space-y-2">
                  {events.length === 0 ? (
                    <div className="text-center text-xs text-white/30 py-8">
                      Очікування облич...
                    </div>
                  ) : (
                    events.map((ev) => (
                      <div key={`${ev.key}-${ev.ts}`} className="p-2 rounded bg-white/5 text-xs">
                        <div className="flex items-center justify-between gap-2">
                          <span className="text-white/30">{ev.ts}</span>
                          {ev.count > 1 && (
                            <Badge className="bg-white/10 text-white/60 border-0 text-[10px]">
                              x{ev.count}
                            </Badge>
                          )}
                        </div>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {ev.faces.map((f, j) => (
                            <Badge
                              key={j}
                              className={`text-[10px] border-0 ${
                                f.is_warming_up ? 'bg-gray-500/20 text-gray-400'
                                  : f.is_spoofing ? 'bg-red-500/20 text-red-400'
                                  : f.is_known ? 'bg-emerald-500/20 text-emerald-400'
                                  : 'bg-amber-500/20 text-amber-400'
                              }`}
                            >
                              {f.is_spoofing && <AlertTriangle size={9} className="mr-1" />}
                              {f.is_warming_up ? '⏳ Warming up'
                                : f.is_spoofing ? 'SPOOF blink failed'
                                : `${f.person_name ?? 'Unknown'}${f.track_id != null ? ` #${f.track_id}` : ''}${f.confidence != null ? ` ${f.confidence.toFixed(0)}%` : ''}`
                              }
                            </Badge>
                          ))}
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </ScrollArea>
            </div>
          </div>
        </div>
      )}

      <canvas ref={captureCanvasRef} className="hidden" />
    </Layout>
  );
}
