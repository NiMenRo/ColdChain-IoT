/**
 * Thin Bootstrap 5 component shim — mirrors the react-bootstrap API surface
 * used in this project without requiring the npm package to be installed.
 * Renders native HTML with Bootstrap CSS class names.
 */
import React, { useState, useRef, useEffect } from 'react';

type Variant = 'primary' | 'secondary' | 'danger' | 'warning' | 'success' | 'info' |
  'outline-primary' | 'outline-secondary' | 'outline-danger' | 'outline-success' |
  'outline-warning' | 'outline-info' | 'link' | 'light' | 'dark';
type BsSize = 'sm' | 'lg';

// ─── Button ──────────────────────────────────────────────────────────────────

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: BsSize;
  as?: React.ElementType;
  href?: string;
  active?: boolean;
}
export function Button({ variant = 'primary', size, className = '', as: As, href, active, children, ...rest }: ButtonProps) {
  const cls = ['btn', `btn-${variant}`, size ? `btn-${size}` : '', active ? 'active' : '', className].filter(Boolean).join(' ');
  if (As || href) {
    const C: React.ElementType = As || 'a';
    return <C className={cls} href={href} {...rest}>{children}</C>;
  }
  return <button className={cls} {...(rest as React.ButtonHTMLAttributes<HTMLButtonElement>)}>{children}</button>;
}

// ─── Row / Col ───────────────────────────────────────────────────────────────

interface RowProps extends React.HTMLAttributes<HTMLDivElement> {
  xs?: number; sm?: number; md?: number; lg?: number; xl?: number;
  as?: React.ElementType;
}
export function Row({ as: As = 'div', className = '', children, xs, sm, md, lg, xl, ...rest }: RowProps) {
  const cols = [xs && `row-cols-${xs}`, sm && `row-cols-sm-${sm}`, md && `row-cols-md-${md}`, lg && `row-cols-lg-${lg}`, xl && `row-cols-xl-${xl}`].filter(Boolean).join(' ');
  const C: React.ElementType = As;
  return <C className={['row', cols, className].filter(Boolean).join(' ')} {...rest}>{children}</C>;
}

interface ColProps extends React.HTMLAttributes<HTMLDivElement> {
  xs?: number | string; sm?: number | string; md?: number | string; lg?: number | string; xl?: number | string;
}
function colCls(prefix: string, val?: number | string) {
  if (val === undefined) return '';
  if (val === 'auto') return `${prefix}-auto`;
  return `${prefix}-${val}`;
}
export function Col({ className = '', xs, sm, md, lg, xl, children, ...rest }: ColProps) {
  const cls = [
    xs !== undefined ? colCls('col', xs) : 'col',
    colCls('col-sm', sm), colCls('col-md', md), colCls('col-lg', lg), colCls('col-xl', xl),
    className,
  ].filter(Boolean).join(' ');
  return <div className={cls} {...rest}>{children}</div>;
}

// ─── Card ─────────────────────────────────────────────────────────────────────

