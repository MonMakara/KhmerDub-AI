import React, { useState, useEffect, useCallback } from 'react';
import { Sidebar } from './components/layout/Sidebar';
import { Header } from './components/layout/Header';
import { Dashboard } from './pages/Dashboard';
import { Projects } from './pages/Projects';
import { Settings } from './pages/Settings';
import { VoiceStudio } from './pages/VoiceStudio';
import { MediaToolkit } from './pages/MediaToolkit';
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
    if (hash.startsWith('toolkit')) {
      return { tab: 'toolkit', projectId: null };
    }
    if (hash === 'projects' || hash === 'settings' || hash === 'dashboard' || hash === 'voices') {
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

  // Responsive Sidebar States:
  // Desktop collapsed preference (persisted to localStorage)
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState<boolean>(() => {
    try {
      const saved = localStorage.getItem('khmerdub_sidebar_collapsed');
      if (saved !== null) {
        return saved === 'true';
      }
      // If tablet width (768px - 1023px), default to compact collapsed state
      if (typeof window !== 'undefined' && window.innerWidth >= 768 && window.innerWidth < 1024) {
        return true;
      }
      return false;
    } catch {
      return false;
    }
  });

  // Mobile Drawer state
  const [isMobileSidebarOpen, setIsMobileSidebarOpen] = useState<boolean>(false);

  const toggleSidebarCollapse = useCallback(() => {
    setIsSidebarCollapsed((prev) => {
      const next = !prev;
      try {
        localStorage.setItem('khmerdub_sidebar_collapsed', String(next));
      } catch (e) {
        console.error('Failed to save sidebar collapsed state:', e);
      }
      return next;
    });
  }, []);

  // Auto-close mobile drawer when window resizes to desktop breakpoint (>= 768px)
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth >= 768) {
        setIsMobileSidebarOpen(false);
      }
    };
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
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

  // Sync state on hash change (back/forward button or manual URL navigation)
  useEffect(() => {
    const onHashChange = () => {
      const { tab, projectId } = parseHash();
      setCurrentTab(tab);
      setSelectedProjectId(projectId);
      setIsMobileSidebarOpen(false);
      if (!projectId) {
        fetchProjects();
      }
    };
    window.addEventListener('hashchange', onHashChange);
    return () => window.removeEventListener('hashchange', onHashChange);
  }, [fetchProjects]);

  useEffect(() => {
    fetchHealth();
    fetchProjects();

    const interval = setInterval(fetchHealth, 30000);
    return () => clearInterval(interval);
  }, [fetchHealth, fetchProjects]);

  // Auto-poll projects when any project is actively processing in background
  useEffect(() => {
    const hasActiveProjects = projects.some((p) =>
      ['uploaded', 'audio_extracted', 'transcribing', 'translating', 'generating_voice', 'synchronizing'].includes(
        p.status
      )
    );
    if (!hasActiveProjects) return;

    const interval = setInterval(() => {
      fetchProjects();
    }, 3000);

    return () => clearInterval(interval);
  }, [projects, fetchProjects]);

  const handleCreateProject = async (title: string): Promise<string> => {
    const created = await api.createProject(title);
    await fetchProjects();
    handleSelectProject(created.id);
    return created.id;
  };

  const handleTabChange = (tab: string) => {
    setCurrentTab(tab);
    setSelectedProjectId(null);
    setIsMobileSidebarOpen(false);
    window.location.hash = tab;
    fetchProjects();
  };

  const handleSelectProject = (projectId: string) => {
    setSelectedProjectId(projectId);
    setCurrentTab('projects');
    setIsMobileSidebarOpen(false);
    window.location.hash = `project/${projectId}`;
  };

  return (
    <div className="flex h-screen bg-slate-100 text-slate-800 font-sans overflow-hidden">
      {/* Sidebar: Supports Desktop Collapsed/Expanded & Mobile Drawer */}
      <Sidebar
        currentTab={currentTab}
        onTabChange={handleTabChange}
        isCollapsed={isSidebarCollapsed}
        onToggleCollapse={toggleSidebarCollapse}
        isMobileOpen={isMobileSidebarOpen}
        onCloseMobile={() => setIsMobileSidebarOpen(false)}
      />

      {/* Main Content Area: Resizes automatically when sidebar expands/collapses */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Responsive Header with Hamburger Menu for Mobile */}
        <Header
          health={health}
          loading={healthLoading}
          onRefreshHealth={fetchHealth}
          onToggleMobileSidebar={() => setIsMobileSidebarOpen((prev) => !prev)}
          isMobileSidebarOpen={isMobileSidebarOpen}
        />

        {/* Global Error Banner if backend unreachable */}
        {error && (
          <div className="bg-rose-50 border-b border-rose-200 px-4 sm:px-8 py-2.5 text-xs text-rose-700 flex flex-wrap sm:flex-nowrap items-center justify-between gap-2">
            <span>{error}</span>
            <button
              onClick={fetchHealth}
              className="font-semibold underline hover:text-rose-900 ml-4 shrink-0"
            >
              Retry
            </button>
          </div>
        )}

        {/* Scrollable Page Body */}
        <main id="main-scroll-container" className="flex-1 overflow-y-auto p-3.5 sm:p-6 md:p-8">
          {currentTab === 'dashboard' && (
            <Dashboard
              health={health}
              projects={projects}
              onCreateProject={handleCreateProject}
              onNavigateProjects={() => handleTabChange('projects')}
              onSelectProject={handleSelectProject}
              onRefresh={fetchProjects}
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
                fetchProjects();
              }}
              onProjectUpdated={fetchProjects}
            />
          )}

          {currentTab === 'toolkit' && <MediaToolkit projects={projects} />}

          {currentTab === 'voices' && <VoiceStudio />}

          {currentTab === 'settings' && <Settings health={health} />}
        </main>
      </div>
    </div>
  );
};

export default App;
