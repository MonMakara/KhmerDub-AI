import React, { useState } from 'react';
import {
  FolderKanban,
  CheckCircle2,
  Clock,
  AlertCircle,
  Plus,
  ArrowRight,
  Film,
  Languages,
  Mic2,
  FileAudio,
  Calendar,
  Play,
} from 'lucide-react';
import { HealthResponse, ProjectSummary, ProjectStatus } from '../types';
import { ProjectActionMenu } from '../components/common/ProjectActionMenu';
import { RenameProjectModal } from '../components/common/RenameProjectModal';
import { DeleteProjectModal } from '../components/common/DeleteProjectModal';

interface DashboardProps {
  health: HealthResponse | null;
  projects: ProjectSummary[];
  onCreateProject: (title: string) => Promise<string | void>;
  onNavigateProjects: () => void;
  onSelectProject: (projectId: string) => void;
  onRefresh?: () => void;
}

export const Dashboard: React.FC<DashboardProps> = ({
  projects,
  onCreateProject,
  onNavigateProjects,
  onSelectProject,
  onRefresh,
}) => {
  const [newTitle, setNewTitle] = useState('');
  const [creating, setCreating] = useState(false);
  const [showQuickCreate, setShowQuickCreate] = useState(false);
  const [renamingProject, setRenamingProject] = useState<ProjectSummary | null>(null);
  const [deletingProject, setDeletingProject] = useState<ProjectSummary | null>(null);

  // Compute real metrics
  const totalProjects = projects.length;
  const completedProjects = projects.filter((p) => p.status === 'completed').length;
  const processingProjects = projects.filter((p) =>
    ['uploaded', 'audio_extracted', 'transcribing', 'translating', 'generating_voice', 'synchronizing'].includes(p.status)
  ).length;
  const attentionProjects = projects.filter((p) => p.status === 'failed' || p.status === 'created').length;

  // Recent 5 projects sorted by updated_at / created_at
  const recentProjects = [...projects]
    .sort((a, b) => new Date(b.updated_at || b.created_at).getTime() - new Date(a.updated_at || a.created_at).getTime())
    .slice(0, 5);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    try {
      setCreating(true);
      const newId = await onCreateProject(newTitle.trim());
      setNewTitle('');
      setShowQuickCreate(false);
      if (newId) {
        onSelectProject(newId);
      }
    } catch (err: any) {
      alert(`Error creating project: ${err.message}`);
    } finally {
      setCreating(false);
    }
  };

  const getStatusInfo = (status: ProjectStatus) => {
    switch (status) {
      case 'completed':
        return { label: 'Completed', color: 'bg-emerald-50 text-emerald-700 border-emerald-200', percent: 100 };
      case 'synchronizing':
        return { label: 'Exporting Video', color: 'bg-cyan-50 text-cyan-700 border-cyan-200 animate-pulse', percent: 90 };
      case 'voice_generated':
        return { label: 'Speech Ready', color: 'bg-indigo-50 text-indigo-700 border-indigo-200', percent: 80 };
      case 'generating_voice':
        return { label: 'Generating Speech', color: 'bg-indigo-50 text-indigo-700 border-indigo-200 animate-pulse', percent: 70 };
      case 'translated':
        return { label: 'Translated', color: 'bg-purple-50 text-purple-700 border-purple-200', percent: 60 };
      case 'translating':
        return { label: 'Translating', color: 'bg-purple-50 text-purple-700 border-purple-200 animate-pulse', percent: 50 };
      case 'transcribed':
        return { label: 'Transcribed', color: 'bg-amber-50 text-amber-700 border-amber-200', percent: 40 };
      case 'transcribing':
        return { label: 'Transcribing', color: 'bg-amber-50 text-amber-700 border-amber-200 animate-pulse', percent: 30 };
      case 'audio_extracted':
      case 'uploaded':
        return { label: 'Media Uploaded', color: 'bg-blue-50 text-blue-700 border-blue-200', percent: 20 };
      case 'failed':
        return { label: 'Needs Attention', color: 'bg-rose-50 text-rose-700 border-rose-200', percent: 0 };
      case 'created':
      default:
        return { label: 'Draft', color: 'bg-slate-100 text-slate-700 border-slate-200', percent: 10 };
    }
  };

  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* Top Banner / Hero */}
      <div className="rounded-2xl bg-gradient-to-r from-slate-900 via-indigo-950 to-slate-900 p-5 sm:p-8 text-white shadow-lg border border-slate-800 relative overflow-hidden">
        <div className="absolute right-0 top-0 w-96 h-96 bg-indigo-500/10 rounded-full blur-3xl pointer-events-none -mr-20 -mt-20" />
        <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-6">
          <div className="max-w-2xl space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-[11px] uppercase tracking-wider px-2.5 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 font-semibold border border-indigo-500/30">
                Studio Dashboard
              </span>
              <span className="text-[11px] text-slate-400">• English → Khmer Dubbing Engine</span>
            </div>
            <h2 className="text-xl sm:text-2xl font-bold tracking-tight text-white">
              KhmerDub AI Dubbing Studio
            </h2>
            <p className="text-slate-300 text-xs sm:text-sm leading-relaxed">
              Automated end-to-end video localization: FFmpeg audio extraction, Faster-Whisper transcription,
              AI Khmer translation (Gemini / NLLB / Custom), natural neural speech (Google & Microsoft),
              and timing-synchronized MP4 export.
            </p>
          </div>

          <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2.5 shrink-0">
            <button
              onClick={() => setShowQuickCreate(!showQuickCreate)}
              className="px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-semibold text-xs sm:text-sm shadow-md shadow-indigo-600/30 transition-all flex items-center justify-center gap-2"
            >
              <Plus className="w-4 h-4" />
              New Dubbing Project
            </button>
            <button
              onClick={onNavigateProjects}
              className="px-4 py-2.5 rounded-xl bg-slate-800/80 hover:bg-slate-700/80 text-slate-200 border border-slate-700 font-medium text-xs sm:text-sm transition-all flex items-center justify-center gap-1.5"
            >
              <FolderKanban className="w-4 h-4 text-slate-400" />
              View All Projects
            </button>
          </div>
        </div>

        {/* Quick Create Drawer / Inline Form */}
        {showQuickCreate && (
          <form
            onSubmit={handleCreate}
            className="mt-6 pt-6 border-t border-slate-800/80 flex flex-col sm:flex-row items-stretch sm:items-center gap-3 animate-fadeIn"
          >
            <div className="flex-1 relative">
              <input
                type="text"
                value={newTitle}
                onChange={(e) => setNewTitle(e.target.value)}
                placeholder="Enter project name (e.g. AI Technology Documentary, Tech Talk Episode 1)..."
                className="w-full text-xs sm:text-sm px-4 py-2.5 bg-slate-950/60 border border-slate-700 rounded-xl text-white placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                autoFocus
                disabled={creating}
              />
            </div>
            <div className="flex items-center gap-2">
              <button
                type="submit"
                disabled={creating || !newTitle.trim()}
                className="px-5 py-2.5 rounded-xl bg-indigo-500 hover:bg-indigo-600 disabled:opacity-50 text-white text-xs sm:text-sm font-semibold transition"
              >
                {creating ? 'Creating...' : 'Create & Open Studio'}
              </button>
              <button
                type="button"
                onClick={() => setShowQuickCreate(false)}
                className="px-3 py-2.5 text-xs text-slate-400 hover:text-white"
              >
                Cancel
              </button>
            </div>
          </form>
        )}
      </div>

      {/* Real Real-Time Metrics Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 sm:gap-4">
        {/* Total Projects */}
        <div className="bg-white p-3.5 sm:p-5 rounded-xl border border-slate-200 shadow-sm space-y-1">
          <div className="flex items-center justify-between text-slate-500 text-xs font-semibold uppercase tracking-wider">
            <span>Total Projects</span>
            <FolderKanban className="w-4 h-4 text-indigo-500" />
          </div>
          <div className="text-2xl sm:text-3xl font-bold text-slate-900">{totalProjects}</div>
          <p className="text-[10px] sm:text-[11px] text-slate-400 truncate">Total videos in workspace</p>
        </div>

        {/* Processing Projects */}
        <div className="bg-white p-3.5 sm:p-5 rounded-xl border border-slate-200 shadow-sm space-y-1">
          <div className="flex items-center justify-between text-slate-500 text-xs font-semibold uppercase tracking-wider">
            <span>In Progress</span>
            <Clock className="w-4 h-4 text-amber-500" />
          </div>
          <div className="text-2xl sm:text-3xl font-bold text-amber-600">{processingProjects}</div>
          <p className="text-[10px] sm:text-[11px] text-slate-400 truncate">Transcribing, translating, dubbing</p>
        </div>

        {/* Completed Projects */}
        <div className="bg-white p-3.5 sm:p-5 rounded-xl border border-slate-200 shadow-sm space-y-1">
          <div className="flex items-center justify-between text-slate-500 text-xs font-semibold uppercase tracking-wider">
            <span>Exported MP4</span>
            <CheckCircle2 className="w-4 h-4 text-emerald-500" />
          </div>
          <div className="text-2xl sm:text-3xl font-bold text-emerald-600">{completedProjects}</div>
          <p className="text-[10px] sm:text-[11px] text-slate-400 truncate">Fully synchronized Khmer videos</p>
        </div>

        {/* Attention / Drafts */}
        <div className="bg-white p-3.5 sm:p-5 rounded-xl border border-slate-200 shadow-sm space-y-1">
          <div className="flex items-center justify-between text-slate-500 text-xs font-semibold uppercase tracking-wider">
            <span>Attention / Draft</span>
            <AlertCircle className="w-4 h-4 text-rose-500" />
          </div>
          <div className="text-2xl sm:text-3xl font-bold text-slate-700">{attentionProjects}</div>
          <p className="text-[10px] sm:text-[11px] text-slate-400 truncate">Awaiting media upload or retry</p>
        </div>
      </div>

      {/* Main Two-Column Section: Recent Projects + Pipeline Status */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Recent Projects List (2 columns on lg) */}
        <div className="lg:col-span-2 bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-4">
          <div className="flex items-center justify-between pb-3 border-b border-slate-100">
            <div>
              <h3 className="text-sm font-bold text-slate-800">Recent Projects</h3>
              <p className="text-xs text-slate-500">Pick up right where you left off</p>
            </div>
            <button
              onClick={onNavigateProjects}
              className="text-xs font-semibold text-indigo-600 hover:text-indigo-700 flex items-center gap-1"
            >
              <span>View All ({projects.length})</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </button>
          </div>

          {recentProjects.length === 0 ? (
            <div className="p-8 text-center bg-slate-50 rounded-xl border border-dashed border-slate-200 space-y-2">
              <FolderKanban className="w-8 h-8 text-slate-400 mx-auto" />
              <h4 className="text-sm font-semibold text-slate-700">No projects created yet</h4>
              <p className="text-xs text-slate-500 max-w-sm mx-auto">
                Click the "New Dubbing Project" button above to upload an English video and start dubbing.
              </p>
            </div>
          ) : (
            <div className="divide-y divide-slate-100 space-y-2">
              {recentProjects.map((proj) => {
                const statusInfo = getStatusInfo(proj.status);
                return (
                  <div
                    key={proj.id}
                    onClick={() => onSelectProject(proj.id)}
                    className="p-3.5 rounded-xl hover:bg-indigo-50/40 border border-transparent hover:border-indigo-100 transition-all cursor-pointer flex flex-col sm:flex-row sm:items-center justify-between gap-3 group"
                  >
                    <div className="space-y-1.5 flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-slate-900 text-sm truncate group-hover:text-indigo-600 transition-colors">
                          {proj.title}
                        </span>
                        <span className={`text-[10px] font-medium px-2 py-0.5 rounded-full border ${statusInfo.color}`}>
                          {statusInfo.label}
                        </span>
                      </div>

                      <div className="flex flex-wrap items-center gap-3 text-xs text-slate-400">
                        <span className="inline-flex items-center gap-1 text-[11px] font-mono text-slate-600 bg-slate-100 px-1.5 py-0.5 rounded">
                          {proj.original_language.toUpperCase()} → {proj.target_language.toUpperCase()}
                        </span>
                        <span>•</span>
                        <span className="flex items-center gap-1 text-[11px]">
                          <Calendar className="w-3 h-3" />
                          {new Date(proj.updated_at || proj.created_at).toLocaleDateString()}
                        </span>
                      </div>

                      {/* Progress Bar */}
                      <div className="w-full max-w-xs bg-slate-100 h-1.5 rounded-full overflow-hidden">
                        <div
                          className="bg-indigo-600 h-full rounded-full transition-all duration-300"
                          style={{ width: `${statusInfo.percent}%` }}
                        />
                      </div>
                    </div>

                    <div className="shrink-0 flex items-center gap-1.5">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectProject(proj.id);
                        }}
                        className="px-3 py-1.5 rounded-lg bg-indigo-50 group-hover:bg-indigo-600 text-indigo-700 group-hover:text-white text-xs font-semibold transition-all flex items-center gap-1.5 shadow-xs"
                      >
                        <Play className="w-3.5 h-3.5" />
                        <span>Continue Studio</span>
                      </button>
                      <ProjectActionMenu
                        onOpenStudio={() => onSelectProject(proj.id)}
                        onRename={() => setRenamingProject(proj)}
                        onDelete={() => setDeletingProject(proj)}
                      />
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* System Capabilities & Model Overview */}
        <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 space-y-4">
          <div className="pb-3 border-b border-slate-100">
            <h3 className="text-sm font-bold text-slate-800">AI Dubbing Engine</h3>
            <p className="text-xs text-slate-500">Active pipeline components</p>
          </div>

          <div className="space-y-3 text-xs">
            {/* STT */}
            <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 space-y-1">
              <div className="flex items-center justify-between font-semibold text-slate-800">
                <span className="flex items-center gap-1.5">
                  <FileAudio className="w-3.5 h-3.5 text-emerald-600" />
                  Speech-to-Text
                </span>
                <span className="text-[10px] bg-emerald-100 text-emerald-800 px-1.5 py-0.5 rounded">Faster-Whisper</span>
              </div>
              <p className="text-slate-500 text-[11px]">
                CTranslate2 INT8 quantized execution with VAD voice activity timestamps.
              </p>
            </div>

            {/* Translation */}
            <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 space-y-1">
              <div className="flex items-center justify-between font-semibold text-slate-800">
                <span className="flex items-center gap-1.5">
                  <Languages className="w-3.5 h-3.5 text-purple-600" />
                  Translation Engine
                </span>
                <span className="text-[10px] bg-purple-100 text-purple-800 px-1.5 py-0.5 rounded">Hybrid AI</span>
              </div>
              <p className="text-slate-500 text-[11px]">
                Meta NLLB-200 (local offline) + Google Gemini / OpenAI / Claude / Custom API with glossary alignment.
              </p>
            </div>

            {/* Voice */}
            <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 space-y-1">
              <div className="flex items-center justify-between font-semibold text-slate-800">
                <span className="flex items-center gap-1.5">
                  <Mic2 className="w-3.5 h-3.5 text-indigo-600" />
                  Khmer Text-to-Speech
                </span>
                <span className="text-[10px] bg-indigo-100 text-indigo-800 px-1.5 py-0.5 rounded">Multi-Voice</span>
              </div>
              <p className="text-slate-500 text-[11px]">
                Google gTTS default + Microsoft Piseth (Male) and Sreymom (Female) neural voices.
              </p>
            </div>

            {/* Video Sync */}
            <div className="p-3 rounded-lg bg-slate-50 border border-slate-200 space-y-1">
              <div className="flex items-center justify-between font-semibold text-slate-800">
                <span className="flex items-center gap-1.5">
                  <Film className="w-3.5 h-3.5 text-rose-600" />
                  Video Synchronization
                </span>
                <span className="text-[10px] bg-rose-100 text-rose-800 px-1.5 py-0.5 rounded">FFmpeg Muxer</span>
              </div>
              <p className="text-slate-500 text-[11px]">
                44.1kHz timeline building, gap silence padding, tempo adjustment & timing conflict safety.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Rename Modal */}
      <RenameProjectModal
        isOpen={!!renamingProject}
        project={renamingProject}
        onClose={() => setRenamingProject(null)}
        onRenamed={() => {
          onRefresh?.();
        }}
      />

      {/* Delete Modal */}
      <DeleteProjectModal
        isOpen={!!deletingProject}
        project={deletingProject}
        onClose={() => setDeletingProject(null)}
        onDeleted={() => {
          onRefresh?.();
        }}
      />
    </div>
  );
};
