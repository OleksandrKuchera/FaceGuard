import { useEffect, useState } from 'react';
import Layout from '@/components/Layout';
import { toast } from 'sonner';
import { getSystemSettings, saveSystemSettings } from '@/api/client';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Separator } from '@/components/ui/separator';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from '@/components/ui/select';
import {
  Tabs, TabsContent, TabsList, TabsTrigger,
} from '@/components/ui/tabs';
import {
  Building2, Brain, Bell, Shield, Save,
} from 'lucide-react';

// ── Section wrapper ───────────────────────────────────────────────────────────
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="card p-5 flex flex-col gap-4">
      <div className="text-sm font-semibold text-white/80">{title}</div>
      <Separator className="bg-white/10" />
      {children}
    </div>
  );
}

function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="flex flex-col gap-0.5 min-w-0">
        <span className="text-sm text-white/80">{label}</span>
        {hint && <span className="text-xs text-white/40">{hint}</span>}
      </div>
      <div className="flex-shrink-0">{children}</div>
    </div>
  );
}

// ── Types ─────────────────────────────────────────────────────────────────────
interface GeneralSettings {
  institution_name: string;
  timezone: string;
  language: string;
}
interface MlSettings {
  global_threshold: string;
  model_version: 'hog' | 'cnn';
  liveness_enabled: boolean;
  min_face_size: string;
}
interface NotifySettings {
  telegram_enabled: boolean;
  telegram_webhook: string;
  email_enabled: boolean;
  email_address: string;
  alert_on_unknown: boolean;
  alert_on_spoofing: boolean;
}
interface CooldownSettings {
  recognized_cooldown: string;
  unknown_cooldown: string;
  spoofing_cooldown: string;
  multi_face_cooldown: string;
}
interface AllSettings {
  general: GeneralSettings;
  ml: MlSettings;
  notify: NotifySettings;
  cooldown: CooldownSettings;
}

const DEFAULTS: AllSettings = {
  general:  { institution_name: 'FaceGuard Security', timezone: 'Europe/Kyiv', language: 'uk' },
  ml:       { global_threshold: '0.55', model_version: 'hog', liveness_enabled: true, min_face_size: '20' },
  notify:   { telegram_enabled: false, telegram_webhook: '', email_enabled: false, email_address: '', alert_on_unknown: true, alert_on_spoofing: true },
  cooldown: { recognized_cooldown: '30', unknown_cooldown: '15', spoofing_cooldown: '5', multi_face_cooldown: '20' },
};

