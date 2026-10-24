import React, { useState, useEffect, useCallback } from 'react';
import { Sidebar } from './components/layout/Sidebar';
import { Header } from './components/layout/Header';
import { Dashboard } from './pages/Dashboard';
import { Projects } from './pages/Projects';
import { Settings } from './pages/Settings';
import { api } from './services/api';
import { HealthResponse, ProjectSummary } from './types';

export const App: React.FC = () => {
  const [currentTab, setCurrentTab] = useState<string>('dashboard');
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [healthLoading, setHealthLoading] = useState<boolean>(true);
  const [projectsLoading, setProjectsLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

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

    // Auto-refresh health every 30 seconds
    const interval = setInterval(fetchHealth, 30000);
    return () => clearInterval(interval);
  }, [fetchHealth, fetchProjects]);

  const handleCreateProject = async (title: string) => {
    await api.createProject(title);
    await fetchProjects();
  };

  return (
    <div className="flex h-screen bg-slate-100 text-slate-800 font-sans overflow-hidden">
      {/* Sidebar */}
      <Sidebar currentTab={currentTab} onTabChange={setCurrentTab} />

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
        <main className="flex-1 overflow-y-auto p-8">
          {currentTab === 'dashboard' && (
            <Dashboard
              health={health}
              projects={projects}
              onCreateProject={handleCreateProject}
              onNavigateProjects={() => setCurrentTab('projects')}
            />
          )}

          {currentTab === 'projects' && (
            <Projects
              projects={projects}
              loading={projectsLoading}
              onCreateProject={handleCreateProject}
              onRefresh={fetchProjects}
            />
          )}

          {currentTab === 'settings' && <Settings health={health} />}
        </main>
      </div>
    </div>
  );
};

export default App;
