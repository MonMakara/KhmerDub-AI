import React from 'react';
import { Activity, CheckCircle2, AlertTriangle, RefreshCw } from 'lucide-react';
import { HealthResponse } from '../../types';

interface HeaderProps {
  health: HealthResponse | null;
  loading: boolean;
  onRefreshHealth: () => void;
}

export const Header: React.FC<HeaderProps> = ({ health, loading, onRefreshHealth }) => {
  const isHealthy = health?.status === 'ok';
  const ffmpegOk = health?.system_info?.ffmpeg_available;

  return (
    <header className="h-16 bg-white border-b border-slate-200 px-8 flex items-center justify-between">
      <div className="flex items-center gap-3">
        <h1 className="text-lg font-semibold text-slate-800">KhmerDub AI Workspace</h1>
        <span className="text-xs px-2.5 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
          Local Docker Dev
        </span>
      </div>

      <div className="flex items-center gap-4">
        {/* Backend Connectivity Status */}
        <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-200 text-xs">
          <Activity className="w-3.5 h-3.5 text-slate-400" />
          <span className="text-slate-500 font-medium">Backend:</span>
          {isHealthy ? (
            <span className="flex items-center gap-1 text-emerald-600 font-semibold">
              <CheckCircle2 className="w-3.5 h-3.5" />
              Connected (v{health?.version})
            </span>
          ) : (
            <span className="flex items-center gap-1 text-rose-600 font-semibold">
              <AlertTriangle className="w-3.5 h-3.5" />
              Disconnected
            </span>
          )}
        </div>

        {/* FFmpeg Status */}
        <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-200 text-xs">
          <span className="text-slate-500 font-medium">FFmpeg:</span>
          {ffmpegOk ? (
            <span className="text-emerald-600 font-semibold flex items-center gap-1">
              <CheckCircle2 className="w-3.5 h-3.5" />
              Ready
            </span>
          ) : (
            <span className="text-amber-600 font-semibold flex items-center gap-1">
              <AlertTriangle className="w-3.5 h-3.5" />
              Missing
            </span>
          )}
        </div>

        {/* Refresh button */}
        <button
          onClick={onRefreshHealth}
          disabled={loading}
          className="p-2 rounded-lg text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition-colors"
          title="Refresh connection status"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>
    </header>
  );
};
