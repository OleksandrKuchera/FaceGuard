import { useEffect, useState } from 'react';
import Layout from '@/components/Layout';
import { getSpoofing, getAuditLog } from '@/api/client';
import type { SpoofingAttempt, AuditLog, AttackType } from '@/types';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Separator } from '@/components/ui/separator';
import { Card, CardContent } from '@/components/ui/card';
import {
  Tabs, TabsContent, TabsList, TabsTrigger,
} from '@/components/ui/tabs';
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter,
} from '@/components/ui/dialog';
import {
  ShieldAlert, FileSearch, Eye, Camera, AlertTriangle,
  Image, RefreshCw, TrendingUp, Shield, Activity,
} from 'lucide-react';

// ── Constants ────────────────────────────────────────────────────────────────
const ATTACK_BADGE: Record<AttackType, string> = {
  photo:   'bg-amber-500/20 text-amber-400',
  video:   'bg-red-500/20 text-red-400',
  unknown: 'bg-gray-500/20 text-gray-400',
};
const ATTACK_LABEL: Record<AttackType, string> = {
  photo:   '📷 Фото-атака',
  video:   '🎬 Відео-атака',
  unknown: '❓ Невідомий тип',
};

// ── Evidence Dialog ───────────────────────────────────────────────────────────
function EvidenceDialog({ attempt, open, onClose }: {
  attempt: SpoofingAttempt | null; open: boolean; onClose: () => void;
}) {
  if (!attempt) return null;
  return (
    <Dialog open={open} onOpenChange={v => { if (!v) onClose(); }}>
      <DialogContent className="bg-[#1a2235] border-white/10 text-white max-w-lg">
        <DialogHeader>
          <DialogTitle>Доказ атаки — {attempt.camera_name}</DialogTitle>
        </DialogHeader>
        <div className="flex flex-col gap-4">
          {attempt.frame_evidence ? (
            <img src={attempt.frame_evidence} alt="evidence"
              className="w-full rounded-lg border border-red-500/20 object-contain max-h-72" />
          ) : (
            <div className="h-40 flex flex-col items-center justify-center bg-white/5 rounded-lg border border-white/10 text-white/30 gap-2">
              <Image size={28} />
              <span className="text-sm">Знімок відсутній</span>
            </div>
          )}
          <div className="grid grid-cols-2 gap-3 text-sm">
            <div className="bg-white/5 rounded-lg p-3">
              <span className="text-white/40 text-xs block mb-1">Тип атаки</span>
              <Badge className={`border-0 ${ATTACK_BADGE[attempt.attack_type]}`}>
                {ATTACK_LABEL[attempt.attack_type]}
              </Badge>
            </div>
            <div className="bg-white/5 rounded-lg p-3">
              <span className="text-white/40 text-xs block mb-1">EAR значення</span>
              <span className="font-mono text-white">{attempt.ear_value?.toFixed(3) ?? '—'}</span>
            </div>
            <div className="bg-white/5 rounded-lg p-3">
              <span className="text-white/40 text-xs block mb-1">IP адреса</span>
              <span className="font-mono text-red-400">{attempt.ip_address ?? '—'}</span>
            </div>
            <div className="bg-white/5 rounded-lg p-3">
              <span className="text-white/40 text-xs block mb-1">Час виявлення</span>
              <span className="text-white text-xs">{new Date(attempt.detected_at).toLocaleString('uk-UA')}</span>
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

// ── Stat Card ─────────────────────────────────────────────────────────────────
function StatCard({ icon: Icon, label, value, color }: {
  icon: React.ElementType; label: string; value: number | string; color: string;
}) {
  return (
    <Card className="bg-[#1a2235] border-white/10">
      <CardContent className="p-4 flex items-center gap-3">
        <div className={`w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0 ${color}`}>
          <Icon size={18} />
        </div>
        <div>
          <div className="text-2xl font-extrabold text-white leading-none">{value}</div>
          <div className="text-xs text-white/40 mt-0.5">{label}</div>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────
export default function Security() {
  const [spoofing, setSpoofing] = useState<SpoofingAttempt[]>([]);
  const [audit, setAudit] = useState<AuditLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [dateFilter, setDateFilter] = useState('');
  const [evidenceTarget, setEvidenceTarget] = useState<SpoofingAttempt | null>(null);

  const [activeTab, setActiveTab] = useState<'spoofing' | 'audit'>('spoofing');
  const [refreshKey, setRefreshKey] = useState(0);

  // Spoofing: load when tab active or refresh triggered
  useEffect(() => {
    if (activeTab !== 'spoofing') return;
    setLoading(true);
    getSpoofing()
      .then(r => setSpoofing((r.data as { results?: SpoofingAttempt[] }).results ?? (r.data as SpoofingAttempt[])))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [activeTab, refreshKey]);

  // Audit: load when tab active, dateFilter changes, or refresh triggered
  useEffect(() => {
    if (activeTab !== 'audit') return;
    setLoading(true);
    const params: Record<string, string> = {};
    if (dateFilter) params.date_from = dateFilter;
    getAuditLog(params)
      .then(r => setAudit((r.data as { results?: AuditLog[] }).results ?? (r.data as AuditLog[])))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [activeTab, dateFilter, refreshKey]);

  // Stats
  const photoCount   = spoofing.filter(s => s.attack_type === 'photo').length;
  const last24h      = spoofing.filter(s => Date.now() - new Date(s.detected_at).getTime() < 86_400_000).length;
  const uniqueCams   = new Set(spoofing.map(s => s.camera_name)).size;

  return (
    <Layout title="Безпека">
      <div className="page-header">
        <div>
          <h1>Безпека</h1>
          <div className="page-subtitle">Anti-spoofing журнал та аудит дій</div>
        </div>
        <Button variant="ghost" size="sm" className="text-white/60 hover:text-white border border-white/10"
          onClick={() => setRefreshKey(k => k + 1)}>
          <RefreshCw size={14} />
          Оновити
        </Button>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <StatCard icon={ShieldAlert}   label="Всього атак"        value={spoofing.length}  color="bg-red-500/20 text-red-400" />
        <StatCard icon={AlertTriangle} label="За 24 год"          value={last24h}           color="bg-amber-500/20 text-amber-400" />
        <StatCard icon={Activity}      label="Фото-атаки"         value={photoCount}        color="bg-purple-500/20 text-purple-400" />
        <StatCard icon={Camera}        label="Камер задіяно"      value={uniqueCams}        color="bg-blue-500/20 text-blue-400" />
      </div>

      <Separator className="mb-5 bg-white/10" />

      <Tabs defaultValue="spoofing" onValueChange={v => setActiveTab(v as 'spoofing' | 'audit')}>
        <TabsList className="bg-[#1a2235] border border-white/10 p-1 mb-5">
          <TabsTrigger
            value="spoofing"
            className="data-[state=active]:bg-blue-600 data-[state=active]:text-white text-white/50 gap-2"
          >
            <ShieldAlert size={14} />
            Spoofing-атаки
            {spoofing.length > 0 && (
              <Badge className="bg-red-500/30 text-red-400 border-0 text-[10px] px-1.5 py-0 ml-1">
                {spoofing.length}
              </Badge>
            )}
          </TabsTrigger>
          <TabsTrigger
            value="audit"
            className="data-[state=active]:bg-blue-600 data-[state=active]:text-white text-white/50 gap-2"
          >
            <FileSearch size={14} />
            Аудит лог
          </TabsTrigger>
        </TabsList>

        {/* Spoofing Tab */}
        <TabsContent value="spoofing">
          {loading ? (
            <div className="flex flex-col gap-2">
              {Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-12 w-full bg-white/5 rounded-xl" />)}
            </div>
          ) : (
            <div className="table-wrap">
              <Table>
                <TableHeader>
                  <TableRow className="border-white/10 hover:bg-transparent">
                    {['Камера', 'Тип атаки', 'EAR', 'Texture', 'Знімок', 'IP адреса', 'Час', 'Дії'].map(h => (
                      <TableHead key={h} className="text-white/40 text-[11px] uppercase tracking-wider">{h}</TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {spoofing.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={8} className="text-center py-16">
                        <div className="flex flex-col items-center gap-2 text-white/30">
                          <Shield size={32} />
                          <span>Спроб spoofing не виявлено 🎉</span>
                        </div>
                      </TableCell>
                    </TableRow>
                  ) : spoofing.map(s => (
                    <TableRow key={s.id} className="border-white/10 hover:bg-white/5">
                      <TableCell className="font-medium text-white">{s.camera_name}</TableCell>
                      <TableCell>
                        <Badge className={`border-0 ${ATTACK_BADGE[s.attack_type] ?? 'bg-gray-500/20 text-gray-400'}`}>
                          {ATTACK_LABEL[s.attack_type] ?? s.attack_type}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-mono text-xs text-white/60">{s.ear_value?.toFixed(3) ?? '—'}</TableCell>
                      <TableCell className="font-mono text-xs text-white/60">{s.texture_score?.toFixed(2) ?? '—'}</TableCell>
                      <TableCell>
                        {s.frame_evidence ? (
                          <img src={s.frame_evidence} alt="evidence"
                            className="w-14 h-10 object-cover rounded border border-red-500/20 cursor-pointer hover:opacity-80 transition-opacity"
                            onClick={() => setEvidenceTarget(s)}
                          />
                        ) : <span className="text-white/30">—</span>}
                      </TableCell>
                      <TableCell className="font-mono text-red-400 text-xs">{s.ip_address ?? '—'}</TableCell>
                      <TableCell className="text-white/40 text-xs whitespace-nowrap">
                        {new Date(s.detected_at).toLocaleString('uk-UA')}
                      </TableCell>
                      <TableCell>
                        <Button variant="ghost" size="icon-xs" onClick={() => setEvidenceTarget(s)}>
                          <Eye size={13} />
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </TabsContent>

        {/* Audit Tab */}
        <TabsContent value="audit">
          <div className="flex gap-3 mb-4 flex-wrap">
            <Input
              type="date"
              value={dateFilter}
              onChange={e => { setDateFilter(e.target.value); }}
              placeholder="Від дати"
              className="bg-[#1a2235] border-white/10 text-white w-44"
            />
            {dateFilter && (
              <Button variant="ghost" size="sm" onClick={() => setDateFilter('')}
                className="text-white/50 hover:text-white border border-white/10">
                Скинути
              </Button>
            )}
          </div>
          {loading ? (
            <div className="flex flex-col gap-2">
              {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-12 w-full bg-white/5 rounded-xl" />)}
            </div>
          ) : (
            <div className="table-wrap">
              <Table>
                <TableHeader>
                  <TableRow className="border-white/10 hover:bg-transparent">
                    {['Користувач', 'Дія', 'Ресурс', 'IP', 'Час'].map(h => (
                      <TableHead key={h} className="text-white/40 text-[11px] uppercase tracking-wider">{h}</TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {audit.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} className="text-center py-16">
                        <div className="flex flex-col items-center gap-2 text-white/30">
                          <TrendingUp size={32} />
                          <span>Аудит-лог порожній</span>
                        </div>
                      </TableCell>
                    </TableRow>
                  ) : audit.map(a => (
                    <TableRow key={a.id} className="border-white/10 hover:bg-white/5">
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <div className="w-6 h-6 rounded-full bg-blue-500/20 flex items-center justify-center">
                            <span className="text-blue-400 text-xs font-bold">
                              {(a.username ?? '?').charAt(0).toUpperCase()}
                            </span>
                          </div>
                          <span className="text-white text-sm">{a.username ?? 'anonymous'}</span>
                        </div>
                      </TableCell>
                      <TableCell className="max-w-xs">
                        <div className="flex items-center gap-2 overflow-hidden">
                          <Badge className="bg-blue-500/20 text-blue-400 border-0 text-[10px] flex-shrink-0">
                            {a.action.split(' ')[0]}
                          </Badge>
                          <span className="text-white/60 text-xs truncate">
                            {a.action.split(' ').slice(1).join(' ')}
                          </span>
                        </div>
                      </TableCell>
                      <TableCell>
                        <Badge className="bg-purple-500/20 text-purple-400 border-0 text-[10px]">
                          {a.resource_type || '—'}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-mono text-white/40 text-xs">{a.ip_address ?? '—'}</TableCell>
                      <TableCell className="text-white/40 text-xs whitespace-nowrap">
                        {new Date(a.timestamp).toLocaleString('uk-UA')}
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </TabsContent>
      </Tabs>

      {/* Evidence Dialog */}
      <EvidenceDialog
        attempt={evidenceTarget}
        open={!!evidenceTarget}
        onClose={() => setEvidenceTarget(null)}
      />
    </Layout>
  );
}
