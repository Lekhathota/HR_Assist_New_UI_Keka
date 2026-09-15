import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';

const ConfirmContext = createContext(null);

export function toast({ type = 'info', message }) {
  window.dispatchEvent(new CustomEvent('enterprise-toast', {
    detail: { type, message },
  }));
}

export function ToastHost() {
  const [items, setItems] = useState([]);

  useEffect(() => {
    const onToast = (event) => {
      const detail = event.detail || {};
      const id = `${Date.now()}-${Math.random()}`;
      setItems(prev => [...prev, { id, type: detail.type || 'info', message: detail.message || '' }]);
      window.setTimeout(() => {
        setItems(prev => prev.filter(item => item.id !== id));
      }, 3600);
    };
    window.addEventListener('enterprise-toast', onToast);
    return () => window.removeEventListener('enterprise-toast', onToast);
  }, []);

  if (items.length === 0) return null;

  return (
    <div className="enterprise-toast-stack" aria-live="polite" aria-atomic="true">
      {items.map(item => (
        <div key={item.id} className={`enterprise-toast enterprise-toast-${item.type}`}>
          <i className={`fas ${item.type === 'success' ? 'fa-check-circle' : item.type === 'error' ? 'fa-exclamation-circle' : 'fa-info-circle'}`}></i>
          <span>{item.message}</span>
        </div>
      ))}
    </div>
  );
}

export function ConfirmProvider({ children }) {
  const [request, setRequest] = useState(null);
  const resolverRef = useRef(null);

  const confirm = useCallback((options) => new Promise(resolve => {
    resolverRef.current = resolve;
    setRequest(options);
  }), []);

  const close = (value) => {
    resolverRef.current?.(value);
    resolverRef.current = null;
    setRequest(null);
  };

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {request && (
        <div className="enterprise-modal-backdrop" role="presentation">
          <div className="enterprise-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="enterprise-confirm-title">
            <button type="button" className="enterprise-confirm-close" aria-label="Close dialog" onClick={() => close(false)}>
              <i className="fas fa-times"></i>
            </button>
            <div className="enterprise-confirm-icon">
              <i className={request.icon || 'fas fa-exclamation-triangle'}></i>
            </div>
            <h2 id="enterprise-confirm-title">{request.title}</h2>
            <p>{request.message}</p>
            <div className="enterprise-confirm-actions">
              <button type="button" className="btn btn-secondary" onClick={() => close(false)}>
                {request.cancelLabel || 'Cancel'}
              </button>
              <button type="button" className={`btn ${request.danger ? 'btn-danger' : 'btn-primary'}`} onClick={() => close(true)}>
                {request.confirmLabel || 'Confirm'}
              </button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  );
}

export function useConfirm() {
  const confirm = useContext(ConfirmContext);
  if (!confirm) {
    throw new Error('useConfirm must be used inside ConfirmProvider');
  }
  return confirm;
}

export function SkeletonBlock({ variant = 'card', count = 1 }) {
  return (
    <div className={`enterprise-skeleton-wrap enterprise-skeleton-${variant}`} aria-hidden="true">
      {Array.from({ length: count }).map((_, index) => (
        <div key={index} className="enterprise-skeleton-item">
          <span></span>
          <span></span>
          <span></span>
        </div>
      ))}
    </div>
  );
}
