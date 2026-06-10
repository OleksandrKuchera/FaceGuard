import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Layout from '@/components/Layout';
import {
  getPersons, createPerson, updatePerson, deletePerson,
  trainPerson, getTrainStatus, uploadPhoto, getPhotos, deletePhoto, getDepartments,
} from '@/api/client';
import type { Person, Department, PersonRole, TrainStatus } from '@/types';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Avatar, AvatarImage, AvatarFallback } from '@/components/ui/avatar';
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
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Tooltip, TooltipContent, TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import { Checkbox } from '@/components/ui/checkbox';
import {
  UserPlus, Zap, Trash2, Upload, Search, Pencil,
  Images, Loader2, CheckCircle2, XCircle, BrainCircuit, ShieldOff, X,
  ChevronUp, ChevronDown, ChevronsUpDown,
} from 'lucide-react';

// ── Sort helpers ──────────────────────────────────────────────────────────────
type PersonSortKey = 'full_name' | 'person_id' | 'role' | 'access_level';
type SortDir = 'asc' | 'desc';

function SortIcon({ col, sortKey, sortDir }: { col: PersonSortKey; sortKey: PersonSortKey; sortDir: SortDir }) {
  if (col !== sortKey) return <ChevronsUpDown size={11} className="text-white/20" />;
  return sortDir === 'asc'
    ? <ChevronUp size={11} className="text-blue-400" />
    : <ChevronDown size={11} className="text-blue-400" />;
}

// ── Constants ────────────────────────────────────────────────────────────────
const ROLE_BADGE: Record<PersonRole, string> = {
  staff:      'bg-blue-500/20 text-blue-400',
  visitor:    'bg-amber-500/20 text-amber-400',
  contractor: 'bg-purple-500/20 text-purple-400',
  unknown:    'bg-gray-500/20 text-gray-400',
};
const ROLE_LABEL: Record<PersonRole, string> = {
  staff:      'Персонал',
  visitor:    'Відвідувач',
  contractor: 'Підрядник',
  unknown:    'Невідомий',
};

interface FormState {
  first_name: string;
  last_name: string;
  middle_name: string;
  person_id: string;
  role: PersonRole;
  access_level: string;
  department_id: string;
  notes: string;
  consent_given: boolean;
}
const EMPTY_FORM: FormState = {
  first_name: '', last_name: '', middle_name: '',
  person_id: '', role: 'staff', access_level: '1',
  department_id: '', notes: '', consent_given: false,
};

