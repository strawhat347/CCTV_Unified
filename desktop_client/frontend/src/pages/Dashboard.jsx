import { ShieldCheck } from 'lucide-react';

export default function Dashboard() {
  return (
    <div className="flex-1 h-full bg-bg-primary flex flex-col items-center justify-center p-6">
      <div className="flex flex-col items-center text-center max-w-md opacity-50">
        <div className="w-20 h-20 bg-bg-elevated rounded-2xl flex items-center justify-center mb-6 border border-border-primary shadow-xl">
          <ShieldCheck className="w-10 h-10 text-accent" />
        </div>
        <h1 className="text-3xl font-bold text-white mb-2 tracking-tight">CCTV Unified</h1>
        <p className="text-text-muted">
          Select a module from the sidebar to begin monitoring.
        </p>
      </div>
    </div>
  );
}
