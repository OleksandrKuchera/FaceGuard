import { useEffect, useState } from 'react';
import { useParams, useNavigate, Link } from 'react-router-dom';
import Layout from '@/components/Layout';
import {
  getPerson, getPhotos, deletePhoto, uploadPhoto,
  trainPerson, getTrainStatus, updatePerson, deletePerson, getEvents,
} from '@/api/client';
import type { Person, PersonPhoto, TrainStatus, RecognitionEvent, EventType } from '@/types';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Separator } from '@/components/ui/separator';
import { Progress } from '@/components/ui/progress';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel,
  AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  BarChart, Bar, XAxis, YAxis, Tooltip as ReTooltip,
  ResponsiveContainer, CartesianGrid,
} from 'recharts';
import {
  ArrowLeft, Zap, Trash2, Upload, CheckCircle2,
  XCircle, AlertTriangle, Loader2, Image,
} from 'lucide-react';

const EVENT_BADGE: Record<EventType, string> = {
  recognized:  'bg-emerald-500/20 text-emerald-400',
  unknown:     'bg-amber-500/20 text-amber-400',
  spoofing:    'bg-red-500/20 text-red-400',
  multi_face:  'bg-purple-500/20 text-purple-400',
  low_quality: 'bg-gray-500/20 text-gray-400',
};
const EVENT_LABEL: Record<EventType, string> = {
  recognized:  'Розпізнано',
  unknown:     'Невідомий',
  spoofing:    'Spoofing',
  multi_face:  'Кілька облич',
  low_quality: 'Низька якість',
};

