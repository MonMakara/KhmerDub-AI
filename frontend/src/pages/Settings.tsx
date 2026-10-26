import React, { useState, useEffect } from 'react';
import {
  Cpu,
  HardDrive,
  Terminal,
  Languages,
  Key,
  CheckCircle2,
  AlertCircle,
  Eye,
  EyeOff,
  RefreshCw,
  Trash2,
  ShieldCheck,
  Server,
  Zap,
  Mic2,
  Layers,
  FileCode,
  Activity,
  Copy,
  Check,
  Search,
  ExternalLink,
} from 'lucide-react';
import { HealthResponse, TranslationProviderInfo } from '../types';
import { api } from '../services/api';

interface SettingsProps {
  health: HealthResponse | null;
}

interface ProviderPreset {
  name: string;
  baseUrl: string;
  defaultModel: string;
}

const CUSTOM_PRESETS: ProviderPreset[] = [
  {
    name: 'DeepSeek',
    baseUrl: 'https://api.deepseek.com/v1',
    defaultModel: 'deepseek-chat',
  },
  {
    name: 'Groq',
    baseUrl: 'https://api.groq.com/openai/v1',
    defaultModel: 'llama-3.3-70b-versatile',
  },
  {
    name: 'OpenRouter',
    baseUrl: 'https://openrouter.ai/api/v1',
    defaultModel: 'deepseek/deepseek-chat',
  },
  {
    name: 'Mistral AI',
    baseUrl: 'https://api.mistral.ai/v1',
    defaultModel: 'mistral-large-latest',
  },
  {
    name: 'Ollama (Local)',
    baseUrl: 'http://host.docker.internal:11434/v1',
    defaultModel: 'llama3.2',
  },
];

interface CliCommandItem {
  id: string;
  category: 'docker' | 'logs' | 'testing' | 'database' | 'shell' | 'voice';
  title: string;
  description: string;
  command: string;
}

const DEV_CATEGORIES = [
  { id: 'all', label: 'All Commands' },
  { id: 'docker', label: 'Docker & Services' },
  { id: 'logs', label: 'Logs & Diagnostics' },
  { id: 'testing', label: 'Testing & QA' },
  { id: 'database', label: 'Database & Migrations' },
  { id: 'shell', label: 'Interactive Shell' },
  { id: 'voice', label: 'Voice Worker & AI' },
];

