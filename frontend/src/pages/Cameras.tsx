import { useEffect, useState } from 'react';
import Layout from '@/components/Layout';
import {
  getCameras, createCamera, updateCamera, deleteCamera,
  startCamera, stopCamera, testCamera, getSnapshot,
} from '@/api/client';
import type { Camera, CameraStatus } from '@/types';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import { Separator } from '@/components/ui/separator';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel,
  AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import {
  Tooltip, TooltipContent, TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  Plus, Play, Square, Wifi, Trash2, RefreshCw, Pencil,
  Camera as CameraIcon, Image, Loader2, ScanLine,
} from 'lucide-react';
import { ZoneEditorDialog } from '@/components/ZoneEditor';

// ── Status helpers ────────────────────────────────────────────────────────────
const STATUS_BADGE: Record<CameraStatus, string> = {
  active:      'bg-emerald-500/20 text-emerald-400',
  offline:     'bg-gray-500/20 text-gray-400',
  maintenance: 'bg-amber-500/20 text-amber-400',
};
const STATUS_DOT: Record<CameraStatus, string> = {
  active:      'bg-emerald-400',
  offline:     'bg-gray-500',
  maintenance: 'bg-amber-400',
};
const STATUS_LABEL: Record<CameraStatus, string> = {
  active:      'Активна',
  offline:     'Офлайн',
  maintenance: 'Обслуговування',
};

// ── Form state ────────────────────────────────────────────────────────────────
interface CamForm {
  name: string;
  location: string;
  camera_code: string;
  stream_url: string;
  detection_confidence: string;
  frame_skip: string;
  recognition_enabled: boolean;
  requires_mfa: boolean;
}
const EMPTY: CamForm = {
  name: '', location: '', camera_code: '', stream_url: '0',
  detection_confidence: '0.55', frame_skip: '2',
  recognition_enabled: true, requires_mfa: false,
};

