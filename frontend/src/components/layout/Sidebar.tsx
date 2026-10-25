import React, { useEffect, useRef } from 'react';
import {
  LayoutDashboard,
  FolderKanban,
  Settings,
  Languages,
  Video,
  Mic2,
  Wrench,
  PanelLeftClose,
  PanelLeftOpen,
  X,
  ChevronRight,
} from 'lucide-react';

interface SidebarProps {
  currentTab: string;
  onTabChange: (tab: string) => void;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  isMobileOpen: boolean;
  onCloseMobile: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({
  currentTab,
  onTabChange,
  isCollapsed,
  onToggleCollapse,
  isMobileOpen,
  onCloseMobile,
}) => {
  const closeButtonRef = useRef<HTMLButtonElement | null>(null);

  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'projects', label: 'Projects', icon: FolderKanban },
    { id: 'toolkit', label: 'Media Toolkit', icon: Wrench },
    { id: 'voices', label: 'Voice Studio', icon: Mic2 },
    { id: 'settings', label: 'Settings', icon: Settings },
  ];

  // Handle Escape key to close mobile drawer & Ctrl+B to toggle collapse
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isMobileOpen) {
        onCloseMobile();
      } else if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'b') {
        e.preventDefault();
        onToggleCollapse();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isMobileOpen, onCloseMobile, onToggleCollapse]);

  // Lock background scroll when mobile drawer is open
  useEffect(() => {
    if (isMobileOpen) {
      const originalOverflow = document.body.style.overflow;
      document.body.style.overflow = 'hidden';
      // Focus close button on mobile open
      closeButtonRef.current?.focus();
      return () => {
        document.body.style.overflow = originalOverflow;
      };
    }
  }, [isMobileOpen]);

  const handleNavClick = (id: string) => {
    onTabChange(id);
    if (isMobileOpen) {
      onCloseMobile();
    }
  };

  return (
    <>
      {/* =========================================================================
          1. DESKTOP / TABLET EXPANDABLE SIDEBAR
          Permanently hidden on mobile (< 768px), resizes dynamically on desktop
      ========================================================================= */}
      <aside
        className={`hidden md:flex flex-col bg-slate-900 text-slate-300 border-r border-slate-800 shrink-0 transition-all duration-300 ease-in-out relative z-30 select-none ${
          isCollapsed ? 'w-16' : 'w-64'
        }`}
        aria-label="Desktop Navigation"
      >
        {/* Brand Header */}
        <div
          className={`h-16 flex items-center border-b border-slate-800 bg-slate-950/40 transition-all duration-300 ${
            isCollapsed ? 'justify-center px-2' : 'justify-between px-4'
          }`}
        >
          {isCollapsed ? (
            <button
              type="button"
              onClick={onToggleCollapse}
              className="w-9 h-9 rounded-lg bg-indigo-600 hover:bg-indigo-500 flex items-center justify-center text-white font-bold shadow-md shadow-indigo-500/20 transition-all group relative cursor-pointer"
              title="Expand sidebar (Ctrl+B)"
              aria-label="Expand sidebar"
            >
              <Languages className="w-5 h-5 group-hover:scale-110 transition-transform" />
              <span
                role="tooltip"
                className="absolute left-full ml-3 px-2 py-1 rounded bg-slate-800 text-white text-xs font-semibold whitespace-nowrap shadow-xl pointer-events-none opacity-0 group-hover:opacity-100 transition-opacity z-50 border border-slate-700"
              >
                Expand Sidebar
              </span>
            </button>
          ) : (
            <>
              <div className="flex items-center gap-3 min-w-0">
                <div className="w-9 h-9 rounded-lg bg-indigo-600 flex items-center justify-center text-white font-bold shadow-md shadow-indigo-500/20 shrink-0">
                  <Languages className="w-5 h-5" />
                </div>
                <div className="min-w-0">
                  <span className="font-bold text-white text-base tracking-wide flex items-center gap-1.5 truncate">
                    KhmerDub{' '}
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-400 font-semibold border border-indigo-500/30">
                      AI
                    </span>
                  </span>
                  <p className="text-[11px] text-slate-400 truncate">EN → KM Video Dubbing</p>
                </div>
              </div>

              {/* Collapse Button */}
              <button
                type="button"
                onClick={onToggleCollapse}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
                title="Collapse sidebar (Ctrl+B)"
                aria-label="Collapse sidebar"
              >
                <PanelLeftClose className="w-4 h-4" />
              </button>
            </>
          )}
        </div>

        {/* Navigation Links */}
        <nav className="flex-1 px-2.5 py-5 space-y-1.5 overflow-y-auto overflow-x-hidden">
          {!isCollapsed && (
            <div className="px-3 pb-2 text-[11px] font-semibold tracking-wider text-slate-400 uppercase">
              Menu
            </div>
          )}

          {navItems.map((item) => {
            const Icon = item.icon;
            const isActive = currentTab === item.id;

            return (
              <div key={item.id} className="relative group">
                <button
                  type="button"
                  onClick={() => handleNavClick(item.id)}
                  aria-current={isActive ? 'page' : undefined}
                  className={`w-full flex items-center rounded-xl text-sm font-medium transition-all duration-150 cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500/40 ${
                    isCollapsed
                      ? 'justify-center p-2.5'
                      : 'justify-start gap-3 px-3 py-2.5'
                  } ${
                    isActive
                      ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-600/30 font-semibold'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
                  }`}
                  aria-label={item.label}
                >
                  <Icon
                    className={`w-5 h-5 shrink-0 ${
                      isActive ? 'text-white' : 'text-slate-400 group-hover:text-slate-200'
                    }`}
                  />
                  {!isCollapsed && <span className="truncate">{item.label}</span>}
                </button>

                {/* Accessible Floating Tooltip in Collapsed State */}
                {isCollapsed && (
                  <div
                    role="tooltip"
                    className="absolute left-full ml-3 top-1/2 -translate-y-1/2 px-2.5 py-1.5 rounded-lg bg-slate-800 text-white text-xs font-semibold whitespace-nowrap shadow-xl pointer-events-none opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 transition-opacity z-50 border border-slate-700/80"
                  >
                    {item.label}
                  </div>
                )}
              </div>
            );
          })}
        </nav>

        {/* Workflow pipeline reminder (expanded only) */}
        {!isCollapsed && (
          <div className="p-3.5 mx-3 mb-4 rounded-xl bg-slate-800/60 border border-slate-800/80 space-y-2">
            <div className="flex items-center gap-2 text-xs font-semibold text-slate-300">
              <Video className="w-4 h-4 text-indigo-400" />
              <span>Workflow Pipeline</span>
            </div>
            <ol className="text-[11px] text-slate-400 space-y-1 list-decimal list-inside leading-relaxed">
              <li>Upload MP4</li>
              <li>Faster-Whisper STT</li>
              <li>Khmer Translation</li>
              <li>Khmer TTS Voice</li>
              <li>Audio Sync & Export</li>
            </ol>
          </div>
        )}

        {/* Desktop Footer */}
        <div
          className={`py-3.5 border-t border-slate-800 text-xs text-slate-400 flex items-center transition-all ${
            isCollapsed ? 'justify-center px-2' : 'justify-between px-4'
          }`}
        >
          {isCollapsed ? (
            <button
              type="button"
              onClick={onToggleCollapse}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
              title="Expand sidebar (Ctrl+B)"
              aria-label="Expand sidebar"
            >
              <PanelLeftOpen className="w-4 h-4" />
            </button>
          ) : (
            <>
              <div className="flex items-center gap-2 text-slate-400 text-xs">
                <span>KhmerDub AI</span>
                <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">
                  v0.1.0
                </span>
              </div>
              <button
                type="button"
                onClick={onToggleCollapse}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
                title="Collapse sidebar (Ctrl+B)"
                aria-label="Collapse sidebar"
              >
                <PanelLeftClose className="w-4 h-4" />
              </button>
            </>
          )}
        </div>
      </aside>

      {/* =========================================================================
          2. MOBILE DRAWER SIDEBAR (< 768px)
          Overlay drawer triggered by header hamburger menu
      ========================================================================= */}
      {isMobileOpen && (
        <>
          {/* Dimmed Backdrop */}
          <div
            className="fixed inset-0 bg-slate-950/70 backdrop-blur-sm z-40 md:hidden transition-opacity animate-in fade-in duration-200"
            onClick={onCloseMobile}
            aria-hidden="true"
          />

          {/* Slide-out Drawer */}
          <aside
            role="dialog"
            aria-modal="true"
            aria-label="Mobile Navigation Menu"
            className="fixed inset-y-0 left-0 z-50 w-72 max-w-[85vw] bg-slate-900 text-slate-300 flex flex-col shadow-2xl border-r border-slate-800 md:hidden transform transition-transform duration-200 ease-in-out select-none"
          >
            {/* Drawer Header */}
            <div className="h-16 flex items-center justify-between px-4 border-b border-slate-800 bg-slate-950/50">
              <div className="flex items-center gap-3 min-w-0">
                <div className="w-9 h-9 rounded-lg bg-indigo-600 flex items-center justify-center text-white font-bold shadow-md shadow-indigo-500/20 shrink-0">
                  <Languages className="w-5 h-5" />
                </div>
                <div className="min-w-0">
                  <span className="font-bold text-white text-base tracking-wide flex items-center gap-1.5 truncate">
                    KhmerDub{' '}
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-400 font-semibold border border-indigo-500/30">
                      AI
                    </span>
                  </span>
                  <p className="text-[11px] text-slate-400 truncate">EN → KM Video Dubbing</p>
                </div>
              </div>

              {/* Close Drawer Button */}
              <button
                ref={closeButtonRef}
                type="button"
                onClick={onCloseMobile}
                className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-800 transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500/40"
                aria-label="Close navigation menu"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Mobile Nav Links */}
            <nav className="flex-1 px-3 py-5 space-y-1.5 overflow-y-auto">
              <div className="px-3 pb-2 text-[11px] font-semibold tracking-wider text-slate-400 uppercase">
                Menu
              </div>
              {navItems.map((item) => {
                const Icon = item.icon;
                const isActive = currentTab === item.id;
                return (
                  <button
                    key={item.id}
                    type="button"
                    onClick={() => handleNavClick(item.id)}
                    aria-current={isActive ? 'page' : undefined}
                    className={`w-full flex items-center justify-between px-3.5 py-3 rounded-xl text-sm font-medium transition-all ${
                      isActive
                        ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-600/30 font-semibold'
                        : 'text-slate-300 hover:text-white hover:bg-slate-800/80'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <Icon className={`w-5 h-5 ${isActive ? 'text-white' : 'text-slate-400'}`} />
                      <span>{item.label}</span>
                    </div>
                    {isActive && <ChevronRight className="w-4 h-4 text-white/70" />}
                  </button>
                );
              })}
            </nav>

            {/* Mobile Workflow Reminder */}
            <div className="p-3.5 mx-3 mb-4 rounded-xl bg-slate-800/60 border border-slate-800/80 space-y-2">
              <div className="flex items-center gap-2 text-xs font-semibold text-slate-300">
                <Video className="w-4 h-4 text-indigo-400" />
                <span>Workflow Pipeline</span>
              </div>
              <ol className="text-[11px] text-slate-400 space-y-1 list-decimal list-inside leading-relaxed">
                <li>Upload MP4</li>
                <li>Faster-Whisper STT</li>
                <li>Khmer Translation</li>
                <li>Khmer TTS Voice</li>
                <li>Audio Sync & Export</li>
              </ol>
            </div>

            {/* Mobile Drawer Footer */}
            <div className="px-4 py-3.5 border-t border-slate-800 text-xs text-slate-400 flex items-center justify-between">
              <span>KhmerDub AI Platform</span>
              <span className="font-mono text-[10px] px-1.5 py-0.5 rounded bg-slate-800 text-slate-400">
                v0.1.0
              </span>
            </div>
          </aside>
        </>
      )}
    </>
  );
};
