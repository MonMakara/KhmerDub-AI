import React, { useState } from 'react';
import {
  UploadCloud,
  FileAudio,
  Languages,
  Mic2,
  Film,
  Plus,
  CheckCircle,
  Cpu,
  Layers,
  ArrowRight,
} from 'lucide-react';
import { HealthResponse, ProjectSummary } from '../types';

interface DashboardProps {
  health: HealthResponse | null;
  projects: ProjectSummary[];
  onCreateProject: (title: string) => Promise<void>;
  onNavigateProjects: () => void;
}

export const Dashboard: React.FC<DashboardProps> = ({
  health,
  projects,
  onCreateProject,
  onNavigateProjects,
}) => {
  const [newTitle, setNewTitle] = useState('');
  const [creating, setCreating] = useState(false);
  const [createMsg, setCreateMsg] = useState<string | null>(null);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    try {
      setCreating(true);
      await onCreateProject(newTitle.trim());
      setNewTitle('');
      setCreateMsg('Project created successfully!');
      setTimeout(() => setCreateMsg(null), 3000);
    } catch (err: any) {
      alert(`Error creating project: ${err.message}`);
    } finally {
      setCreating(false);
    }
  };

  const steps = [
    {
      num: 1,
      title: 'Video Upload',
      desc: 'Upload English MP4 video safely into persistent storage.',
      icon: UploadCloud,
      color: 'bg-blue-50 text-blue-600 border-blue-200',
    },
    {
      num: 2,
      title: 'Audio & Transcribe',
      desc: 'Extract audio with FFmpeg & transcribe using faster-whisper.',
      icon: FileAudio,
      color: 'bg-emerald-50 text-emerald-600 border-emerald-200',
    },
    {
      num: 3,
      title: 'Khmer Translation',
      desc: 'Translate English segments into Khmer with segment editing.',
      icon: Languages,
      color: 'bg-purple-50 text-purple-600 border-purple-200',
    },
    {
      num: 4,
      title: 'Khmer Voice (gTTS)',
      desc: 'Synthesize natural Khmer speech segments via Google gTTS.',
      icon: Mic2,
      color: 'bg-amber-50 text-amber-600 border-amber-200',
    },
    {
      num: 5,
      title: 'Sync & Video Export',
      desc: 'Synchronize audio timeline and export dubbed MP4 video.',
      icon: Film,
      color: 'bg-rose-50 text-rose-600 border-rose-200',
    },
  ];

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Welcome Banner */}
      <div className="rounded-2xl bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 p-8 text-white shadow-lg border border-slate-800">
        <div className="max-w-2xl">
          <span className="text-xs uppercase tracking-wider px-3 py-1 rounded-full bg-indigo-500/20 text-indigo-300 font-semibold border border-indigo-500/30">
            Phase 1 • Environment Initialized
          </span>
          <h2 className="text-2xl font-bold mt-4 tracking-tight">
            AI-Powered English-to-Khmer Video Dubbing
          </h2>
          <p className="text-slate-300 mt-2 text-sm leading-relaxed">
            Welcome to KhmerDub AI. This platform automates the complete video dubbing lifecycle
            from English speech extraction to synchronized Khmer audio dubbing.
          </p>
        </div>
      </div>

      {/* Stats / System Readiness Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-5">
        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between text-slate-500 text-xs font-semibold uppercase tracking-wider">
            <span>Total Projects</span>
            <Layers className="w-4 h-4 text-slate-400" />
          </div>
          <div className="mt-2 text-3xl font-bold text-slate-900">{projects.length}</div>
          <p className="text-xs text-slate-400 mt-1">Stored in SQLite database</p>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between text-slate-500 text-xs font-semibold uppercase tracking-wider">
            <span>Backend API</span>
            <CheckCircle className="w-4 h-4 text-emerald-500" />
          </div>
          <div className="mt-2 text-xl font-bold text-slate-900 capitalize">
            {health?.status || 'Connecting...'}
          </div>
          <p className="text-xs text-slate-400 mt-1 font-mono">
            {health?.app_name} v{health?.version || '0.1.0'}
          </p>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between text-slate-500 text-xs font-semibold uppercase tracking-wider">
            <span>Media Engine</span>
            <Film className="w-4 h-4 text-indigo-500" />
          </div>
          <div className="mt-2 text-xl font-bold text-slate-900">
            {health?.system_info?.ffmpeg_available ? 'FFmpeg Ready' : 'Unavailable'}
          </div>
          <p className="text-xs text-slate-400 mt-1">Video & Audio Processing</p>
        </div>

        <div className="bg-white p-5 rounded-xl border border-slate-200 shadow-sm">
          <div className="flex items-center justify-between text-slate-500 text-xs font-semibold uppercase tracking-wider">
            <span>AI Inference</span>
            <Cpu className="w-4 h-4 text-purple-500" />
          </div>
          <div className="mt-2 text-xl font-bold text-slate-900 uppercase">
            {health?.system_info?.whisper_device || 'CPU'}
          </div>
          <p className="text-xs text-slate-400 mt-1">
            Whisper model: {health?.system_info?.whisper_model || 'base'}
          </p>
        </div>
      </div>

      {/* Workflow Steps Overview */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
        <h3 className="text-base font-semibold text-slate-800 mb-1">
          Video Dubbing Workflow Pipeline
        </h3>
        <p className="text-xs text-slate-500 mb-6">
          The 5 core modules designed for complete English to Khmer dubbing
        </p>

        <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
          {steps.map((st) => {
            const Icon = st.icon;
            return (
              <div
                key={st.num}
                className="p-4 rounded-xl border border-slate-200/90 bg-slate-50/50 hover:bg-slate-50 transition-colors flex flex-col justify-between"
              >
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <span className="text-xs font-mono font-bold px-2 py-0.5 rounded bg-slate-200 text-slate-700">
                      0{st.num}
                    </span>
                    <div className={`p-2 rounded-lg border ${st.color}`}>
                      <Icon className="w-4 h-4" />
                    </div>
                  </div>
                  <h4 className="font-semibold text-sm text-slate-800 mb-1">{st.title}</h4>
                  <p className="text-xs text-slate-500 leading-relaxed">{st.desc}</p>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Quick Action: Create New Project */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm">
        <div className="flex items-center justify-between mb-4">
          <div>
            <h3 className="text-base font-semibold text-slate-800">Quick Test Project</h3>
            <p className="text-xs text-slate-500">
              Verify database writes and frontend-to-backend communication
            </p>
          </div>
          <button
            onClick={onNavigateProjects}
            className="text-xs font-semibold text-indigo-600 hover:text-indigo-700 flex items-center gap-1"
          >
            View All Projects ({projects.length})
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>

        <form onSubmit={handleCreate} className="flex flex-col sm:flex-row gap-3">
          <input
            type="text"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder="e.g. English Tech Tutorial Video"
            className="flex-1 px-4 py-2.5 rounded-lg border border-slate-300 text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
            disabled={creating}
          />
          <button
            type="submit"
            disabled={creating || !newTitle.trim()}
            className="inline-flex items-center justify-center gap-2 px-5 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-medium transition-colors shadow-sm"
          >
            <Plus className="w-4 h-4" />
            {creating ? 'Creating...' : 'Create Project'}
          </button>
        </form>

        {createMsg && (
          <div className="mt-3 text-xs text-emerald-600 font-semibold flex items-center gap-1.5">
            <CheckCircle className="w-3.5 h-3.5" />
            {createMsg}
          </div>
        )}
      </div>
    </div>
  );
};
