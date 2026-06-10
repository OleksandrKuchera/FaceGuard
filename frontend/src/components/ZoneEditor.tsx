import { useCallback, useEffect, useRef, useState } from 'react';
import { toast } from 'sonner';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Trash2, Plus, Loader2 } from 'lucide-react';
import {
  getCameraZones, createCameraZone, deleteCameraZone, getSnapshot,
} from '@/api/client';

interface Zone {
  id: number;
  name: string;
  x1: number; y1: number; x2: number; y2: number;
  trigger_alert: boolean;
}

interface Draft {
  x1: number; y1: number; x2: number; y2: number;
  name: string;
  trigger_alert: boolean;
}

interface Props {
  open: boolean;
  cameraId: number | null;
  cameraName: string;
  onClose: () => void;
}

const COLORS = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899'];

export function ZoneEditorDialog({ open, cameraId, cameraName, onClose }: Props) {
  const canvasRef  = useRef<HTMLCanvasElement>(null);
  const imgRef     = useRef<HTMLImageElement | null>(null);
  const drawing    = useRef(false);
  const startPos   = useRef<{ x: number; y: number } | null>(null);
  const liveRect   = useRef<Draft | null>(null);

  const [zones, setZones]       = useState<Zone[]>([]);
  const [snapshot, setSnapshot] = useState<string | null>(null);
  const [loading, setLoading]   = useState(true);
  const [saving, setSaving]     = useState(false);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [draft, setDraft]       = useState<Draft | null>(null);

  const load = useCallback(async () => {
    if (!cameraId) return;
    setLoading(true);
    const [zRes, sRes] = await Promise.allSettled([
      getCameraZones(cameraId),
      getSnapshot(cameraId),
    ]);
    if (zRes.status === 'fulfilled') setZones(zRes.value.data as Zone[]);
    if (sRes.status === 'fulfilled')
      setSnapshot((sRes.value.data as { frame: string }).frame);
    else
      setSnapshot(null);
    setLoading(false);
  }, [cameraId]);

  useEffect(() => {
    if (open && cameraId) {
      setDraft(null); setSelectedId(null);
      load();
    }
  }, [open, cameraId, load]);

  // ── Canvas drawing ────────────────────────────────────────────────────────
  const redraw = useCallback(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    const W = canvas.width, H = canvas.height;

    ctx.clearRect(0, 0, W, H);

    if (imgRef.current?.complete) {
      ctx.drawImage(imgRef.current, 0, 0, W, H);
    } else {
      ctx.fillStyle = '#0d1117';
      ctx.fillRect(0, 0, W, H);
      ctx.fillStyle = 'rgba(255,255,255,0.12)';
      ctx.font = '13px monospace';
      ctx.textAlign = 'center';
      ctx.fillText('Знімок відсутній', W / 2, H / 2);
    }

    zones.forEach((z, i) => {
      const color = COLORS[i % COLORS.length];
      const x = z.x1 * W, y = z.y1 * H;
      const w = (z.x2 - z.x1) * W, h = (z.y2 - z.y1) * H;
      const sel = z.id === selectedId;

      ctx.setLineDash(z.trigger_alert ? [6, 3] : []);
      ctx.strokeStyle = sel ? '#ffffff' : color;
      ctx.lineWidth   = sel ? 2.5 : 1.5;
      ctx.strokeRect(x, y, w, h);

      ctx.fillStyle = sel ? 'rgba(255,255,255,0.10)' : `${color}28`;
      ctx.fillRect(x, y, w, h);

      // label pill
      ctx.setLineDash([]);
      ctx.font = 'bold 11px sans-serif';
      const tw = ctx.measureText(z.name).width + 10;
      ctx.fillStyle = `${color}dd`;
      ctx.beginPath();
      ctx.roundRect(x + 4, y + 4, tw, 18, 4);
      ctx.fill();
      ctx.fillStyle = '#fff';
      ctx.fillText(z.name, x + 9, y + 17);
    });

    // live drag rect
    if (liveRect.current) {
      const r = liveRect.current;
      const x = r.x1 * W, y = r.y1 * H;
      const w = (r.x2 - r.x1) * W, h = (r.y2 - r.y1) * H;
      ctx.setLineDash([5, 3]);
      ctx.strokeStyle = '#60a5fa';
      ctx.lineWidth = 2;
      ctx.strokeRect(x, y, w, h);
      ctx.fillStyle = 'rgba(96,165,250,0.12)';
      ctx.fillRect(x, y, w, h);
      ctx.setLineDash([]);
    }
  }, [zones, selectedId]);

  useEffect(() => { redraw(); }, [redraw]);

  useEffect(() => {
    if (!snapshot) return;
    const img = new Image();
    img.onload = () => { imgRef.current = img; redraw(); };
    img.src = snapshot;
  }, [snapshot, redraw]);

  // ── Mouse events ──────────────────────────────────────────────────────────
  const canvasXY = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const r = canvasRef.current!.getBoundingClientRect();
    return { x: (e.clientX - r.left) / r.width, y: (e.clientY - r.top) / r.height };
  };

  const onMouseDown = (e: React.MouseEvent<HTMLCanvasElement>) => {
    const p = canvasXY(e);
    const hit = zones.find(z => p.x >= z.x1 && p.x <= z.x2 && p.y >= z.y1 && p.y <= z.y2);
    if (hit) { setSelectedId(hit.id); setDraft(null); return; }
    setSelectedId(null); setDraft(null);
    drawing.current = true;
    startPos.current = p;
    liveRect.current = null;
  };

  const onMouseMove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!drawing.current || !startPos.current) return;
    const p = canvasXY(e);
    liveRect.current = {
      x1: Math.min(startPos.current.x, p.x), y1: Math.min(startPos.current.y, p.y),
      x2: Math.max(startPos.current.x, p.x), y2: Math.max(startPos.current.y, p.y),
      name: '', trigger_alert: false,
    };
    redraw();
  };

  const onMouseUp = (e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!drawing.current || !startPos.current) return;
    drawing.current = false;
    const p = canvasXY(e);
    const r = {
      x1: Math.min(startPos.current.x, p.x), y1: Math.min(startPos.current.y, p.y),
      x2: Math.max(startPos.current.x, p.x), y2: Math.max(startPos.current.y, p.y),
    };
    liveRect.current = null;
    if (r.x2 - r.x1 < 0.02 || r.y2 - r.y1 < 0.02) { redraw(); return; }
    setDraft({ ...r, name: `Зона ${zones.length + 1}`, trigger_alert: false });
    redraw();
  };

  // ── Save / Delete ─────────────────────────────────────────────────────────
  const handleSave = async () => {
    if (!draft || !cameraId) return;
    setSaving(true);
    try {
      await createCameraZone(cameraId, {
        name: draft.name, x1: draft.x1, y1: draft.y1, x2: draft.x2, y2: draft.y2,
        trigger_alert: draft.trigger_alert,
      });
      toast.success(`Зону «${draft.name}» збережено`);
      setDraft(null);
      load();
    } catch {
      toast.error('Помилка збереження зони');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (zoneId: number) => {
    if (!cameraId) return;
    try {
      await deleteCameraZone(cameraId, zoneId);
      toast.success('Зону видалено');
      setSelectedId(null);
      load();
    } catch {
      toast.error('Помилка видалення');
    }
  };

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) onClose(); }}>
      <DialogContent className="bg-[#1a2235] border-white/10 text-white max-w-3xl">
        <DialogHeader>
          <DialogTitle>Зони камери — {cameraName}</DialogTitle>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center justify-center h-60">
            <Loader2 className="animate-spin text-white/40" size={28} />
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            <p className="text-xs text-white/40">
              Намалюйте прямокутник для додавання зони. Клікніть на зону щоб виділити/видалити.
            </p>

            <canvas
              ref={canvasRef}
              width={640}
              height={360}
              className="w-full rounded-lg border border-white/10 cursor-crosshair select-none"
              onMouseDown={onMouseDown}
              onMouseMove={onMouseMove}
              onMouseUp={onMouseUp}
              onMouseLeave={() => {
                if (drawing.current) {
                  drawing.current = false; liveRect.current = null; redraw();
                }
              }}
            />

            {/* Draft zone form */}
            {draft && (
              <div className="flex flex-wrap items-end gap-3 p-4 rounded-xl border border-blue-500/30 bg-blue-500/5">
                <p className="w-full text-xs text-blue-300 font-medium flex items-center gap-1.5 mb-1">
                  <Plus size={12} /> Нова зона
                </p>
                <div className="flex flex-col gap-1 flex-1 min-w-40">
                  <Label className="text-white/60 text-xs">Назва</Label>
                  <Input
                    value={draft.name}
                    onChange={e => setDraft(d => d ? { ...d, name: e.target.value } : d)}
                    className="bg-[#0a0e1a] border-white/10 text-white h-8 text-sm"
                    autoFocus
                  />
                </div>
                <div className="flex flex-col gap-1 items-center">
                  <Label className="text-white/60 text-xs">Алерт</Label>
                  <Switch
                    checked={draft.trigger_alert}
                    onCheckedChange={v => setDraft(d => d ? { ...d, trigger_alert: v } : d)}
                  />
                </div>
                <Button
                  className="bg-blue-600 hover:bg-blue-500 text-white h-8 text-xs"
                  onClick={handleSave}
                  disabled={saving || !draft.name.trim()}
                >
                  {saving ? <Loader2 size={13} className="animate-spin" /> : 'Зберегти'}
                </Button>
                <Button
                  variant="ghost" size="sm"
                  className="text-white/40 hover:text-white h-8 text-xs"
                  onClick={() => { setDraft(null); liveRect.current = null; redraw(); }}
                >
                  Скасувати
                </Button>
              </div>
            )}

            {/* Saved zones list */}
            {zones.length > 0 && (
              <div className="flex flex-col gap-2">
                <p className="text-xs text-white/40 uppercase tracking-wider">Збережені зони ({zones.length})</p>
                <div className="flex flex-wrap gap-2">
                  {zones.map((z, i) => (
                    <div
                      key={z.id}
                      style={{ borderLeftColor: COLORS[i % COLORS.length] }}
                      className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border border-white/10 border-l-[3px] cursor-pointer text-sm transition-colors ${
                        z.id === selectedId ? 'bg-white/10' : 'bg-white/5 hover:bg-white/10'
                      }`}
                      onClick={() => setSelectedId(id => id === z.id ? null : z.id)}
                    >
                      <span className="text-white/80">{z.name}</span>
                      {z.trigger_alert && (
                        <Badge className="bg-red-500/20 text-red-400 border-0 text-[10px] px-1 py-0">Алерт</Badge>
                      )}
                      {z.id === selectedId && (
                        <button
                          className="text-red-400 hover:text-red-300 ml-1"
                          onClick={e => { e.stopPropagation(); handleDelete(z.id); }}
                        >
                          <Trash2 size={12} />
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            {zones.length === 0 && !draft && (
              <p className="text-center text-white/25 text-sm py-2">Зони ще не додані</p>
            )}
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} className="text-white/60 hover:text-white">
            Закрити
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
