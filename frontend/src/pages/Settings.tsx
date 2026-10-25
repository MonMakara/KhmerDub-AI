import React, { useState, useEffect } from 'react';
import {
  Cpu,
  HardDrive,
  Terminal,
  Info,
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

type SettingsSection =
  | 'translation'
  | 'voices'
  | 'models'
  | 'hardware'
  | 'storage'
  | 'developer';

export const Settings: React.FC<SettingsProps> = ({ health }) => {
  const [activeSection, setActiveSection] = useState<SettingsSection>('translation');
  const [providers, setProviders] = useState<TranslationProviderInfo[]>([]);
  const [loadingProviders, setLoadingProviders] = useState<boolean>(true);

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

  useEffect(() => {
    fetchProviders();
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
    { id: 'translation', label: 'AI Translation & APIs', icon: Languages },
    { id: 'voices', label: 'Voice & TTS Providers', icon: Mic2 },
    { id: 'models', label: 'AI Models Catalog', icon: Layers },
    { id: 'hardware', label: 'Hardware & Compute', icon: Cpu },
    { id: 'storage', label: 'Storage & Mounts', icon: HardDrive },
    { id: 'developer', label: 'Developer & CLI', icon: Terminal },
  ];

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
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
                Google Gemini (<code>gemini-2.5-flash</code>), OpenAI (<code>gpt-4o-mini</code>), Anthropic Claude (<code>claude-3-5-sonnet</code>), and Custom OpenAI endpoints for style-tailored dubbing phrasing.
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

          <div className="p-4 rounded-xl bg-amber-50/70 border border-amber-200 text-xs text-amber-900 flex gap-3">
            <Info className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
            <div className="space-y-1">
              <p className="font-semibold">Optional NVIDIA RTX 4060 GPU Acceleration</p>
              <p className="text-amber-800">
                To enable CUDA acceleration, install the NVIDIA Container Toolkit and set <code className="font-mono bg-amber-100 px-1 rounded">runtime: nvidia</code> in docker-compose.yml.
              </p>
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
        <div className="bg-slate-950 rounded-2xl p-6 text-white text-xs space-y-4 border border-slate-800">
          <div className="flex items-center gap-2 text-slate-300 font-semibold text-sm">
            <Terminal className="w-4 h-4 text-indigo-400" />
            <span>Developer Controls & Quick CLI</span>
          </div>

          <div className="space-y-2 font-mono text-slate-300">
            <div className="bg-slate-900 p-3 rounded-lg border border-slate-800 flex items-center justify-between">
              <span>docker compose logs -f backend</span>
              <span className="text-slate-500 text-[10px]">View live server logs</span>
            </div>
            <div className="bg-slate-900 p-3 rounded-lg border border-slate-800 flex items-center justify-between">
              <span>docker compose exec backend pytest -v</span>
              <span className="text-slate-500 text-[10px]">Run 106 automated tests</span>
            </div>
            <div className="bg-slate-900 p-3 rounded-lg border border-slate-800 flex items-center justify-between">
              <span>docker compose exec frontend npm run typecheck</span>
              <span className="text-slate-500 text-[10px]">TypeScript check</span>
            </div>
          </div>

          <div className="pt-2 text-slate-400 text-[11px] flex items-center gap-4">
            <a
              href="http://localhost:8000/docs"
              target="_blank"
              rel="noreferrer"
              className="text-indigo-400 hover:underline flex items-center gap-1"
            >
              <FileCode className="w-3.5 h-3.5" />
              <span>Interactive FastAPI Swagger Docs</span>
            </a>
            <span>•</span>
            <a
              href="http://localhost:8000/api/health"
              target="_blank"
              rel="noreferrer"
              className="text-indigo-400 hover:underline"
            >
              System Health API Endpoint
            </a>
          </div>
        </div>
      )}
    </div>
  );
};
