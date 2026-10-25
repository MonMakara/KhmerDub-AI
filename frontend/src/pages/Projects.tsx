import React, { useState, useMemo } from 'react';
import {
  FolderKanban,
  Plus,
  Clock,
  Globe2,
  RefreshCw,
  Search,
  ArrowUpDown,
  Play,
  LayoutGrid,
  List as ListIcon,
} from 'lucide-react';
import { ProjectSummary, ProjectStatus } from '../types';

interface ProjectsProps {
  projects: ProjectSummary[];
  loading: boolean;
  onCreateProject: (title: string) => Promise<string | void>;
  onRefresh: () => void;
  onSelectProject: (projectId: string) => void;
}

type FilterStatus = 'all' | 'in_progress' | 'completed' | 'attention';
type SortOption = 'newest' | 'oldest' | 'title';

export const Projects: React.FC<ProjectsProps> = ({
  projects,
  loading,
  onCreateProject,
  onRefresh,
  onSelectProject,
}) => {
  const [newTitle, setNewTitle] = useState('');
  const [creating, setCreating] = useState(false);
  const [searchQuery, setSearchQuery] = useState('');
  const [filterStatus, setFilterStatus] = useState<FilterStatus>('all');
  const [sortBy, setSortBy] = useState<SortOption>('newest');
  const [viewMode, setViewMode] = useState<'grid' | 'table'>('grid');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    try {
      setCreating(true);
      const newId = await onCreateProject(newTitle.trim());
      setNewTitle('');
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
        return { label: 'Completed', color: 'bg-emerald-50 text-emerald-700 border-emerald-200', percent: 100, isProgress: false };
      case 'synchronizing':
        return { label: 'Exporting Video', color: 'bg-cyan-50 text-cyan-700 border-cyan-200 animate-pulse', percent: 90, isProgress: true };
      case 'voice_generated':
        return { label: 'Speech Ready', color: 'bg-indigo-50 text-indigo-700 border-indigo-200', percent: 80, isProgress: false };
      case 'generating_voice':
        return { label: 'Generating Speech', color: 'bg-indigo-50 text-indigo-700 border-indigo-200 animate-pulse', percent: 70, isProgress: true };
      case 'translated':
        return { label: 'Translated', color: 'bg-purple-50 text-purple-700 border-purple-200', percent: 60, isProgress: false };
      case 'translating':
        return { label: 'Translating', color: 'bg-purple-50 text-purple-700 border-purple-200 animate-pulse', percent: 50, isProgress: true };
      case 'transcribed':
        return { label: 'Transcribed', color: 'bg-amber-50 text-amber-700 border-amber-200', percent: 40, isProgress: false };
      case 'transcribing':
        return { label: 'Transcribing', color: 'bg-amber-50 text-amber-700 border-amber-200 animate-pulse', percent: 30, isProgress: true };
      case 'audio_extracted':
      case 'uploaded':
        return { label: 'Media Uploaded', color: 'bg-blue-50 text-blue-700 border-blue-200', percent: 20, isProgress: false };
      case 'failed':
        return { label: 'Failed', color: 'bg-rose-50 text-rose-700 border-rose-200', percent: 0, isProgress: false };
      case 'created':
      default:
        return { label: 'Draft', color: 'bg-slate-100 text-slate-700 border-slate-200', percent: 10, isProgress: false };
    }
  };

  // Filter & Search & Sort pipeline
  const filteredProjects = useMemo(() => {
    let result = [...projects];

    // Search query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      result = result.filter(
        (p) =>
          p.title.toLowerCase().includes(q) ||
          p.original_language.toLowerCase().includes(q) ||
          p.target_language.toLowerCase().includes(q) ||
          p.status.toLowerCase().includes(q)
      );
    }

    // Status filter
    if (filterStatus === 'completed') {
      result = result.filter((p) => p.status === 'completed');
    } else if (filterStatus === 'in_progress') {
      result = result.filter((p) =>
        ['uploaded', 'audio_extracted', 'transcribing', 'transcribed', 'translating', 'translated', 'generating_voice', 'voice_generated', 'synchronizing'].includes(p.status)
      );
    } else if (filterStatus === 'attention') {
      result = result.filter((p) => p.status === 'failed' || p.status === 'created');
    }

    // Sort
    result.sort((a, b) => {
      if (sortBy === 'newest') {
        return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
      } else if (sortBy === 'oldest') {
        return new Date(a.created_at).getTime() - new Date(b.created_at).getTime();
      } else if (sortBy === 'title') {
        return a.title.localeCompare(b.title);
      }
      return 0;
    });

    return result;
  }, [projects, searchQuery, filterStatus, sortBy]);

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Header and Fast Create Bar */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 bg-white p-6 rounded-2xl border border-slate-200 shadow-sm">
        <div>
          <h2 className="text-xl font-bold text-slate-900">Dubbing Projects</h2>
          <p className="text-xs text-slate-500 mt-1">
            English-to-Khmer automated localization workspace ({projects.length} total)
          </p>
        </div>

        <form onSubmit={handleSubmit} className="flex items-center gap-2">
          <input
            type="text"
            value={newTitle}
            onChange={(e) => setNewTitle(e.target.value)}
            placeholder="New project title..."
            className="w-full sm:w-72 text-xs sm:text-sm px-3.5 py-2 rounded-xl border border-slate-300 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
            disabled={creating}
          />
          <button
            type="submit"
            disabled={creating || !newTitle.trim()}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs sm:text-sm font-semibold transition-all shadow-sm shrink-0"
          >
            <Plus className="w-4 h-4" />
            {creating ? 'Creating...' : 'Create Project'}
          </button>
        </form>
      </div>

      {/* Filter and Search Bar */}
      <div className="bg-white p-4 rounded-xl border border-slate-200 shadow-sm flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3">
        {/* Search */}
        <div className="relative flex-1 max-w-md">
          <Search className="w-4 h-4 text-slate-400 absolute left-3 top-2.5" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            placeholder="Search projects by title or status..."
            className="w-full pl-9 pr-4 py-2 text-xs sm:text-sm rounded-lg border border-slate-200 bg-slate-50 focus:bg-white focus:outline-none focus:ring-2 focus:ring-indigo-500"
          />
        </div>

        {/* Filter Pills */}
        <div className="flex flex-wrap items-center gap-1.5">
          {[
            { id: 'all', label: 'All Projects', count: projects.length },
            { id: 'in_progress', label: 'In Progress', count: projects.filter((p) => p.status !== 'completed' && p.status !== 'failed' && p.status !== 'created').length },
            { id: 'completed', label: 'Completed', count: projects.filter((p) => p.status === 'completed').length },
            { id: 'attention', label: 'Needs Attention', count: projects.filter((p) => p.status === 'failed' || p.status === 'created').length },
          ].map((tab) => (
            <button
              key={tab.id}
              onClick={() => setFilterStatus(tab.id as FilterStatus)}
              className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-all ${
                filterStatus === tab.id
                  ? 'bg-indigo-600 text-white shadow-sm'
                  : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
              }`}
            >
              {tab.label} <span className="opacity-75">({tab.count})</span>
            </button>
          ))}
        </div>

        {/* Controls: Sorting and Grid/Table Switcher */}
        <div className="flex items-center gap-2 shrink-0">
          <div className="flex items-center gap-1 bg-slate-100 px-2 py-1 rounded-lg text-xs">
            <ArrowUpDown className="w-3.5 h-3.5 text-slate-400" />
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as SortOption)}
              className="bg-transparent text-xs text-slate-700 font-medium focus:outline-none cursor-pointer"
            >
              <option value="newest">Newest First</option>
              <option value="oldest">Oldest First</option>
              <option value="title">Title (A-Z)</option>
            </select>
          </div>

          <div className="flex items-center border border-slate-200 rounded-lg p-0.5 bg-slate-50">
            <button
              onClick={() => setViewMode('grid')}
              className={`p-1.5 rounded ${viewMode === 'grid' ? 'bg-white text-indigo-600 shadow-xs' : 'text-slate-400 hover:text-slate-700'}`}
              title="Grid View"
            >
              <LayoutGrid className="w-4 h-4" />
            </button>
            <button
              onClick={() => setViewMode('table')}
              className={`p-1.5 rounded ${viewMode === 'table' ? 'bg-white text-indigo-600 shadow-xs' : 'text-slate-400 hover:text-slate-700'}`}
              title="Table View"
            >
              <ListIcon className="w-4 h-4" />
            </button>
          </div>

          <button
            onClick={onRefresh}
            disabled={loading}
            className="p-2 rounded-lg border border-slate-200 text-slate-500 hover:text-slate-800 hover:bg-slate-100 transition-colors"
            title="Refresh projects"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Projects Display: Grid or Table */}
      {loading ? (
        <div className="p-16 text-center bg-white rounded-2xl border border-slate-200 shadow-sm space-y-3">
          <RefreshCw className="w-8 h-8 text-indigo-600 animate-spin mx-auto" />
          <p className="text-sm font-semibold text-slate-700">Loading projects...</p>
        </div>
      ) : filteredProjects.length === 0 ? (
        <div className="p-16 text-center bg-white rounded-2xl border border-slate-200 shadow-sm space-y-3">
          <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center mx-auto text-slate-400">
            <FolderKanban className="w-6 h-6" />
          </div>
          <h3 className="text-base font-bold text-slate-800">
            {searchQuery ? 'No matching projects found' : 'No projects in this category'}
          </h3>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            {searchQuery
              ? `No projects matched "${searchQuery}". Clear your search or create a new one.`
              : 'Create a project to begin uploading and dubbing video files.'}
          </p>
          {searchQuery && (
            <button
              onClick={() => setSearchQuery('')}
              className="px-3.5 py-1.5 text-xs text-indigo-600 font-semibold hover:underline"
            >
              Clear Search
            </button>
          )}
        </div>
      ) : viewMode === 'grid' ? (
        /* Card Grid View */
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {filteredProjects.map((proj) => {
            const statusInfo = getStatusInfo(proj.status);
            return (
              <div
                key={proj.id}
                onClick={() => onSelectProject(proj.id)}
                className="bg-white rounded-2xl border border-slate-200 hover:border-indigo-300 hover:shadow-md transition-all p-5 flex flex-col justify-between space-y-4 cursor-pointer group"
              >
                {/* Top Section */}
                <div className="space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <span className="font-bold text-slate-900 text-sm group-hover:text-indigo-600 transition-colors line-clamp-1">
                      {proj.title}
                    </span>
                    <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border shrink-0 ${statusInfo.color}`}>
                      {statusInfo.label}
                    </span>
                  </div>

                  <div className="flex items-center gap-2 text-xs text-slate-500">
                    <span className="inline-flex items-center gap-1 font-mono text-[11px] bg-slate-100 text-slate-700 px-2 py-0.5 rounded">
                      <Globe2 className="w-3 h-3 text-slate-400" />
                      {proj.original_language.toUpperCase()} → {proj.target_language.toUpperCase()}
                    </span>
                    <span>•</span>
                    <span className="text-[11px] text-slate-400 flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      {new Date(proj.created_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>

                {/* Progress & Bottom Actions */}
                <div className="space-y-3 pt-3 border-t border-slate-100">
                  <div className="space-y-1">
                    <div className="flex justify-between text-[11px] text-slate-500">
                      <span>Dubbing Progress</span>
                      <span className="font-semibold text-slate-700">{statusInfo.percent}%</span>
                    </div>
                    <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden">
                      <div
                        className="bg-indigo-600 h-full rounded-full transition-all duration-300"
                        style={{ width: `${statusInfo.percent}%` }}
                      />
                    </div>
                  </div>

                  <div className="flex items-center justify-between pt-1">
                    <span className="text-[11px] text-slate-400 capitalize">
                      {proj.translation_provider || 'nllb'} • {proj.tts_provider || 'gtts'}
                    </span>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelectProject(proj.id);
                      }}
                      className="px-3 py-1.5 rounded-lg bg-indigo-50 group-hover:bg-indigo-600 text-indigo-700 group-hover:text-white text-xs font-semibold transition-all flex items-center gap-1 shadow-xs"
                    >
                      <Play className="w-3 h-3" />
                      <span>Continue</span>
                    </button>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* Table View */
        <div className="bg-white rounded-2xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider border-b border-slate-200">
                <tr>
                  <th className="px-6 py-3.5 font-semibold">Project Title</th>
                  <th className="px-6 py-3.5 font-semibold">Languages</th>
                  <th className="px-6 py-3.5 font-semibold">Status</th>
                  <th className="px-6 py-3.5 font-semibold">Progress</th>
                  <th className="px-6 py-3.5 font-semibold">Created</th>
                  <th className="px-6 py-3.5 font-semibold text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {filteredProjects.map((proj) => {
                  const statusInfo = getStatusInfo(proj.status);
                  return (
                    <tr
                      key={proj.id}
                      onClick={() => onSelectProject(proj.id)}
                      className="hover:bg-indigo-50/40 cursor-pointer transition-colors"
                    >
                      <td className="px-6 py-4 font-semibold text-slate-900 flex items-center gap-2.5">
                        <FolderKanban className="w-4 h-4 text-indigo-500 shrink-0" />
                        <span className="hover:text-indigo-600">{proj.title}</span>
                      </td>
                      <td className="px-6 py-4">
                        <span className="inline-flex items-center gap-1.5 text-xs text-slate-700 bg-slate-100 px-2 py-1 rounded font-mono">
                          <Globe2 className="w-3.5 h-3.5 text-slate-400" />
                          {proj.original_language.toUpperCase()} → {proj.target_language.toUpperCase()}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${statusInfo.color}`}>
                          {statusInfo.label}
                        </span>
                      </td>
                      <td className="px-6 py-4">
                        <div className="w-32 space-y-1">
                          <div className="flex justify-between text-[10px] text-slate-500">
                            <span>{statusInfo.percent}%</span>
                          </div>
                          <div className="w-full bg-slate-100 h-1.5 rounded-full overflow-hidden">
                            <div
                              className="bg-indigo-600 h-full rounded-full"
                              style={{ width: `${statusInfo.percent}%` }}
                            />
                          </div>
                        </div>
                      </td>
                      <td className="px-6 py-4 text-xs text-slate-500">
                        {new Date(proj.created_at).toLocaleDateString()}
                      </td>
                      <td className="px-6 py-4 text-right">
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            onSelectProject(proj.id);
                          }}
                          className="px-3.5 py-1.5 bg-indigo-50 hover:bg-indigo-600 text-indigo-700 hover:text-white rounded-lg text-xs font-semibold transition-all inline-flex items-center gap-1"
                        >
                          <Play className="w-3 h-3" />
                          <span>Open Studio</span>
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
};
