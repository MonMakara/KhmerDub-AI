import React, { useState } from 'react';
import { FolderKanban, Plus, Clock, Globe2, RefreshCw } from 'lucide-react';
import { ProjectSummary } from '../types';

interface ProjectsProps {
  projects: ProjectSummary[];
  loading: boolean;
  onCreateProject: (title: string) => Promise<string | void>;
  onRefresh: () => void;
  onSelectProject: (projectId: string) => void;
}

export const Projects: React.FC<ProjectsProps> = ({
  projects,
  loading,
  onCreateProject,
  onRefresh,
  onSelectProject,
}) => {
  const [newTitle, setNewTitle] = useState('');
  const [creating, setCreating] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newTitle.trim()) return;
    try {
      setCreating(true);
      await onCreateProject(newTitle.trim());
      setNewTitle('');
    } catch (err: any) {
      alert(`Error creating project: ${err.message}`);
    } finally {
      setCreating(false);
    }
  };

  const getStatusBadge = (status: string) => {
    const styles: Record<string, string> = {
      created: 'bg-slate-100 text-slate-700 border-slate-200',
      uploaded: 'bg-blue-100 text-blue-700 border-blue-200',
      transcribing: 'bg-amber-100 text-amber-700 border-amber-200 animate-pulse',
      transcribed: 'bg-emerald-100 text-emerald-700 border-emerald-200',
      translating: 'bg-purple-100 text-purple-700 border-purple-200 animate-pulse',
      translated: 'bg-purple-100 text-purple-700 border-purple-200',
      generating_voice: 'bg-indigo-100 text-indigo-700 border-indigo-200 animate-pulse',
      voice_generated: 'bg-indigo-100 text-indigo-700 border-indigo-200',
      synchronizing: 'bg-cyan-100 text-cyan-700 border-cyan-200 animate-pulse',
      completed: 'bg-green-100 text-green-800 border-green-200',
      failed: 'bg-rose-100 text-rose-700 border-rose-200',
    };
    return (
      <span
        className={`px-2.5 py-0.5 rounded-full text-xs font-medium border uppercase tracking-wider ${
          styles[status] || 'bg-slate-100 text-slate-700 border-slate-200'
        }`}
      >
        {status.replace('_', ' ')}
      </span>
    );
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Page Title & Actions */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-slate-900">Dubbing Projects</h2>
          <p className="text-xs text-slate-500 mt-1">
            Manage your English-to-Khmer video dubbing projects
          </p>
        </div>

        <div className="flex items-center gap-2">
          <button
            onClick={onRefresh}
            disabled={loading}
            className="p-2 rounded-lg border border-slate-300 text-slate-600 hover:bg-slate-100 transition-colors"
            title="Refresh projects"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <form onSubmit={handleSubmit} className="flex items-center gap-2">
            <input
              type="text"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="New Project Title..."
              className="px-3.5 py-2 rounded-lg border border-slate-300 text-xs sm:text-sm focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
              disabled={creating}
            />
            <button
              type="submit"
              disabled={creating || !newTitle.trim()}
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs sm:text-sm font-medium transition-colors shadow-sm"
            >
              <Plus className="w-4 h-4" />
              {creating ? 'Creating...' : 'New Project'}
            </button>
          </form>
        </div>
      </div>

      {/* Projects Table / List */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-slate-500 text-sm">Loading projects...</div>
        ) : projects.length === 0 ? (
          <div className="p-12 text-center">
            <div className="w-12 h-12 rounded-full bg-slate-100 flex items-center justify-center mx-auto text-slate-400 mb-3">
              <FolderKanban className="w-6 h-6" />
            </div>
            <h3 className="text-sm font-semibold text-slate-800">No projects yet</h3>
            <p className="text-xs text-slate-500 mt-1 max-w-sm mx-auto">
              Create your first project above to test database connectivity and prepare for Phase 2 video uploads.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm text-slate-600">
              <thead className="bg-slate-50 text-slate-500 text-xs uppercase tracking-wider border-b border-slate-200">
                <tr>
                  <th className="px-6 py-3 font-semibold">Title</th>
                  <th className="px-6 py-3 font-semibold">Languages</th>
                  <th className="px-6 py-3 font-semibold">Status</th>
                  <th className="px-6 py-3 font-semibold">Created</th>
                  <th className="px-6 py-3 font-semibold text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {projects.map((proj) => (
                  <tr
                    key={proj.id}
                    onClick={() => onSelectProject(proj.id)}
                    className="hover:bg-indigo-50/40 cursor-pointer transition-colors"
                  >
                    <td className="px-6 py-4 font-medium text-slate-900 flex items-center gap-2">
                      <FolderKanban className="w-4 h-4 text-indigo-500 shrink-0" />
                      <span>{proj.title}</span>
                    </td>
                    <td className="px-6 py-4">
                      <span className="inline-flex items-center gap-1.5 text-xs text-slate-700 bg-slate-100 px-2 py-1 rounded">
                        <Globe2 className="w-3.5 h-3.5 text-slate-400" />
                        {proj.original_language.toUpperCase()} → {proj.target_language.toUpperCase()}
                      </span>
                    </td>
                    <td className="px-6 py-4">{getStatusBadge(proj.status)}</td>
                    <td className="px-6 py-4 text-xs text-slate-500">
                      <span className="flex items-center gap-1">
                        <Clock className="w-3.5 h-3.5 text-slate-400" />
                        {new Date(proj.created_at).toLocaleString()}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectProject(proj.id);
                        }}
                        className="px-3 py-1 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 rounded text-xs font-semibold transition-colors"
                      >
                        Open Workspace
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
