import { useEffect, useState } from 'react';
import Layout from '@/components/Layout';
import { getEventStats, getDailyStats } from '@/api/client';
import type { EventStats, DailyStat } from '@/types';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { Shield, UserCheck, CircleHelp, Siren, CalendarDays } from 'lucide-react';

const cards = [
  { key: 'today', label: 'Подій сьогодні', icon: CalendarDays, tone: 'bg-blue-500/15 text-blue-300' },
  { key: 'recognized', label: 'Розпізнано', icon: UserCheck, tone: 'bg-emerald-500/15 text-emerald-300' },
  { key: 'unknown', label: 'Невідомі', icon: CircleHelp, tone: 'bg-amber-500/15 text-amber-300' },
  { key: 'spoofing', label: 'Спуфінг', icon: Shield, tone: 'bg-red-500/15 text-red-300' },
  { key: 'alerts', label: 'Алерти', icon: Siren, tone: 'bg-fuchsia-500/15 text-fuchsia-300' },
] as const;

export default function Dashboard() {
  const [stats, setStats] = useState<EventStats | null>(null);
  const [daily, setDaily] = useState<DailyStat[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([getEventStats(), getDailyStats()])
      .then(([statsRes, dailyRes]) => {
        setStats(statsRes.data as EventStats);
        setDaily(dailyRes.data as DailyStat[]);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const recent = daily.slice(-7).reverse();

  return (
    <Layout title="Dashboard">
      <div className="page-header">
        <div>
          <h1>Dashboard</h1>
          <div className="page-subtitle">Коротка аналітика розпізнавання, невідомих осіб та spoofing-подій</div>
        </div>
        <Badge variant="outline" className="text-blue-300 border-blue-400/30 bg-blue-500/10">
          Оновлено з реальних подій
        </Badge>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-5 gap-4 mb-6">
        {cards.map(({ key, label, icon: Icon, tone }) => (
          <div key={key} className="rounded-2xl border border-white/10 bg-[#1a2235] p-4">
            {loading || !stats ? (
              <Skeleton className="h-24 w-full bg-white/5 rounded-xl" />
            ) : (
              <>
                <div className={`w-10 h-10 rounded-xl flex items-center justify-center ${tone}`}>
                  <Icon size={18} />
                </div>
                <div className="text-3xl font-semibold text-white mt-4">
                  {stats[key] ?? 0}
                </div>
                <div className="text-sm text-white/45 mt-1">{label}</div>
              </>
            )}
          </div>
        ))}
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-[1.4fr_0.9fr] gap-5">
        <div className="rounded-2xl border border-white/10 bg-[#1a2235] p-5">
          <div className="text-white font-medium mb-4">Останні 7 днів</div>
          {loading ? (
            <div className="space-y-2">
              {Array.from({ length: 7 }).map((_, i) => <Skeleton key={i} className="h-11 w-full bg-white/5 rounded-xl" />)}
            </div>
          ) : recent.length === 0 ? (
            <div className="text-white/35 text-sm">Дані ще не накопичені.</div>
          ) : (
            <div className="space-y-2">
              {recent.map(day => (
                <div key={day.date} className="rounded-xl bg-white/5 px-4 py-3 flex items-center justify-between gap-4">
                  <div>
                    <div className="text-white text-sm font-medium">{new Date(day.date).toLocaleDateString('uk-UA')}</div>
                    <div className="text-xs text-white/40">Унікальних осіб: {day.unique_persons}</div>
                  </div>
                  <div className="flex flex-wrap justify-end gap-2 text-xs">
                    <Badge className="bg-blue-500/15 text-blue-300 border-0">Всього {day.total_events}</Badge>
                    <Badge className="bg-emerald-500/15 text-emerald-300 border-0">Розпізнано {day.recognized}</Badge>
                    <Badge className="bg-amber-500/15 text-amber-300 border-0">Невідомі {day.unknown}</Badge>
                    <Badge className="bg-red-500/15 text-red-300 border-0">Спуфінг {day.spoofing_attempts}</Badge>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="rounded-2xl border border-white/10 bg-[#111827] p-5">
          <div className="text-white font-medium mb-3">Що потрапляє в аналітику</div>
          <div className="space-y-3 text-sm text-white/55">
            <div>Розпізнані особи враховуються у головній статистиці та live-аналізі камер.</div>
            <div>Невідомі особи враховуються у головній статистиці та live-аналізі камер.</div>
            <div>Spoofing-події враховуються у головній статистиці та live-аналізі камер.</div>
          </div>
        </div>
      </div>
    </Layout>
  );
}
