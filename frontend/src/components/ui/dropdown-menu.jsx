import React, { createContext, useContext, useEffect, useRef, useState, cloneElement } from 'react';

const Ctx = createContext(null);

export function DropdownMenu({ children }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef(null);

  // Close on outside click or Escape
  useEffect(() => {
    if (!open) return;
    const onDown = (e) => {
      if (!rootRef.current) return;
      if (!rootRef.current.contains(e.target)) setOpen(false);
    };
    const onKey = (e) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  return (
    <div ref={rootRef} className="relative inline-block text-left">
      <Ctx.Provider value={{ open, setOpen, rootRef }}>
        {children}
      </Ctx.Provider>
    </div>
  );
}

export function DropdownMenuTrigger({ asChild, children, ...rest }) {
  const { open, setOpen } = useContext(Ctx) || {};
  const toggle = (e) => {
    e.preventDefault();
    setOpen && setOpen(!open);
  };
  if (asChild && React.isValidElement(children)) {
    return cloneElement(children, {
      ...rest,
      onClick: (e) => {
        children.props.onClick && children.props.onClick(e);
        toggle(e);
      },
    });
  }
  return (
    <button type="button" onClick={toggle} {...rest}>
      {children}
    </button>
  );
}

export function DropdownMenuContent({ children, align = 'start', className = '', ...rest }) {
  const { open } = useContext(Ctx) || {};
  if (!open) return null;
  const alignClass = align === 'end' ? 'right-0' : 'left-0';
  return (
    <div
      role="menu"
      className={`absolute z-50 mt-2 min-w-[10rem] rounded-md border bg-white shadow-md p-1 ${alignClass} ${className}`}
      {...rest}
    >
      {children}
    </div>
  );
}

export function DropdownMenuItem({ children, className = '', onClick, ...rest }) {
  const { setOpen } = useContext(Ctx) || {};
  const handleClick = (e) => {
    onClick && onClick(e);
    setOpen && setOpen(false);
  };
  return (
    <button
      type="button"
      role="menuitem"
      className={`w-full text-left px-3 py-2 text-sm rounded hover:bg-gray-100 ${className}`}
      onClick={handleClick}
      {...rest}
    >
      {children}
    </button>
  );
}
