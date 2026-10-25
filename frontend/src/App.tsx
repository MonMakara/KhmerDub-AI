import React, { useState, useEffect, useCallback } from 'react';
import { Sidebar } from './components/layout/Sidebar';
import { Header } from './components/layout/Header';
import { Dashboard } from './pages/Dashboard';
import { Projects } from './pages/Projects';
import { Settings } from './pages/Settings';
import { ProjectWorkspace } from './pages/ProjectWorkspace';
import { api } from './services/api';
import { HealthResponse, ProjectSummary } from './types';

export const App: React.FC = () => {
  const parseHash = () => {
    const hash = window.location.hash.replace(/^#\/?/, '');
    if (hash.startsWith('project/')) {
      const pid = hash.replace('project/', '').trim();
      return { tab: 'projects', projectId: pid || null };
    }
    if (hash === 'projects' || hash === 'settings' || hash === 'dashboard') {
      return { tab: hash, projectId: null };
    }
    return { tab: 'dashboard', projectId: null };
  };

  const initial = parseHash();
  const [currentTab, setCurrentTab] = useState<string>(initial.tab);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(initial.projectId);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [healthLoading, setHealthLoading] = useState<boolean>(true);
  const [projectsLoading, setProjectsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  // Sync state on hash change (back/forward button or manual URL navigation)
  useEffect(() => {
    const onHashChange = () => {
      const { tab, projectId } = parseHash();
      setCurrentTab(tab);
      setSelectedProjectId(projectId);
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, []);

  const fetchHealth = useCallback(async () => {
    try {
      setHealthLoading(true);
      setError(null);
      const data = await api.getHealth();
      setHealth(data);
    } catch (err: any) {
      console.error('Failed to fetch health check:', err);
      setHealth(null);
      setError('Cannot reach backend server. Please verify Docker backend container is running.');
    } finally {
      setHealthLoading(false);
    }
  }, []);

  const fetchProjects = useCallback(async () => {
    try {
      setProjectsLoading(true);
      const data = await api.listProjects();
      setProjects(data);
    } catch (err: any) {
      console.error('Failed to list projects:', err);
    } finally {
      setProjectsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchHealth();
    fetchProjects();

    const interval = setInterval(fetchHealth, 30000);
    return () => clearInterval(interval);
  }, [fetchHealth, fetchProjects]);

  const handleCreateProject = async (title: string): Promise<string> => {
    const created = await api.createProject(title);
    await fetchProjects();
    handleSelectProject(created.id);
    return created.id;
  };

  const handleTabChange = (tab: string) => {
    setCurrentTab(tab);
    setSelectedProjectId(null);
    window.location.hash = tab;
  };

  const handleSelectProject = (projectId: string) => {
    setSelectedProjectId(projectId);
    setCurrentTab('projects');
    window.location.hash = `project/${projectId}`;
  };

  return (
    <div className="flex h-screen bg-slate-100 text-slate-800 font-sans overflow-hidden">
      {/* Sidebar */}
      <Sidebar currentTab={currentTab} onTabChange={handleTabChange} />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Header */}
        <Header
          health={health}
          loading={healthLoading}
          onRefreshHealth={fetchHealth}
        />

        {/* Global Error Banner if backend unreachable */}
        {error && (
          <div className="bg-rose-50 border-b border-rose-200 px-8 py-2.5 text-xs text-rose-700 flex items-center justify-between">
            <span>{error}</span>
            <button
              onClick={fetchHealth}
              className="font-semibold underline hover:text-rose-900 ml-4"
            >
              Retry
            </button>
          </div>
        )}

        {/* Scrollable Page Body */}
        <main className="flex-1 overflow-y-auto p-4 sm:p-6 md:p-8">
          {currentTab === 'dashboard' && (
            <Dashboard
              health={health}
              projects={projects}
              onCreateProject={handleCreateProject}
              onNavigateProjects={() => handleTabChange('projects')}
              onSelectProject={handleSelectProject}
            />
          )}

          {currentTab === 'projects' && !selectedProjectId && (
            <Projects
              projects={projects}
              loading={projectsLoading}
              onCreateProject={handleCreateProject}
              onRefresh={fetchProjects}
              onSelectProject={handleSelectProject}
            />
          )}

          {currentTab === 'projects' && selectedProjectId && (
            <ProjectWorkspace
              projectId={selectedProjectId}
              onBack={() => {
                setSelectedProjectId(null);
                window.location.hash = 'projects';
              }}
              onProjectUpdated={fetchProjects}
            />
          )}

          {currentTab === 'settings' && <Settings health={health} />}
        </main>
      </div>
    </div>
  );
};

export default App;
