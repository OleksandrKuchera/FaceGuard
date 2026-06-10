import { useEffect, useMemo, useState } from 'react';
import { useSearchParams, Link } from 'react-router-dom';
import Layout from '@/components/Layout';
import { getEvents, reviewEvent } from '@/api/client';
import type { RecognitionEvent, EventType } from '@/types';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Progress } from '@/components/ui/progress';
import { Separator } from '@/components/ui/separator';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import {
  Tooltip, TooltipContent, TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  CheckCircle2, AlertTriangle, Image, ChevronLeft, ChevronRight, X,
  ChevronUp, ChevronDown, ChevronsUpDown,
} from 'lucide-react';

// ── Sort helpers ──────────────────────────────────────────────────────────────
type EventSortKey = 'event_type' | 'confidence' | 'timestamp' | 'is_alert';
type SortDir = 'asc' | 'desc';

function SortIcon({ col, sortKey, sortDir }: { col: EventSortKey; sortKey: EventSortKey; sortDir: SortDir }) {
  if (col !== sortKey) return <ChevronsUpDown size={11} className="text-white/20" />;
  return sortDir === 'asc'
    ? <ChevronUp size={11} className="text-blue-400" />
    : <ChevronDown size={11} className="text-blue-400" />;
}

// ── Constants ────────────────────────────────────────────────────────────────
const EVENT_BADGE: Record<EventType, string> = {
  recognized:  'bg-emerald-500/20 text-emerald-400',
  unknown:     'bg-amber-500/20 text-amber-400',
  spoofing:    'bg-red-500/20 text-red-400',
  multi_face:  'bg-purple-500/20 text-purple-400',
  low_quality: 'bg-gray-500/20 text-gray-400',
};
const EVENT_LABEL: Record<EventType, string> = {
  recognized:  '✅ Розпізнано',
  unknown:     '❓ Невідомий',
  spoofing:    '🚨 Spoofing',
  multi_face:  '👥 Кілька облич',
  low_quality: '🌫 Низька якість',
};

