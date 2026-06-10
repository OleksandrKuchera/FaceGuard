import { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import { useAuthStore } from '@/store/authStore';
import {
  LayoutDashboard, Video, Users, Camera, Eye,
  FileText, ShieldAlert, LogOut, Shield, ChevronDown,
  UserCog, Settings, Menu, Scan,
} from 'lucide-react';
import type { ReactNode } from 'react';
import { Separator } from '@/components/ui/separator';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Sheet,
  SheetContent,
  SheetTrigger,
} from '@/components/ui/sheet';
import { Badge } from '@/components/ui/badge';
import { AlertPanelTrigger, AlertPanel } from '@/components/AlertPanel';
import { Button } from '@/components/ui/button';

const NAV = [
  { to: '/',         icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/monitor',  icon: Video,           label: 'Live Monitor' },
  { to: '/webcam',   icon: Scan,            label: 'Веб-камера' },
  { to: '/persons',  icon: Users,           label: 'Особи' },
  { to: '/cameras',  icon: Camera,          label: 'Камери' },
  { to: '/events',   icon: Eye,             label: 'Події' },
  { to: '/reports',  icon: FileText,        label: 'Звіти' },
  { to: '/security', icon: ShieldAlert,     label: 'Безпека' },
  { to: '/users',    icon: UserCog,         label: 'Користувачі' },
  { to: '/settings', icon: Settings,        label: 'Налаштування' },
];

const ROLE_LABELS: Record<string, string> = {
  superadmin: 'Супер-адмін',
  admin: 'Адмін',
  guard: 'Охоронець',
  readonly: 'Перегляд',
};

const ROLE_COLORS: Record<string, string> = {
  superadmin: 'bg-red-500/20 text-red-400',
  admin: 'bg-blue-500/20 text-blue-400',
  guard: 'bg-green-500/20 text-green-400',
  readonly: 'bg-gray-500/20 text-gray-400',
};

function NavItems({ onNavigate }: { onNavigate?: () => void }) {
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();

  const handleLogout = () => { logout(); navigate('/login'); };

  return (
    <>
      <div className="sidebar-section-label">Навігація</div>

      {NAV.map(({ to, icon: Icon, label }) => (
        <NavLink
          key={to}
          to={to}
          end={to === '/'}
          className={({ isActive }) => `nav-item${isActive ? ' active' : ''}`}
          onClick={onNavigate}
        >
          <Icon size={16} />
          {label}
        </NavLink>
      ))}

      <div className="sidebar-bottom">
        <Separator className="mb-3 bg-white/10" />
        {user && (
          <div className="px-3 py-2 mb-1">
            <div className="text-xs font-semibold text-white/80 truncate">{user.username}</div>
            <span className={`text-[10px] font-medium px-1.5 py-0.5 rounded-full ${ROLE_COLORS[user.role] ?? 'bg-gray-500/20 text-gray-400'}`}>
              {ROLE_LABELS[user.role] ?? user.role}
            </span>
          </div>
        )}
        <button className="nav-item w-full text-red-400 hover:text-red-300 hover:bg-red-500/10" onClick={handleLogout}>
          <LogOut size={16} />
          Вийти
        </button>
      </div>
    </>
  );
}

export default function Layout({ children, title }: { children: ReactNode; title: string }) {
  const { user, logout } = useAuthStore();
  const navigate = useNavigate();
  const [mobileOpen, setMobileOpen] = useState(false);

  const handleLogout = () => { logout(); navigate('/login'); };

  return (
    <div className="app-layout">
      {/* Desktop sidebar */}
      <aside className="sidebar hidden md:flex">
        <div className="sidebar-logo">
          <div className="logo-icon">
            <Shield size={18} className="text-white" />
          </div>
          FaceGuard
        </div>
        <NavItems />
      </aside>

      <div className="main-content">
        <header className="topbar">
          {/* Mobile hamburger */}
          <div className="flex items-center gap-3 md:hidden">
            <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
              <SheetTrigger asChild>
                <Button variant="ghost" size="icon" className="text-white/60 hover:text-white">
                  <Menu size={20} />
                </Button>
              </SheetTrigger>
              <SheetContent
                side="left"
                className="w-[240px] p-0 bg-[var(--fg-surface)] border-r border-white/10"
              >
                <div className="sidebar-logo">
                  <div className="logo-icon">
                    <Shield size={18} className="text-white" />
                  </div>
                  FaceGuard
                </div>
                <div className="flex flex-col px-3 gap-1 flex-1">
                  <NavItems onNavigate={() => setMobileOpen(false)} />
                </div>
              </SheetContent>
            </Sheet>
            <span className="topbar-title">{title}</span>
          </div>

          {/* Desktop title */}
          <div className="topbar-title hidden md:block">{title}</div>

          <div className="topbar-right">
            <div className="live-dot" />
            <span className="text-xs text-white/40 hidden sm:inline">LIVE</span>
            <AlertPanelTrigger />

            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <button className="user-badge cursor-pointer">
                  <div className="w-6 h-6 rounded-full bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center text-white text-xs font-bold">
                    {user?.username?.charAt(0).toUpperCase() ?? 'U'}
                  </div>
                  <span className="text-sm font-medium hidden sm:inline">{user?.username ?? 'User'}</span>
                  <Badge variant="outline" className={`text-[10px] px-1.5 py-0 border-0 hidden sm:inline-flex ${ROLE_COLORS[user?.role ?? ''] ?? ''}`}>
                    {ROLE_LABELS[user?.role ?? ''] ?? user?.role}
                  </Badge>
                  <ChevronDown size={12} className="text-white/40" />
                </button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-44 bg-[#1a2235] border-white/10">
                <DropdownMenuLabel className="text-white/60 text-xs">Акаунт</DropdownMenuLabel>
                <DropdownMenuSeparator className="bg-white/10" />
                <DropdownMenuItem className="text-red-400 focus:text-red-300 focus:bg-red-500/10 cursor-pointer" onClick={handleLogout}>
                  <LogOut size={14} />
                  Вийти
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </header>

        <div className="page-scroll">{children}</div>
      </div>

      <AlertPanel />
    </div>
  );
}