// ── Camera Form Dialog ────────────────────────────────────────────────────────
function CameraFormDialog({
  open, mode, initial, editId, onClose, onSaved,
}: {
  open: boolean; mode: 'create' | 'edit';
  initial: CamForm; editId: number | null;
  onClose: () => void; onSaved: () => void;
}) {
  const [form, setForm] = useState<CamForm>(initial);
  const [saving, setSaving] = useState(false);

  useEffect(() => { setForm(initial); }, [initial]);
  const set = (k: keyof CamForm, v: string | boolean) => setForm(f => ({ ...f, [k]: v }));

  const handleSubmit = async (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault();
    setSaving(true);
    try {
      const payload = {
        ...form,
        detection_confidence: parseFloat(form.detection_confidence),
        frame_skip: parseInt(form.frame_skip),
      };
      if (mode === 'create') {
        await createCamera(payload);
        toast.success('Камеру додано');
      } else if (editId) {
        await updateCamera(editId, payload);
        toast.success('Камеру оновлено');
      }
      onSaved();
      onClose();
    } catch {
      toast.error('Помилка збереження');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) onClose(); }}>
      <DialogContent className="bg-[#1a2235] border-white/10 text-white max-w-lg">
        <DialogHeader>
          <DialogTitle>{mode === 'create' ? '📷 Нова камера' : '📷 Редагувати камеру'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3">
            {([['Назва', 'name'], ['Розташування', 'location']] as [string, keyof CamForm][]).map(([lbl, k]) => (
              <div key={k} className="flex flex-col gap-1.5">
                <Label className="text-white/60 text-xs">{lbl} *</Label>
                <Input required value={form[k] as string} onChange={e => set(k, e.target.value)}
                  className="bg-[#0a0e1a] border-white/10 text-white" />
              </div>
            ))}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label className="text-white/60 text-xs">Код камери *</Label>
              <Input required value={form.camera_code} onChange={e => set('camera_code', e.target.value)}
                placeholder="CAM-001" className="bg-[#0a0e1a] border-white/10 text-white font-mono" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label className="text-white/60 text-xs">URL потоку *</Label>
              <Input required value={form.stream_url} onChange={e => set('stream_url', e.target.value)}
                placeholder="rtsp:// або 0" className="bg-[#0a0e1a] border-white/10 text-white font-mono" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label className="text-white/60 text-xs">Поріг впевненості (0.1–1.0)</Label>
              <Input type="number" step="0.05" min="0.1" max="1.0"
                value={form.detection_confidence} onChange={e => set('detection_confidence', e.target.value)}
                className="bg-[#0a0e1a] border-white/10 text-white" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label className="text-white/60 text-xs">Frame skip (1–10)</Label>
              <Input type="number" min="1" max="10"
                value={form.frame_skip} onChange={e => set('frame_skip', e.target.value)}
                className="bg-[#0a0e1a] border-white/10 text-white" />
            </div>
          </div>

          <Separator className="bg-white/10" />

          <div className="flex gap-6">
            <div className="flex items-center gap-2">
              <Switch
                id="recog"
                checked={form.recognition_enabled}
                onCheckedChange={v => set('recognition_enabled', v)}
              />
              <Label htmlFor="recog" className="text-white/70 text-sm cursor-pointer">Розпізнавання</Label>
            </div>
            <div className="flex items-center gap-2">
              <Switch
                id="mfa"
                checked={form.requires_mfa}
                onCheckedChange={v => set('requires_mfa', v)}
              />
              <Label htmlFor="mfa" className="text-white/70 text-sm cursor-pointer">Вимагати MFA</Label>
            </div>
          </div>

          <DialogFooter className="mt-2">
            <Button type="button" variant="ghost" onClick={onClose} className="text-white/60 hover:text-white">
              Скасувати
            </Button>
            <Button type="submit" disabled={saving}
              className="bg-gradient-to-r from-blue-700 to-blue-500 text-white">
              {saving ? <Loader2 size={14} className="animate-spin" /> : null}
              {mode === 'create' ? 'Додати' : 'Зберегти'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ── Snapshot Dialog ───────────────────────────────────────────────────────────
function SnapshotDialog({ cameraId, cameraName, open, onClose }: {
  cameraId: number | null; cameraName: string; open: boolean; onClose: () => void;
}) {
  const [src, setSrc] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!open || !cameraId) return;
    setLoading(true);
    getSnapshot(cameraId)
      .then(r => {
        const d = r.data as { snapshot?: string; frame?: string };
        setSrc(d.snapshot ?? d.frame ?? null);
      })
      .catch(() => toast.error('Не вдалося отримати знімок'))
      .finally(() => setLoading(false));
  }, [open, cameraId]);

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) { onClose(); setSrc(null); } }}>
      <DialogContent className="bg-[#1a2235] border-white/10 text-white max-w-2xl">
        <DialogHeader>
          <DialogTitle>Знімок — {cameraName}</DialogTitle>
        </DialogHeader>
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <Loader2 size={32} className="animate-spin text-white/30" />
          </div>
        ) : src ? (
          <img src={src} alt="snapshot" className="w-full rounded-lg border border-white/10" />
        ) : (
          <div className="flex flex-col items-center justify-center h-48 text-white/30 gap-2">
            <Image size={32} />
            <span className="text-sm">Знімок недоступний</span>
          </div>
        )}
        <DialogFooter>
          <Button variant="ghost" onClick={onClose} className="text-white/60 hover:text-white">Закрити</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────