export default function Settings() {
  const [loading, setLoading]   = useState(true);
  const [saving, setSaving]     = useState(false);
  const [general, setGeneral]   = useState<GeneralSettings>(DEFAULTS.general);
  const [ml, setMl]             = useState<MlSettings>(DEFAULTS.ml);
  const [notify, setNotify]     = useState<NotifySettings>(DEFAULTS.notify);
  const [cooldown, setCooldown] = useState<CooldownSettings>(DEFAULTS.cooldown);

  useEffect(() => {
    getSystemSettings()
      .then(r => {
        const d = r.data as AllSettings;
        if (d.general)  setGeneral(d.general);
        if (d.ml)       setMl(d.ml);
        if (d.notify)   setNotify(d.notify);
        if (d.cooldown) setCooldown(d.cooldown);
      })
      .catch(() => { /* use defaults silently */ })
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    try {
      await saveSystemSettings({ general, ml, notify, cooldown });
      toast.success('Налаштування збережено', {
        description: 'Деякі зміни ML набудуть чинності після перезапуску worker.',
      });
    } catch {
      toast.error('Помилка збереження налаштувань');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <Layout title="Налаштування">
        <div className="flex flex-col gap-4 mt-4">
          {[1, 2, 3].map(i => <Skeleton key={i} className="h-32 w-full bg-white/5 rounded-xl" />)}
        </div>
      </Layout>
    );
  }

  return (
    <Layout title="Налаштування">
      <div className="page-header">
        <div>
          <h1>Налаштування</h1>
          <div className="page-subtitle">Конфігурація системи FaceGuard</div>
        </div>
        <Button
          className="bg-gradient-to-r from-blue-700 to-blue-500 text-white"
          onClick={handleSave}
          disabled={saving}
        >
          <Save size={14} />
          {saving ? 'Збереження…' : 'Зберегти зміни'}
        </Button>
      </div>

      <Tabs defaultValue="general" className="mt-2">
        <TabsList className="bg-white/5 border border-white/10 mb-5">
          <TabsTrigger value="general" className="data-[state=active]:bg-white/10 data-[state=active]:text-white text-white/50 gap-1.5">
            <Building2 size={13} />Загальне
          </TabsTrigger>
          <TabsTrigger value="ml" className="data-[state=active]:bg-white/10 data-[state=active]:text-white text-white/50 gap-1.5">
            <Brain size={13} />ML / Розпізнавання
          </TabsTrigger>
          <TabsTrigger value="notify" className="data-[state=active]:bg-white/10 data-[state=active]:text-white text-white/50 gap-1.5">
            <Bell size={13} />Сповіщення
          </TabsTrigger>
          <TabsTrigger value="security" className="data-[state=active]:bg-white/10 data-[state=active]:text-white text-white/50 gap-1.5">
            <Shield size={13} />Безпека / Cooldown
          </TabsTrigger>
        </TabsList>

        {/* ── General ── */}
        <TabsContent value="general" className="flex flex-col gap-4">
          <Section title="Налаштування закладу">
            <Row label="Назва закладу" hint="Відображається у звітах та заголовках">
              <Input
                value={general.institution_name}
                onChange={e => setGeneral(g => ({ ...g, institution_name: e.target.value }))}
                className="bg-[#0a0e1a] border-white/10 text-white w-64"
              />
            </Row>
            <Row label="Часовий пояс">
              <Select value={general.timezone} onValueChange={v => setGeneral(g => ({ ...g, timezone: v }))}>
                <SelectTrigger className="bg-[#0a0e1a] border-white/10 text-white w-52">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-[#1a2235] border-white/10">
                  <SelectItem value="Europe/Kyiv" className="text-white focus:bg-white/10">Europe/Kyiv (UTC+3)</SelectItem>
                  <SelectItem value="Europe/London" className="text-white focus:bg-white/10">Europe/London (UTC+0)</SelectItem>
                  <SelectItem value="America/New_York" className="text-white focus:bg-white/10">America/New_York (UTC-5)</SelectItem>
                  <SelectItem value="UTC" className="text-white focus:bg-white/10">UTC</SelectItem>
                </SelectContent>
              </Select>
            </Row>
            <Row label="Мова інтерфейсу">
              <Select value={general.language} onValueChange={v => setGeneral(g => ({ ...g, language: v }))}>
                <SelectTrigger className="bg-[#0a0e1a] border-white/10 text-white w-52">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-[#1a2235] border-white/10">
                  <SelectItem value="uk" className="text-white focus:bg-white/10">🇺🇦 Українська</SelectItem>
                  <SelectItem value="en" className="text-white focus:bg-white/10">🇬🇧 English</SelectItem>
                </SelectContent>
              </Select>
            </Row>
          </Section>

          <div className="card p-4 bg-blue-500/5 border border-blue-500/20">
            <div className="text-xs text-blue-300 flex items-start gap-2">
              <span className="mt-0.5">ℹ️</span>
              <span>Версія системи: <strong>FaceGuard v1.0</strong> · Django 5 + React 19 · Офлайн-режим активний</span>
            </div>
          </div>
        </TabsContent>

        {/* ── ML ── */}
        <TabsContent value="ml" className="flex flex-col gap-4">
          <Section title="Параметри розпізнавання">
            <Row label="Глобальний поріг впевненості" hint="Мінімальна схожість для підтвердження особи (0.1–1.0)">
              <div className="flex items-center gap-2">
                <Input
                  type="number" step="0.05" min="0.1" max="1.0"
                  value={ml.global_threshold}
                  onChange={e => setMl(m => ({ ...m, global_threshold: e.target.value }))}
                  className="bg-[#0a0e1a] border-white/10 text-white w-24"
                />
                <Badge className="bg-blue-500/20 text-blue-400 border-0">
                  {(parseFloat(ml.global_threshold || '0') * 100).toFixed(0)}%
                </Badge>
              </div>
            </Row>
            <Row label="Модель детекції" hint="HOG — швидша; CNN — точніша, але потребує GPU">
              <Select value={ml.model_version} onValueChange={v => setMl(m => ({ ...m, model_version: v as 'hog' | 'cnn' }))}>
                <SelectTrigger className="bg-[#0a0e1a] border-white/10 text-white w-44">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="bg-[#1a2235] border-white/10">
                  <SelectItem value="hog" className="text-white focus:bg-white/10">HOG (CPU, швидко)</SelectItem>
                  <SelectItem value="cnn" className="text-white focus:bg-white/10">CNN (GPU, точно)</SelectItem>
                </SelectContent>
              </Select>
            </Row>
            <Row label="Мінімальний розмір обличчя (px)" hint="Обличчя менше цього розміру ігноруються">
              <Input
                type="number" min="10" max="100"
                value={ml.min_face_size}
                onChange={e => setMl(m => ({ ...m, min_face_size: e.target.value }))}
                className="bg-[#0a0e1a] border-white/10 text-white w-24"
              />
            </Row>
            <Row label="Liveness Detection" hint="Виявлення спроб обманути систему фотографіями">
              <Switch
                checked={ml.liveness_enabled}
                onCheckedChange={v => setMl(m => ({ ...m, liveness_enabled: v }))}
              />
            </Row>
          </Section>
        </TabsContent>

        {/* ── Notify ── */}
        <TabsContent value="notify" className="flex flex-col gap-4">
          <Section title="Telegram">
            <Row label="Увімкнути Telegram-сповіщення">
              <Switch
                checked={notify.telegram_enabled}
                onCheckedChange={v => setNotify(n => ({ ...n, telegram_enabled: v }))}
              />
            </Row>
            {notify.telegram_enabled && (
              <div className="flex flex-col gap-1.5">
                <Label className="text-white/60 text-xs">Webhook URL або Bot Token + Chat ID</Label>
                <Input
                  value={notify.telegram_webhook}
                  onChange={e => setNotify(n => ({ ...n, telegram_webhook: e.target.value }))}
                  placeholder="https://api.telegram.org/bot.../sendMessage"
                  className="bg-[#0a0e1a] border-white/10 text-white font-mono text-xs"
                />
              </div>
            )}
          </Section>

          <Section title="Email">
            <Row label="Увімкнути Email-сповіщення">
              <Switch
                checked={notify.email_enabled}
                onCheckedChange={v => setNotify(n => ({ ...n, email_enabled: v }))}
              />
            </Row>
            {notify.email_enabled && (
              <div className="flex flex-col gap-1.5">
                <Label className="text-white/60 text-xs">Адреса отримувача</Label>
                <Input
                  type="email"
                  value={notify.email_address}
                  onChange={e => setNotify(n => ({ ...n, email_address: e.target.value }))}
                  placeholder="security@company.ua"
                  className="bg-[#0a0e1a] border-white/10 text-white"
                />
              </div>
            )}
          </Section>

          <Section title="Тригери алертів">
            <Row label="Невідома особа" hint="Надсилати сповіщення при появі невідомої особи">
              <Switch
                checked={notify.alert_on_unknown}
                onCheckedChange={v => setNotify(n => ({ ...n, alert_on_unknown: v }))}
              />
            </Row>
            <Row label="Спроба спуфінгу" hint="Надсилати при виявленні атаки підробкою">
              <Switch
                checked={notify.alert_on_spoofing}
                onCheckedChange={v => setNotify(n => ({ ...n, alert_on_spoofing: v }))}
              />
            </Row>
          </Section>
        </TabsContent>

        {/* ── Security / Cooldown ── */}
        <TabsContent value="security" className="flex flex-col gap-4">
          <Section title="Cooldown флудингу подій (секунди)">
            <p className="text-xs text-white/40 -mt-2">
              Мінімальний інтервал між двома однотипними подіями від однієї камери. Захищає від переповнення БД.
            </p>
            {([
              ['Розпізнана особа', 'recognized_cooldown'],
              ['Невідома особа',   'unknown_cooldown'],
              ['Спуфінг',          'spoofing_cooldown'],
              ['Кілька облич',     'multi_face_cooldown'],
            ] as [string, keyof CooldownSettings][]).map(([label, key]) => (
              <Row key={key} label={label}>
                <div className="flex items-center gap-2">
                  <Input
                    type="number" min="1" max="3600"
                    value={cooldown[key]}
                    onChange={e => setCooldown(c => ({ ...c, [key]: e.target.value }))}
                    className="bg-[#0a0e1a] border-white/10 text-white w-20"
                  />
                  <span className="text-white/40 text-xs">с</span>
                </div>
              </Row>
            ))}
          </Section>

          <div className="card p-4 bg-amber-500/5 border border-amber-500/20">
            <div className="text-xs text-amber-300 flex items-start gap-2">
              <span className="mt-0.5">⚠️</span>
              <span>
                Cooldown зберігається в пам'яті worker-процесу і скидається при його перезапуску.
                Для продакшн-середовища рекомендується зберігання у Redis.
              </span>
            </div>
          </div>
        </TabsContent>
      </Tabs>
    </Layout>
  );
}