const CLI_COMMANDS: CliCommandItem[] = [
  // 1. Docker & Services
  {
    id: 'docker-up-build',
    category: 'docker',
    title: 'Start All Services (with Build)',
    description: 'Builds images if necessary and starts backend & frontend in detached background mode.',
    command: 'docker compose up -d --build',
  },
  {
    id: 'docker-up',
    category: 'docker',
    title: 'Start All Services Quickly',
    description: 'Starts existing container services without rebuilding images.',
    command: 'docker compose up -d',
  },
  {
    id: 'docker-down',
    category: 'docker',
    title: 'Stop All Services',
    description: 'Stops and removes running containers while preserving data volumes.',
    command: 'docker compose down',
  },
  {
    id: 'docker-restart-all',
    category: 'docker',
    title: 'Restart All Services',
    description: 'Restarts both backend and frontend containers gracefully.',
    command: 'docker compose restart',
  },
  {
    id: 'docker-restart-backend',
    category: 'docker',
    title: 'Restart Backend Service Only',
    description: 'Restarts FastAPI container to apply python backend or env changes.',
    command: 'docker compose restart backend',
  },
  {
    id: 'docker-ps',
    category: 'docker',
    title: 'Check Containers Health & Status',
    description: 'Lists running containers, uptime, mapped ports, and healthcheck status.',
    command: 'docker compose ps',
  },

  // 2. Logs & Monitoring
  {
    id: 'logs-all',
    category: 'logs',
    title: 'Stream All Live Logs',
    description: 'Follows combined real-time stdout and stderr output for all services.',
    command: 'docker compose logs -f',
  },
  {
    id: 'logs-backend',
    category: 'logs',
    title: 'Stream Backend Server Logs',
    description: 'Follows real-time FastAPI requests, AI job logs, and errors.',
    command: 'docker compose logs -f backend',
  },
  {
    id: 'logs-frontend',
    category: 'logs',
    title: 'Stream Frontend Dev Logs',
    description: 'Follows Vite development server compilation and bundle logs.',
    command: 'docker compose logs -f frontend',
  },
  {
    id: 'logs-backend-tail',
    category: 'logs',
    title: 'Tail Recent Backend Logs (100 lines)',
    description: 'Quickly shows the last 100 log lines from backend without streaming.',
    command: 'docker compose logs --tail=100 backend',
  },

  // 3. Testing & Code Quality
  {
    id: 'test-all',
    category: 'testing',
    title: 'Run Entire Backend Test Suite',
    description: 'Executes all 255+ unit, integration, and E2E tests inside Docker.',
    command: 'docker compose exec backend pytest -v',
  },
  {
    id: 'test-downloader',
    category: 'testing',
    title: 'Run Video Downloader Tests',
    description: 'Runs SSRF, URL extraction, direct media, and yt-dlp downloader tests.',
    command: 'docker compose exec backend pytest -v tests/test_video_downloader.py',
  },
  {
    id: 'test-toolkit',
    category: 'testing',
    title: 'Run Media Toolkit Tests',
    description: 'Runs tests for Video-to-Audio, Transcript, Translation, and TTS tools.',
    command: 'docker compose exec backend pytest -v tests/test_media_toolkit.py',
  },
  {
    id: 'test-dubbing-e2e',
    category: 'testing',
    title: 'Run Dubbing Pipeline & E2E Tests',
    description: 'Tests audio synchronization, tempo adjustment, and video remuxing.',
    command: 'docker compose exec backend pytest -v tests/test_dubbing.py tests/test_e2e_pipeline.py',
  },
  {
    id: 'frontend-build',
    category: 'testing',
    title: 'Frontend Typecheck & Production Build',
    description: 'Verifies strict TypeScript types (tsc) and generates production bundle.',
    command: 'docker compose exec -T frontend npm run build',
  },
  {
    id: 'frontend-lint',
    category: 'testing',
    title: 'Frontend ESLint Verification',
    description: 'Runs ESLint static analysis across React TypeScript components.',
    command: 'docker compose exec frontend npm run lint',
  },

  // 4. Database & Migrations
  {
    id: 'db-upgrade',
    category: 'database',
    title: 'Apply Database Migrations (Upgrade Head)',
    description: 'Runs pending Alembic schema migrations on SQLite database.',
    command: 'docker compose exec backend alembic upgrade head',
  },
  {
    id: 'db-current',
    category: 'database',
    title: 'Show Current Migration Revision',
    description: 'Displays the current active Alembic migration version.',
    command: 'docker compose exec backend alembic current',
  },
  {
    id: 'db-history',
    category: 'database',
    title: 'Show Migration History',
    description: 'Lists all migration revisions and timestamps in chronological order.',
    command: 'docker compose exec backend alembic history --verbose',
  },
  {
    id: 'db-autogenerate',
    category: 'database',
    title: 'Autogenerate New Migration Script',
    description: 'Detects model changes in SQLAlchemy and generates a migration script.',
    command: 'docker compose exec backend alembic revision --autogenerate -m "update_schema"',
  },

  // 5. Interactive Shell & CLI
  {
    id: 'shell-backend',
    category: 'shell',
    title: 'Backend Interactive Bash Shell',
    description: 'Opens an interactive bash terminal inside the running backend container.',
    command: 'docker compose exec -it backend /bin/bash',
  },
  {
    id: 'shell-frontend',
    category: 'shell',
    title: 'Frontend Interactive Shell',
    description: 'Opens an interactive shell inside the running frontend container.',
    command: 'docker compose exec -it frontend /bin/sh',
  },
  {
    id: 'sqlite-cli',
    category: 'shell',
    title: 'Interactive SQLite Database CLI',
    description: 'Directly opens SQLite CLI on the app database (.tables, .schema).',
    command: 'docker compose exec -it backend sqlite3 /app/data/khmerdub.db',
  },
  {
    id: 'inspect-storage',
    category: 'shell',
    title: 'Inspect Media Storage Usage',
    description: 'Shows human-readable disk usage for uploads, outputs, temp, and toolkit.',
    command: 'docker compose exec backend du -sh /app/data/*',
  },

  // 6. Voice Cloning & Worker
  {
    id: 'voice-worker-start',
    category: 'voice',
    title: 'Start VoxCPM2 Voice Worker (Host GPU)',
    description: 'Starts the GPU-accelerated VoxCPM2 voice cloning worker daemon (port 8002).',
    command: 'PYTHONPATH=backend /home/mark/miniconda3/envs/voxcpm-bench/bin/python backend/app/services/voice/worker.py',
  },
  {
    id: 'voice-worker-health',
    category: 'voice',
    title: 'Check VoxCPM2 Worker Health',
    description: 'Queries VoxCPM2 worker health status, GPU memory, and model state.',
    command: 'curl -s http://localhost:8002/health | jq .',
  },
  {
    id: 'backend-health',
    category: 'voice',
    title: 'Check Backend API Health',
    description: 'Returns FastAPI server status, version, and FFmpeg capability check.',
    command: 'curl -s http://localhost:8000/api/health | jq .',
  },
];

type SettingsSection =
  | 'status'
  | 'translation'
  | 'voices'
  | 'models'
  | 'hardware'
  | 'storage'
  | 'developer';

