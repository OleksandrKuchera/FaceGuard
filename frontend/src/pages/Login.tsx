import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { login } from '@/api/client';
import { useAuthStore } from '@/store/authStore';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Shield, Lock, User, Eye, EyeOff } from 'lucide-react';
import type { User as UserType } from '@/types';

export default function Login() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const { setAuth } = useAuthStore();
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);
    try {
      const { data } = await login(username, password);
      const payload = JSON.parse(atob(data.access.split('.')[1])) as Record<string, unknown>;
      const user: UserType = {
        username: (payload.username as string) ?? username,
        role: (payload.role as UserType['role']) ?? 'guard',
        first_name: (payload.first_name as string) ?? '',
        last_name: (payload.last_name as string) ?? '',
      };
      setAuth(user, data.access as string, data.refresh as string);
      toast.success('Успішний вхід!', { description: `Ласкаво просимо, ${user.username}` });
      navigate('/');
    } catch {
      toast.error('Помилка входу', { description: 'Невірний логін або пароль' });
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card">
        <div className="login-logo">
          <div className="logo-icon-lg">
            <Shield size={30} className="text-white" />
          </div>
          <h1>FaceGuard</h1>
          <p>Система відеонагляду з розпізнаванням облич</p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="username" className="text-white/70 text-xs font-semibold uppercase tracking-wide">
              Логін
            </Label>
            <div className="relative">
              <User size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30" />
              <Input
                id="username"
                value={username}
                onChange={e => setUsername(e.target.value)}
                placeholder="Введіть логін"
                autoFocus
                required
                className="pl-9 bg-[#0a0e1a] border-white/10 text-white placeholder:text-white/30 focus:border-blue-500 focus:ring-blue-500/20"
              />
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="password" className="text-white/70 text-xs font-semibold uppercase tracking-wide">
              Пароль
            </Label>
            <div className="relative">
              <Lock size={15} className="absolute left-3 top-1/2 -translate-y-1/2 text-white/30" />
              <Input
                id="password"
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="Введіть пароль"
                required
                className="pl-9 pr-9 bg-[#0a0e1a] border-white/10 text-white placeholder:text-white/30 focus:border-blue-500 focus:ring-blue-500/20"
              />
              <button
                type="button"
                onClick={() => setShowPassword(p => !p)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-white/30 hover:text-white/70 transition-colors"
              >
                {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          </div>

          <Button
            type="submit"
            disabled={loading}
            className="w-full mt-2 h-11 bg-gradient-to-r from-blue-700 to-blue-500 hover:from-blue-600 hover:to-blue-400 text-white font-semibold"
          >
            {loading ? (
              <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            ) : (
              <>
                <Lock size={15} />
                Увійти
              </>
            )}
          </Button>
        </form>
      </div>
    </div>
  );
}
