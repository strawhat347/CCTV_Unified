import React, { useState, useEffect } from 'react';
import { AlertTriangle, X } from 'lucide-react';

const CONFIRM_EVENT = 'cctv_app_confirm';

let confirmResolver = null;

/**
 * Open a sleek in-app confirmation modal that returns a Promise<boolean>:
 * const ok = await confirmModal({
 *   title: 'Delete Camera',
 *   message: 'Are you sure you want to delete this camera?',
 *   isDanger: true
 * });
 */
export function confirmModal({
  title = 'Confirmation Required',
  message = 'Are you sure you want to proceed?',
  confirmText = 'Confirm',
  cancelText = 'Cancel',
  isDanger = false,
}) {
  if (typeof window === 'undefined') return Promise.resolve(false);

  return new Promise((resolve) => {
    confirmResolver = resolve;
    window.dispatchEvent(
      new CustomEvent(CONFIRM_EVENT, {
        detail: {
          title,
          message,
          confirmText,
          cancelText,
          isDanger,
        },
      })
    );
  });
}

export function ConfirmModalContainer() {
  const [dialog, setDialog] = useState(null);

  useEffect(() => {
    const handleOpen = (e) => {
      setDialog(e.detail);
    };

    window.addEventListener(CONFIRM_EVENT, handleOpen);
    return () => window.removeEventListener(CONFIRM_EVENT, handleOpen);
  }, []);

  const handleChoice = (result) => {
    if (confirmResolver) {
      confirmResolver(result);
      confirmResolver = null;
    }
    setDialog(null);
  };

  if (!dialog) return null;

  return (
    <div
      className="fixed inset-0 z-[9999999] flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-150"
      onClick={() => handleChoice(false)}
    >
      <div
        className="bg-bg-elevated border border-border-secondary rounded-xl shadow-2xl w-full max-w-md overflow-hidden flex flex-col animate-in zoom-in-95 duration-150"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="p-4 border-b border-border-secondary flex items-center justify-between bg-bg-secondary">
          <div className="flex items-center gap-2.5">
            {dialog.isDanger && <AlertTriangle className="w-5 h-5 text-danger shrink-0" />}
            <h3 className="font-semibold text-text-bright text-sm">{dialog.title}</h3>
          </div>
          <button
            onClick={() => handleChoice(false)}
            className="text-text-muted hover:text-text-primary p-1 rounded transition-colors"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        <div className="p-5 text-sm text-text-secondary leading-relaxed">
          {dialog.message}
        </div>

        <div className="p-4 border-t border-border-secondary bg-bg-secondary flex justify-end gap-2.5">
          <button
            type="button"
            onClick={() => handleChoice(false)}
            className="px-4 py-2 text-xs font-medium rounded-lg border border-border-primary bg-bg-elevated text-text-primary hover:bg-bg-hover transition-colors"
          >
            {dialog.cancelText || 'Cancel'}
          </button>
          <button
            type="button"
            onClick={() => handleChoice(true)}
            className={`px-4 py-2 text-xs font-medium rounded-lg text-white shadow-sm transition-colors ${
              dialog.isDanger
                ? 'bg-danger hover:bg-danger/90'
                : 'bg-accent hover:bg-accent-hover'
            }`}
          >
            {dialog.confirmText || 'Confirm'}
          </button>
        </div>
      </div>
    </div>
  );
}

export default ConfirmModalContainer;