export const Settings: React.FC<SettingsProps> = ({ health }) => {
  const [activeSection, setActiveSection] = useState<SettingsSection>('status');
  const [providers, setProviders] = useState<TranslationProviderInfo[]>([]);
  const [loadingProviders, setLoadingProviders] = useState<boolean>(true);
  const [voiceData, setVoiceData] = useState<any>(null);
  const [loadingVoiceData, setLoadingVoiceData] = useState<boolean>(false);

  // Active provider tab to configure (gemini, openai, claude, custom)
  const [activeTab, setActiveTab] = useState<string>('gemini');

  // Form states per provider
  const [apiKeyInput, setApiKeyInput] = useState<string>('');
  const [showApiKey, setShowApiKey] = useState<boolean>(false);
  const [baseUrlInput, setBaseUrlInput] = useState<string>('');
  const [modelInput, setModelInput] = useState<string>('');

  // Action states
  const [testingConnection, setTestingConnection] = useState<boolean>(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [savingKey, setSavingKey] = useState<boolean>(false);
  const [statusMessage, setStatusMessage] = useState<{ text: string; isError: boolean } | null>(null);

  // Developer Controls & CLI States
  const [devCategoryFilter, setDevCategoryFilter] = useState<string>('all');
  const [devSearchQuery, setDevSearchQuery] = useState<string>('');
  const [copiedCommandId, setCopiedCommandId] = useState<string | null>(null);

  const handleCopyCommand = (id: string, text: string) => {
    if (navigator?.clipboard?.writeText) {
      navigator.clipboard.writeText(text);
    } else {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      document.body.appendChild(textarea);
      textarea.select();
      document.execCommand('copy');
      document.body.removeChild(textarea);
    }
    setCopiedCommandId(id);
    setTimeout(() => {
      setCopiedCommandId(null);
    }, 2000);
  };

  const filteredCommands = CLI_COMMANDS.filter((cmd) => {
    const matchesCategory = devCategoryFilter === 'all' || cmd.category === devCategoryFilter;
    if (!matchesCategory) return false;
    if (!devSearchQuery.trim()) return true;
    const q = devSearchQuery.toLowerCase().trim();
    return (
      cmd.title.toLowerCase().includes(q) ||
      cmd.description.toLowerCase().includes(q) ||
      cmd.command.toLowerCase().includes(q) ||
      cmd.category.toLowerCase().includes(q)
    );
  });

  const syncFormForProvider = (providerId: string, providerList: TranslationProviderInfo[]) => {
    const p = providerList.find((item) => item.id === providerId);
    if (!p) return;

    setApiKeyInput('');
    setShowApiKey(false);
    setTestResult(null);
    setStatusMessage(null);

    if (p.id === 'custom') {
      setBaseUrlInput(p.base_url || 'https://api.deepseek.com/v1');
      setModelInput(p.configured_model || p.default_model || 'deepseek-chat');
    } else {
      setBaseUrlInput(p.base_url || '');
      setModelInput(p.configured_model || p.default_model || '');
    }
  };

  const fetchProviders = async () => {
    try {
      setLoadingProviders(true);
      const res = await api.getTranslationProviders();
      setProviders(res.providers);
      syncFormForProvider(activeTab, res.providers);
    } catch (err: any) {
      console.error('Failed to load translation providers', err);
    } finally {
      setLoadingProviders(false);
    }
  };

  const fetchVoiceData = async () => {
    try {
      setLoadingVoiceData(true);
      const data = await api.getVoiceStudio();
      setVoiceData(data);
    } catch (err) {
      console.warn('Could not load voice data for system status', err);
    } finally {
      setLoadingVoiceData(false);
    }
  };

  useEffect(() => {
    fetchProviders();
    fetchVoiceData();
  }, []);

  const handleTabChange = (providerId: string) => {
    setActiveTab(providerId);
    syncFormForProvider(providerId, providers);
  };

  const currentProvider = providers.find((p) => p.id === activeTab);

  const handleTestConnection = async () => {
    setTestingConnection(true);
    setTestResult(null);
    setStatusMessage(null);
    try {
      const res = await api.testTranslationConnection({
        provider: activeTab,
        api_key: apiKeyInput.trim() || undefined,
        base_url: activeTab === 'custom' ? baseUrlInput.trim() || undefined : undefined,
        model: modelInput.trim() || undefined,
      });
      setTestResult({ success: res.success, message: res.message });
    } catch (err: any) {
      setTestResult({
        success: false,
        message: err.message || 'Connection test failed',
      });
    } finally {
      setTestingConnection(false);
    }
  };

  const handleSaveKey = async () => {
    if (!apiKeyInput.trim() && !currentProvider?.is_configured) {
      setStatusMessage({ text: `Please enter an API key for ${currentProvider?.name || activeTab}.`, isError: true });
      return;
    }
    setSavingKey(true);
    setStatusMessage(null);
    try {
      const res = await api.saveTranslationCredentials(
        activeTab,
        apiKeyInput.trim(),
        activeTab === 'custom' ? baseUrlInput.trim() : undefined,
        modelInput.trim() || undefined
      );
      setStatusMessage({ text: res.message || `${currentProvider?.name || activeTab} credentials saved securely.`, isError: false });
      setApiKeyInput('');
      await fetchProviders();
    } catch (err: any) {
      setStatusMessage({ text: err.message || 'Failed to save credentials.', isError: true });
    } finally {
      setSavingKey(false);
    }
  };

  const handleDeleteKey = async () => {
    if (!confirm(`Are you sure you want to remove credentials for ${currentProvider?.name || activeTab}?`)) {
      return;
    }
    setStatusMessage(null);
    try {
      const res = await api.deleteTranslationCredentials(activeTab);
      setStatusMessage({ text: res.message || 'Credentials removed.', isError: false });
      setApiKeyInput('');
      setTestResult(null);
      await fetchProviders();
    } catch (err: any) {
      setStatusMessage({ text: err.message || 'Failed to delete credentials.', isError: true });
    }
  };

  const applyCustomPreset = (preset: ProviderPreset) => {
    setBaseUrlInput(preset.baseUrl);
    setModelInput(preset.defaultModel);
  };

  const navSections: { id: SettingsSection; label: string; icon: React.ElementType }[] = [
    { id: 'status', label: 'System Status', icon: Activity },
    { id: 'translation', label: 'AI Translation & APIs', icon: Languages },
    { id: 'voices', label: 'Voice & TTS Providers', icon: Mic2 },
    { id: 'models', label: 'AI Models Catalog', icon: Layers },
    { id: 'hardware', label: 'Hardware & Compute', icon: Cpu },
    { id: 'storage', label: 'Storage & Mounts', icon: HardDrive },
    { id: 'developer', label: 'Developer & CLI', icon: Terminal },
  ];

  const isWorkerOnline = voiceData?.cloning_engine_status?.includes('Online') ?? false;
  const isBackendHealthy = health?.status === 'ok';
  const isFfmpegAvailable = health?.system_info?.ffmpeg_available ?? false;
  const rawGpuLabel = voiceData?.cloning_engine_status?.match(/\((.*?)\)/)?.[1] || (isWorkerOnline ? 'CUDA GPU' : 'GPU Worker Offline');
  const gpuCleanLabel = rawGpuLabel.replace('VoxCPM2 — ', '');

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-12">
      {/* Settings Header */}
      <div>
        <h2 className="text-xl font-bold text-slate-900">Platform Settings</h2>
        <p className="text-xs text-slate-500 mt-1">
          Manage AI translation credentials, custom OpenAI-compatible endpoints, TTS voices, and hardware parameters.
        </p>
      </div>

      {/* Navigation Tabs Bar */}
      <div className="flex items-center gap-2 overflow-x-auto pb-1 border-b border-slate-200">
        {navSections.map((sec) => {
          const Icon = sec.icon;
          const isActive = activeSection === sec.id;
          return (
            <button
              key={sec.id}
              onClick={() => setActiveSection(sec.id)}
              className={`flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold whitespace-nowrap transition-all ${
                isActive
                  ? 'bg-indigo-600 text-white shadow-xs'
                  : 'bg-white text-slate-600 hover:text-slate-900 hover:bg-slate-100 border border-slate-200'
              }`}
            >
              <Icon className="w-4 h-4" />
              <span>{sec.label}</span>
            </button>
          );
        })}
      </div>

      {/* SECTION 0: System Status */}
      {activeSection === 'status' && (
        <div className="space-y-6">
          {/* Main Status Cards Grid */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Backend Connection */}
            <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase text-slate-500 tracking-wider">
                  Backend Service
                </span>
                <Server className="w-4 h-4 text-indigo-600" />
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={`w-2.5 h-2.5 rounded-full ${
                    isBackendHealthy ? 'bg-emerald-500 animate-pulse' : 'bg-rose-500'
                  }`}
                />
                <span className="text-base font-bold text-slate-900">
                  {isBackendHealthy ? 'Connected' : 'Offline'}
                </span>
              </div>
              <p className="text-xs text-slate-500">
                FastAPI Core v{health?.version || '0.1.0'}
              </p>
            </div>

            {/* FFmpeg Engine */}
            <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase text-slate-500 tracking-wider">
                  FFmpeg Engine
                </span>
                <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={`w-2.5 h-2.5 rounded-full ${
                    isFfmpegAvailable ? 'bg-emerald-500' : 'bg-rose-500'
                  }`}
                />
                <span className="text-base font-bold text-slate-900">
                  {isFfmpegAvailable ? 'Available' : 'Missing'}
                </span>
              </div>
              <p className="text-xs text-slate-500">
                Audio demuxing & lossless remuxing
              </p>
            </div>

            {/* VoxCPM2 Worker Status */}
            <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase text-slate-500 tracking-wider">
                  Voice Cloning Worker
                </span>
                <Mic2 className="w-4 h-4 text-indigo-600" />
              </div>
              <div className="flex items-center gap-2">
                <span
                  className={`w-2.5 h-2.5 rounded-full ${
                    isWorkerOnline ? 'bg-emerald-500' : 'bg-amber-500'
                  }`}
                />
                <span className="text-base font-bold text-slate-900">
                  {isWorkerOnline ? 'Online' : 'Offline'}
                </span>
              </div>
              <p className="text-xs text-slate-500 truncate" title={gpuCleanLabel}>
                {isWorkerOnline ? gpuCleanLabel : 'GPU worker inactive'}
              </p>
            </div>

            {/* Speech-to-Text Device */}
            <div className="bg-white p-5 rounded-2xl border border-slate-200 shadow-sm space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase text-slate-500 tracking-wider">
                  Whisper ASR Engine
                </span>
                <Cpu className="w-4 h-4 text-indigo-600" />
              </div>
              <div className="flex items-center gap-2">
                <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
                <span className="text-base font-bold text-slate-900 uppercase">
                  {health?.system_info?.whisper_device || 'CPU'}
                </span>
              </div>
              <p className="text-xs text-slate-500">
                Model: {health?.system_info?.whisper_model || 'base'} (int8)
              </p>
            </div>
          </div>

          {/* AI Providers & Services Summary Card */}
          <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-5">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-4 border-b border-slate-100">
              <div>
                <h3 className="font-bold text-slate-900 text-base flex items-center gap-2">
                  <Activity className="w-5 h-5 text-indigo-600" />
                  Available AI Providers & Capabilities
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Summary of all configured AI models across dubbing and media workflows
                </p>
              </div>

              <button
                type="button"
                onClick={() => {
                  fetchProviders();
                  fetchVoiceData();
                }}
                disabled={loadingProviders || loadingVoiceData}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl border border-slate-200 bg-slate-50 hover:bg-slate-100 text-xs font-semibold text-slate-700 transition cursor-pointer self-start sm:self-auto"
              >
                <RefreshCw
                  className={`w-3.5 h-3.5 ${
                    loadingProviders || loadingVoiceData ? 'animate-spin' : ''
                  }`}
                />
                <span>Refresh Status</span>
              </button>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-5 text-xs">
              {/* Translation Providers */}
              <div className="p-4 rounded-xl border border-slate-200 bg-slate-50/70 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-slate-900 text-sm flex items-center gap-1.5">
                    <Languages className="w-4 h-4 text-purple-600" />
                    Translation Providers
                  </span>
                  <span className="text-[11px] font-semibold text-slate-500">
                    {providers.filter((p) => p.is_configured).length} Configured
                  </span>
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between bg-white p-2.5 rounded-lg border border-slate-200">
                    <span className="font-semibold text-slate-800">Meta NLLB-200</span>
                    <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                      Local Offline Default
                    </span>
                  </div>
                  {providers.map((p) => (
                    <div
                      key={p.id}
                      className="flex items-center justify-between bg-white p-2.5 rounded-lg border border-slate-200"
                    >
                      <span className="font-semibold text-slate-800">{p.name}</span>
                      {p.is_configured ? (
                        <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200 flex items-center gap-1">
                          <CheckCircle2 className="w-3 h-3 text-emerald-600" /> Ready
                        </span>
                      ) : (
                        <span className="px-2 py-0.5 rounded text-[10px] bg-slate-100 text-slate-500">
                          API Key Required
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              </div>

              {/* Speech Synthesis Providers */}
              <div className="p-4 rounded-xl border border-slate-200 bg-slate-50/70 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="font-bold text-slate-900 text-sm flex items-center gap-1.5">
                    <Mic2 className="w-4 h-4 text-indigo-600" />
                    Speech Synthesis Providers
                  </span>
                  <span className="text-[11px] font-semibold text-slate-500">
                    Standard & Custom
                  </span>
                </div>

                <div className="space-y-2">
                  <div className="flex items-center justify-between bg-white p-2.5 rounded-lg border border-slate-200">
                    <span className="font-semibold text-slate-800">Google Khmer (gTTS)</span>
                    <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                      Active
                    </span>
                  </div>
                  <div className="flex items-center justify-between bg-white p-2.5 rounded-lg border border-slate-200">
                    <span className="font-semibold text-slate-800">Microsoft Edge Neural</span>
                    <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                      Piseth & Sreymom
                    </span>
                  </div>
                  <div className="flex items-center justify-between bg-white p-2.5 rounded-lg border border-slate-200">
                    <span className="font-semibold text-slate-800">VoxCPM2 Voice Cloning</span>
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-semibold border ${
                        isWorkerOnline
                          ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                          : 'bg-amber-50 text-amber-700 border-amber-200'
                      }`}
                    >
                      {isWorkerOnline ? 'Worker Online' : 'Worker Offline'}
                    </span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 1: AI Translation Providers & Credentials */}
      {activeSection === 'translation' && (
        <div className="space-y-6">
          <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-6">
            <div className="flex items-center justify-between pb-4 border-b border-slate-100">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-xl bg-indigo-50 text-indigo-600">
                  <Languages className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-slate-800">AI Translation Providers & API Keys</h3>
                  <p className="text-xs text-slate-500">
                    Configure Google Gemini, OpenAI, Claude, or any Custom OpenAI-compatible endpoint
                  </p>
                </div>
              </div>
              <button
                onClick={fetchProviders}
                disabled={loadingProviders}
                className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-800 px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 transition"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${loadingProviders ? 'animate-spin' : ''}`} />
                Refresh
              </button>
            </div>

            {/* Provider Switcher Tabs */}
            <div className="space-y-2">
              <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider block">
                Select Provider to Configure
              </span>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                {[
                  { id: 'gemini', label: 'Google Gemini', tag: 'Fast Spoken' },
                  { id: 'openai', label: 'OpenAI (GPT-4o)', tag: 'High Precision' },
                  { id: 'claude', label: 'Anthropic Claude', tag: 'Conversational' },
                  { id: 'custom', label: 'Custom AI API', tag: 'DeepSeek / Groq / Ollama' },
                ].map((tab) => {
                  const pInfo = providers.find((p) => p.id === tab.id);
                  const isSelected = activeTab === tab.id;
                  return (
                    <button
                      key={tab.id}
                      type="button"
                      onClick={() => handleTabChange(tab.id)}
                      className={`p-3 rounded-xl text-left border transition-all ${
                        isSelected
                          ? 'bg-indigo-50/70 border-indigo-600 ring-1 ring-indigo-500'
                          : 'bg-slate-50/70 border-slate-200 hover:bg-white hover:border-slate-300'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="font-bold text-xs text-slate-800">{tab.label}</span>
                        {pInfo?.is_configured ? (
                          <span className="text-[9px] bg-emerald-100 text-emerald-800 px-1.5 py-0.5 rounded font-semibold flex items-center gap-0.5">
                            <CheckCircle2 className="w-2.5 h-2.5 text-emerald-600" /> Ready
                          </span>
                        ) : (
                          <span className="text-[9px] bg-slate-200 text-slate-600 px-1.5 py-0.5 rounded">
                            Key Needed
                          </span>
                        )}
                      </div>
                      <p className="text-[10px] text-slate-400 mt-1">{tab.tag}</p>
                    </button>
                  );
                })}
              </div>
            </div>

            {/* Active Provider Form */}
            <div className="p-5 rounded-2xl border border-slate-200 bg-slate-50/60 space-y-4">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
                  <Key className="w-4 h-4 text-indigo-600" />
                  {currentProvider?.name || activeTab} Credentials
                </span>
                {currentProvider?.masked_key && (
                  <span className="text-xs font-mono bg-white px-2.5 py-1 rounded-md border border-slate-200 text-slate-700">
                    Encrypted Key: <strong className="text-slate-900">{currentProvider.masked_key}</strong>
                  </span>
                )}
              </div>

              {/* Quick Fill Presets for Custom API */}
              {activeTab === 'custom' && (
                <div className="space-y-1.5 p-3.5 bg-white rounded-xl border border-purple-200">
                  <span className="text-[11px] font-semibold text-purple-900 flex items-center gap-1">
                    <Zap className="w-3.5 h-3.5 text-purple-600" />
                    Compatible API Presets:
                  </span>
                  <div className="flex flex-wrap gap-1.5">
                    {CUSTOM_PRESETS.map((preset) => (
                      <button
                        key={preset.name}
                        type="button"
                        onClick={() => applyCustomPreset(preset)}
                        className="text-[11px] px-2.5 py-1 rounded-lg bg-purple-50 text-purple-800 hover:bg-purple-100 border border-purple-200 transition font-medium"
                      >
                        {preset.name}
                      </button>
                    ))}
                  </div>
                </div>
              )}

              {/* Form Inputs */}
              <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
                {activeTab === 'custom' && (
                  <div className="md:col-span-3 space-y-1">
                    <label className="text-[11px] font-medium text-slate-600 flex items-center gap-1">
                      <Server className="w-3.5 h-3.5 text-slate-400" />
                      <span>Custom OpenAI-Compatible Base URL</span>
                    </label>
                    <input
                      type="text"
                      placeholder="https://api.deepseek.com/v1"
                      value={baseUrlInput}
                      onChange={(e) => setBaseUrlInput(e.target.value)}
                      className="w-full text-xs font-mono px-3.5 py-2 bg-white border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                  </div>
                )}

                {/* API Key Input */}
                <div className="md:col-span-2 space-y-1">
                  <label className="text-[11px] font-medium text-slate-600">
                    {currentProvider?.name || 'Provider'} API Key
                  </label>
                  <div className="relative">
                    <input
                      type={showApiKey ? 'text' : 'password'}
                      placeholder={
                        currentProvider?.is_configured
                          ? 'Enter new API key to replace existing...'
                          : 'Enter API key...'
                      }
                      value={apiKeyInput}
                      onChange={(e) => setApiKeyInput(e.target.value)}
                      className="w-full text-xs font-mono px-3.5 py-2 pr-9 bg-white border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                    <button
                      type="button"
                      onClick={() => setShowApiKey(!showApiKey)}
                      className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-600"
                    >
                      {showApiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>
                </div>

                {/* Model */}
                <div className="space-y-1">
                  <label className="text-[11px] font-medium text-slate-600">Model Name</label>
                  {activeTab === 'custom' ? (
                    <input
                      type="text"
                      placeholder="deepseek-chat"
                      value={modelInput}
                      onChange={(e) => setModelInput(e.target.value)}
                      className="w-full text-xs font-mono px-3.5 py-2 bg-white border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    />
                  ) : (
                    <select
                      value={modelInput}
                      onChange={(e) => setModelInput(e.target.value)}
                      className="w-full text-xs px-3.5 py-2 bg-white border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                    >
                      {(currentProvider?.available_models || []).map((m) => (
                        <option key={m} value={m}>
                          {m}
                        </option>
                      ))}
                    </select>
                  )}
                </div>
              </div>

              {/* Action Buttons */}
              <div className="flex flex-wrap items-center gap-2 pt-2">
                <button
                  onClick={handleSaveKey}
                  disabled={savingKey || (!apiKeyInput.trim() && !currentProvider?.is_configured)}
                  className="px-4 py-2 bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-300 text-white text-xs font-semibold rounded-lg shadow-sm transition flex items-center gap-1.5"
                >
                  <ShieldCheck className="w-4 h-4" />
                  <span>{savingKey ? 'Saving...' : 'Save Credentials'}</span>
                </button>

                <button
                  onClick={handleTestConnection}
                  disabled={testingConnection || (!currentProvider?.is_configured && !apiKeyInput.trim())}
                  className="px-4 py-2 bg-white border border-slate-300 hover:bg-slate-100 disabled:opacity-50 text-slate-700 text-xs font-semibold rounded-lg transition flex items-center gap-1.5"
                >
                  <RefreshCw className={`w-3.5 h-3.5 ${testingConnection ? 'animate-spin' : ''}`} />
                  <span>{testingConnection ? 'Testing...' : 'Test Connection'}</span>
                </button>

                {currentProvider?.is_configured && (
                  <button
                    onClick={handleDeleteKey}
                    className="px-3.5 py-2 bg-rose-50 border border-rose-200 hover:bg-rose-100 text-rose-700 text-xs font-semibold rounded-lg transition flex items-center gap-1.5 ml-auto"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                    <span>Remove Key</span>
                  </button>
                )}
              </div>

              {/* Feedback messages */}
              {statusMessage && (
                <div
                  className={`p-3 rounded-lg text-xs flex items-center gap-2 ${
                    statusMessage.isError
                      ? 'bg-rose-50 text-rose-800 border border-rose-200'
                      : 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                  }`}
                >
                  {statusMessage.isError ? (
                    <AlertCircle className="w-4 h-4 shrink-0 text-rose-600" />
                  ) : (
                    <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600" />
                  )}
                  <span>{statusMessage.text}</span>
                </div>
              )}

              {testResult && (
                <div
                  className={`p-3 rounded-lg text-xs flex items-start gap-2 ${
                    testResult.success
                      ? 'bg-emerald-50 text-emerald-800 border border-emerald-200'
                      : 'bg-rose-50 text-rose-800 border border-rose-200'
                  }`}
                >
                  {testResult.success ? (
                    <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600 mt-0.5" />
                  ) : (
                    <AlertCircle className="w-4 h-4 shrink-0 text-rose-600 mt-0.5" />
                  )}
                  <div>
                    <span className="font-semibold block">
                      {testResult.success ? 'Connection Successful' : 'Connection Failed'}
                    </span>
                    <span className="text-[11px] opacity-90">{testResult.message}</span>
                  </div>
                </div>
              )}

              <div className="p-3 bg-white rounded-lg border border-slate-200 text-[11px] text-slate-500 space-y-1">
                <span className="font-semibold text-slate-700 flex items-center gap-1">
                  <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
                  Bank-Grade Fernet Key Encryption
                </span>
                <p>
                  API keys and custom URLs are encrypted via AES-128-CBC + HMAC-SHA256 at <code className="font-mono bg-slate-100 px-1 py-0.5 rounded text-slate-800">/app/data/.secrets/credentials.enc</code> with restricted file permissions (0600). Sensitive plaintext keys are never returned to the browser or committed to Git.
                </p>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 2: Voice Providers */}
      {activeSection === 'voices' && (
        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-5">
          <div className="flex items-center gap-3 pb-3 border-b border-slate-100">
            <div className="p-2 rounded-xl bg-indigo-50 text-indigo-600">
              <Mic2 className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-800">Khmer Text-to-Speech Providers</h3>
              <p className="text-xs text-slate-500">Configured speech synthesis engines</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
            <div className="p-4 rounded-xl border border-slate-200 bg-slate-50 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-bold text-slate-800">Google Khmer (gTTS)</span>
                <span className="text-[10px] bg-emerald-100 text-emerald-800 font-semibold px-2 py-0.5 rounded-full">
                  Free Default
                </span>
              </div>
              <p className="text-slate-500 leading-relaxed">
                Standard natural Google Khmer speech model. Completely free and runs with exponential backoff network retry logic.
              </p>
            </div>

            <div className="p-4 rounded-xl border border-slate-200 bg-slate-50 space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-bold text-slate-800">Microsoft Edge Neural</span>
                <span className="text-[10px] bg-blue-100 text-blue-800 font-semibold px-2 py-0.5 rounded-full">
                  High-Fidelity Neural
                </span>
              </div>
              <p className="text-slate-500 leading-relaxed">
                Offers <strong>Microsoft Piseth</strong> (Male) and <strong>Microsoft Sreymom</strong> (Female) Cambodian neural voices with rich natural cadence.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 3: AI Models Catalog */}
      {activeSection === 'models' && (
        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-5">
          <div className="flex items-center gap-3 pb-3 border-b border-slate-100">
            <div className="p-2 rounded-xl bg-purple-50 text-purple-600">
              <Layers className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-800">AI Models Catalog</h3>
              <p className="text-xs text-slate-500">Models utilized across speech recognition, translation, and voice dubbing</p>
            </div>
          </div>

          <div className="space-y-3 text-xs">
            <div className="p-3.5 rounded-xl border border-slate-200 bg-slate-50 space-y-1">
              <span className="font-bold text-slate-800">1. Faster-Whisper (Speech-to-Text)</span>
              <p className="text-slate-500 leading-relaxed">
                Uses CTranslate2 with INT8 quantization running on CPU. Integrated with Silero Voice Activity Detection (VAD) for precise speech segmentation.
              </p>
            </div>

            <div className="p-3.5 rounded-xl border border-slate-200 bg-slate-50 space-y-1">
              <span className="font-bold text-slate-800">2. Meta NLLB-200 (Local Neural Translation)</span>
              <p className="text-slate-500 leading-relaxed">
                <code>facebook/nllb-200-distilled-600M</code> translates English (<code>eng_Latn</code>) directly to Khmer (<code>khm_Khmr</code>). Cached persistently in Docker volume.
              </p>
            </div>

            <div className="p-3.5 rounded-xl border border-slate-200 bg-slate-50 space-y-1">
              <span className="font-bold text-slate-800">3. Cloud & Custom AI LLMs</span>
              <p className="text-slate-500 leading-relaxed">
                Google Gemini (<code>gemini-3.5-flash</code>), OpenAI (<code>gpt-4o-mini</code>), Anthropic Claude (<code>claude-3-5-sonnet</code>), and Custom OpenAI endpoints for style-tailored dubbing phrasing.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 4: Hardware & Compute */}
      {activeSection === 'hardware' && (
        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-5">
          <div className="flex items-center gap-3 pb-3 border-b border-slate-100">
            <div className="p-2 rounded-xl bg-indigo-50 text-indigo-600">
              <Cpu className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-800">Hardware & Compute Status</h3>
              <p className="text-xs text-slate-500">Current device execution parameters</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-1">
              <span className="text-slate-400 font-medium text-[11px] block">Whisper Inference Device</span>
              <span className="font-bold text-slate-800 text-sm uppercase">
                {health?.system_info?.whisper_device || 'CPU'}
              </span>
              <p className="text-slate-400 mt-1">CPU execution ensures 100% reproducible startup without CUDA driver conflicts.</p>
            </div>

            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 space-y-1">
              <span className="text-slate-400 font-medium text-[11px] block">Whisper Model Size</span>
              <span className="font-bold text-slate-800 text-sm">
                {health?.system_info?.whisper_model || 'base'} (int8 quantized)
              </span>
              <p className="text-slate-400 mt-1">Optimized for low RAM footprint and fast inference on standard laptop CPUs.</p>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 5: Storage & Mounts */}
      {activeSection === 'storage' && (
        <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-5">
          <div className="flex items-center gap-3 pb-3 border-b border-slate-100">
            <div className="p-2 rounded-xl bg-emerald-50 text-emerald-600">
              <HardDrive className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-800">Storage & Volumes</h3>
              <p className="text-xs text-slate-500">Persistent storage mounts and media caching</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs font-mono">
            <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
              <span className="text-slate-500 font-sans block text-[11px] mb-1">Uploads Path</span>
              <span className="text-slate-800 font-semibold">/app/data/uploads</span>
            </div>
            <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
              <span className="text-slate-500 font-sans block text-[11px] mb-1">Outputs Path</span>
              <span className="text-slate-800 font-semibold">/app/data/outputs</span>
            </div>
            <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200">
              <span className="text-slate-500 font-sans block text-[11px] mb-1">AI Model Cache</span>
              <span className="text-slate-800 font-semibold">/root/.cache</span>
            </div>
          </div>
        </div>
      )}

      {/* SECTION 6: Developer Controls */}
      {activeSection === 'developer' && (
        <div className="bg-slate-950 rounded-2xl p-6 text-white text-xs space-y-6 border border-slate-800 shadow-sm">
          {/* Header */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-800/80">
            <div className="flex items-center gap-3">
              <div className="p-2.5 rounded-xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400">
                <Terminal className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-white flex items-center gap-2">
                  <span>Developer Controls & Quick CLI</span>
                  <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                    {filteredCommands.length} of {CLI_COMMANDS.length} Commands
                  </span>
                </h3>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  Click the <strong className="text-slate-200">Copy</strong> button on any command to copy it to clipboard, then paste into your terminal.
                </p>
              </div>
            </div>

            {/* Live Search Input */}
            <div className="relative w-full sm:w-72">
              <Search className="w-3.5 h-3.5 text-slate-500 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={devSearchQuery}
                onChange={(e) => setDevSearchQuery(e.target.value)}
                placeholder="Search commands (e.g. pytest, logs, alembic)..."
                className="w-full pl-9 pr-8 py-1.5 rounded-xl bg-slate-900 border border-slate-800 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
              />
              {devSearchQuery && (
                <button
                  type="button"
                  onClick={() => setDevSearchQuery('')}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[10px] text-slate-400 hover:text-white"
                >
                  Clear
                </button>
              )}
            </div>
          </div>

          {/* Category Filter Pills */}
          <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none text-[11px]">
            {DEV_CATEGORIES.map((cat) => {
              const isSelected = devCategoryFilter === cat.id;
              const count =
                cat.id === 'all'
                  ? CLI_COMMANDS.length
                  : CLI_COMMANDS.filter((c) => c.category === cat.id).length;
              return (
                <button
                  key={cat.id}
                  type="button"
                  onClick={() => setDevCategoryFilter(cat.id)}
                  className={`px-3 py-1.5 rounded-lg font-medium whitespace-nowrap transition-all flex items-center gap-1.5 cursor-pointer ${
                    isSelected
                      ? 'bg-indigo-600 text-white shadow-xs font-semibold'
                      : 'bg-slate-900 text-slate-400 hover:text-slate-200 hover:bg-slate-800/80 border border-slate-800/80'
                  }`}
                >
                  <span>{cat.label}</span>
                  <span
                    className={`text-[10px] px-1.5 py-0.2 rounded-full ${
                      isSelected
                        ? 'bg-indigo-700/80 text-indigo-100'
                        : 'bg-slate-800 text-slate-500'
                    }`}
                  >
                    {count}
                  </span>
                </button>
              );
            })}
          </div>

          {/* Commands List */}
          <div className="space-y-3">
            {filteredCommands.length === 0 ? (
              <div className="p-8 text-center bg-slate-900/40 rounded-xl border border-slate-800/60 text-slate-400">
                <Search className="w-6 h-6 mx-auto mb-2 text-slate-500 opacity-60" />
                <p className="font-semibold text-xs">No matching commands found</p>
                <p className="text-[11px] text-slate-500 mt-1">
                  Try a different search keyword or reset the category filter.
                </p>
              </div>
            ) : (
              filteredCommands.map((cmd) => {
                const isCopied = copiedCommandId === cmd.id;
                return (
                  <div
                    key={cmd.id}
                    className="bg-slate-900/90 rounded-xl p-3.5 border border-slate-800/90 hover:border-slate-700/90 transition-all space-y-2 group"
                  >
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1.5">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold text-slate-200 text-xs">
                          {cmd.title}
                        </span>
                        <span className="text-[9px] uppercase font-bold tracking-wider px-1.5 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700">
                          {cmd.category}
                        </span>
                      </div>
                      <span className="text-[11px] text-slate-400">
                        {cmd.description}
                      </span>
                    </div>

                    <div className="flex items-center justify-between gap-3 bg-slate-950 p-2.5 rounded-lg border border-slate-800/80 font-mono text-xs">
                      <div className="overflow-x-auto text-indigo-300 font-medium select-all py-0.5">
                        {cmd.command}
                      </div>

                      <button
                        type="button"
                        onClick={() => handleCopyCommand(cmd.id, cmd.command)}
                        title="Copy command to clipboard"
                        className={`px-3 py-1.5 rounded-lg text-xs font-semibold transition-all flex items-center gap-1.5 shrink-0 cursor-pointer ${
                          isCopied
                            ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40'
                            : 'bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700'
                        }`}
                      >
                        {isCopied ? (
                          <>
                            <Check className="w-3.5 h-3.5 text-emerald-400" />
                            <span>Copied!</span>
                          </>
                        ) : (
                          <>
                            <Copy className="w-3.5 h-3.5 text-slate-400 group-hover:text-white" />
                            <span>Copy</span>
                          </>
                        )}
                      </button>
                    </div>
                  </div>
                );
              })
            )}
          </div>

          {/* Useful Documentation & Endpoints Links */}
          <div className="pt-4 border-t border-slate-800/80 text-slate-400 text-xs flex flex-wrap items-center gap-y-2 gap-x-4">
            <span className="text-slate-500 font-semibold text-[11px] uppercase tracking-wider">
              Quick Links:
            </span>
            <a
              href="http://localhost:8000/docs"
              target="_blank"
              rel="noreferrer"
              className="text-indigo-400 hover:text-indigo-300 hover:underline flex items-center gap-1"
            >
              <FileCode className="w-3.5 h-3.5" />
              <span>Interactive Swagger Docs</span>
              <ExternalLink className="w-3 h-3 opacity-60" />
            </a>
            <span className="text-slate-700">•</span>
            <a
              href="http://localhost:8000/redoc"
              target="_blank"
              rel="noreferrer"
              className="text-indigo-400 hover:text-indigo-300 hover:underline flex items-center gap-1"
            >
              <FileCode className="w-3.5 h-3.5" />
              <span>FastAPI ReDoc</span>
              <ExternalLink className="w-3 h-3 opacity-60" />
            </a>
            <span className="text-slate-700">•</span>
            <a
              href="http://localhost:8000/api/health"
              target="_blank"
              rel="noreferrer"
              className="text-indigo-400 hover:text-indigo-300 hover:underline flex items-center gap-1"
            >
              <Activity className="w-3.5 h-3.5" />
              <span>Backend Health API</span>
              <ExternalLink className="w-3 h-3 opacity-60" />
            </a>
            <span className="text-slate-700">•</span>
            <a
              href="http://localhost:8002/health"
              target="_blank"
              rel="noreferrer"
              className="text-indigo-400 hover:text-indigo-300 hover:underline flex items-center gap-1"
            >
              <Zap className="w-3.5 h-3.5" />
              <span>VoxCPM2 Worker Health</span>
              <ExternalLink className="w-3 h-3 opacity-60" />
            </a>
          </div>
        </div>
      )}
    </div>
  );
};
