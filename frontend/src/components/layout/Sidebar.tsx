import React from 'react';
import { LayoutDashboard, FolderKanban, Settings, Languages, Video } from 'lucide-react';

interface SidebarProps {
  currentTab: string;
  onTabChange: (tab: string) => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ currentTab, onTabChange }) => {
  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { id: 'projects', label: 'Projects', icon: FolderKanban },
    { id: 'settings', label: 'Settings', icon: Settings },
  ];

  return (
    <aside className="w-16 md:w-64 bg-slate-900 text-slate-300 flex flex-col border-r border-slate-800 shrink-0 transition-all duration-200">
      {/* Brand Header */}
      <div className="h-16 flex items-center justify-center md:justify-start px-3 md:px-6 gap-3 border-b border-slate-800 bg-slate-950/40">
        <div className="w-9 h-9 rounded-lg bg-indigo-600 flex items-center justify-center text-white font-bold shadow-md shadow-indigo-500/20 shrink-0">
          <Languages className="w-5 h-5" />
        </div>
        <div className="hidden md:block min-w-0">
          <span className="font-bold text-white text-base tracking-wide flex items-center gap-1.5 truncate">
            KhmerDub <span className="text-xs px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-400 font-semibold border border-indigo-500/30">AI</span>
          </span>
          <p className="text-xs text-slate-400 truncate">EN → KM Video Dubbing</p>
        </div>
      </div>

      {/* Navigation Links */}
      <nav className="flex-1 px-2 md:px-3 py-6 space-y-1.5">
        <div className="hidden md:block px-3 pb-2 text-[11px] font-semibold tracking-wider text-slate-400 uppercase">
          Menu
        </div>
        {navItems.map((item) => {
          const Icon = item.icon;
          const isActive = currentTab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onTabChange(item.id)}
              title={item.label}
              className={`w-full flex items-center justify-center md:justify-start gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 ${
                isActive
                  ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-600/30'
                  : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
              }`}
            >
              <Icon className={`w-5 h-5 shrink-0 ${isActive ? 'text-white' : 'text-slate-400'}`} />
              <span className="hidden md:inline truncate">{item.label}</span>
            </button>
          );
        })}
      </nav>

      {/* Workflow pipeline reminder */}
      <div className="hidden md:block p-4 mx-3 mb-4 rounded-xl bg-slate-800/60 border border-slate-800">
        <div className="flex items-center gap-2 text-xs font-semibold text-slate-300 mb-2">
          <Video className="w-4 h-4 text-indigo-400" />
          <span>Workflow Pipeline</span>
        </div>
        <ol className="text-xs text-slate-400 space-y-1 list-decimal list-inside">
          <li>Upload MP4</li>
          <li>Whisper STT</li>
          <li>Khmer Translation</li>
          <li>Khmer TTS Voice</li>
          <li>Audio Sync & Export</li>
        </ol>
      </div>

      {/* Version footer */}
      <div className="px-3 md:px-6 py-4 border-t border-slate-800 text-xs text-slate-400 flex items-center justify-center md:justify-between">
        <span className="hidden md:inline">KhmerDub AI</span>
        <span className="font-mono text-[10px] md:text-xs">v0.1.0</span>
      </div>
    </aside>
  );
};
