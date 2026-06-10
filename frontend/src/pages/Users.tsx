import { useEffect, useState } from 'react';
import Layout from '@/components/Layout';
import { getUsers, createUser, updateUser, deleteUser, resetPassword } from '@/api/client';
import type { SystemUser, SystemRole } from '@/types';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
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
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from '@/components/ui/table';
import {
  Tooltip, TooltipContent, TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  UserPlus, Pencil, Trash2, KeyRound, Loader2,
  CheckCircle2, XCircle, RefreshCw, ShieldCheck,
} from 'lucide-react';

// ── Constants ────────────────────────────────────────────────────────────────
const ROLE_BADGE: Record<SystemRole, string> = {
  superadmin: 'bg-red-500/20 text-red-400',
  admin:      'bg-blue-500/20 text-blue-400',
  guard:      'bg-emerald-500/20 text-emerald-400',
  readonly:   'bg-gray-500/20 text-gray-400',
};
const ROLE_LABEL: Record<SystemRole, string> = {
  superadmin: 'Супер-адмін',
  admin:      'Адмін',
  guard:      'Охоронець',
  readonly:   'Перегляд',
};

// ── Form types ────────────────────────────────────────────────────────────────
interface UserForm {
  username: string;
  first_name: string;
  last_name: string;
  email: string;
  role: SystemRole;
  password: string;
}
const EMPTY_FORM: UserForm = {
  username: '', first_name: '', last_name: '',
  email: '', role: 'guard', password: '',
};