// ── PersonFormDialog ─────────────────────────────────────────────────────────
function PersonFormDialog({
  open, editId, initial, departments, onClose, onSaved,
}: {
  open: boolean;
  editId: number | null;   // null = create mode
  initial: FormState;
  departments: Department[];
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<FormState>(initial);
  const [saving, setSaving] = useState(false);
  const isEdit = editId !== null;

  // Reset form whenever the modal opens with new data
  useEffect(() => { if (open) setForm(initial); }, [open, initial]);

  const set = (k: keyof FormState, v: string) => setForm(f => ({ ...f, [k]: v }));

  const handleSubmit = async (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault();
    setSaving(true);
    try {
      const fd = new FormData();
      Object.entries(form).forEach(([k, v]) => {
        if (k === 'consent_given') {
          fd.append('consent_given', String(v));
          return;
        }
        if (v) fd.append(k === 'department_id' ? 'department' : k, v);
      });

      if (isEdit) {
        await updatePerson(editId, fd);
        toast.success('Особу оновлено');
      } else {
        await createPerson(fd);
        toast.success('Особу додано');
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
          <DialogTitle>{isEdit ? 'Редагувати особу' : 'Нова особа'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="grid grid-cols-2 gap-3">
            {([["Ім'я", 'first_name'], ['Прізвище', 'last_name']] as [string, keyof FormState][]).map(([lbl, k]) => (
              <div key={k} className="flex flex-col gap-1.5">
                <Label className="text-white/60 text-xs">{lbl} *</Label>
                <Input required value={form[k] as string} onChange={e => set(k, e.target.value)}
                  className="bg-[#0a0e1a] border-white/10 text-white" />
              </div>
            ))}
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label className="text-white/60 text-xs">По-батькові</Label>
              <Input value={form.middle_name} onChange={e => set('middle_name', e.target.value)}
                className="bg-[#0a0e1a] border-white/10 text-white" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label className="text-white/60 text-xs">ID (табельний) *</Label>
              <Input required value={form.person_id} onChange={e => set('person_id', e.target.value)}
                placeholder="EMP-001"
                className="bg-[#0a0e1a] border-white/10 text-white font-mono" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label className="text-white/60 text-xs">Роль</Label>
              <Select value={form.role} onValueChange={v => set('role', v)}>
                <SelectTrigger className="bg-[#0a0e1a] border-white/10 text-white">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-[#1a2235] border-white/10">
                  {Object.entries(ROLE_LABEL).map(([k, v]) => (
                    <SelectItem key={k} value={k} className="text-white focus:bg-white/10">{v}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label className="text-white/60 text-xs">Рівень доступу (1–5)</Label>
              <Input type="number" min={1} max={5} value={form.access_level}
                onChange={e => set('access_level', e.target.value)}
                className="bg-[#0a0e1a] border-white/10 text-white" />
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label className="text-white/60 text-xs">Підрозділ</Label>
            <Select value={form.department_id || '__none__'} onValueChange={v => set('department_id', v === '__none__' ? '' : v)}>
              <SelectTrigger className="bg-[#0a0e1a] border-white/10 text-white">
                <SelectValue placeholder="— Без підрозділу —" />
              </SelectTrigger>
              <SelectContent className="bg-[#1a2235] border-white/10">
                <SelectItem value="__none__" className="text-white/50 focus:bg-white/10">— Без підрозділу —</SelectItem>
                {departments.map(d => (
                  <SelectItem key={d.id} value={String(d.id)} className="text-white focus:bg-white/10">{d.name}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label className="text-white/60 text-xs">Нотатки</Label>
            <Input value={form.notes} onChange={e => set('notes', e.target.value)}
              className="bg-[#0a0e1a] border-white/10 text-white" />
          </div>

          <div className="flex items-center gap-2 rounded-lg border border-white/10 bg-white/5 px-3 py-2">
            <Checkbox
              checked={form.consent_given}
              onCheckedChange={checked => setForm(f => ({ ...f, consent_given: checked === true }))}
            />
            <div className="flex flex-col">
              <Label className="text-white/80 text-xs">Згода на обробку біометричних даних</Label>
              <span className="text-[11px] text-white/40">Без цієї згоди фото не повинні використовуватись для розпізнавання.</span>
            </div>
          </div>

          <DialogFooter className="mt-2">
            <Button type="button" variant="ghost" onClick={onClose} className="text-white/60 hover:text-white">
              Скасувати
            </Button>
            <Button type="submit" disabled={saving}
              className="bg-gradient-to-r from-blue-700 to-blue-500 text-white">
              {saving && <Loader2 size={14} className="animate-spin" />}
              {isEdit ? 'Зберегти' : 'Додати'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ── PhotoGalleryDialog ────────────────────────────────────────────────────────
function PhotoGalleryDialog({
  person, open, onClose,
}: { person: Person | null; open: boolean; onClose: () => void }) {
  const fileRef = useRef<HTMLInputElement>(null);
  const [photos, setPhotos] = useState<import('@/types').PersonPhoto[]>([]);
  const [loadingPhotos, setLoadingPhotos] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const loadPhotos = async () => {
    if (!person) return;
    setLoadingPhotos(true);
    try {
      const r = await getPhotos(person.id);
      setPhotos(r.data as import('@/types').PersonPhoto[]);
    } catch {
      toast.error('Не вдалося завантажити фотографії');
    } finally {
      setLoadingPhotos(false);
    }
  };

  useEffect(() => {
    if (open && person) {
      loadPhotos();
    } else {
      setPhotos([]);
    }
  }, [open, person?.id]);

  const handleUpload = async (files: FileList | null) => {
    if (!files?.length || !person) return;
    setUploading(true);
    try {
      await uploadPhoto(person.id, Array.from(files));
      toast.success(`Завантажено ${files.length} фото`, {
        description: 'Система автоматично перевірить фото та оновить embeddings',
      });
      loadPhotos();
    } catch {
      toast.error('Помилка завантаження');
    } finally {
      setUploading(false);
      if (fileRef.current) fileRef.current.value = '';
    }
  };

  const handleDelete = async (photoId: number) => {
    if (!person) return;
    setDeletingId(photoId);
    try {
      await deletePhoto(person.id, photoId);
      setPhotos(prev => prev.filter(p => p.id !== photoId));
      toast.success('Фото видалено');
    } catch {
      toast.error('Помилка видалення');
    } finally {
      setDeletingId(null);
    }
  };

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) onClose(); }}>
      <DialogContent className="bg-[#1a2235] border-white/10 text-white max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            Фотографії — {person?.full_name}
            <span className="ml-2 text-sm font-normal text-white/40">({photos.length} фото)</span>
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          {/* Photo grid */}
          {loadingPhotos ? (
            <div className="grid grid-cols-4 gap-3">
              {Array.from({ length: 4 }).map((_, i) => (
                <Skeleton key={i} className="aspect-square rounded-lg bg-white/5" />
              ))}
            </div>
          ) : photos.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-10 text-white/30 gap-2">
              <Upload size={32} />
              <span className="text-sm">Фотографій ще немає</span>
            </div>
          ) : (
            <div className="grid grid-cols-4 gap-3 max-h-80 overflow-y-auto pr-1">
              {photos.map(photo => (
                <div key={photo.id} className="relative group rounded-lg overflow-hidden border border-white/10">
                  <img
                    src={photo.image}
                    alt="photo"
                    className="w-full aspect-square object-cover"
                  />
                  {/* Overlay on hover */}
                  <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                    <Button
                      variant="ghost"
                      size="icon-xs"
                      className="text-red-400 hover:text-red-300 hover:bg-red-500/20"
                      onClick={() => handleDelete(photo.id)}
                      disabled={deletingId === photo.id}
                    >
                      {deletingId === photo.id
                        ? <Loader2 size={14} className="animate-spin" />
                        : <Trash2 size={14} />}
                    </Button>
                  </div>
                  {/* Badges */}
                  <div className="absolute bottom-0 left-0 right-0 p-1 flex flex-col gap-0.5">
                    {photo.face_detected === true && (
                      <Badge className="bg-emerald-500/80 text-white border-0 text-[9px] px-1 py-0 leading-tight w-fit">
                        ✓ Обличчя
                      </Badge>
                    )}
                    {photo.face_detected === false && (
                      <Badge className="bg-red-500/80 text-white border-0 text-[9px] px-1 py-0 leading-tight w-fit">
                        ✗ Не виявлено
                      </Badge>
                    )}
                    {photo.quality_score != null && (
                      <Badge className="bg-black/60 text-white/80 border-0 text-[9px] px-1 py-0 leading-tight w-fit">
                        {(photo.quality_score * 100).toFixed(0)}%
                      </Badge>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}

          <Separator className="bg-white/10" />

          <div className="flex flex-col gap-2">
            <p className="text-xs text-white/50">
              Рекомендовано 5–10 фото з різних кутів та освітлення для кращого розпізнавання.
            </p>
            <p className="text-xs text-white/40">
              Після завантаження фото автоматично йдуть у валідацію та генерацію embeddings.
            </p>
            <Button
              variant="outline"
              className="border-white/20 text-white hover:bg-white/10 w-full"
              onClick={() => fileRef.current?.click()}
              disabled={uploading}
            >
              {uploading ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
              {uploading ? 'Завантаження...' : 'Додати фото'}
            </Button>
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              multiple
              className="hidden"
              onChange={e => handleUpload(e.target.files)}
            />
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={onClose} className="text-white/60 hover:text-white">Закрити</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────
interface ModalState {
  open: boolean;
  editId: number | null;
  initial: FormState;
}

export default function Persons() {
  const [persons, setPersons] = useState<Person[]>([]);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState<PersonRole | ''>('');
  const [loading, setLoading] = useState(true);

  // ── Sorting ────────────────────────────────────────────────────────────────
  const [sortKey, setSortKey] = useState<PersonSortKey>('full_name');
  const [sortDir, setSortDir] = useState<SortDir>('asc');

  const toggleSort = useCallback((key: PersonSortKey) => {
    setSortKey(prev => {
      if (prev === key) { setSortDir(d => d === 'asc' ? 'desc' : 'asc'); return key; }
      setSortDir('asc');
      return key;
    });
  }, []);

  const sorted = useMemo(() => {
    return [...persons].sort((a, b) => {
      let av: string | number = '';
      let bv: string | number = '';
      if (sortKey === 'full_name')    { av = a.full_name ?? ''; bv = b.full_name ?? ''; }
      else if (sortKey === 'person_id') { av = a.person_id ?? ''; bv = b.person_id ?? ''; }
      else if (sortKey === 'role')      { av = a.role ?? ''; bv = b.role ?? ''; }
      else if (sortKey === 'access_level') { av = a.access_level ?? 0; bv = b.access_level ?? 0; }
      if (av < bv) return sortDir === 'asc' ? -1 : 1;
      if (av > bv) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
  }, [persons, sortKey, sortDir]);

  const [modal, setModal] = useState<ModalState>({ open: false, editId: null, initial: EMPTY_FORM });
  const [galleryPerson, setGalleryPerson] = useState<Person | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<Person | null>(null);
  const [trainingId, setTrainingId] = useState<number | null>(null);
  const [trainStatus, setTrainStatus] = useState<Record<number, TrainStatus>>({});
  const pollIntervals = useRef<Map<number, ReturnType<typeof setInterval>>>(new Map());

  // ── Bulk selection ─────────────────────────────────────────────────────────
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [bulkDeactivateOpen, setBulkDeactivateOpen] = useState(false);
  const [bulkWorking, setBulkWorking] = useState(false);

  const toggleSelect = useCallback((id: number) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }, []);

  const allSelected = sorted.length > 0 && sorted.every(p => selectedIds.has(p.id));
  const someSelected = !allSelected && sorted.some(p => selectedIds.has(p.id));

  const toggleSelectAll = useCallback(() => {
    setSelectedIds(allSelected ? new Set() : new Set(sorted.map(p => p.id)));
  }, [allSelected, sorted]);

  const handleBulkTrain = async () => {
    setBulkWorking(true);
    const ids = [...selectedIds];
    let ok = 0;
    for (const id of ids) {
      try { await trainPerson(id); ok++; } catch { /* skip */ }
    }
    toast.success(`Навчання запущено для ${ok} з ${ids.length} осіб`);
    setSelectedIds(new Set());
    setBulkWorking(false);
  };

  const handleBulkDeactivate = async () => {
    setBulkWorking(true);
    const ids = [...selectedIds];
    let ok = 0;
    for (const id of ids) {
      try { await deletePerson(id); ok++; } catch { /* skip */ }
    }
    toast.success(`Деактивовано ${ok} з ${ids.length} осіб`);
    setSelectedIds(new Set());
    setBulkDeactivateOpen(false);
    setBulkWorking(false);
    load();
  };

  const load = () => {
    setLoading(true);
    const params: Record<string, string> = {};
    if (search) params.search = search;
    if (roleFilter) params.role = roleFilter;
    getPersons(params)
      .then(r => setPersons((r.data as { results?: Person[] }).results ?? (r.data as Person[])))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [search, roleFilter]);

  useEffect(() => {
    getDepartments()
      .then(r => setDepartments((r.data as { results?: Department[] }).results ?? (r.data as Department[])))
      .catch(() => {});
  }, []);

  // Cleanup all polling intervals on unmount
  useEffect(() => {
    return () => { pollIntervals.current.forEach(id => clearInterval(id)); };
  }, []);

  const handleDelete = async () => {
    if (!deleteTarget) return;
    try {
      await deletePerson(deleteTarget.id);
      toast.success(`«${deleteTarget.full_name}» деактивовано`);
      load();
    } catch {
      toast.error('Помилка деактивації');
    } finally {
      setDeleteTarget(null);
    }
  };

  const handleTrain = async (p: Person) => {
    // Clear any existing poll for this person
    const existing = pollIntervals.current.get(p.id);
    if (existing) { clearInterval(existing); pollIntervals.current.delete(p.id); }

    setTrainingId(p.id);
    try {
      await trainPerson(p.id);
      toast.success(`Навчання для «${p.full_name}» запущено`, {
        description: 'Опитуємо стан кожні 3 секунди…',
      });

      const intervalId = setInterval(async () => {
        try {
          const res = await getTrainStatus(p.id);
          const st = res.data as TrainStatus;
          setTrainStatus(prev => ({ ...prev, [p.id]: st }));

          if (st.task_state === 'SUCCESS' || st.task_state === 'FAILURE') {
            clearInterval(intervalId);
            pollIntervals.current.delete(p.id);
            if (st.task_state === 'SUCCESS') {
              const qual = st.best_quality_score != null
                ? `, якість ${(st.best_quality_score * 100).toFixed(0)}%`
                : '';
              toast.success(`«${p.full_name}» — навчання завершено`, {
                description: `Створено ${st.encodings_created} кодувань${qual}`,
              });
            } else {
              toast.error(`«${p.full_name}» — навчання провалилось`);
            }
          }
        } catch {
          clearInterval(intervalId);
          pollIntervals.current.delete(p.id);
        }
      }, 3000);

      pollIntervals.current.set(p.id, intervalId);
    } catch {
      toast.error('Помилка запуску навчання');
    } finally {
      setTrainingId(null);
    }
  };

  const navigate = useNavigate();
  const openCreate = () => setModal({ open: true, editId: null, initial: EMPTY_FORM });

  const openEdit = (p: Person) => setModal({
    open: true,
    editId: p.id,
      initial: {
        first_name:    p.first_name,
        last_name:     p.last_name,
        middle_name:   p.middle_name ?? '',
        person_id:     p.person_id,
        role:          p.role,
        access_level:  String(p.access_level),
        department_id: p.department ? String(p.department) : '',
        notes:         p.notes ?? '',
        consent_given: Boolean(p.consent_given),
      },
    });

  return (
    <Layout title="Особи">
      <div className="page-header">
        <div>
          <h1>Особи</h1>
          <div className="page-subtitle">Управління персоналом та їх обличчями</div>
        </div>
        <Button
          className="bg-gradient-to-r from-blue-700 to-blue-500 text-white"
          onClick={openCreate}
        >
          <UserPlus size={15} />
          Додати особу
        </Button>
      </div>

      {/* Bulk action toolbar */}
      {selectedIds.size > 0 && (
        <div className="flex items-center gap-3 mb-4 px-4 py-2.5 rounded-xl bg-blue-500/10 border border-blue-500/20">
          <span className="text-sm font-medium text-blue-300">
            Вибрано: {selectedIds.size}
          </span>
          <div className="flex-1" />
          <Button
            size="sm"
            className="bg-blue-600 hover:bg-blue-500 text-white h-7 text-xs gap-1.5"
            onClick={handleBulkTrain}
            disabled={bulkWorking}
          >
            {bulkWorking ? <Loader2 size={12} className="animate-spin" /> : <BrainCircuit size={12} />}
            Навчати вибраних
          </Button>
          <Button
            size="sm"
            variant="destructive"
            className="h-7 text-xs gap-1.5"
            onClick={() => setBulkDeactivateOpen(true)}
            disabled={bulkWorking}
          >
            <ShieldOff size={12} />
            Деактивувати
          </Button>
          <Button
            size="sm" variant="ghost"
            className="h-7 text-xs text-white/40 hover:text-white gap-1"
            onClick={() => setSelectedIds(new Set())}
          >
            <X size={12} />
            Скинути
          </Button>
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-3 mb-5 flex-wrap">
        <div className="relative">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30" />
          <Input
            placeholder="Пошук..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="pl-8 bg-[#1a2235] border-white/10 text-white w-56"
          />
        </div>
        <Select value={roleFilter || '__all__'} onValueChange={v => setRoleFilter(v === '__all__' ? '' : v as PersonRole)}>
          <SelectTrigger className="bg-[#1a2235] border-white/10 text-white w-44">
            <SelectValue placeholder="Всі ролі" />
          </SelectTrigger>
          <SelectContent className="bg-[#1a2235] border-white/10">
            <SelectItem value="__all__" className="text-white focus:bg-white/10">Всі ролі</SelectItem>
            {Object.entries(ROLE_LABEL).map(([k, v]) => (
              <SelectItem key={k} value={k} className="text-white focus:bg-white/10">{v}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Table */}
      {loading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full bg-white/5 rounded-xl" />
          ))}
        </div>
      ) : (
        <div className="table-wrap">
          <Table>
            <TableHeader>
              <TableRow className="border-white/10 hover:bg-transparent">
                <TableHead className="w-10">
                  <Checkbox
                    checked={allSelected}
                    data-state={someSelected ? 'indeterminate' : allSelected ? 'checked' : 'unchecked'}
                    onCheckedChange={toggleSelectAll}
                    className="border-white/30 data-[state=checked]:bg-blue-500 data-[state=checked]:border-blue-500"
                  />
                </TableHead>
                <TableHead className="text-white/40 text-[11px] uppercase tracking-wider">Фото</TableHead>
                {([
                  ['Особа',   'full_name'],
                  ['ID',      'person_id'],
                  ['Роль',    'role'],
                ] as [string, PersonSortKey][]).map(([label, key]) => (
                  <TableHead key={key}
                    className="text-white/40 text-[11px] uppercase tracking-wider cursor-pointer select-none hover:text-white/70 transition-colors"
                    onClick={() => toggleSort(key)}
                  >
                    <span className="flex items-center gap-1">
                      {label}
                      <SortIcon col={key} sortKey={sortKey} sortDir={sortDir} />
                    </span>
                  </TableHead>
                ))}
                <TableHead className="text-white/40 text-[11px] uppercase tracking-wider">Підрозділ</TableHead>
                <TableHead
                  className="text-white/40 text-[11px] uppercase tracking-wider cursor-pointer select-none hover:text-white/70 transition-colors"
                  onClick={() => toggleSort('access_level')}
                >
                  <span className="flex items-center gap-1">
                    Рівень
                    <SortIcon col="access_level" sortKey={sortKey} sortDir={sortDir} />
                  </span>
                </TableHead>
                <TableHead className="text-white/40 text-[11px] uppercase tracking-wider">Статус</TableHead>
                <TableHead className="text-white/40 text-[11px] uppercase tracking-wider">Дії</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {sorted.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={9} className="text-center py-16 text-white/30">
                    Особи не знайдені
                  </TableCell>
                </TableRow>
              ) : sorted.map(p => (
                <TableRow key={p.id} className={`border-white/10 hover:bg-white/5 cursor-pointer ${selectedIds.has(p.id) ? 'bg-blue-500/5' : ''}`} onClick={() => navigate(`/persons/${p.id}`)}>
                  <TableCell onClick={e => e.stopPropagation()}>
                    <Checkbox
                      checked={selectedIds.has(p.id)}
                      onCheckedChange={() => toggleSelect(p.id)}
                      className="border-white/30 data-[state=checked]:bg-blue-500 data-[state=checked]:border-blue-500"
                    />
                  </TableCell>
                  <TableCell>
                    <Avatar className="w-9 h-9 rounded-lg">
                      <AvatarImage src={p.primary_photo} alt={p.full_name} className="object-cover" />
                      <AvatarFallback className="bg-gradient-to-br from-blue-700 to-purple-600 text-white text-sm rounded-lg">
                        {p.full_name?.charAt(0) ?? '?'}
                      </AvatarFallback>
                    </Avatar>
                  </TableCell>
                  <TableCell className="font-medium text-white">{p.full_name}</TableCell>
                  <TableCell className="font-mono text-blue-400 text-xs">{p.person_id}</TableCell>
                  <TableCell>
                    <Badge className={`border-0 text-[11px] ${ROLE_BADGE[p.role] ?? 'bg-gray-500/20 text-gray-400'}`}>
                      {ROLE_LABEL[p.role] ?? p.role}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-white/60">{p.department_name ?? '—'}</TableCell>
                  <TableCell>
                    <Badge className="bg-purple-500/20 text-purple-400 border-0">{p.access_level}</Badge>
                  </TableCell>
                  <TableCell>
                    <div className="flex flex-col gap-1">
                      {p.is_active
                        ? <Badge className="bg-emerald-500/20 text-emerald-400 border-0 gap-1 w-fit"><CheckCircle2 size={10} />Активний</Badge>
                        : <Badge className="bg-gray-500/20 text-gray-400 border-0 gap-1 w-fit"><XCircle size={10} />Неактивний</Badge>}
                      {p.consent_given
                        ? <Badge className="bg-emerald-500/20 text-emerald-400 border-0 gap-1 w-fit text-[10px]">Consent</Badge>
                        : <Badge className="bg-amber-500/20 text-amber-400 border-0 gap-1 w-fit text-[10px]">No consent</Badge>}
                      {(() => {
                        const ts = trainStatus[p.id];
                        if (!ts) return null;
                        if (ts.task_state === 'PENDING' || ts.task_state === 'STARTED') {
                          return (
                            <Badge className="bg-blue-500/20 text-blue-300 border-0 gap-1 w-fit text-[10px]">
                              <Loader2 size={9} className="animate-spin" />Навчання…
                            </Badge>
                          );
                        }
                        if (ts.task_state === 'SUCCESS' && ts.is_ready) {
                          const qual = ts.best_quality_score != null
                            ? ` · ${(ts.best_quality_score * 100).toFixed(0)}%`
                            : '';
                          return (
                            <Badge className="bg-purple-500/20 text-purple-300 border-0 gap-1 w-fit text-[10px]">
                              <Zap size={9} />{ts.encodings_created} enc{qual}
                            </Badge>
                          );
                        }
                        if (ts.task_state === 'FAILURE') {
                          return (
                            <Badge className="bg-red-500/20 text-red-400 border-0 gap-1 w-fit text-[10px]">
                              <XCircle size={9} />Помилка навчання
                            </Badge>
                          );
                        }
                        return null;
                      })()}
                    </div>
                  </TableCell>
                  <TableCell onClick={e => e.stopPropagation()}>
                    <div className="flex gap-1.5">
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button variant="ghost" size="icon-xs" onClick={() => setGalleryPerson(p)}>
                            <Images size={13} />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Фотографії</TooltipContent>
                      </Tooltip>

                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button variant="ghost" size="icon-xs" onClick={() => openEdit(p)}>
                            <Pencil size={13} />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Редагувати</TooltipContent>
                      </Tooltip>

                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost" size="icon-xs"
                            className="text-emerald-400 hover:text-emerald-300 hover:bg-emerald-500/10"
                            onClick={() => handleTrain(p)}
                            disabled={trainingId === p.id}
                          >
                            {trainingId === p.id
                              ? <Loader2 size={13} className="animate-spin" />
                              : <Zap size={13} />}
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Навчати модель</TooltipContent>
                      </Tooltip>

                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost" size="icon-xs"
                            className="text-red-400 hover:text-red-300 hover:bg-red-500/10"
                            onClick={() => setDeleteTarget(p)}
                          >
                            <Trash2 size={13} />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Деактивувати</TooltipContent>
                      </Tooltip>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Form Dialog — handles both create & edit */}
      <PersonFormDialog
        open={modal.open}
        editId={modal.editId}
        initial={modal.initial}
        departments={departments}
        onClose={() => setModal(s => ({ ...s, open: false }))}
        onSaved={load}
      />

      {/* Gallery Dialog */}
      <PhotoGalleryDialog
        person={galleryPerson}
        open={!!galleryPerson}
        onClose={() => setGalleryPerson(null)}
      />

      {/* Bulk Deactivate Confirm */}
      <AlertDialog open={bulkDeactivateOpen} onOpenChange={v => { if (!v) setBulkDeactivateOpen(false); }}>
        <AlertDialogContent className="bg-[#1a2235] border-white/10 text-white">
          <AlertDialogHeader>
            <AlertDialogTitle>Деактивувати {selectedIds.size} осіб?</AlertDialogTitle>
            <AlertDialogDescription className="text-white/50">
              Всі вибрані особи будуть деактивовані. Дані збережуться.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="bg-white/10 border-0 text-white hover:bg-white/20">Скасувати</AlertDialogCancel>
            <AlertDialogAction
              className="bg-red-600 hover:bg-red-500 text-white"
              onClick={handleBulkDeactivate}
              disabled={bulkWorking}
            >
              {bulkWorking ? <Loader2 size={13} className="animate-spin mr-1" /> : null}
              Деактивувати
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Delete Confirm */}
      <AlertDialog open={!!deleteTarget} onOpenChange={v => { if (!v) setDeleteTarget(null); }}>
        <AlertDialogContent className="bg-[#1a2235] border-white/10 text-white">
          <AlertDialogHeader>
            <AlertDialogTitle>Деактивувати особу?</AlertDialogTitle>
            <AlertDialogDescription className="text-white/50">
              «{deleteTarget?.full_name}» буде деактивовано. Всі дані збережуться.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="bg-white/10 border-0 text-white hover:bg-white/20">
              Скасувати
            </AlertDialogCancel>
            <AlertDialogAction
              className="bg-red-600 hover:bg-red-500 text-white"
              onClick={handleDelete}
            >
              Деактивувати
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Layout>
  );
}
