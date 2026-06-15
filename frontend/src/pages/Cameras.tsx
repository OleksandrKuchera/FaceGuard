import { useEffect, useRef, useState } from 'react';
import Layout from '@/components/Layout';
import { createCamera, getCameras, updateCamera, deleteCamera } from '@/api/client';
import type { Camera } from '@/types';
import { toast } from 'sonner';
import { useNavigate } from 'react-router-dom';

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
  Plus, RefreshCw, Pencil, Trash2, Camera as CameraIcon, Video, VideoOff, MonitorX, Copy,
} from 'lucide-react';
import { loadDemoCameras, saveDemoCameras, type DemoCamera } from '@/utils/demoCameras';

const LOCAL_CAMERA_LOCATION = 'Локальна веб-камера';

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
  name: '',
  location: '',
  camera_code: '',
  stream_url: '0',
  detection_confidence: '0.55',
  frame_skip: '2',
  recognition_enabled: true,
  requires_mfa: false,
};

function CameraFormDialog({
  open, initial, editId, onClose, onSaved,
}: {
  open: boolean;
  initial: CamForm;
  editId: number | null;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<CamForm>(initial);
  const [saving, setSaving] = useState(false);

  useEffect(() => { setForm(initial); }, [initial]);
  const set = (k: keyof CamForm, v: string | boolean) => setForm(f => ({ ...f, [k]: v }));

  const handleSubmit = async (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!editId) return;

    setSaving(true);
    try {
      await updateCamera(editId, {
        ...form,
        detection_confidence: parseFloat(form.detection_confidence),
        frame_skip: parseInt(form.frame_skip),
      });
      toast.success('Камеру оновлено');
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
          <DialogTitle>Редагувати камеру</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3">
            {([['Назва', 'name'], ['Розташування', 'location']] as [string, keyof CamForm][]).map(([lbl, k]) => (
              <div key={k} className="flex flex-col gap-1.5">
                <Label className="text-white/60 text-xs">{lbl} *</Label>
                <Input
                  required
                  value={form[k] as string}
                  onChange={e => set(k, e.target.value)}
                  className="bg-[#0a0e1a] border-white/10 text-white"
                />
              </div>
            ))}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label className="text-white/60 text-xs">Код камери *</Label>
              <Input
                required
                value={form.camera_code}
                onChange={e => set('camera_code', e.target.value)}
                className="bg-[#0a0e1a] border-white/10 text-white font-mono"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label className="text-white/60 text-xs">URL потоку *</Label>
              <Input
                required
                value={form.stream_url}
                onChange={e => set('stream_url', e.target.value)}
                className="bg-[#0a0e1a] border-white/10 text-white font-mono"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label className="text-white/60 text-xs">Поріг впевненості</Label>
              <Input
                type="number"
                step="0.05"
                min="0.1"
                max="1.0"
                value={form.detection_confidence}
                onChange={e => set('detection_confidence', e.target.value)}
                className="bg-[#0a0e1a] border-white/10 text-white"
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label className="text-white/60 text-xs">Frame skip</Label>
              <Input
                type="number"
                min="1"
                max="10"
                value={form.frame_skip}
                onChange={e => set('frame_skip', e.target.value)}
                className="bg-[#0a0e1a] border-white/10 text-white"
              />
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
              <Label htmlFor="mfa" className="text-white/70 text-sm cursor-pointer">MFA</Label>
            </div>
          </div>

          <DialogFooter className="mt-2">
            <Button type="button" variant="ghost" onClick={onClose} className="text-white/60 hover:text-white">
              Скасувати
            </Button>
            <Button type="submit" disabled={saving} className="bg-gradient-to-r from-blue-700 to-blue-500 text-white">
              Зберегти
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function PreviewTile({
  stream,
  camera,
  onRemove,
  onOpen,
}: {
  stream: MediaStream | null;
  camera: DemoCamera;
  onRemove: () => void;
  onOpen: () => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video || !stream) return;

    video.srcObject = stream;
    video.muted = true;
    video.playsInline = true;
    void video.play().catch(() => {});
  }, [stream]);

  return (
    <div className="rounded-2xl border border-white/10 bg-[#1a2235] overflow-hidden">
      <div className="aspect-video bg-black relative">
        {stream ? (
          <video
            ref={videoRef}
            autoPlay
            playsInline
            muted
            className="w-full h-full object-cover"
            style={{ transform: 'scaleX(-1)' }}
          />
        ) : (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 text-white/35">
            <MonitorX size={28} />
            <span className="text-sm">Камера не підключена</span>
          </div>
        )}
        <div className="absolute top-3 left-3">
          <Badge className={`${stream ? 'bg-emerald-500/80' : 'bg-gray-500/80'} text-white border-0 gap-1`}>
            {stream ? <Video size={10} /> : <VideoOff size={10} />}
            {stream ? 'LIVE' : 'OFFLINE'}
          </Badge>
        </div>
      </div>
        <div className="p-4 flex items-start justify-between gap-3">
        <button className="text-left flex-1" onClick={onOpen}>
          <div className="text-white font-medium hover:text-blue-300 transition-colors">{camera.name}</div>
          <div className="text-xs text-white/45">{camera.location}</div>
          <div className="text-[11px] text-blue-300/70 mt-1">Дубль локальної веб-камери</div>
        </button>
        <Button
          variant="ghost"
          size="sm"
          onClick={onRemove}
          className="text-white/50 hover:text-red-300 hover:bg-red-500/10"
        >
          Прибрати
        </Button>
      </div>
    </div>
  );
}

export default function Cameras() {
  const navigate = useNavigate();
  const [cameras, setCameras] = useState<Camera[]>([]);
  const [loading, setLoading] = useState(true);
  const [localPreviews, setLocalPreviews] = useState<DemoCamera[]>([]);
  const [cameraError, setCameraError] = useState<string | null>(null);
  const [localStream, setLocalStream] = useState<MediaStream | null>(null);

  const [formModal, setFormModal] = useState<{ open: boolean; initial: CamForm; editId: number | null }>({
    open: false, initial: EMPTY, editId: null,
  });
  const [deleteTarget, setDeleteTarget] = useState<Camera | null>(null);

  const syncPreviewMetadata = (nextCameras: Camera[]) => {
    setLocalPreviews(prev => prev.map(preview => {
      const matched = nextCameras.find(camera => camera.id === preview.id);
      if (!matched) return preview;
      return {
        ...preview,
        name: matched.name,
        location: matched.location,
      };
    }));
  };

  const load = () => {
    setLoading(true);
    getCameras()
      .then(r => {
        const nextCameras = (r.data as { results?: Camera[] }).results ?? (r.data as Camera[]);
        setCameras(nextCameras);
        syncPreviewMetadata(nextCameras);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  useEffect(() => {
    setLocalPreviews(loadDemoCameras());
  }, []);

  useEffect(() => {
    return () => {
      localStream?.getTracks().forEach(track => track.stop());
    };
  }, [localStream]);

  useEffect(() => {
    saveDemoCameras(localPreviews);
  }, [localPreviews]);

  useEffect(() => {
    if (localPreviews.length === 0 || localStream) {
      return;
    }

    void ensureLocalStream();
  }, [localPreviews, localStream]);

  const ensureLocalStream = async () => {
    if (localStream) return localStream;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 1280 },
          height: { ideal: 720 },
          facingMode: 'user',
        },
        audio: false,
      });
      setLocalStream(stream);
      setCameraError(null);
      return stream;
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Невідома помилка';
      setCameraError(msg);
      toast.error(`Не вдалося відкрити веб-камеру: ${msg}`);
      return null;
    }
  };

  const handleAddPreview = async () => {
    const stream = await ensureLocalStream();
    if (!stream) return;

    const cameraNumber = cameras.length + 1;
    const cameraCode = `LOCAL-${Date.now()}`;

    try {
      const response = await createCamera({
        name: `Камера ${cameraNumber}`,
        location: LOCAL_CAMERA_LOCATION,
        camera_code: cameraCode,
        stream_url: '0',
        is_local: true,
        recognition_enabled: true,
        detection_confidence: 0.55,
        frame_skip: 2,
        resolution_scale: 0.25,
        requires_mfa: false,
      });
      const createdCamera = response.data as Camera;

      setCameras(prev => [...prev, createdCamera]);
      setLocalPreviews(prev => [
        ...prev,
        {
          id: createdCamera.id,
          name: createdCamera.name,
          location: createdCamera.location,
        },
      ]);
      toast.success('Камеру створено у плитках і в таблиці');
    } catch {
      toast.error('Не вдалося створити камеру');
    }
  };

  const handleRemovePreview = async (id: number) => {
    const target = cameras.find(camera => camera.id === id);

    try {
      if (target) {
        await deleteCamera(target.id);
      }
      setLocalPreviews(prev => prev.filter(item => item.id !== id));
      setCameras(prev => prev.filter(camera => camera.id !== id));
      toast.success(target ? `«${target.name}» видалено` : 'Плитку камери прибрано');
    } catch {
      toast.error('Помилка видалення камери');
    }
  };

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deleteCamera(deleteTarget.id);
      setCameras(prev => prev.filter(camera => camera.id !== deleteTarget.id));
      setLocalPreviews(prev => prev.filter(camera => camera.id !== deleteTarget.id));
      toast.success(`«${deleteTarget.name}» видалено`);
    } catch {
      toast.error('Помилка видалення');
    } finally {
      setDeleteTarget(null);
    }
  };

  const openEdit = (cam: Camera) => {
    setFormModal({
      open: true,
      editId: cam.id,
      initial: {
        name: cam.name,
        location: cam.location,
        camera_code: cam.camera_code,
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
          <div className="page-subtitle">Візуальні дублікати вашої локальної камери без реального підключення нових пристроїв</div>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={load} className="text-white/60 hover:text-white border border-white/10">
            <RefreshCw size={14} />
          </Button>
          <Button className="bg-gradient-to-r from-blue-700 to-blue-500 text-white" onClick={handleAddPreview}>
            <Plus size={15} />
            Додати камеру
          </Button>
        </div>
      </div>

      <div className="rounded-2xl border border-white/10 bg-[#111827] p-4 mb-6">
        <div className="flex flex-wrap items-center gap-3 justify-between">
          <div>
            <div className="text-white font-medium">Покази локальної камери</div>
            <div className="text-sm text-white/45">Кожне натискання на кнопку створює і плитку зверху, і запис камери в таблиці нижче.</div>
          </div>
          <div className="flex items-center gap-2">
            <Badge className={`${localStream ? 'bg-emerald-500/20 text-emerald-400' : 'bg-gray-500/20 text-gray-400'} border-0`}>
              {localStream ? <Video size={12} /> : <VideoOff size={12} />}
              {localStream ? 'Камера активна' : 'Камера не активна'}
            </Badge>
            <Badge className="bg-blue-500/15 text-blue-300 border-0 gap-1">
              <Copy size={11} />
              {localPreviews.length} показів
            </Badge>
          </div>
        </div>

        {cameraError && (
          <div className="mt-4 rounded-xl border border-red-500/20 bg-red-500/10 px-4 py-3 text-sm text-red-300">
            Не вдалося отримати доступ до веб-камери: {cameraError}
          </div>
        )}

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4 mt-4">
          {localPreviews.map(item => (
            <PreviewTile
              key={item.id}
              stream={localStream}
              camera={item}
              onRemove={() => { void handleRemovePreview(item.id); }}
              onOpen={() => navigate(`/cameras/${item.id}`)}
            />
          ))}
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
                {['Камера', 'Розташування', 'URL потоку', 'Поріг', 'Розпізн.', 'Дії'].map(h => (
                  <TableHead key={h} className="text-white/40 text-[11px] uppercase tracking-wider">{h}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {cameras.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={6} className="text-center py-16 text-white/30">Реальних камер у базі немає</TableCell>
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
                          <Button variant="ghost" size="icon-xs" onClick={() => openEdit(cam)}>
                            <Pencil size={13} />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Редагувати</TooltipContent>
                      </Tooltip>

                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost"
                            size="icon-xs"
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

      <CameraFormDialog
        open={formModal.open}
        initial={formModal.initial}
        editId={formModal.editId}
        onClose={() => setFormModal(s => ({ ...s, open: false }))}
        onSaved={load}
      />

      <AlertDialog open={!!deleteTarget} onOpenChange={v => { if (!v) setDeleteTarget(null); }}>
        <AlertDialogContent className="bg-[#1a2235] border-white/10 text-white">
          <AlertDialogHeader>
            <AlertDialogTitle>Видалити камеру?</AlertDialogTitle>
            <AlertDialogDescription className="text-white/50">
              «{deleteTarget?.name}» буде видалено з бази.
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
