import React, { useState, useEffect } from 'react';
import {
  Activity,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Menu,
  X,
  Server,
  Film,
  Info,
} from 'lucide-react';
import { HealthResponse } from '../../types';

interface HeaderProps {
  health: HealthResponse | null;
  loading: boolean;
  onRefreshHealth: () => void;
  onToggleMobileSidebar: () => void;
  isMobileSidebarOpen?: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  health,
  loading,
  onRefreshHealth,
  onToggleMobileSidebar,
  isMobileSidebarOpen = false,
}) => {
  const isHealthy = health?.status === 'ok';
  const ffmpegOk = health?.system_info?.ffmpeg_available;
  const [showDetailsModal, setShowDetailsModal] = useState<boolean>(false);

  // Close modal on Escape key
  useEffect(() => {
    if (!showDetailsModal) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setShowDetailsModal(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [showDetailsModal]);

  return (
    <>
      <header className="h-16 bg-white border-b border-slate-200 px-3 sm:px-6 md:px-8 flex items-center justify-between min-w-0 shrink-0 select-none">
        {/* Left: Mobile Menu Toggle + App Branding / Title */}
        <div className="flex items-center gap-2 sm:gap-3 min-w-0">
          <button
            type="button"
            onClick={onToggleMobileSidebar}
            className="md:hidden p-2 -ml-1.5 rounded-xl text-slate-600 hover:text-slate-900 hover:bg-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500/20 transition-colors"
            aria-label={isMobileSidebarOpen ? 'Close navigation menu' : 'Open navigation menu'}
            aria-expanded={isMobileSidebarOpen}
          >
            <Menu className="w-5 h-5" />
          </button>

          <div className="flex items-center gap-2 min-w-0">
            <h1 className="text-base sm:text-lg font-bold text-slate-800 tracking-tight whitespace-nowrap truncate">
              <span className="sm:hidden">KhmerDub AI</span>
              <span className="hidden sm:inline">KhmerDub AI Workspace</span>
            </h1>
            <span className="hidden sm:inline-flex items-center text-[11px] font-medium px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 border border-slate-200 whitespace-nowrap">
              Local Docker Dev
            </span>
          </div>
        </div>

        {/* Right: Status Indicators + Actions */}
        <div className="flex items-center gap-2 sm:gap-3 shrink-0">
          {/* Desktop Backend Connectivity Status */}
          <div className="hidden md:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-200 text-xs">
            <Activity className="w-3.5 h-3.5 text-slate-400" />
            <span className="text-slate-500 font-medium">Backend:</span>
            {loading && !health ? (
              <span className="flex items-center gap-1 text-slate-500 font-semibold">
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                Connecting...
              </span>
            ) : isHealthy ? (
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

          {/* Desktop FFmpeg Status */}
          <div className="hidden lg:flex items-center gap-2 px-3 py-1.5 rounded-lg bg-slate-50 border border-slate-200 text-xs">
            <span className="text-slate-500 font-medium">FFmpeg:</span>
            {loading && !health ? (
              <span className="text-slate-500 font-semibold flex items-center gap-1">Checking...</span>
            ) : ffmpegOk ? (
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

          {/* Mobile / Compact Status Pill (tap to view details modal) */}
          <button
            type="button"
            onClick={() => setShowDetailsModal(true)}
            className="md:hidden flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg bg-slate-50 hover:bg-slate-100 border border-slate-200 text-xs font-medium text-slate-700 transition-colors cursor-pointer"
            title="Tap to view backend status details"
            aria-label="Backend status"
          >
            {loading && !health ? (
              <>
                <RefreshCw className="w-3 h-3 text-slate-400 animate-spin" />
                <span className="text-[11px] text-slate-500 font-semibold">Connecting</span>
              </>
            ) : isHealthy ? (
              <>
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
                <span className="text-[11px] text-emerald-700 font-semibold">Online</span>
              </>
            ) : (
              <>
                <span className="w-2 h-2 rounded-full bg-rose-500" />
                <span className="text-[11px] text-rose-700 font-semibold">Offline</span>
              </>
            )}
          </button>

          {/* Refresh button */}
          <button
            type="button"
            onClick={onRefreshHealth}
            disabled={loading}
            className="p-2 rounded-xl text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500/20"
            title="Refresh connection status"
            aria-label="Refresh connection status"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-indigo-600' : ''}`} />
          </button>
        </div>
      </header>

      {/* Mobile Backend Connection Details Modal */}
      {showDetailsModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/60 backdrop-blur-xs animate-in fade-in duration-150"
          onClick={() => setShowDetailsModal(false)}
          role="dialog"
          aria-modal="true"
          aria-labelledby="backend-details-title"
        >
          <div
            className="bg-white rounded-2xl shadow-2xl border border-slate-200 w-full max-w-sm p-5 space-y-4 text-slate-800"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2">
                <div className="p-2 rounded-lg bg-indigo-50 text-indigo-600">
                  <Server className="w-4 h-4" />
                </div>
                <div>
                  <h3 id="backend-details-title" className="text-sm font-bold text-slate-900">
                    System Connectivity
                  </h3>
                  <p className="text-[11px] text-slate-500">KhmerDub AI Platform Status</p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowDetailsModal(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100"
                aria-label="Close details"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-2.5 text-xs">
              {/* Backend API */}
              <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/80 flex items-center justify-between">
                <span className="text-slate-600 font-medium flex items-center gap-2">
                  <Activity className="w-4 h-4 text-slate-400" />
                  FastAPI Backend
                </span>
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

              {/* FFmpeg Engine */}
              <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/80 flex items-center justify-between">
                <span className="text-slate-600 font-medium flex items-center gap-2">
                  <Film className="w-4 h-4 text-slate-400" />
                  FFmpeg Media Engine
                </span>
                {ffmpegOk ? (
                  <span className="flex items-center gap-1 text-emerald-600 font-semibold">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    Ready
                  </span>
                ) : (
                  <span className="flex items-center gap-1 text-amber-600 font-semibold">
                    <AlertTriangle className="w-3.5 h-3.5" />
                    Missing
                  </span>
                )}
              </div>

              {/* Environment */}
              <div className="p-3 rounded-xl bg-slate-50 border border-slate-200/80 flex items-center justify-between">
                <span className="text-slate-600 font-medium flex items-center gap-2">
                  <Info className="w-4 h-4 text-slate-400" />
                  Environment
                </span>
                <span className="font-semibold text-slate-800">Local Docker Dev</span>
              </div>
            </div>

            <div className="pt-2 flex items-center gap-2">
              <button
                type="button"
                onClick={() => {
                  onRefreshHealth();
                }}
                disabled={loading}
                className="flex-1 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold flex items-center justify-center gap-1.5 transition-colors disabled:opacity-50"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
                <span>{loading ? 'Checking...' : 'Refresh Status'}</span>
              </button>
              <button
                type="button"
                onClick={() => setShowDetailsModal(false)}
                className="px-4 py-2 rounded-xl border border-slate-200 text-slate-600 hover:bg-slate-100 text-xs font-medium transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
};
