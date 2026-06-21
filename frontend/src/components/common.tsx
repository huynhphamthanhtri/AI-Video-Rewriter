import type { ElementType, ReactNode } from 'react';

export function Card({ children, className = '' }: { children: ReactNode; className?: string }) {
  return <section className={`panel ${className}`}>{children}</section>;
}

export function SectionTitle({ icon: Icon, title, desc }: { icon: ElementType; title: string; desc: string }) {
  return <div className="mb-5 flex items-start gap-3"><div className="icon-box"><Icon size={20}/></div><div><h2 className="text-xl font-bold text-white">{title}</h2><p className="text-sm text-slate-400">{desc}</p></div></div>;
}

export function Pill({ children, tone = 'violet' }: { children: ReactNode; tone?: 'violet' | 'green' | 'red' | 'yellow' | 'cyan' }) {
  return <span className={`pill pill-${tone}`}>{children}</span>;
}

export function Stat({ label, value }: { label: string; value: string }) {
  return <div className="stat"><span>{label}</span><b>{value}</b></div>;
}
