import { useAlertStore } from '@/store/alertStore';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { ScrollArea } from '@/components/ui/scroll-area';
import {
  Sheet, SheetContent, SheetHeader, SheetTitle,
} from '@/components/ui/sheet';
import { AlertTriangle, Bell, CheckCheck, Trash2, X } from 'lucide-react';

const LEVEL_STYLE = {
  high:   { bar: 'bg-red-500',    badge: 'bg-red-500/20 text-red-400',    label: 'Критично' },
  medium: { bar: 'bg-amber-500',  badge: 'bg-amber-500/20 text-amber-400', label: 'Середній' },
  low:    { bar: 'bg-blue-500',   badge: 'bg-blue-500/20 text-blue-400',   label: 'Низький'  },
};

export function AlertPanelTrigger() {
  const { togglePanel, unreadCount } = useAlertStore();
  const count = unreadCount();

  return (
    <button
      className="relative p-2 rounded-lg text-white/40 hover:text-white hover:bg-white/10 transition-colors"
      onClick={togglePanel}
      title="Сповіщення"
    >
      <Bell size={18} />
      {count > 0 && (
        <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 flex items-center justify-center rounded-full bg-red-500 text-white text-[9px] font-bold px-0.5 animate-pulse">
          {count > 99 ? '99+' : count}
        </span>
      )}
    </button>
  );
}

export function AlertPanel() {
  const {
    alerts, panelOpen, closePanel,
    acknowledge, acknowledgeAll, clearAcknowledged,
  } = useAlertStore();

  const unread = alerts.filter(a => !a.acknowledged).length;

  return (
    <Sheet open={panelOpen} onOpenChange={v => { if (!v) closePanel(); }}>
      <SheetContent
        side="right"
        className="w-[360px] p-0 bg-[#111827] border-l border-white/10 flex flex-col"
      >
        <SheetHeader className="px-4 pt-4 pb-3 border-b border-white/10 flex-shrink-0">
          <div className="flex items-center justify-between">
            <SheetTitle className="text-white text-sm font-semibold flex items-center gap-2">
              <Bell size={16} className="text-blue-400" />
              Сповіщення
              {unread > 0 && (
                <Badge className="bg-red-500/20 text-red-400 border-0 text-[10px] px-1.5 py-0">
                  {unread} нових
                </Badge>
              )}
            </SheetTitle>
            <button onClick={closePanel} className="text-white/40 hover:text-white">
              <X size={16} />
            </button>
          </div>

          {alerts.length > 0 && (
            <div className="flex gap-2 mt-2">
              <Button
                variant="ghost" size="sm"
                className="h-6 text-[11px] text-white/40 hover:text-white gap-1 px-2"
                onClick={acknowledgeAll}
              >
                <CheckCheck size={11} />
                Всі прочитано
              </Button>
              <Button
                variant="ghost" size="sm"
                className="h-6 text-[11px] text-white/40 hover:text-white gap-1 px-2"
                onClick={clearAcknowledged}
              >
                <Trash2 size={11} />
                Очистити прочитані
              </Button>
            </div>
          )}
        </SheetHeader>

        <ScrollArea className="flex-1">
          {alerts.length === 0 ? (
            <div className="flex flex-col items-center justify-center h-48 text-white/30 gap-2">
              <Bell size={28} className="opacity-30" />
              <p className="text-sm">Сповіщень немає</p>
            </div>
          ) : (
            <div className="py-2">
              {alerts.map(alert => {
                const style = LEVEL_STYLE[alert.level] ?? LEVEL_STYLE.low;
                return (
                  <div
                    key={alert.id}
                    className={`relative flex gap-3 px-4 py-3 border-b border-white/5 transition-colors ${
                      alert.acknowledged ? 'opacity-40' : 'hover:bg-white/5'
                    }`}
                  >
                    {/* Level bar */}
                    <div className={`absolute left-0 top-0 bottom-0 w-0.5 ${style.bar}`} />

                    <div className="flex-shrink-0 mt-0.5">
                      <AlertTriangle size={14} className={
                        alert.level === 'high' ? 'text-red-400' :
                        alert.level === 'medium' ? 'text-amber-400' : 'text-blue-400'
                      } />
                    </div>

                    <div className="flex-1 min-w-0">
                      <div className="flex items-start justify-between gap-2">
                        <p className="text-xs text-white leading-snug">{alert.message}</p>
                        {!alert.acknowledged && (
                          <button
                            className="flex-shrink-0 text-white/30 hover:text-white mt-0.5"
                            onClick={() => acknowledge(alert.id)}
                            title="Позначити прочитаним"
                          >
                            <X size={12} />
                          </button>
                        )}
                      </div>
                      <div className="flex items-center gap-2 mt-1">
                        <Badge className={`border-0 text-[9px] px-1 py-0 ${style.badge}`}>
                          {style.label}
                        </Badge>
                        <span className="text-[10px] text-white/30">
                          {new Date(alert.timestamp).toLocaleString('uk-UA', {
                            day: '2-digit', month: '2-digit',
                            hour: '2-digit', minute: '2-digit',
                          })}
                        </span>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </ScrollArea>

        {alerts.length > 0 && (
          <div className="px-4 py-3 border-t border-white/10 flex-shrink-0">
            <p className="text-[10px] text-white/30 text-center">
              {alerts.length} сповіщень · {unread} непрочитаних
            </p>
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
