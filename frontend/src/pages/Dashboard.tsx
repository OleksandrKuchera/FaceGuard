import { useEffect, useState } from 'react';
import Layout from '@/components/Layout';
import {
  getEventStats, getDailyStats,
  getHourlyHeatmap, getTopVisitors, getCameraStats,
} from '@/api/client';
import type { EventStats, DailyStat } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { Badge } from '@/components/ui/badge';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell,
  BarChart, Bar,
} from 'recharts';
import {
  Activity, CheckCircle2, HelpCircle, ShieldAlert, AlertTriangle,
  TrendingUp, Clock, Star, Video,
} from 'lucide-react';

const STAT_CARDS = [
  { key: 'today',      label: 'Всього сьогодні', icon: Activity,       gradient: 'from-blue-700 to-blue-500',    glow: 'rgba(59,130,246,0.3)' },
  { key: 'recognized', label: 'Розпізнано',      icon: CheckCircle2,   gradient: 'from-emerald-700 to-emerald-500', glow: 'rgba(16,185,129,0.3)' },
  { key: 'unknown',    label: 'Невідомі',         icon: HelpCircle,     gradient: 'from-amber-700 to-amber-500',  glow: 'rgba(245,158,11,0.3)' },
  { key: 'spoofing',   label: 'Spoofing',         icon: ShieldAlert,    gradient: 'from-red-700 to-red-500',      glow: 'rgba(239,68,68,0.3)' },
  { key: 'alerts',     label: 'Алерти',           icon: AlertTriangle,  gradient: 'from-purple-700 to-purple-500', glow: 'rgba(139,92,246,0.3)' },
] as const;

const PIE_COLORS = ['#3b82f6', '#f59e0b', '#ef4444'];

// Colour an hourly bar by count intensity
function heatColor(count: number, max: number) {
  if (max === 0 || count === 0) return 'rgba(59,130,246,0.12)';
  const t = count / max;
  if (t < 0.33) return 'rgba(59,130,246,0.35)';
  if (t < 0.66) return 'rgba(59,130,246,0.65)';
  return 'rgba(59,130,246,0.95)';
}

interface HourRow { hour: number; count: number }
interface TopVisitor { person_id: number; full_name: string; department: string | null; visits: number }
interface CameraRow { camera_name: string; total: number; recognized: number; unknown: number; spoofing: number }

