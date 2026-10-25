import React from 'react';
import {
  ArrowLeft,
  Film,
  FileText,
  Languages,
  Mic2,
  Download,
  RefreshCw,
  CheckCircle2,
  AlertTriangle,
  Globe2,
  Edit3,
} from 'lucide-react';
import { ProjectDetail } from '../../types';

export type StudioTab = 'media' | 'transcript' | 'translation' | 'voice' | 'export';

interface StudioHeaderProps {
  project: ProjectDetail;
  activeTab: StudioTab;
  onTabChange: (tab: StudioTab) => void;
  onBack: () => void;
  onRefresh: () => void;
  refreshing: boolean;
  hasMedia: boolean;
  hasTranscript: boolean;
  hasTranslation: boolean;
  hasVoice: boolean;
  hasExport: boolean;
  isExtracting: boolean;
  isTranscribing: boolean;
  isTranslating: boolean;
  isGeneratingVoice: boolean;
  isExporting: boolean;
  timingConflictsCount: number;
  onRename?: () => void;
}

export const StudioHeader: React.FC<StudioHeaderProps> = ({
  project,
  activeTab,
  onTabChange,
  onBack,
  onRefresh,
  refreshing,
  hasMedia,
  hasTranscript,
  hasTranslation,
  hasVoice,
  hasExport,
  isExtracting,
  isTranscribing,
  isTranslating,
  isGeneratingVoice,
  isExporting,
  timingConflictsCount,
  onRename,
}) => {
  const steps: {
    id: StudioTab;
    num: number;
    label: string;
    icon: React.ElementType;
    isComplete: boolean;
    isRunning: boolean;
    hasWarning?: boolean;
  }[] = [
    {
      id: 'media',
      num: 1,
      label: 'Media',
      icon: Film,
      isComplete: hasMedia,
      isRunning: isExtracting,
    },
    {
      id: 'transcript',
      num: 2,
      label: 'Transcript',
      icon: FileText,
      isComplete: hasTranscript,
      isRunning: isTranscribing,
    },
    {
      id: 'translation',
      num: 3,
      label: 'Translation',
      icon: Languages,
      isComplete: hasTranslation,
      isRunning: isTranslating,
      hasWarning: timingConflictsCount > 0,
    },
    {
      id: 'voice',
      num: 4,
      label: 'Voice',
      icon: Mic2,
      isComplete: hasVoice,
      isRunning: isGeneratingVoice,
    },
    {
      id: 'export',
      num: 5,
      label: 'Export',
      icon: Download,
      isComplete: hasExport,
      isRunning: isExporting,
    },
  ];

  return (
    <div className="bg-white border-b border-slate-200 px-6 py-4 space-y-4">
      {/* Top Row: Back button, Title, Language Pair, Refresh */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <button
            onClick={onBack}
            className="p-2 rounded-xl text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition-colors shrink-0"
            title="Back to Projects"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-bold text-slate-900 truncate">{project.title}</h2>
              {onRename && (
                <button
                  type="button"
                  onClick={onRename}
                  className="p-1 rounded-md text-slate-400 hover:text-indigo-600 hover:bg-slate-100 transition-colors"
                  title="Rename Project"
                  aria-label="Rename Project"
                >
                  <Edit3 className="w-3.5 h-3.5" />
                </button>
              )}
              <span className="inline-flex items-center gap-1 text-[11px] font-mono text-slate-600 bg-slate-100 px-2 py-0.5 rounded-md border border-slate-200 shrink-0">
                <Globe2 className="w-3 h-3 text-indigo-500" />
                {project.original_language.toUpperCase()} → {project.target_language.toUpperCase()}
              </span>
            </div>
            <div className="flex items-center gap-2 text-xs text-slate-400 mt-0.5">
              <span>Studio Workspace</span>
              <span>•</span>
              <span className="capitalize text-slate-600 font-medium">{project.status.replace('_', ' ')}</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          {timingConflictsCount > 0 && (
            <div className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-amber-50 text-amber-800 border border-amber-200 text-xs font-semibold">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
              <span>{timingConflictsCount} Timing Conflict{timingConflictsCount > 1 ? 's' : ''}</span>
            </div>
          )}

          <button
            onClick={onRefresh}
            disabled={refreshing}
            className="p-2 rounded-xl border border-slate-200 text-slate-600 hover:text-slate-900 hover:bg-slate-50 transition-colors flex items-center gap-1.5 text-xs font-medium"
            title="Refresh Studio State"
          >
            <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin text-indigo-600' : ''}`} />
            <span className="hidden sm:inline">Sync</span>
          </button>
        </div>
      </div>

      {/* Stepper Navigation Tabs */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1 no-scrollbar">
        {steps.map((step) => {
          const Icon = step.icon;
          const isActive = activeTab === step.id;

          return (
            <button
              key={step.id}
              onClick={() => onTabChange(step.id)}
              className={`flex items-center gap-2.5 px-4 py-2 rounded-xl text-xs font-semibold transition-all shrink-0 border ${
                isActive
                  ? 'bg-indigo-600 text-white border-indigo-600 shadow-sm shadow-indigo-600/20'
                  : 'bg-slate-50 hover:bg-slate-100 text-slate-700 border-slate-200'
              }`}
            >
              <div className="flex items-center justify-center">
                {step.isRunning ? (
                  <RefreshCw className={`w-3.5 h-3.5 animate-spin ${isActive ? 'text-white' : 'text-indigo-600'}`} />
                ) : step.isComplete ? (
                  <CheckCircle2 className={`w-3.5 h-3.5 ${isActive ? 'text-white' : 'text-emerald-600'}`} />
                ) : (
                  <Icon className={`w-3.5 h-3.5 ${isActive ? 'text-white' : 'text-slate-400'}`} />
                )}
              </div>
              <span>
                {step.num}. {step.label}
              </span>
              {step.hasWarning && (
                <span className={`w-2 h-2 rounded-full ${isActive ? 'bg-amber-300' : 'bg-amber-500'}`} />
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
};