export default function Cameras() {
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState(true);

  const [formModal, setFormModal] = useState<{ open: boolean; mode: 'create' | 'edit'; initial: CamForm; editId: number | null }>({
    open: false, mode: 'create', initial: EMPTY, editId: null,
  });
  const [snapshotTarget, setSnapshotTarget] = useState<Camera | null>(null);
  const [deleteTarget, setDeleteTarget]   = useState<Camera | null>(null);
  const [zoneTarget, setZoneTarget]       = useState<Camera | null>(null);
  const [testing, setTesting] = useState<number | null>(null);
  const [toggling, setToggling] = useState<number | null>(null);

  const load = () => {
    setLoading(true);
    getCameras()
      .then(r => setCameras((r.data as { results?: Camera[] }).results ?? (r.data as Camera[])))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const handleTest = async (cam: Camera) => {
    setTesting(cam.id);
    try {
      const r = await testCamera(cam.id);
      const d = r.data as { connected?: boolean };
      if (d.connected) toast.success(`«${cam.name}» — підключення успішне`);
      else toast.error(`«${cam.name}» — камера недоступна`);
    } catch {
      toast.error('Помилка перевірки');
    } finally {
      setTesting(null);
    }
  };

  const handleToggle = async (cam: Camera) => {
    setToggling(cam.id);
    try {
      if (cam.status === 'active') {
        await stopCamera(cam.id);
        toast.info(`«${cam.name}» зупинено`);
      } else {
        await startCamera(cam.id);
        toast.success(`«${cam.name}» запущено`);
      }
      setTimeout(load, 1200);
    } catch {
      toast.error('Помилка зміни статусу');
    } finally {
      setToggling(null);
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteCamera(deleteTarget.id);
      toast.success(`«${deleteTarget.name}» видалено`);
      load();
    } catch {
      toast.error('Помилка видалення');
    } finally {
      setDeleteTarget(null);
    }
  };

  const openEdit = (cam: Camera) => {
    setFormModal({
      open: true, mode: 'edit', editId: cam.id,
      initial: {
        name: cam.name, location: cam.location, camera_code: cam.camera_code,
        stream_url: cam.stream_url,
        detection_confidence: String(cam.detection_confidence),
        frame_skip: String(cam.frame_skip),
        recognition_enabled: cam.recognition_enabled,
        requires_mfa: cam.requires_mfa,
      },
    });
  };

  return (
    <Layout title="Камери">
      <div className="page-header">
        <div>
          <h1>Камери</h1>
          <div className="page-subtitle">Управління камерами спостереження</div>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={load} className="text-white/60 hover:text-white border border-white/10">
            <RefreshCw size={14} />
          </Button>
          <Button
            className="bg-gradient-to-r from-blue-700 to-blue-500 text-white"
            onClick={() => setFormModal({ open: true, mode: 'create', initial: EMPTY, editId: null })}
          >
            <Plus size={15} />
            Додати камеру
          </Button>
        </div>
      </div>

      {loading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-14 w-full bg-white/5 rounded-xl" />)}
        </div>
      ) : (
        <div className="table-wrap">
          <Table>
            <TableHeader>
              <TableRow className="border-white/10 hover:bg-transparent">
                {['Камера', 'Розташування', 'URL потоку', 'Статус', 'Поріг', 'Розпізн.', 'Дії'].map(h => (
                  <TableHead key={h} className="text-white/40 text-[11px] uppercase tracking-wider">{h}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {cameras.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-16 text-white/30">Камери не знайдено</TableCell>
                </TableRow>
              ) : cameras.map(cam => (
                <TableRow key={cam.id} className="border-white/10 hover:bg-white/5">
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <div className="w-8 h-8 rounded-lg bg-blue-500/20 flex items-center justify-center flex-shrink-0">
                        <CameraIcon size={14} className="text-blue-400" />
                      </div>
                      <div>
                        <div className="font-medium text-white text-sm">{cam.name}</div>
                        <div className="text-[11px] text-white/40 font-mono">{cam.camera_code}</div>
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="text-white/60">{cam.location}</TableCell>
                  <TableCell className="font-mono text-blue-400 text-xs">{cam.stream_url}</TableCell>
                  <TableCell>
                    <div className="flex flex-col gap-0.5">
                      <Badge className={`border-0 gap-1.5 w-fit ${STATUS_BADGE[cam.status] ?? 'bg-gray-500/20 text-gray-400'}`}>
                        <span className={`w-1.5 h-1.5 rounded-full ${STATUS_DOT[cam.status] ?? 'bg-gray-500'}`} />
                        {STATUS_LABEL[cam.status] ?? cam.status}
                      </Badge>
                      {cam.last_ping && (
                        <span className="text-[10px] text-white/30">
                          {(() => {
                            const diff = Math.floor((Date.now() - new Date(cam.last_ping).getTime()) / 1000);
                            if (diff < 60) return `${diff}с тому`;
                            if (diff < 3600) return `${Math.floor(diff / 60)}хв тому`;
                            return `${Math.floor(diff / 3600)}год тому`;
                          })()}
                        </span>
                      )}
                    </div>
                  </TableCell>
                  <TableCell className="text-white/60 font-mono text-xs">{cam.detection_confidence}</TableCell>
                  <TableCell>
                    <Badge className={`border-0 ${cam.recognition_enabled ? 'bg-emerald-500/20 text-emerald-400' : 'bg-gray-500/20 text-gray-400'}`}>
                      {cam.recognition_enabled ? 'Увімк.' : 'Вимк.'}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1.5">
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button variant="ghost" size="icon-xs" onClick={() => setSnapshotTarget(cam)}>
                            <Image size={13} />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Знімок</TooltipContent>
                      </Tooltip>

                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button variant="ghost" size="icon-xs" onClick={() => setZoneTarget(cam)}>
                            <ScanLine size={13} />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Зони камери</TooltipContent>
                      </Tooltip>

                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button variant="ghost" size="icon-xs" onClick={() => handleTest(cam)} disabled={testing === cam.id}>
                            {testing === cam.id ? <Loader2 size={13} className="animate-spin" /> : <Wifi size={13} />}
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Тест зв'язку</TooltipContent>
                      </Tooltip>

                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost" size="icon-xs"
                            className={cam.status === 'active' ? 'text-amber-400 hover:text-amber-300 hover:bg-amber-500/10' : 'text-emerald-400 hover:text-emerald-300 hover:bg-emerald-500/10'}
                            onClick={() => handleToggle(cam)}
                            disabled={toggling === cam.id}
                          >
                            {toggling === cam.id
                              ? <Loader2 size={13} className="animate-spin" />
                              : cam.status === 'active' ? <Square size={13} /> : <Play size={13} />}
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>{cam.status === 'active' ? 'Зупинити' : 'Запустити'}</TooltipContent>
                      </Tooltip>

                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button variant="ghost" size="icon-xs" onClick={() => openEdit(cam)}>
                            <Pencil size={13} />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Редагувати</TooltipContent>
                      </Tooltip>

                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost" size="icon-xs"
                            className="text-red-400 hover:text-red-300 hover:bg-red-500/10"
                            onClick={() => setDeleteTarget(cam)}
                          >
                            <Trash2 size={13} />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Видалити</TooltipContent>
                      </Tooltip>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Form Dialog */}
      <CameraFormDialog
        open={formModal.open}
        mode={formModal.mode}
        initial={formModal.initial}
        editId={formModal.editId}
        onClose={() => setFormModal(s => ({ ...s, open: false }))}
        onSaved={load}
      />

      {/* Snapshot Dialog */}
      <SnapshotDialog
        open={!!snapshotTarget}
        cameraId={snapshotTarget?.id ?? null}
        cameraName={snapshotTarget?.name ?? ''}
        onClose={() => setSnapshotTarget(null)}
      />

      {/* Zone Editor Dialog */}
      <ZoneEditorDialog
        open={!!zoneTarget}
        cameraId={zoneTarget?.id ?? null}
        cameraName={zoneTarget?.name ?? ''}
        onClose={() => setZoneTarget(null)}
      />

      {/* Delete Confirm */}
      <AlertDialog open={!!deleteTarget} onOpenChange={v => { if (!v) setDeleteTarget(null); }}>
        <AlertDialogContent className="bg-[#1a2235] border-white/10 text-white">
          <AlertDialogHeader>
            <AlertDialogTitle>Видалити камеру?</AlertDialogTitle>
            <AlertDialogDescription className="text-white/50">
              «{deleteTarget?.name}» буде видалено разом з усіма налаштуваннями.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="bg-white/10 border-0 text-white hover:bg-white/20">Скасувати</AlertDialogCancel>
            <AlertDialogAction className="bg-red-600 hover:bg-red-500 text-white" onClick={handleDelete}>
              Видалити
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Layout>
  );
}