export default function Dashboard() {
  const [stats, setStats]         = useState<EventStats | null>(null);
  const [chart, setChart]         = useState<DailyStat[]>([]);
  const [heatmap, setHeatmap]     = useState<HourRow[]>([]);
  const [topVisitors, setTopVisitors] = useState<TopVisitor[]>([]);
  const [camStats, setCamStats]   = useState<CameraRow[]>([]);
  const [loadingStats, setLoadingStats] = useState(true);
  const [loadingChart, setLoadingChart] = useState(true);
  const [loadingExtra, setLoadingExtra] = useState(true);

  useEffect(() => {
    getEventStats()
      .then(r => setStats(r.data as EventStats))
      .catch(() => {})
      .finally(() => setLoadingStats(false));

    getDailyStats()
      .then(r => setChart(([...r.data] as DailyStat[]).reverse()))
      .catch(() => {})
      .finally(() => setLoadingChart(false));

    Promise.all([getHourlyHeatmap(), getTopVisitors(), getCameraStats()])
      .then(([h, t, c]) => {
        // Fill all 24 hours (backend only returns hours with events)
        const hourMap = new Map<number, number>((h.data as HourRow[]).map(r => [r.hour, r.count]));
        setHeatmap(Array.from({ length: 24 }, (_, i) => ({ hour: i, count: hourMap.get(i) ?? 0 })));
        setTopVisitors(t.data as TopVisitor[]);
        setCamStats(c.data as CameraRow[]);
      })
      .catch(() => {})
      .finally(() => setLoadingExtra(false));
  }, []);

  const pieData = stats
    ? [
        { name: 'Розпізнано', value: stats.recognized },
        { name: 'Невідомі',   value: stats.unknown },
        { name: 'Spoofing',   value: stats.spoofing },
      ]
    : [];

  const maxHeat = Math.max(...heatmap.map(h => h.count), 1);
  const today = new Date().toLocaleDateString('uk-UA', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });

  return (
    <Layout title="Dashboard">
      <div className="page-header">
        <div>
          <h1>Dashboard</h1>
          <div className="page-subtitle capitalize">{today}</div>
        </div>
        <Badge variant="outline" className="text-emerald-400 border-emerald-400/30 bg-emerald-400/10 gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse inline-block" />
          Система активна
        </Badge>
      </div>

      {/* Stat Cards */}
      <div className="stat-grid">
        {STAT_CARDS.map(({ key, label, icon: Icon, gradient, glow }) => (
          <Card key={key} className="bg-[#1a2235] border-white/10 hover:-translate-y-0.5 transition-transform cursor-default">
            <CardContent className="p-5 flex items-center gap-4">
              {loadingStats ? (
                <Skeleton className="w-12 h-12 rounded-xl bg-white/5" />
              ) : (
                <div
                  className={`w-12 h-12 rounded-xl bg-gradient-to-br ${gradient} flex items-center justify-center flex-shrink-0`}
                  style={{ boxShadow: `0 0 20px ${glow}` }}
                >
                  <Icon size={20} className="text-white" />
                </div>
              )}
              <div>
                {loadingStats ? (
                  <Skeleton className="h-7 w-12 mb-1 bg-white/5" />
                ) : (
                  <div className="text-3xl font-extrabold text-white leading-none">
                    {stats?.[key] ?? 0}
                  </div>
                )}
                <div className="text-xs text-white/50 font-medium mt-1">{label}</div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Row 1: Area chart + Pie */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-5 mb-5">
        <Card className="xl:col-span-2 bg-[#1a2235] border-white/10">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-semibold text-white/40 uppercase tracking-widest flex items-center gap-2">
              <TrendingUp size={13} />
              Активність за 30 днів
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loadingChart ? (
              <Skeleton className="h-52 w-full bg-white/5 rounded-lg" />
            ) : chart.length === 0 ? (
              <div className="h-52 flex items-center justify-center text-white/30 text-sm">Дані відсутні</div>
            ) : (
              <ResponsiveContainer width="100%" height={220}>
                <AreaChart data={chart} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                  <defs>
                    <linearGradient id="gRec" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="gUnk" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#f59e0b" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="#f59e0b" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(99,120,180,0.1)" />
                  <XAxis dataKey="date" tick={{ fill: '#506080', fontSize: 11 }} />
                  <YAxis tick={{ fill: '#506080', fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{ background: '#1a2235', border: '1px solid rgba(99,120,180,0.2)', borderRadius: 8, color: '#f0f4ff', fontSize: 12 }}
                  />
                  <Area type="monotone" dataKey="recognized" stroke="#3b82f6" fill="url(#gRec)" name="Розпізнано" strokeWidth={2} />
                  <Area type="monotone" dataKey="unknown" stroke="#f59e0b" fill="url(#gUnk)" name="Невідомі" strokeWidth={2} />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

        <Card className="bg-[#1a2235] border-white/10">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-semibold text-white/40 uppercase tracking-widest">
              Розбивка сьогодні
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loadingStats || !stats ? (
              <Skeleton className="h-52 w-full bg-white/5 rounded-lg" />
            ) : (
              <div className="flex flex-col items-center gap-4">
                <ResponsiveContainer width="100%" height={160}>
                  <PieChart>
                    <Pie data={pieData} cx="50%" cy="50%" innerRadius={45} outerRadius={70} paddingAngle={3} dataKey="value">
                      {pieData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i]} opacity={0.85} />)}
                    </Pie>
                    <Tooltip contentStyle={{ background: '#1a2235', border: '1px solid rgba(99,120,180,0.2)', borderRadius: 8, color: '#f0f4ff', fontSize: 12 }} />
                  </PieChart>
                </ResponsiveContainer>
                <div className="flex flex-col gap-1.5 w-full">
                  {pieData.map((d, i) => (
                    <div key={i} className="flex items-center justify-between text-xs">
                      <div className="flex items-center gap-2">
                        <span className="w-2 h-2 rounded-full inline-block" style={{ background: PIE_COLORS[i] }} />
                        <span className="text-white/60">{d.name}</span>
                      </div>
                      <span className="font-semibold text-white">{d.value}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Row 2: Hourly heatmap + Top visitors + Camera bar chart */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">

        {/* Hourly heatmap */}
        <Card className="bg-[#1a2235] border-white/10">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-semibold text-white/40 uppercase tracking-widest flex items-center gap-2">
              <Clock size={13} />
              Активність по годинах (14 днів)
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loadingExtra ? (
              <Skeleton className="h-28 w-full bg-white/5 rounded-lg" />
            ) : (
              <div className="flex items-end gap-0.5 h-28">
                {heatmap.map(({ hour, count }) => (
                  <div key={hour} className="flex flex-col items-center flex-1 gap-1">
                    <div
                      className="w-full rounded-sm transition-all"
                      style={{
                        height: `${Math.max(4, (count / maxHeat) * 80)}px`,
                        background: heatColor(count, maxHeat),
                      }}
                      title={`${hour}:00 — ${count} подій`}
                    />
                    {hour % 6 === 0 && (
                      <span className="text-[9px] text-white/30">{hour}</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Top visitors */}
        <Card className="bg-[#1a2235] border-white/10">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-semibold text-white/40 uppercase tracking-widest flex items-center gap-2">
              <Star size={13} />
              Топ відвідувачів (30 днів)
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loadingExtra ? (
              <div className="space-y-2">
                {[...Array(5)].map((_, i) => <Skeleton key={i} className="h-8 w-full bg-white/5 rounded" />)}
              </div>
            ) : topVisitors.length === 0 ? (
              <div className="text-center text-white/30 text-sm py-6">Немає даних</div>
            ) : (
              <div className="space-y-2">
                {topVisitors.map((v, i) => (
                  <div key={v.person_id} className="flex items-center gap-3">
                    <span className="text-[10px] font-bold text-white/30 w-4 text-right">{i + 1}</span>
                    <div className="w-6 h-6 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white text-[10px] font-bold flex-shrink-0">
                      {v.full_name?.charAt(0) ?? '?'}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-medium text-white truncate">{v.full_name}</div>
                      <div className="text-[10px] text-white/40 truncate">{v.department ?? '—'}</div>
                    </div>
                    <Badge className="bg-blue-500/15 text-blue-300 border-0 text-[10px] px-1.5">
                      {v.visits}
                    </Badge>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Camera comparison bar chart */}
        <Card className="bg-[#1a2235] border-white/10">
          <CardHeader className="pb-2">
            <CardTitle className="text-xs font-semibold text-white/40 uppercase tracking-widest flex items-center gap-2">
              <Video size={13} />
              Активність по камерах (7 днів)
            </CardTitle>
          </CardHeader>
          <CardContent>
            {loadingExtra ? (
              <Skeleton className="h-40 w-full bg-white/5 rounded-lg" />
            ) : camStats.length === 0 ? (
              <div className="h-40 flex items-center justify-center text-white/30 text-sm">Немає даних</div>
            ) : (
              <ResponsiveContainer width="100%" height={160}>
                <BarChart data={camStats} margin={{ top: 0, right: 0, left: -25, bottom: 0 }} barSize={8}>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgba(99,120,180,0.1)" />
                  <XAxis
                    dataKey="camera_name"
                    tick={{ fill: '#506080', fontSize: 10 }}
                    tickFormatter={(v: string) => v.length > 8 ? v.slice(0, 8) + '…' : v}
                  />
                  <YAxis tick={{ fill: '#506080', fontSize: 10 }} />
                  <Tooltip
                    contentStyle={{ background: '#1a2235', border: '1px solid rgba(99,120,180,0.2)', borderRadius: 8, color: '#f0f4ff', fontSize: 11 }}
                  />
                  <Bar dataKey="recognized" stackId="a" fill="#3b82f6" name="Розпізнано" radius={[0,0,0,0]} />
                  <Bar dataKey="unknown"    stackId="a" fill="#f59e0b" name="Невідомі"   radius={[0,0,0,0]} />
                  <Bar dataKey="spoofing"   stackId="a" fill="#ef4444" name="Spoofing"   radius={[3,3,0,0]} />
                </BarChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>

      </div>
    </Layout>
  );
}
