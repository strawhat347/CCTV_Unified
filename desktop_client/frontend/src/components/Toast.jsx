import React, { useState, useEffect, useCallback } from 'react';
import { CheckCircle2, AlertCircle, AlertTriangle, Info, X } from 'lucide-react';

// Event-based communication so any function or component can trigger toasts without prop-drilling
const TOAST_EVENT = 'cctv_app_toast';

/**
 * Trigger a toast from anywhere in the application:
 * toast.success('Camera added successfully!');
 * toast.error('Failed to connect to camera.');
 * toast.warning('Please enter a valid RTSP URL.');
 * toast.info('Starting sync...');
 */
export const toast = {
  success: (message, duration = 4000) => emitToast(message, 'success', duration),
  error: (message, duration = 5000) => emitToast(message, 'error', duration),
  warning: (message, duration = 4500) => emitToast(message, 'warning', duration),
  info: (message, duration = 4000) => emitToast(message, 'info', duration),
};

function emitToast(message, type = 'info', duration = 4000) {
  if (typeof window === 'undefined') return;
  const text = typeof message === 'object' ? (message?.message || JSON.stringify(message)) : String(message ?? '');
  window.dispatchEvent(
    new CustomEvent(TOAST_EVENT, {
      detail: {
        id: Date.now() + Math.random(),
        message: text,
        type,
        duration,
      },
    })
  );
}

/**
 * Globally overrides window.alert so that ANY native alert() call
 * anywhere in the app is automatically converted into a smooth in-app toast,
 * completely preventing the WebView2/Windows mouse cursor disappearance bug.
 */
export function initGlobalAlertInterceptor() {
  if (typeof window === 'undefined') return;
  if (window.__cctv_alert_intercepted) return;
  window.__cctv_alert_intercepted = true;

  window.alert = (message) => {
    const text = typeof message === 'object' ? (message?.message || JSON.stringify(message)) : String(message ?? '');
    const lower = text.toLowerCase();

    let type = 'info';
    if (
      lower.includes('success') ||
      lower.includes('added') ||
      lower.includes('deleted') ||
      lower.includes('updated') ||
      lower.includes('uploaded') ||
      lower.includes('cleared')
    ) {
      type = 'success';
    } else if (
      lower.includes('fail') ||
      lower.includes('error') ||
      lower.includes('invalid') ||
      lower.includes('cannot') ||
      lower.includes('denied') ||
      lower.includes('unauthorized')
    ) {
      type = 'error';
    } else if (
      lower.includes('require') ||
      lower.includes('must') ||
      lower.includes('warn') ||
      lower.includes('please')
    ) {
      type = 'warning';
    }

    emitToast(text, type, type === 'error' ? 5000 : 4000);
  };
}

// Auto-run interceptor upon import
initGlobalAlertInterceptor();

export function ToastContainer() {
  const [toasts, setToasts] = useState([]);

  const removeToast = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  useEffect(() => {
    const handleToast = (e) => {
      const toastItem = e.detail;
      setToasts((prev) => [...prev, toastItem]);

      if (toastItem.duration > 0) {
        setTimeout(() => {
          removeToast(toastItem.id);
        }, toastItem.duration);
      }
    };

    window.addEventListener(TOAST_EVENT, handleToast);
    return () => window.removeEventListener(TOAST_EVENT, handleToast);
  }, [removeToast]);

  if (toasts.length === 0) return null;

  return (
    <div className="fixed top-5 right-5 z-[999999] flex flex-col gap-2.5 max-w-sm w-full pointer-events-none px-3">
      {toasts.map((item) => (
        <ToastItem key={item.id} item={item} onDismiss={() => removeToast(item.id)} />
      ))}
    </div>
  );
}

function ToastItem({ item, onDismiss }) {
  const { message, type } = item;

  const config = {
    success: {
      icon: <CheckCircle2 className="w-5 h-5 text-emerald-500 shrink-0 mt-0.5" />,
      border: 'border-emerald-500/40',
      bg: 'bg-bg-elevated',
      badge: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400',
      title: 'Success',
    },
    error: {
      icon: <AlertCircle className="w-5 h-5 text-rose-500 shrink-0 mt-0.5" />,
      border: 'border-rose-500/40',
      bg: 'bg-bg-elevated',
      badge: 'bg-rose-500/10 text-rose-600 dark:text-rose-400',
      title: 'Error',
    },
    warning: {
      icon: <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />,
      border: 'border-amber-500/40',
      bg: 'bg-bg-elevated',
      badge: 'bg-amber-500/10 text-amber-600 dark:text-amber-400',
      title: 'Notice',
    },
    info: {
      icon: <Info className="w-5 h-5 text-sky-500 shrink-0 mt-0.5" />,
      border: 'border-sky-500/40',
      bg: 'bg-bg-elevated',
      badge: 'bg-sky-500/10 text-sky-600 dark:text-sky-400',
      title: 'Information',
    },
  }[type] || {
    icon: <Info className="w-5 h-5 text-sky-500 shrink-0 mt-0.5" />,
    border: 'border-border-primary',
    bg: 'bg-bg-elevated',
    badge: 'bg-accent/10 text-accent',
    title: 'Notification',
  };

  return (
    <div
      role="alert"
      className={`pointer-events-auto flex items-start gap-3 p-3.5 rounded-lg border shadow-xl ${config.border} ${config.bg} backdrop-blur-md transition-all duration-200 animate-in fade-in slide-in-from-top-3`}
      style={{
        boxShadow: '0 10px 25px -5px rgba(0, 0, 0, 0.15), 0 8px 10px -6px rgba(0, 0, 0, 0.1)',
      }}
    >
      {config.icon}
      <div className="flex-1 min-w-0 pr-1">
        <div className="text-xs font-semibold text-text-primary mb-0.5 flex items-center gap-1.5">
          <span>{config.title}</span>
        </div>
        <div className="text-xs text-text-secondary leading-relaxed break-words">{message}</div>
      </div>
      <button
        onClick={onDismiss}
        className="text-text-muted hover:text-text-primary p-1 rounded transition-colors -mr-1 -mt-1 shrink-0"
        title="Dismiss"
      >
        <X className="w-4 h-4" />
      </button>
    </div>
  );
}

export default ToastContainer;
