import React, { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';

const MENU_WIDTH = 210;

// "⋮" actions menu. items: [{ label, icon, onSelect | to, danger, disabled, title }].
// The menu is fixed to the viewport so table/card containers with overflow do not clip it.
function KebabMenu({ items, label = 'Actions', className = '' }) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState(null);
  const container = useRef(null);
  const trigger = useRef(null);
  const menu = useRef(null);

  const close = (refocus = false) => {
    setOpen(false);
    if (refocus) trigger.current?.focus();
  };

  useLayoutEffect(() => {
    if (!open || !trigger.current) return;
    const rect = trigger.current.getBoundingClientRect();
    const height = menu.current?.offsetHeight || 0;
    const below = window.innerHeight - rect.bottom;
    const top = height && below < height + 6 && rect.top > below ? rect.top - height - 4 : rect.bottom + 4;
    const left = Math.max(8, Math.min(rect.right - MENU_WIDTH, window.innerWidth - MENU_WIDTH - 8));
    setPosition({ top, left });
  }, [open]);

  useEffect(() => {
    if (!open) return undefined;
    const enabled = () => [...(menu.current?.querySelectorAll('[role="menuitem"]:not([aria-disabled="true"])') || [])];
    enabled()[0]?.focus();
    const onPointerDown = (event) => { if (!container.current?.contains(event.target)) close(); };
    const onKeyDown = (event) => {
      if (event.key === 'Escape') { event.preventDefault(); close(true); return; }
      if (event.key === 'Tab') { close(); return; }
      if (event.key !== 'ArrowDown' && event.key !== 'ArrowUp') return;
      const list = enabled();
      if (!list.length) return;
      event.preventDefault();
      const index = list.indexOf(document.activeElement);
      list[(index + (event.key === 'ArrowDown' ? 1 : -1) + list.length) % list.length].focus();
    };
    const onViewportChange = () => close();
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    window.addEventListener('resize', onViewportChange);
    window.addEventListener('scroll', onViewportChange, true);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
      window.removeEventListener('resize', onViewportChange);
      window.removeEventListener('scroll', onViewportChange, true);
    };
  }, [open]);

  return (
    <div className={`kebab-menu ${className}`} ref={container}>
      <button ref={trigger} type="button" className="kebab-trigger" aria-haspopup="menu" aria-expanded={open}
        aria-label={label} title={label} onClick={() => setOpen(prev => !prev)}>
        <i className="fas fa-ellipsis-vertical" aria-hidden="true"></i>
      </button>
      {open && (
        <div ref={menu} className="kebab-dropdown" role="menu" aria-label={label}
          style={position ? { top: position.top, left: position.left, width: MENU_WIDTH } : { visibility: 'hidden', width: MENU_WIDTH }}>
          {items.filter(Boolean).map(item => {
            const content = <><i className={`fas ${item.icon || 'fa-circle'}`} aria-hidden="true"></i><span>{item.label}</span></>;
            const cls = `kebab-item${item.danger ? ' danger' : ''}`;
            if (item.to && !item.disabled) {
              return <Link key={item.label} role="menuitem" tabIndex={-1} className={cls} to={item.to} onClick={() => close()}>{content}</Link>;
            }
            return (
              <button key={item.label} type="button" role="menuitem" tabIndex={-1} className={cls}
                aria-disabled={item.disabled ? 'true' : undefined} title={item.title}
                onClick={() => { if (item.disabled) return; close(true); item.onSelect?.(); }}>
                {content}
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
}

export default KebabMenu;