interface CardProps extends React.HTMLAttributes<HTMLDivElement> { body?: boolean; as?: React.ElementType; }
function CardRoot({ as: As = 'div', className = '', children, body: _body, ...rest }: CardProps) {
  const C: React.ElementType = As;
  return <C className={['card', className].filter(Boolean).join(' ')} {...rest}>{children}</C>;
}
function CardBody({ className = '', children, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={['card-body', className].filter(Boolean).join(' ')} {...rest}>{children}</div>;
}
function CardHeader({ className = '', children, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={['card-header', className].filter(Boolean).join(' ')} {...rest}>{children}</div>;
}
function CardFooter({ className = '', children, ...rest }: React.HTMLAttributes<HTMLDivElement>) {
  return <div className={['card-footer', className].filter(Boolean).join(' ')} {...rest}>{children}</div>;
}
function CardTitle({ className = '', children, ...rest }: React.HTMLAttributes<HTMLHeadingElement>) {
  return <h5 className={['card-title', className].filter(Boolean).join(' ')} {...rest}>{children}</h5>;
}
function CardText({ className = '', children, ...rest }: React.HTMLAttributes<HTMLParagraphElement>) {
  return <p className={['card-text', className].filter(Boolean).join(' ')} {...rest}>{children}</p>;
}
export const Card = Object.assign(CardRoot, { Body: CardBody, Header: CardHeader, Footer: CardFooter, Title: CardTitle, Text: CardText });

// ─── Table ────────────────────────────────────────────────────────────────────

interface TableProps extends React.TableHTMLAttributes<HTMLTableElement> {
  responsive?: boolean | string;
  hover?: boolean;
  striped?: boolean;
  bordered?: boolean;
  borderless?: boolean;
  size?: BsSize;
}
export function Table({ responsive, hover, striped, bordered, borderless, size, className = '', children, ...rest }: TableProps) {
  const tblCls = ['table', hover ? 'table-hover' : '', striped ? 'table-striped' : '', bordered ? 'table-bordered' : '', borderless ? 'table-borderless' : '', size ? `table-${size}` : '', className].filter(Boolean).join(' ');
  const table = <table className={tblCls} {...rest}>{children}</table>;
  if (!responsive) return table;
  const wrapCls = typeof responsive === 'string' ? `table-responsive-${responsive}` : 'table-responsive';
  return <div className={wrapCls}>{table}</div>;
}

// ─── Alert ────────────────────────────────────────────────────────────────────

interface AlertProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: string;
  dismissible?: boolean;
  onClose?: () => void;
}
export function Alert({ variant = 'primary', dismissible, onClose, className = '', children, ...rest }: AlertProps) {
  const [show, setShow] = useState(true);
  if (!show) return null;
  return (
    <div className={['alert', `alert-${variant}`, dismissible ? 'alert-dismissible fade show' : '', className].filter(Boolean).join(' ')} role="alert" {...rest}>
      {children}
      {dismissible && (
        <button type="button" className="btn-close" aria-label="Close" onClick={() => { setShow(false); onClose?.(); }} />
      )}
    </div>
  );
}

// ─── Badge ────────────────────────────────────────────────────────────────────

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> { bg?: string; text?: string; pill?: boolean; }
export function Badge({ bg = 'primary', text, pill, className = '', children, ...rest }: BadgeProps) {
  const cls = ['badge', `bg-${bg}`, text ? `text-${text}` : '', pill ? 'rounded-pill' : '', className].filter(Boolean).join(' ');
  return <span className={cls} {...rest}>{children}</span>;
}

// ─── ProgressBar ──────────────────────────────────────────────────────────────

interface ProgressBarProps extends React.HTMLAttributes<HTMLDivElement> {
  now?: number; min?: number; max?: number; label?: React.ReactNode;
  variant?: string; striped?: boolean; animated?: boolean;
}
export function ProgressBar({ now = 0, min = 0, max = 100, label, variant, striped, animated, className = '', ...rest }: ProgressBarProps) {
  const pct = Math.round(((now - min) / (max - min)) * 100);
  const barCls = ['progress-bar', variant ? `bg-${variant}` : '', striped ? 'progress-bar-striped' : '', animated ? 'progress-bar-animated' : ''].filter(Boolean).join(' ');
  return (
    <div className={['progress', className].filter(Boolean).join(' ')} {...rest}>
      <div className={barCls} role="progressbar" style={{ width: `${pct}%` }} aria-valuenow={now} aria-valuemin={min} aria-valuemax={max}>
        {label}
      </div>
    </div>
  );
}

// ─── Form ─────────────────────────────────────────────────────────────────────

interface FormProps extends React.FormHTMLAttributes<HTMLFormElement> { validated?: boolean; }
function FormRoot({ validated, className = '', children, ...rest }: FormProps) {
  return <form className={[validated ? 'was-validated' : '', className].filter(Boolean).join(' ')} noValidate={validated} {...rest}>{children}</form>;
}
interface FormControlProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'size'> { size?: BsSize; isInvalid?: boolean; isValid?: boolean; as?: 'input' | 'textarea'; rows?: number; }
function FormControl({ size, isInvalid, isValid, as: As = 'input', className = '', rows, ...rest }: FormControlProps) {
  const cls = ['form-control', size ? `form-control-${size}` : '', isInvalid ? 'is-invalid' : '', isValid ? 'is-valid' : '', className].filter(Boolean).join(' ');
  if (As === 'textarea') return <textarea className={cls} rows={rows} {...(rest as React.TextareaHTMLAttributes<HTMLTextAreaElement>)} />;
  return <input className={cls} {...rest} />;
}
interface FormSelectProps extends Omit<React.SelectHTMLAttributes<HTMLSelectElement>, 'size'> { size?: BsSize; isInvalid?: boolean; isValid?: boolean; }
function FormSelect({ size, isInvalid, isValid, className = '', children, ...rest }: FormSelectProps) {
  const cls = ['form-select', size ? `form-select-${size}` : '', isInvalid ? 'is-invalid' : '', isValid ? 'is-valid' : '', className].filter(Boolean).join(' ');
  return <select className={cls} {...rest}>{children}</select>;
}
interface FormCheckProps extends React.InputHTMLAttributes<HTMLInputElement> { type?: 'checkbox' | 'radio' | 'switch'; label?: React.ReactNode; id?: string; inline?: boolean; }
function FormCheck({ type = 'checkbox', label, id, inline, className = '', ...rest }: FormCheckProps) {
  const isSwitch = type === 'switch';
  const wrapCls = ['form-check', isSwitch ? 'form-switch' : '', inline ? 'form-check-inline' : '', className].filter(Boolean).join(' ');
  return (
    <div className={wrapCls}>
      <input className="form-check-input" type={isSwitch ? 'checkbox' : type} id={id} role={isSwitch ? 'switch' : undefined} {...rest} />
      {label && <label className="form-check-label" htmlFor={id}>{label}</label>}
    </div>
  );
}
interface FormGroupProps extends React.HTMLAttributes<HTMLDivElement> { controlId?: string; }
function FormGroup({ controlId, className = '', children, ...rest }: FormGroupProps) {
  return <div className={['mb-3', className].filter(Boolean).join(' ')} {...rest}>{children}</div>;
}
function FormLabel({ className = '', children, ...rest }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={['form-label', className].filter(Boolean).join(' ')} {...rest}>{children}</label>;
}
function FormText({ className = '', children, muted, ...rest }: React.HTMLAttributes<HTMLElement> & { muted?: boolean }) {
  return <div className={['form-text', muted ? 'text-muted' : '', className].filter(Boolean).join(' ')} {...rest}>{children}</div>;
}
function FormFeedback({ type = 'invalid', children }: { type?: 'invalid' | 'valid'; children?: React.ReactNode }) {
  return <div className={`${type}-feedback`}>{children}</div>;
}
export const Form = Object.assign(FormRoot, {
  Control: FormControl,
  Select: FormSelect,
  Check: FormCheck,
  Group: FormGroup,
  Label: FormLabel,
  Text: FormText,
  Feedback: FormFeedback,
});

// ─── Nav ──────────────────────────────────────────────────────────────────────

interface NavProps extends Omit<React.HTMLAttributes<HTMLElement>, 'onSelect'> { variant?: 'tabs' | 'pills'; fill?: boolean; justify?: boolean; as?: React.ElementType; activeKey?: string; onSelect?: (k: string | null) => void; }
function NavRoot({ variant, fill, justify, as: As = 'nav', className = '', children, activeKey: _ak, onSelect: _os, ...rest }: NavProps) {
  const cls = ['nav', variant ? `nav-${variant}` : '', fill ? 'nav-fill' : '', justify ? 'nav-justified' : '', className].filter(Boolean).join(' ');
  const C: React.ElementType = As;
  return <C className={cls} {...rest}>{children}</C>;
}
function NavItem({ className = '', children, ...rest }: React.HTMLAttributes<HTMLLIElement>) {
  return <li className={['nav-item', className].filter(Boolean).join(' ')} {...rest}>{children}</li>;
}
interface NavLinkProps extends React.AnchorHTMLAttributes<HTMLAnchorElement> { active?: boolean; disabled?: boolean; as?: React.ElementType; eventKey?: string; }
function NavLink({ active, disabled, as: As = 'a', className = '', children, eventKey, onClick, ...rest }: NavLinkProps) {
  const cls = ['nav-link', active ? 'active' : '', disabled ? 'disabled' : '', className].filter(Boolean).join(' ');
  const C: React.ElementType = As;
  return <C className={cls} onClick={onClick} {...rest}>{children}</C>;
}
export const Nav = Object.assign(NavRoot, { Item: NavItem, Link: NavLink });

// ─── NavDropdown ─────────────────────────────────────────────────────────────

interface NavDropdownProps extends Omit<React.HTMLAttributes<HTMLLIElement>, 'title'> { title: React.ReactNode; id?: string; align?: 'end' | 'start'; menuVariant?: string; }
function NavDropdownRoot({ title, id, align, className = '', children, ...rest }: NavDropdownProps) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLLIElement>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => { if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false); };
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, []);

  return (
    <li ref={ref} className={['nav-item dropdown', className].filter(Boolean).join(' ')} {...rest}>
      <a className="nav-link dropdown-toggle" href="#" role="button" id={id} onClick={e => { e.preventDefault(); setOpen(o => !o); }} aria-expanded={open}>
        {title}
      </a>
      <ul className={['dropdown-menu', open ? 'show' : '', align === 'end' ? 'dropdown-menu-end' : ''].filter(Boolean).join(' ')} aria-labelledby={id}>
        {children}
      </ul>
    </li>
  );
}
function NavDropdownHeader({ children }: { children?: React.ReactNode }) {
  return <h6 className="dropdown-header">{children}</h6>;
}
function NavDropdownItem({ className = '', children, onClick, href = '#', ...rest }: React.AnchorHTMLAttributes<HTMLAnchorElement>) {
  return <li><a className={['dropdown-item', className].filter(Boolean).join(' ')} href={href} onClick={onClick} {...rest}>{children}</a></li>;
}
function NavDropdownDivider() {
  return <li><hr className="dropdown-divider" /></li>;
}
export const NavDropdown = Object.assign(NavDropdownRoot, {
  Header: NavDropdownHeader,
  Item: NavDropdownItem,
  Divider: NavDropdownDivider,
});