export default function PersonDetail() {
  const { id } = useParams<{ id: string }>();
  const personId = Number(id);
  const navigate = useNavigate();

  const [person, setPerson] = useState<Person | null>(null);
  const [photos, setPhotos] = useState<PersonPhoto[]>([]);
  const [events, setEvents] = useState<RecognitionEvent[]>([]);
  const [chartEvents, setChartEvents] = useState<RecognitionEvent[]>([]);
  const [trainStatus, setTrainStatus] = useState<TrainStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [deletingPhoto, setDeletingPhoto] = useState<number | null>(null);
  const [uploading, setUploading] = useState(false);
  const [training, setTraining] = useState(false);
  const [confirmDeactivate, setConfirmDeactivate] = useState(false);
  const pollRef = { current: null as ReturnType<typeof setInterval> | null };

  const fetchChartEvents = async (targetPersonId: number) => {
    const since = new Date();
    since.setDate(since.getDate() - 13);
    const dateFrom = since.toISOString().slice(0, 10);

    const allEvents: RecognitionEvent[] = [];
    let page = 1;
    let total = 0;

    do {
      const response = await getEvents({
        person: String(targetPersonId),
        date_from: dateFrom,
        page: String(page),
      });
      const payload = response.data as {
        count?: number;
        results?: RecognitionEvent[];
      } | RecognitionEvent[];
      const batch = Array.isArray(payload) ? payload : (payload.results ?? []);
      total = Array.isArray(payload) ? batch.length : (payload.count ?? batch.length);
      allEvents.push(...batch);
      page += 1;
      if (Array.isArray(payload)) break;
    } while (allEvents.length < total);

    return allEvents;
  };

  const load = async () => {
    setLoading(true);
    try {
      const [personRes, photosRes, eventsRes, trainRes, chartEventsRes] = await Promise.all([
        getPerson(personId),
        getPhotos(personId),
        getEvents({ person: String(personId), page: '1' }),
        getTrainStatus(personId),
        fetchChartEvents(personId),
      ]);
      setPerson(personRes.data as Person);
      setPhotos(photosRes.data as PersonPhoto[]);
      const ed = eventsRes.data as { results?: RecognitionEvent[] };
      setEvents(ed.results ?? (eventsRes.data as RecognitionEvent[]));
      setTrainStatus(trainRes.data as TrainStatus);
      setChartEvents(chartEventsRes);
    } catch {
      toast.error('Помилка завантаження даних');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (personId) load();
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [personId]);

  const handleDeletePhoto = async (photoId: number) => {
    setDeletingPhoto(photoId);
    try {
      await deletePhoto(personId, photoId);
      setPhotos(prev => prev.filter(p => p.id !== photoId));
      toast.success('Фото видалено');
    } catch {
      toast.error('Помилка видалення');
    } finally {
      setDeletingPhoto(null);
    }
  };

  const handleUpload = async (files: FileList | null) => {
    if (!files?.length) return;
    setUploading(true);
    try {
      await uploadPhoto(personId, Array.from(files));
      toast.success(`Завантажено ${files.length} фото`);
      const r = await getPhotos(personId);
      setPhotos(r.data as PersonPhoto[]);
      window.setTimeout(async () => {
        try {
          const st = (await getTrainStatus(personId)).data as TrainStatus;
          setTrainStatus(st);
        } catch {
          // ignore
        }
      }, 2000);
    } catch {
      toast.error('Помилка завантаження');
    } finally {
      setUploading(false);
    }
  };

  const handleTrain = async () => {
    if (!person) return;
    setTraining(true);
    try {
      await trainPerson(personId);
      toast.success('Навчання запущено', { description: 'Опитуємо стан кожні 3 с…' });

      pollRef.current = setInterval(async () => {
        try {
          const r = await getTrainStatus(personId);
          const st = r.data as TrainStatus;
          setTrainStatus(st);
          if (st.task_state === 'SUCCESS' || st.task_state === 'FAILURE') {
            clearInterval(pollRef.current!);
            if (st.task_state === 'SUCCESS') {
              toast.success('Навчання завершено', {
                description: `${st.encodings_created} кодувань · якість ${((st.best_quality_score ?? 0) * 100).toFixed(0)}%`,
              });
            } else {
              toast.error('Навчання провалилось');
            }
          }
        } catch {
          clearInterval(pollRef.current!);
        }
      }, 3000);
    } catch {
      toast.error('Помилка запуску навчання');
    } finally {
      setTraining(false);
    }
  };

  const handleDeactivate = async () => {
    try {
      const fd = new FormData();
      fd.append('is_active', 'false');
      await updatePerson(personId, fd);
      await deletePerson(personId);
      toast.success(`«${person?.full_name}» деактивовано`);
      navigate('/persons');
    } catch {
      toast.error('Помилка деактивації');
    } finally {
      setConfirmDeactivate(false);
    }
  };

  // Build attendance chart data from last 14 days of events
  const chartData = (() => {
    const days: Record<string, number> = {};
    const now = new Date();
    for (let i = 13; i >= 0; i--) {
      const d = new Date(now);
      d.setDate(d.getDate() - i);
      days[d.toISOString().slice(0, 10)] = 0;
    }
    chartEvents
      .filter(ev => ev.event_type === 'recognized')
      .forEach(ev => {
        const day = ev.timestamp.slice(0, 10);
        if (day in days) days[day]++;
      });
    return Object.entries(days).map(([date, count]) => ({
      date: date.slice(5),
      count,
    }));
  })();

  if (loading) {
    return (
      <Layout title="Деталі особи">
        <div className="flex flex-col gap-4">
          <Skeleton className="h-10 w-48 bg-white/5 rounded-xl" />
          <Skeleton className="h-40 w-full bg-white/5 rounded-xl" />
          <Skeleton className="h-64 w-full bg-white/5 rounded-xl" />
        </div>
      </Layout>
    );
  }

  if (!person) {
    return (
      <Layout title="Не знайдено">
        <div className="empty-state">
          <XCircle size={40} className="mx-auto mb-3 text-white/20" />
          <p>Особу не знайдено.</p>
          <Link to="/persons" className="text-blue-400 text-sm mt-2 block">← Повернутись до списку</Link>
        </div>
      </Layout>
    );
  }

  return (
    <Layout title={person.full_name}>
      {/* Header */}
      <div className="page-header">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="icon-xs" onClick={() => navigate('/persons')}
            className="text-white/50 hover:text-white border border-white/10">
            <ArrowLeft size={14} />
          </Button>
          <div>
            <h1>{person.full_name}</h1>
            <div className="page-subtitle font-mono text-blue-400">{person.person_id}</div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            className="border-white/20 text-white hover:bg-white/10 gap-1.5"
            onClick={handleTrain}
            disabled={training}
          >
            {training ? <Loader2 size={14} className="animate-spin" /> : <Zap size={14} />}
            Навчати
          </Button>
          <Button
            variant="ghost"
            className="text-red-400 hover:text-red-300 hover:bg-red-500/10 border border-red-500/20"
            onClick={() => setConfirmDeactivate(true)}
          >
            <Trash2 size={14} />
            Деактивувати
          </Button>
        </div>
      </div>

      <div className="grid grid-cols-3 gap-5">

        {/* ── Info card */}
        <div className="col-span-1 flex flex-col gap-4">
          <div className="card p-5 flex flex-col gap-4">
            <div className="flex items-center gap-4">
              <Avatar className="w-16 h-16 rounded-xl">
                <AvatarImage src={person.primary_photo} className="object-cover" />
                <AvatarFallback className="bg-gradient-to-br from-blue-700 to-purple-600 text-white text-xl rounded-xl">
                  {person.full_name.charAt(0)}
                </AvatarFallback>
              </Avatar>
              <div>
                <div className="font-semibold text-white">{person.full_name}</div>
                <div className="text-xs text-white/40 mt-0.5">{person.department_name ?? '—'}</div>
                {person.is_active
                  ? <Badge className="bg-emerald-500/20 text-emerald-400 border-0 gap-1 mt-1 text-[10px]"><CheckCircle2 size={9} />Активний</Badge>
                  : <Badge className="bg-gray-500/20 text-gray-400 border-0 gap-1 mt-1 text-[10px]"><XCircle size={9} />Неактивний</Badge>}
              </div>
            </div>

            <Separator className="bg-white/10" />

            {[
              ['Роль', person.role],
              ['Рівень доступу', String(person.access_level)],
              ['Зареєстровано', new Date(person.created_at).toLocaleDateString('uk-UA')],
            ].map(([label, value]) => (
              <div key={label} className="flex justify-between text-sm">
                <span className="text-white/40">{label}</span>
                <span className="text-white">{value}</span>
              </div>
            ))}

            <div className="flex flex-wrap gap-2">
              {person.consent_given ? (
                <Badge className="bg-emerald-500/20 text-emerald-400 border-0">Consent given</Badge>
              ) : (
                <Badge className="bg-amber-500/20 text-amber-400 border-0">Consent missing</Badge>
              )}
              {person.deletion_requested && (
                <Badge className="bg-red-500/20 text-red-400 border-0">Deletion requested</Badge>
              )}
            </div>

            {person.notes && (
              <div className="bg-white/5 rounded-lg p-3 text-xs text-white/60">{person.notes}</div>
            )}
          </div>

          {/* Training status */}
          {trainStatus && (
            <div className="card p-4 flex flex-col gap-3">
              <div className="text-xs text-white/40 uppercase tracking-wider">Навчання</div>
              <div className="flex items-center gap-2">
                {trainStatus.task_state === 'PENDING' || trainStatus.task_state === 'STARTED' ? (
                  <Badge className="bg-blue-500/20 text-blue-300 border-0 gap-1"><Loader2 size={9} className="animate-spin" />Навчання…</Badge>
                ) : trainStatus.is_ready ? (
                  <Badge className="bg-purple-500/20 text-purple-300 border-0 gap-1"><Zap size={9} />{trainStatus.encodings_created} кодувань</Badge>
                ) : (
                  <Badge className="bg-gray-500/20 text-gray-400 border-0">Не навчено</Badge>
                )}
              </div>
              <div className="flex justify-between text-xs text-white/50">
                <span>Фото: {trainStatus.total_photos}</span>
                <span>Виявлено: {trainStatus.photos_processed}</span>
                <span>Помилок: {trainStatus.photos_failed}</span>
              </div>
              {trainStatus.best_quality_score != null && (
                <div className="flex items-center gap-2 text-xs text-white/50">
                  <span>Якість</span>
                  <Progress value={trainStatus.best_quality_score * 100} className="h-1.5 flex-1 bg-white/10" />
                  <span className="font-mono">{(trainStatus.best_quality_score * 100).toFixed(0)}%</span>
                </div>
              )}
            </div>
          )}
        </div>

        {/* ── Right column */}
        <div className="col-span-2 flex flex-col gap-5">

          {/* Attendance chart */}
          <div className="card p-5">
            <div className="text-sm font-medium text-white/80 mb-4">Відвідуваність (14 днів)</div>
            <ResponsiveContainer width="100%" height={120}>
              <BarChart data={chartData} margin={{ top: 0, right: 0, left: -20, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="date" tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 10 }} />
                <YAxis tick={{ fill: 'rgba(255,255,255,0.3)', fontSize: 10 }} allowDecimals={false} />
                <ReTooltip
                  contentStyle={{ background: '#1a2235', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 8, color: '#fff' }}
                  labelStyle={{ color: 'rgba(255,255,255,0.5)', fontSize: 11 }}
                />
                <Bar dataKey="count" fill="#3b82f6" radius={[3, 3, 0, 0]} name="Входи" />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Photo gallery */}
          <div className="card p-5">
            <div className="flex items-center justify-between mb-4">
              <div className="text-sm font-medium text-white/80">
                Фотографії <span className="text-white/40">({photos.length})</span>
              </div>
              <label className="cursor-pointer">
                <Button variant="outline" size="sm" className="border-white/20 text-white hover:bg-white/10 gap-1.5" asChild>
                  <span>
                    {uploading ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
                    Додати
                  </span>
                </Button>
                <input type="file" accept="image/*" multiple className="hidden"
                  onChange={e => handleUpload(e.target.files)} disabled={uploading} />
              </label>
            </div>

            <div className="mb-4 rounded-lg border border-blue-500/20 bg-blue-500/10 p-3 text-xs text-blue-100/80">
              Завантаження фото тут запускає автоматичну валідацію і генерацію embeddings.
              Для нормального навчання завантажте 5-10 чітких фото однієї людини з різних кутів,
              після чого натисніть «Навчати», якщо хочете примусово перебудувати кеш.
            </div>

            {photos.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-10 text-white/30 gap-2">
                <Image size={28} />
                <span className="text-sm">Фото відсутні</span>
              </div>
            ) : (
              <div className="grid grid-cols-6 gap-2">
                {photos.map(photo => (
                  <div key={photo.id} className="relative group rounded-lg overflow-hidden border border-white/10 aspect-square">
                    <img src={photo.image} alt="" className="w-full h-full object-cover" />
                    <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                      <Button
                        variant="ghost" size="icon-xs"
                        className="text-red-400 hover:text-red-300 hover:bg-red-500/20"
                        onClick={() => handleDeletePhoto(photo.id)}
                        disabled={deletingPhoto === photo.id}
                      >
                        {deletingPhoto === photo.id ? <Loader2 size={12} className="animate-spin" /> : <Trash2 size={12} />}
                      </Button>
                    </div>
                    <div className="absolute bottom-0 left-0 right-0 p-0.5 flex flex-col gap-0.5">
                      {photo.face_detected === true && (
                        <Badge className="bg-emerald-500/80 text-white border-0 text-[8px] px-1 py-0 w-fit leading-tight">✓</Badge>
                      )}
                      {photo.face_detected === false && (
                        <Badge className="bg-red-500/80 text-white border-0 text-[8px] px-1 py-0 w-fit leading-tight">✗</Badge>
                      )}
                      {photo.quality_score != null && (
                        <Badge className="bg-black/60 text-white/70 border-0 text-[8px] px-1 py-0 w-fit leading-tight">
                          {(photo.quality_score * 100).toFixed(0)}%
                        </Badge>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Recent events */}
          <div className="card p-5">
            <div className="flex items-center justify-between mb-4">
              <div className="text-sm font-medium text-white/80">Остання активність</div>
              <Link to={`/events?person=${personId}`}
                className="text-xs text-blue-400 hover:text-blue-300">
                Всі події →
              </Link>
            </div>
            {events.length === 0 ? (
              <div className="text-center py-6 text-white/30 text-sm">Подій не знайдено</div>
            ) : (
              <div className="table-wrap">
                <Table>
                  <TableHeader>
                    <TableRow className="border-white/10 hover:bg-transparent">
                      {['Тип', 'Камера', 'Впевненість', 'Час'].map(h => (
                        <TableHead key={h} className="text-white/40 text-[11px] uppercase tracking-wider">{h}</TableHead>
                      ))}
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {events.slice(0, 10).map(ev => (
                      <TableRow key={ev.id} className={`border-white/10 hover:bg-white/5 ${ev.is_alert ? 'bg-red-500/5' : ''}`}>
                        <TableCell>
                          <Badge className={`border-0 text-[11px] gap-1 ${EVENT_BADGE[ev.event_type] ?? 'bg-gray-500/20 text-gray-400'}`}>
                            {ev.is_alert && <AlertTriangle size={9} />}
                            {EVENT_LABEL[ev.event_type] ?? ev.event_type}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-white/60 text-sm">{ev.camera?.name}</TableCell>
                        <TableCell>
                          {ev.confidence != null ? (
                            <div className="flex items-center gap-2 w-20">
                              <Progress value={ev.confidence} className="h-1.5 flex-1 bg-white/10" />
                              <span className="text-xs font-mono text-white/50">{ev.confidence.toFixed(0)}%</span>
                            </div>
                          ) : <span className="text-white/30">—</span>}
                        </TableCell>
                        <TableCell className="text-white/40 text-xs whitespace-nowrap">
                          {new Date(ev.timestamp).toLocaleString('uk-UA')}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            )}
          </div>

        </div>
      </div>

      {/* Deactivate confirm */}
      <AlertDialog open={confirmDeactivate} onOpenChange={setConfirmDeactivate}>
        <AlertDialogContent className="bg-[#1a2235] border-white/10 text-white">
          <AlertDialogHeader>
            <AlertDialogTitle>Деактивувати особу?</AlertDialogTitle>
            <AlertDialogDescription className="text-white/50">
              «{person.full_name}» буде деактивовано. Всі дані збережуться.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="bg-white/10 border-0 text-white hover:bg-white/20">Скасувати</AlertDialogCancel>
            <AlertDialogAction className="bg-red-600 hover:bg-red-500 text-white" onClick={handleDeactivate}>
              Деактивувати
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Layout>
  );
}
