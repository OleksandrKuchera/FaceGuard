import { useEffect, useRef, useState } from 'react';
import Layout from '@/components/Layout';
import { getReports, createReport, downloadReport } from '@/api/client';
import type { Report, ReportType, ReportFormat, ReportStatus } from '@/types';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Separator } from '@/components/ui/separator';
import { Progress } from '@/components/ui/progress';
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
  Plus, Download, RefreshCw, Loader2, FileText,
  FileSpreadsheet, File, AlertCircle,
} from 'lucide-react';

// ── Constants ────────────────────────────────────────────────────────────────
const STATUS_BADGE: Record<ReportStatus, string> = {
  pending:    'bg-amber-500/20 text-amber-400',
  generating: 'bg-blue-500/20 text-blue-400',
  ready:      'bg-emerald-500/20 text-emerald-400',
  failed:     'bg-red-500/20 text-red-400',
};
const STATUS_LABEL: Record<ReportStatus, string> = {
  pending:    'Очікує',
  generating: 'Генерується',
  ready:      'Готово',
  failed:     'Помилка',
};

const REPORT_LABELS: Record<ReportType, string> = {
  attendance:      'Відвідуваність',
  unknown_persons: 'Невідомі особи',
  security_audit:  'Аудит безпеки',
  daily_summary:   'Денний підсумок',
  custom:          'Власний',
};

const FORMAT_ICON: Record<ReportFormat, React.ReactNode> = {
  pdf:  <File size={12} className="text-red-400" />,
  csv:  <FileText size={12} className="text-emerald-400" />,
  xlsx: <FileSpreadsheet size={12} className="text-blue-400" />,
};

// ── Main Page ────────────────────────────────────────────────────────────────
interface CreateForm {
  name: string;
  report_type: ReportType;
  format: ReportFormat;
  date_from: string;
  date_to: string;
}
const EMPTY_FORM: CreateForm = {
  name: '', report_type: 'attendance', format: 'pdf', date_from: '', date_to: '',
};