// ── Snapshot Dialog ───────────────────────────────────────────────────────────
function EventSnapshotDialog({ event, open, onClose }: {
  event: RecognitionEvent | null; open: boolean; onClose: () => void;
}) {
  if (!event) return null;
  return (
    <Dialog open={open} onOpenChange={v => { if (!v) onClose(); }}>
      <DialogContent className="bg-[#1a2235] border-white/10 text-white max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            Подія #{event.id} — {new Date(event.timestamp).toLocaleString('uk-UA')}
          </DialogTitle>
        </DialogHeader>

        <div className="flex flex-col gap-4">
          {event.frame_snapshot ? (
            <img src={event.frame_snapshot} alt="frame"
              className="w-full rounded-lg border border-white/10 object-contain max-h-80" />
          ) : (
            <div className="h-48 flex flex-col items-center justify-center bg-white/5 rounded-lg border border-white/10 text-white/30 gap-2">
              <Image size={32} />
              <span className="text-sm">Знімок відсутній</span>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="bg-white/5 rounded-lg p-3 flex flex-col gap-1">
              <span className="text-white/40 text-xs uppercase tracking-wider">Тип події</span>
              <Badge className={`border-0 w-fit ${EVENT_BADGE[event.event_type] ?? 'bg-gray-500/20 text-gray-400'}`}>
                {EVENT_LABEL[event.event_type] ?? event.event_type}
              </Badge>
            </div>
            <div className="bg-white/5 rounded-lg p-3 flex flex-col gap-1">
              <span className="text-white/40 text-xs uppercase tracking-wider">Особа</span>
              <span className="text-white font-medium">
                {event.person ? `${event.person.full_name} (${event.person.person_id})` : <span className="text-amber-400">Невідомий</span>}
              </span>
            </div>
            <div className="bg-white/5 rounded-lg p-3 flex flex-col gap-1">
              <span className="text-white/40 text-xs uppercase tracking-wider">Камера</span>
              <span className="text-white">{event.camera?.name}</span>
            </div>
            <div className="bg-white/5 rounded-lg p-3 flex flex-col gap-1">
              <span className="text-white/40 text-xs uppercase tracking-wider">Впевненість</span>
              {event.confidence != null ? (
                <div className="flex items-center gap-2">
                  <Progress value={event.confidence} className="h-2 flex-1 bg-white/10" />
                  <span className="text-white font-mono text-xs">{event.confidence.toFixed(1)}%</span>
                </div>
              ) : <span className="text-white/40">—</span>}
            </div>
            <div className="bg-white/5 rounded-lg p-3 flex flex-col gap-1">
              <span className="text-white/40 text-xs uppercase tracking-wider">Liveness score</span>
              {event.liveness_score != null ? (
                <div className="flex items-center gap-2">
                  <Progress
                    value={event.liveness_score * 100}
                    className="h-2 flex-1 bg-white/10"
                  />
                  <span className={`font-mono text-xs ${event.liveness_score > 0.7 ? 'text-emerald-400' : 'text-amber-400'}`}>
                    {(event.liveness_score * 100).toFixed(0)}%
                  </span>
                </div>
              ) : <span className="text-white/40">—</span>}
            </div>
            <div className="bg-white/5 rounded-lg p-3 flex flex-col gap-1">
              <span className="text-white/40 text-xs uppercase tracking-wider">Алерт</span>
              {event.is_alert
                ? <Badge className="bg-red-500/20 text-red-400 border-0 w-fit gap-1"><AlertTriangle size={10} />Так</Badge>
                : <span className="text-white/40">—</span>}
            </div>
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
interface Filters {
  event_type: EventType | '';
  is_alert: '' | 'true' | 'false';
  date_from: string;
  date_to: string;
  person: string;
}

const EMPTY_FILTERS: Filters = { event_type: '', is_alert: '', date_from: '', date_to: '', person: '' };
const PAGE_SIZE = 50;

export default function Events() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [events, setEvents] = useState<RecognitionEvent[]>([]);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState<Filters>({
    ...EMPTY_FILTERS,
    person: searchParams.get('person') ?? '',
  });
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [selected, setSelected] = useState<RecognitionEvent | null>(null);
  const [reviewing, setReviewing] = useState<number | null>(null);

  // ── Sorting (client-side on current page) ──────────────────────────────────
  const [sortKey, setSortKey] = useState<EventSortKey>('timestamp');
  const [sortDir, setSortDir] = useState<SortDir>('desc');

  const toggleSort = (key: EventSortKey) => {
    if (sortKey === key) { setSortDir(d => d === 'asc' ? 'desc' : 'asc'); }
    else { setSortKey(key); setSortDir('asc'); }
  };

  const sorted = useMemo(() => {
    return [...events].sort((a, b) => {
      let av: string | number = 0;
      let bv: string | number = 0;
      if (sortKey === 'event_type')  { av = a.event_type;      bv = b.event_type; }
      if (sortKey === 'confidence')  { av = a.confidence ?? 0; bv = b.confidence ?? 0; }
      if (sortKey === 'timestamp')   { av = a.timestamp;        bv = b.timestamp; }
      if (sortKey === 'is_alert')    { av = a.is_alert ? 1 : 0; bv = b.is_alert ? 1 : 0; }
      if (av < bv) return sortDir === 'asc' ? -1 : 1;
      if (av > bv) return sortDir === 'asc' ? 1 : -1;
      return 0;
    });
  }, [events, sortKey, sortDir]);

  const load = () => {
    setLoading(true);
    const params: Record<string, string> = { page: String(page) };
    if (filters.event_type) params.event_type = filters.event_type;
    if (filters.is_alert)   params.is_alert   = filters.is_alert;
    if (filters.date_from)  params.date_from  = filters.date_from;
    if (filters.date_to)    params.date_to    = filters.date_to;
    if (filters.person)     params.person     = filters.person;

    getEvents(params)
      .then(r => {
        const d = r.data as { results?: RecognitionEvent[]; count?: number };
        setEvents(d.results ?? (r.data as RecognitionEvent[]));
        setTotal(d.count ?? 0);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [filters, page]);

  const setF = <K extends keyof Filters>(k: K, v: Filters[K]) => {
    setFilters(f => ({ ...f, [k]: v }));
    setPage(1);
    if (k === 'person') {
      const next = new URLSearchParams(searchParams);
      if (v) next.set('person', v as string); else next.delete('person');
      setSearchParams(next, { replace: true });
    }
  };

  const clearAll = () => {
    setFilters(EMPTY_FILTERS);
    setPage(1);
    setSearchParams({}, { replace: true });
  };

  const handleReview = async (ev: RecognitionEvent) => {
    setReviewing(ev.id);
    try {
      await reviewEvent(ev.id);
      toast.success('Подію позначено як переглянуту');
      load();
    } catch {
      toast.error('Помилка');
    } finally {
      setReviewing(null);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <Layout title="Журнал подій">
      <div className="page-header">
        <div>
          <h1>Журнал подій</h1>
          <div className="page-subtitle">Всього: {total.toLocaleString('uk-UA')} подій</div>
        </div>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-5">
        <Select value={filters.event_type || '__all__'} onValueChange={v => setF('event_type', v === '__all__' ? '' : v as EventType)}>
          <SelectTrigger className="bg-[#1a2235] border-white/10 text-white w-48">
            <SelectValue placeholder="Всі типи" />
          </SelectTrigger>
          <SelectContent className="bg-[#1a2235] border-white/10">
            <SelectItem value="__all__" className="text-white focus:bg-white/10">Всі типи</SelectItem>
            {Object.entries(EVENT_LABEL).map(([k, v]) => (
              <SelectItem key={k} value={k} className="text-white focus:bg-white/10">{v}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select value={filters.is_alert || '__all__'} onValueChange={v => setF('is_alert', v === '__all__' ? '' : v as 'true' | 'false')}>
          <SelectTrigger className="bg-[#1a2235] border-white/10 text-white w-44">
            <SelectValue placeholder="Алерти" />
          </SelectTrigger>
          <SelectContent className="bg-[#1a2235] border-white/10">
            <SelectItem value="__all__" className="text-white focus:bg-white/10">Всі алерти</SelectItem>
            <SelectItem value="true"    className="text-white focus:bg-white/10">🔴 Тільки алерти</SelectItem>
            <SelectItem value="false"   className="text-white focus:bg-white/10">Без алертів</SelectItem>
          </SelectContent>
        </Select>

        <div className="flex items-center gap-2">
          <Input type="date" value={filters.date_from} onChange={e => setF('date_from', e.target.value)}
            className="bg-[#1a2235] border-white/10 text-white w-40" />
          <span className="text-white/30 text-sm">—</span>
          <Input type="date" value={filters.date_to} onChange={e => setF('date_to', e.target.value)}
            className="bg-[#1a2235] border-white/10 text-white w-40" />
        </div>

        <div className="relative">
          <Input
            placeholder="ID особи…"
            value={filters.person}
            onChange={e => setF('person', e.target.value)}
            className="bg-[#1a2235] border-white/10 text-white w-36 pr-7"
          />
          {filters.person && (
            <button
              onClick={() => setF('person', '')}
              className="absolute right-2 top-1/2 -translate-y-1/2 text-white/30 hover:text-white"
            >
              <X size={12} />
            </button>
          )}
        </div>

        {(filters.event_type || filters.is_alert || filters.date_from || filters.date_to || filters.person) && (
          <Button variant="ghost" size="sm" onClick={clearAll}
            className="text-white/50 hover:text-white border border-white/10">
            Скинути фільтри
          </Button>
        )}
      </div>

      <Separator className="mb-5 bg-white/10" />

      {loading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} className="h-12 w-full bg-white/5 rounded-xl" />)}
        </div>
      ) : (
        <>
          <div className="table-wrap">
            <Table>
              <TableHeader>
                <TableRow className="border-white/10 hover:bg-transparent">
                  {([
                    ['Тип',         'event_type'],
                    ['Особа',       null],
                    ['Камера',      null],
                    ['Впевненість', 'confidence'],
                    ['Liveness',    null],
                    ['Час',         'timestamp'],
                    ['Алерт',       'is_alert'],
                    ['Дії',         null],
                  ] as [string, EventSortKey | null][]).map(([label, key]) => (
                    <TableHead
                      key={label}
                      className={`text-white/40 text-[11px] uppercase tracking-wider ${key ? 'cursor-pointer select-none hover:text-white/70 transition-colors' : ''}`}
                      onClick={key ? () => toggleSort(key) : undefined}
                    >
                      {key ? (
                        <span className="flex items-center gap-1">
                          {label}
                          <SortIcon col={key} sortKey={sortKey} sortDir={sortDir} />
                        </span>
                      ) : label}
                    </TableHead>
                  ))}
                </TableRow>
              </TableHeader>
              <TableBody>
                {sorted.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={8} className="text-center py-16 text-white/30">
                      Подій не знайдено
                    </TableCell>
                  </TableRow>
                ) : sorted.map(ev => (
                  <TableRow
                    key={ev.id}
                    className={`border-white/10 hover:bg-white/5 cursor-pointer ${ev.is_alert ? 'bg-red-500/5' : ''}`}
                    onClick={() => setSelected(ev)}
                  >
                    <TableCell onClick={e => e.stopPropagation()}>
                      <Badge className={`border-0 text-[11px] ${EVENT_BADGE[ev.event_type] ?? 'bg-gray-500/20 text-gray-400'}`}>
                        {EVENT_LABEL[ev.event_type] ?? ev.event_type}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-white/80">
                      {ev.person
                        ? <Link
                            to={`/persons/${ev.person.id}`}
                            className="hover:text-blue-400 transition-colors"
                            onClick={e => e.stopPropagation()}
                          >
                            {ev.person.full_name}{' '}
                            <span className="text-blue-400 font-mono text-xs">({ev.person.person_id})</span>
                          </Link>
                        : <span className="text-amber-400">невідомий</span>}
                    </TableCell>
                    <TableCell className="text-white/60 text-sm">{ev.camera?.name}</TableCell>
                    <TableCell>
                      {ev.confidence != null ? (
                        <div className="flex items-center gap-2 w-24">
                          <Progress value={ev.confidence} className="h-1.5 flex-1 bg-white/10" />
                          <span className="text-white/60 font-mono text-xs">{ev.confidence.toFixed(0)}%</span>
                        </div>
                      ) : <span className="text-white/30">—</span>}
                    </TableCell>
                    <TableCell>
                      {ev.liveness_score != null ? (
                        <div className="w-16 h-1.5 bg-white/10 rounded-full overflow-hidden">
                          <div
                            className={`h-full rounded-full ${ev.liveness_score > 0.7 ? 'bg-emerald-400' : 'bg-amber-400'}`}
                            style={{ width: `${ev.liveness_score * 100}%` }}
                          />
                        </div>
                      ) : <span className="text-white/30">—</span>}
                    </TableCell>
                    <TableCell className="text-white/50 text-xs whitespace-nowrap">
                      {new Date(ev.timestamp).toLocaleString('uk-UA')}
                    </TableCell>
                    <TableCell>
                      {ev.is_alert
                        ? <Badge className="bg-red-500/20 text-red-400 border-0 gap-1"><AlertTriangle size={10} />Алерт</Badge>
                        : <span className="text-white/30">—</span>}
                    </TableCell>
                    <TableCell onClick={e => e.stopPropagation()}>
                      {!ev.reviewed_at ? (
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <Button
                              variant="ghost" size="icon-xs"
                              className="text-emerald-400 hover:text-emerald-300 hover:bg-emerald-500/10"
                              disabled={reviewing === ev.id}
                              onClick={() => handleReview(ev)}
                            >
                              <CheckCircle2 size={14} />
                            </Button>
                          </TooltipTrigger>
                          <TooltipContent>Позначити переглянутим</TooltipContent>
                        </Tooltip>
                      ) : (
                        <span className="text-emerald-400/60 text-xs">✓ Переглянуто</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>

          {/* Pagination */}
          <div className="flex items-center justify-between mt-4">
            <span className="text-xs text-white/40">
              Показано {Math.min((page - 1) * PAGE_SIZE + 1, total)}–{Math.min(page * PAGE_SIZE, total)} з {total}
            </span>
            <div className="flex items-center gap-2">
              <Button variant="ghost" size="icon-sm" disabled={page === 1} onClick={() => setPage(p => p - 1)}
                className="text-white/60 hover:text-white border border-white/10">
                <ChevronLeft size={14} />
              </Button>
              <span className="text-white/50 text-xs px-2">Стор. {page} / {totalPages}</span>
              <Button variant="ghost" size="icon-sm" disabled={page >= totalPages} onClick={() => setPage(p => p + 1)}
                className="text-white/60 hover:text-white border border-white/10">
                <ChevronRight size={14} />
              </Button>
            </div>
          </div>
        </>
      )}

      {/* Snapshot Dialog */}
      <EventSnapshotDialog
        event={selected}
        open={!!selected}
        onClose={() => setSelected(null)}
      />
    </Layout>
  );
}