// ── UserFormDialog ────────────────────────────────────────────────────────────
function UserFormDialog({
  open, editId, initial, onClose, onSaved,
}: {
  open: boolean;
  editId: number | null;
  initial: UserForm;
  onClose: () => void;
  onSaved: () => void;
}) {
  const [form, setForm] = useState<UserForm>(initial);
  const [saving, setSaving] = useState(false);
  const isEdit = editId !== null;

  useEffect(() => { if (open) setForm(initial); }, [open, initial]);
  const set = (k: keyof UserForm, v: string) => setForm(f => ({ ...f, [k]: v }));

  const handleSubmit = async (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault();
    setSaving(true);
    try {
      if (isEdit) {
        const { password: _p, username: _u, ...updateData } = form;
        await updateUser(editId, updateData);
        toast.success('Користувача оновлено');
      } else {
        await createUser(form);
        toast.success('Користувача створено');
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
      <DialogContent className="bg-[#1a2235] border-white/10 text-white max-w-md">
        <DialogHeader>
          <DialogTitle>{isEdit ? 'Редагувати користувача' : 'Новий користувач'}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          {!isEdit && (
            <div className="flex flex-col gap-1.5">
              <Label className="text-white/60 text-xs">Логін *</Label>
              <Input required value={form.username} onChange={e => set('username', e.target.value)}
                placeholder="ivanov_guard" className="bg-[#0a0e1a] border-white/10 text-white font-mono" />
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div className="flex flex-col gap-1.5">
              <Label className="text-white/60 text-xs">Ім'я</Label>
              <Input value={form.first_name} onChange={e => set('first_name', e.target.value)}
                className="bg-[#0a0e1a] border-white/10 text-white" />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label className="text-white/60 text-xs">Прізвище</Label>
              <Input value={form.last_name} onChange={e => set('last_name', e.target.value)}
                className="bg-[#0a0e1a] border-white/10 text-white" />
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label className="text-white/60 text-xs">Email</Label>
            <Input type="email" value={form.email} onChange={e => set('email', e.target.value)}
              className="bg-[#0a0e1a] border-white/10 text-white" />
          </div>

          <div className="flex flex-col gap-1.5">
            <Label className="text-white/60 text-xs">Роль</Label>
            <Select value={form.role} onValueChange={v => set('role', v)}>
              <SelectTrigger className="bg-[#0a0e1a] border-white/10 text-white">
                <SelectValue />
              </SelectTrigger>
              <SelectContent className="bg-[#1a2235] border-white/10">
                {(Object.entries(ROLE_LABEL) as [SystemRole, string][]).map(([k, v]) => (
                  <SelectItem key={k} value={k} className="text-white focus:bg-white/10">
                    <span className={`inline-block text-xs px-1.5 py-0.5 rounded-full mr-2 ${ROLE_BADGE[k]}`}>{k}</span>
                    {v}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {!isEdit && (
            <div className="flex flex-col gap-1.5">
              <Label className="text-white/60 text-xs">Пароль *</Label>
              <Input required type="password" value={form.password} onChange={e => set('password', e.target.value)}
                placeholder="мін. 6 символів" className="bg-[#0a0e1a] border-white/10 text-white" />
            </div>
          )}

          <DialogFooter className="mt-2">
            <Button type="button" variant="ghost" onClick={onClose} className="text-white/60 hover:text-white">Скасувати</Button>
            <Button type="submit" disabled={saving} className="bg-gradient-to-r from-blue-700 to-blue-500 text-white">
              {saving && <Loader2 size={14} className="animate-spin" />}
              {isEdit ? 'Зберегти' : 'Створити'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ── ResetPasswordDialog ───────────────────────────────────────────────────────
function ResetPasswordDialog({
  user, open, onClose,
}: { user: SystemUser | null; open: boolean; onClose: () => void }) {
  const [pwd, setPwd] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => { if (open) setPwd(''); }, [open]);

  const handleSubmit = async (e: React.SyntheticEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!user) return;
    setSaving(true);
    try {
      await resetPassword(user.id, pwd);
      toast.success(`Пароль для «${user.username}» змінено`);
      onClose();
    } catch {
      toast.error('Помилка зміни паролю');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={v => { if (!v) onClose(); }}>
      <DialogContent className="bg-[#1a2235] border-white/10 text-white max-w-sm">
        <DialogHeader>
          <DialogTitle>Змінити пароль — {user?.username}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label className="text-white/60 text-xs">Новий пароль *</Label>
            <Input required type="password" value={pwd} onChange={e => setPwd(e.target.value)}
              placeholder="мін. 6 символів" className="bg-[#0a0e1a] border-white/10 text-white" />
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={onClose} className="text-white/60 hover:text-white">Скасувати</Button>
            <Button type="submit" disabled={saving || pwd.length < 6} className="bg-amber-600 hover:bg-amber-500 text-white">
              {saving && <Loader2 size={14} className="animate-spin" />}
              Змінити
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ── Main Page ────────────────────────────────────────────────────────────────
export default function Users() {
  const [users, setUsers] = useState<SystemUser[]>([]);
  const [loading, setLoading] = useState(true);
  const [modal, setModal] = useState<{ open: boolean; editId: number | null; initial: UserForm }>({
    open: false, editId: null, initial: EMPTY_FORM,
  });
  const [resetTarget, setResetTarget] = useState<SystemUser | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<SystemUser | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);

  const load = () => {
    setLoading(true);
    getUsers()
      .then(r => setUsers((r.data as { results?: SystemUser[] }).results ?? (r.data as SystemUser[])))
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const openEdit = (u: SystemUser) => setModal({
    open: true, editId: u.id,
    initial: {
      username: u.username, first_name: u.first_name, last_name: u.last_name,
      email: u.email, role: u.role, password: '',
    },
  });

  const handleDelete = async () => {
    if (!deleteTarget) return;
    setDeleting(deleteTarget.id);
    try {
      await deleteUser(deleteTarget.id);
      toast.success(`«${deleteTarget.username}» деактивовано`);
      load();
    } catch {
      toast.error('Помилка деактивації');
    } finally {
      setDeleting(null);
      setDeleteTarget(null);
    }
  };

  const activeCount = users.filter(u => u.is_active).length;

  return (
    <Layout title="Користувачі системи">
      <div className="page-header">
        <div>
          <h1>Користувачі</h1>
          <div className="page-subtitle">Облікові записи та ролі системи</div>
        </div>
        <div className="flex gap-2">
          <Button variant="ghost" size="sm" onClick={load} className="text-white/60 hover:text-white border border-white/10">
            <RefreshCw size={14} />
          </Button>
          <Button
            className="bg-gradient-to-r from-blue-700 to-blue-500 text-white"
            onClick={() => setModal({ open: true, editId: null, initial: EMPTY_FORM })}
          >
            <UserPlus size={15} />
            Додати користувача
          </Button>
        </div>
      </div>

      {/* Stats row */}
      <div className="flex gap-3 mb-5">
        {[
          { label: 'Всього', value: users.length, color: 'text-white' },
          { label: 'Активних', value: activeCount, color: 'text-emerald-400' },
          { label: 'Адмінів', value: users.filter(u => u.role === 'admin' || u.role === 'superadmin').length, color: 'text-blue-400' },
          { label: 'Охоронців', value: users.filter(u => u.role === 'guard').length, color: 'text-emerald-400' },
        ].map(s => (
          <div key={s.label} className="card px-4 py-3 flex flex-col gap-0.5 min-w-[100px]">
            <div className={`text-xl font-bold ${s.color}`}>{s.value}</div>
            <div className="text-xs text-white/40">{s.label}</div>
          </div>
        ))}
      </div>

      <Separator className="mb-5 bg-white/10" />

      {loading ? (
        <div className="flex flex-col gap-2">
          {Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-14 w-full bg-white/5 rounded-xl" />)}
        </div>
      ) : (
        <div className="table-wrap">
          <Table>
            <TableHeader>
              <TableRow className="border-white/10 hover:bg-transparent">
                {['Логін', 'Ім\'я', 'Email', 'Роль', 'Статус', 'Зареєстровано', 'Дії'].map(h => (
                  <TableHead key={h} className="text-white/40 text-[11px] uppercase tracking-wider">{h}</TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center py-16 text-white/30">Користувачів не знайдено</TableCell>
                </TableRow>
              ) : users.map(u => (
                <TableRow key={u.id} className="border-white/10 hover:bg-white/5">
                  <TableCell>
                    <div className="flex items-center gap-2">
                      <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-700 to-purple-600 flex items-center justify-center text-white font-bold text-sm flex-shrink-0">
                        {u.username.charAt(0).toUpperCase()}
                      </div>
                      <span className="font-mono text-sm text-white">{u.username}</span>
                    </div>
                  </TableCell>
                  <TableCell className="text-white/70">
                    {u.first_name || u.last_name ? `${u.first_name} ${u.last_name}`.trim() : '—'}
                  </TableCell>
                  <TableCell className="text-white/50 text-sm">{u.email || '—'}</TableCell>
                  <TableCell>
                    <Badge className={`border-0 gap-1 ${ROLE_BADGE[u.role] ?? 'bg-gray-500/20 text-gray-400'}`}>
                      <ShieldCheck size={10} />
                      {ROLE_LABEL[u.role] ?? u.role}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    {u.is_active
                      ? <Badge className="bg-emerald-500/20 text-emerald-400 border-0 gap-1"><CheckCircle2 size={10} />Активний</Badge>
                      : <Badge className="bg-gray-500/20 text-gray-400 border-0 gap-1"><XCircle size={10} />Неактивний</Badge>}
                  </TableCell>
                  <TableCell className="text-white/40 text-xs">
                    {new Date(u.date_joined).toLocaleDateString('uk-UA')}
                  </TableCell>
                  <TableCell>
                    <div className="flex gap-1.5">
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button variant="ghost" size="icon-xs" onClick={() => openEdit(u)}>
                            <Pencil size={13} />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Редагувати</TooltipContent>
                      </Tooltip>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button variant="ghost" size="icon-xs" className="text-amber-400 hover:text-amber-300 hover:bg-amber-500/10"
                            onClick={() => setResetTarget(u)}>
                            <KeyRound size={13} />
                          </Button>
                        </TooltipTrigger>
                        <TooltipContent>Змінити пароль</TooltipContent>
                      </Tooltip>
                      <Tooltip>
                        <TooltipTrigger asChild>
                          <Button
                            variant="ghost" size="icon-xs"
                            className="text-red-400 hover:text-red-300 hover:bg-red-500/10"
                            onClick={() => setDeleteTarget(u)}
                            disabled={deleting === u.id}
                          >
                            {deleting === u.id ? <Loader2 size={13} className="animate-spin" /> : <Trash2 size={13} />}
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

      <UserFormDialog
        open={modal.open}
        editId={modal.editId}
        initial={modal.initial}
        onClose={() => setModal(s => ({ ...s, open: false }))}
        onSaved={load}
      />

      <ResetPasswordDialog
        user={resetTarget}
        open={!!resetTarget}
        onClose={() => setResetTarget(null)}
      />

      <AlertDialog open={!!deleteTarget} onOpenChange={v => { if (!v) setDeleteTarget(null); }}>
        <AlertDialogContent className="bg-[#1a2235] border-white/10 text-white">
          <AlertDialogHeader>
            <AlertDialogTitle>Деактивувати користувача?</AlertDialogTitle>
            <AlertDialogDescription className="text-white/50">
              «{deleteTarget?.username}» втратить доступ до системи.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel className="bg-white/10 border-0 text-white hover:bg-white/20">Скасувати</AlertDialogCancel>
            <AlertDialogAction className="bg-red-600 hover:bg-red-500 text-white" onClick={handleDelete}>
              Деактивувати
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Layout>
  );
}