export default function Reports() {
  const [reports, setReports] = useState<Report[]>([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState(false);
  const [form, setForm] = useState<CreateForm>(EMPTY_FORM);
  const [saving, setSaving] = useState(false);
  const pollerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = () => {
    setLoading(true);
    getReports()
      .then(r => setReports((r.data as { results?: Report[] }).results ?? (r.data as Report[])))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    load();
    return () => { if (pollerRef.current) clearInterval(pollerRef.current); };
  }, []);

  // Poll while any report is in generating/pending state
  useEffect(() => {
    const hasActive = reports.some(r => r.status === 'generating' || r.status === 'pending');
    if (hasActive) {
      pollerRef.current = setInterval(() => {
        getReports()
          .then(r => {
            const updated = (r.data as { results?: Report[] }).results ?? (r.data as Report[]);
            setReports(updated);
            const stillActive = updated.some(rep => rep.status === 'generating' || rep.status === 'pending');
            if (!stillActive && pollerRef.current) {
              clearInterval(pollerRef.current);
              toast.success('Всі звіти згенеровано');
            }
          })
          .catch(() => {});
      }, 4000);
    } else if (pollerRef.current) {
      clearInterval(pollerRef.current);
    }
    return () => { if (pollerRef.current) clearInterval(pollerRef.current); };
  }, [reports]);

  const handleCreate = async (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault();
    setSaving(true);
    try {
      await createReport({
        name: form.name,
        report_type: form.report_type,
        format: form.format,
        params_json: { date_from: form.date_from, date_to: form.date_to },
      });
      toast.success('Звіт поставлено в чергу', { description: 'Генерація може зайняти кілька секунд' });
      setModal(false);
      setForm(EMPTY_FORM);
      load();
    } catch {
      toast.error('Помилка створення звіту');
    } finally {
      setSaving(false);
    }
  };

  const set = <K extends keyof CreateForm>(k: K, v: CreateForm[K]) => setForm(f => ({ ...f, [k]: v }));

  const handleDownload = async (r: Report) => {
    try {
      const res = await downloadReport(r.id);
      const url = URL.createObjectURL(new Blob([res.data as BlobPart]));
      const a = document.createElement('a');
      a.href = url;
      a.download = `${r.name}.${r.format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error('Помилка завантаження файлу');
    }
  };

  return (
    <Layout title="Звіти">
      <div className="page-header">
        <div>
          <h1>Звіти</h1>
          <div className="page-subtitle">Генерація PDF, CSV, Excel звітів</div>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={load} className="text-white/60 hover:text-white border border-white/10">
            <RefreshCw size={14} />
          </Button>
          <Button
            className="bg-gradient-to-r from-blue-700 to-blue-500 text-white"
            onClick={() => setModal(true)}
          >
            <Plus size={15} />
            Новий звіт
          </Button>
        </div>
      </div>

      <Separator className="mb-5 bg-white/10" />

      {/* Active progress banner */}
      {reports.some(r => r.status === 'generating') && (
        <div className="mb-4 p-4 rounded-xl bg-blue-500/10 border border-blue-500/20 flex items-center gap-3">
          <Loader2 size={16} className="text-blue-400 animate-spin flex-shrink-0" />
          <div className="flex-1">
            <div className="text-blue-400 text-sm font-medium">Генерується звіт...</div>
            <Progress value={undefined} className="mt-1.5 h-1 bg-white/10" />
          </div>
        </div>
      )}

      {loading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-14 w-full bg-white/5 rounded-xl" />)}
        </div>
      ) : (
        <div className="table-wrap">
          <Table>
            <TableHeader>
              <TableRow className="border-white/10 hover:bg-transparent">
                {['Назва', 'Тип', 'Формат', 'Статус', 'Хто створив', 'Дата', 'Дії'].map(h => (
                  <TableHead key={h} className="text-white/40 text-[11px] uppercase tracking-wider">{h}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {reports.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-16 text-white/30">
                    Звітів немає. Створіть перший!
                  </TableCell>
                </TableRow>
              ) : reports.map(r => (
                <TableRow key={r.id} className="border-white/10 hover:bg-white/5">
                  <TableCell className="font-medium text-white">{r.name}</TableCell>
                  <TableCell className="text-white/60 text-sm">{REPORT_LABELS[r.report_type] ?? r.report_type}</TableCell>
                  <TableCell>
                    <Badge className="bg-blue-500/20 text-blue-400 border-0 gap-1.5">
                      {FORMAT_ICON[r.format]}
                      {r.format.toUpperCase()}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    <Badge className={`border-0 gap-1.5 ${STATUS_BADGE[r.status] ?? 'bg-gray-500/20 text-gray-400'}`}>
                      {r.status === 'generating' && <Loader2 size={10} className="animate-spin" />}
                      {STATUS_LABEL[r.status] ?? r.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-white/50 text-sm">{r.created_by_name || '—'}</TableCell>
                  <TableCell className="text-white/40 text-xs whitespace-nowrap">
                    {new Date(r.created_at).toLocaleString('uk-UA')}
                  </TableCell>
                  <TableCell>
                    {r.status === 'ready' && (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            size="xs"
                            className="bg-emerald-600/80 hover:bg-emerald-500 text-white border-0"
                            onClick={() => handleDownload(r)}
                          >
                            <Download size={12} />
                            Завантажити
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Завантажити файл</TooltipContent>
                      </Tooltip>
                    )}
                    {r.status === 'failed' && (
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Badge className="bg-red-500/20 text-red-400 border-0 gap-1 cursor-help">
                            <AlertCircle size={10} />
                            Помилка
                          </Badge>
                        </TooltipTrigger>
                        <TooltipContent className="max-w-xs">{r.error_message || 'Невідома помилка'}</TooltipContent>
                      </Tooltip>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      {/* Create Dialog */}
      <Dialog open={modal} onOpenChange={v => { if (!v) { setModal(false); setForm(EMPTY_FORM); } }}>
        <DialogContent className="bg-[#1a2235] border-white/10 text-white max-w-md">
          <DialogHeader>
            <DialogTitle>Новий звіт</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleCreate} className="flex flex-col gap-4">
            <div className="flex flex-col gap-1.5">
              <Label className="text-white/60 text-xs">Назва звіту *</Label>
              <Input required value={form.name} onChange={e => set('name', e.target.value)}
                placeholder="Наприклад: Відвідуваність за квітень"
                className="bg-[#0a0e1a] border-white/10 text-white" />
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <Label className="text-white/60 text-xs">Тип звіту</Label>
                <Select value={form.report_type} onValueChange={v => set('report_type', v as ReportType)}>
                  <SelectTrigger className="bg-[#0a0e1a] border-white/10 text-white">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-[#1a2235] border-white/10">
                    {Object.entries(REPORT_LABELS).map(([k, v]) => (
                      <SelectItem key={k} value={k} className="text-white focus:bg-white/10">{v}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label className="text-white/60 text-xs">Формат</Label>
                <Select value={form.format} onValueChange={v => set('format', v as ReportFormat)}>
                  <SelectTrigger className="bg-[#0a0e1a] border-white/10 text-white">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent className="bg-[#1a2235] border-white/10">
                    <SelectItem value="pdf"  className="text-white focus:bg-white/10">PDF</SelectItem>
                    <SelectItem value="csv"  className="text-white focus:bg-white/10">CSV</SelectItem>
                    <SelectItem value="xlsx" className="text-white focus:bg-white/10">Excel (.xlsx)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="flex flex-col gap-1.5">
                <Label className="text-white/60 text-xs">Дата від</Label>
                <Input type="date" value={form.date_from} onChange={e => set('date_from', e.target.value)}
                  className="bg-[#0a0e1a] border-white/10 text-white" />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label className="text-white/60 text-xs">Дата до</Label>
                <Input type="date" value={form.date_to} onChange={e => set('date_to', e.target.value)}
                  className="bg-[#0a0e1a] border-white/10 text-white" />
              </div>
            </div>

            <DialogFooter className="mt-2">
              <Button type="button" variant="ghost" onClick={() => { setModal(false); setForm(EMPTY_FORM); }}
                className="text-white/60 hover:text-white">
                Скасувати
              </Button>
              <Button type="submit" disabled={saving}
                className="bg-gradient-to-r from-blue-700 to-blue-500 text-white">
                {saving ? <Loader2 size={14} className="animate-spin" /> : null}
                Генерувати
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </Layout>
  );
}
