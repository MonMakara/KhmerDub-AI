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
  Sparkles,
  RefreshCw,
  Trash2,
  ShieldCheck,
  Globe,
  Server,
  Zap,
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

export const Settings: React.FC<SettingsProps> = ({ health }) => {
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

      // Initialize form for current activeTab
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
      const keyToSave = apiKeyInput.trim() || (currentProvider?.masked_key ? '__KEEP_EXISTING__' : '');
      if (!keyToSave) {
        setStatusMessage({ text: 'API key cannot be empty.', isError: true });
        return;
      }
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
    if (!confirm(`Are you sure you want to remove the saved credentials for ${currentProvider?.name || activeTab}?`)) {
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

  const nllbProvider = providers.find((p) => p.id === 'nllb');

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div>
        <h2 className="text-xl font-bold text-slate-900">System Configuration</h2>
        <p className="text-xs text-slate-500 mt-1">
          Review environment parameters, AI translation providers, custom endpoints, hardware allocation, and storage mount points.
        </p>
      </div>

      {/* AI Translation Providers & Credentials */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-6">
        <div className="flex items-center justify-between pb-4 border-b border-slate-100">
          <div className="flex items-center gap-3">
            <div className="p-2 rounded-lg bg-indigo-50 text-indigo-600">
              <Languages className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-semibold text-slate-800">AI Translation Providers & APIs</h3>
              <p className="text-xs text-slate-500">
                Support for Meta NLLB-200, Google Gemini, OpenAI, Claude, and any Custom OpenAI-compatible endpoint
              </p>
            </div>
          </div>
          <button
            onClick={fetchProviders}
            disabled={loadingProviders}
            className="flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-800 px-2.5 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 transition"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loadingProviders ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>

        {/* Local vs Cloud Providers Overview Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {/* NLLB Provider Card */}
          <div className="p-3.5 rounded-xl border border-slate-200 bg-slate-50/70 space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <span className="font-semibold text-slate-800 text-xs">{nllbProvider?.name || 'Meta NLLB-200'}</span>
                <span className="text-[9px] bg-emerald-100 text-emerald-800 font-medium px-1.5 py-0.5 rounded-full">
                  Free & Local
                </span>
              </div>
              <span className="text-[11px] font-medium text-emerald-600 flex items-center gap-1">
                <CheckCircle2 className="w-3 h-3" /> Ready
              </span>
            </div>
            <p className="text-[11px] text-slate-500 leading-relaxed">
              Offline neural machine translation on CPU. Zero cost, no API key or internet required.
            </p>
          </div>

          {/* Standard AI Cloud Providers */}
          <div className="p-3.5 rounded-xl border border-indigo-100 bg-indigo-50/40 space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <span className="font-semibold text-slate-800 text-xs">Standard AI APIs</span>
                <span className="text-[9px] bg-indigo-100 text-indigo-800 font-medium px-1.5 py-0.5 rounded-full flex items-center gap-0.5">
                  <Sparkles className="w-2.5 h-2.5 text-indigo-600" /> Cloud LLMs
                </span>
              </div>
              <span className="text-[11px] font-medium text-slate-600">Gemini / OpenAI / Claude</span>
            </div>
            <p className="text-[11px] text-slate-500 leading-relaxed">
              State-of-the-art conversational phrasing, scriptio continua formatting, and dubbing timing adaptation.
            </p>
          </div>

          {/* Custom OpenAI-Compatible Card */}
          <div className="p-3.5 rounded-xl border border-purple-100 bg-purple-50/40 space-y-2">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-1.5">
                <span className="font-semibold text-slate-800 text-xs">Custom OpenAI API</span>
                <span className="text-[9px] bg-purple-100 text-purple-800 font-medium px-1.5 py-0.5 rounded-full flex items-center gap-0.5">
                  <Globe className="w-2.5 h-2.5 text-purple-600" /> Flexible
                </span>
              </div>
              <span className="text-[11px] font-medium text-slate-600">Any Endpoint</span>
            </div>
            <p className="text-[11px] text-slate-500 leading-relaxed">
              DeepSeek, Groq, OpenRouter, Together AI, Mistral, Ollama, or local vLLM with custom Base URL.
            </p>
          </div>
        </div>

        {/* Multi-Provider Configuration Interface */}
        <div className="p-5 rounded-xl border border-slate-200 bg-slate-50 space-y-4">
          {/* Provider Selection Tabs */}
          <div>
            <span className="text-[11px] font-semibold text-slate-600 uppercase tracking-wide block mb-2">
              Select AI Translation Provider to Configure
            </span>
            <div className="flex flex-wrap gap-2">
              {[
                { id: 'gemini', label: 'Google Gemini', tag: 'Fast & Natural' },
                { id: 'openai', label: 'OpenAI (GPT-4o)', tag: 'High Precision' },
                { id: 'claude', label: 'Anthropic Claude', tag: 'Nuanced' },
                { id: 'custom', label: 'Custom AI API', tag: 'DeepSeek / Groq / Ollama' },
              ].map((tab) => {
                const pInfo = providers.find((p) => p.id === tab.id);
                const isSelected = activeTab === tab.id;
                return (
                  <button
                    key={tab.id}
                    type="button"
                    onClick={() => handleTabChange(tab.id)}
                    className={`flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium border transition-all ${
                      isSelected
                        ? 'bg-white border-indigo-600 text-indigo-700 shadow-sm ring-1 ring-indigo-500'
                        : 'bg-white/80 border-slate-200 text-slate-700 hover:bg-white hover:border-slate-300'
                    }`}
                  >
                    <span>{tab.label}</span>
                    {pInfo?.is_configured ? (
                      <span className="text-[10px] bg-emerald-100 text-emerald-800 px-1.5 py-0.5 rounded font-semibold flex items-center gap-0.5">
                        <CheckCircle2 className="w-2.5 h-2.5 text-emerald-600" /> Active
                      </span>
                    ) : (
                      <span className="text-[10px] bg-slate-100 text-slate-500 px-1.5 py-0.5 rounded">
                        {tab.tag}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Active Provider Info Header */}
          <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-200">
            <div className="flex items-center gap-2 text-slate-800 font-semibold text-xs">
              <Key className="w-4 h-4 text-indigo-600" />
              <span>{currentProvider?.name || activeTab} Configuration</span>
            </div>
            {currentProvider?.masked_key && (
              <span className="text-xs font-mono bg-white px-2.5 py-1 rounded-md border border-slate-200 text-slate-700">
                Active Key: <strong className="text-slate-900">{currentProvider.masked_key}</strong>
              </span>
            )}
          </div>

          {/* Custom Endpoint Quick Presets (Shown only when Custom is active) */}
          {activeTab === 'custom' && (
            <div className="space-y-1.5 p-3 bg-white rounded-lg border border-purple-200">
              <div className="flex items-center gap-1.5 text-[11px] font-semibold text-purple-900">
                <Zap className="w-3.5 h-3.5 text-purple-600" />
                <span>Quick Fill Compatible Endpoints:</span>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {CUSTOM_PRESETS.map((preset) => (
                  <button
                    key={preset.name}
                    type="button"
                    onClick={() => applyCustomPreset(preset)}
                    className="text-[11px] px-2.5 py-1 rounded bg-purple-50 text-purple-800 hover:bg-purple-100 border border-purple-200 transition font-medium"
                  >
                    {preset.name}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* Input Fields */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {/* Custom Base URL (if custom) */}
            {activeTab === 'custom' && (
              <div className="md:col-span-3 space-y-1">
                <label className="text-[11px] font-medium text-slate-600 flex items-center gap-1">
                  <Server className="w-3.5 h-3.5 text-slate-500" />
                  <span>Custom OpenAI-Compatible Base URL</span>
                </label>
                <input
                  type="text"
                  placeholder="https://api.deepseek.com/v1"
                  value={baseUrlInput}
                  onChange={(e) => setBaseUrlInput(e.target.value)}
                  className="w-full text-xs font-mono px-3 py-2 bg-white border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
                <span className="text-[10px] text-slate-400">
                  Endpoint should implement standard OpenAI chat completions (<code className="font-mono">/chat/completions</code>).
                </span>
              </div>
            )}

            {/* API Key */}
            <div className="md:col-span-2 space-y-1">
              <label className="text-[11px] font-medium text-slate-600 flex items-center justify-between">
                <span>{currentProvider?.name || 'Provider'} API Key</span>
                {currentProvider?.is_configured && (
                  <span className="text-[10px] text-emerald-600 font-semibold">Configured</span>
                )}
              </label>
              <div className="relative">
                <input
                  type={showApiKey ? 'text' : 'password'}
                  placeholder={
                    currentProvider?.is_configured
                      ? 'Enter new API key to replace existing...'
                      : activeTab === 'gemini'
                      ? 'AIzaSy...'
                      : activeTab === 'openai'
                      ? 'sk-...'
                      : activeTab === 'claude'
                      ? 'sk-ant-...'
                      : 'sk-...'
                  }
                  value={apiKeyInput}
                  onChange={(e) => setApiKeyInput(e.target.value)}
                  className="w-full text-xs font-mono px-3 py-2 pr-9 bg-white border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
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

            {/* Model Selector / Input */}
            <div className="space-y-1">
              <label className="text-[11px] font-medium text-slate-600">Model Name</label>
              {activeTab === 'custom' ? (
                <input
                  type="text"
                  placeholder="deepseek-chat"
                  value={modelInput}
                  onChange={(e) => setModelInput(e.target.value)}
                  className="w-full text-xs font-mono px-3 py-2 bg-white border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              ) : (
                <select
                  value={modelInput}
                  onChange={(e) => setModelInput(e.target.value)}
                  className="w-full text-xs px-3 py-2 bg-white border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
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
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <button
              onClick={handleSaveKey}
              disabled={savingKey || (!apiKeyInput.trim() && !currentProvider?.is_configured)}
              className="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-300 text-white text-xs font-medium rounded-lg shadow-sm transition flex items-center gap-1.5"
            >
              <ShieldCheck className="w-3.5 h-3.5" />
              {savingKey ? 'Saving...' : 'Save Credentials'}
            </button>

            <button
              onClick={handleTestConnection}
              disabled={testingConnection || (!currentProvider?.is_configured && !apiKeyInput.trim())}
              className="px-3.5 py-1.5 bg-white border border-slate-300 hover:bg-slate-100 disabled:opacity-50 text-slate-700 text-xs font-medium rounded-lg transition flex items-center gap-1.5"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${testingConnection ? 'animate-spin' : ''}`} />
              {testingConnection ? 'Testing...' : 'Test Connection'}
            </button>

            {currentProvider?.is_configured && (
              <button
                onClick={handleDeleteKey}
                className="px-3.5 py-1.5 bg-rose-50 border border-rose-200 hover:bg-rose-100 text-rose-700 text-xs font-medium rounded-lg transition flex items-center gap-1.5 ml-auto"
              >
                <Trash2 className="w-3.5 h-3.5" />
                Remove Key
              </button>
            )}
          </div>

          {/* Status and Feedback Messages */}
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
            <div className="flex items-center gap-1.5 font-medium text-slate-700">
              <ShieldCheck className="w-3.5 h-3.5 text-indigo-600" />
              <span>Security & Privacy Guarantee</span>
            </div>
            <p>
              Your API keys and custom endpoint URLs are encrypted using Fernet (AES-128-CBC with SHA-256 HMAC) and stored securely at <code className="font-mono bg-slate-100 px-1 py-0.5 rounded text-slate-800">/app/data/.secrets/credentials.enc</code> with restricted file permissions (0600).
              They are never committed to Git, logged in plain text, or returned unmasked to the browser.
            </p>
          </div>
        </div>
      </div>

      {/* Hardware & Acceleration Status */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-6">
        <div className="flex items-center gap-3 pb-4 border-b border-slate-100">
          <div className="p-2 rounded-lg bg-indigo-50 text-indigo-600">
            <Cpu className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-800">Compute & Hardware</h3>
            <p className="text-xs text-slate-500">Current device configuration for AI inference</p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-xs">
          <div className="p-4 rounded-lg bg-slate-50 border border-slate-200">
            <span className="text-slate-500 font-medium">Whisper Device:</span>
            <div className="font-semibold text-slate-800 text-sm mt-1 uppercase">
              {health?.system_info?.whisper_device || 'CPU'}
            </div>
            <p className="text-slate-400 mt-1">Initial CPU execution ensures 100% reproducible startup without CUDA driver locks.</p>
          </div>

          <div className="p-4 rounded-lg bg-slate-50 border border-slate-200">
            <span className="text-slate-500 font-medium">Whisper Model Size:</span>
            <div className="font-semibold text-slate-800 text-sm mt-1">
              {health?.system_info?.whisper_model || 'base'} (int8 quantized)
            </div>
            <p className="text-slate-400 mt-1">Optimized for low RAM footprint and fast inference on Intel i7 laptop CPU.</p>
          </div>
        </div>

        {/* NVIDIA GPU Note */}
        <div className="p-4 rounded-xl bg-amber-50/70 border border-amber-200 text-xs text-amber-900 flex gap-3">
          <Info className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
          <div className="space-y-1">
            <p className="font-semibold">Optional NVIDIA RTX 4060 GPU Acceleration</p>
            <p className="text-amber-800">
              Per requirements, Version 1 defaults to CPU execution to guarantee zero-hassle startup. 
              Once Phase 1 is validated, the Docker Compose configuration can be toggled to utilize 
              the NVIDIA Container Toolkit (<code className="font-mono bg-amber-100 px-1 rounded">runtime: nvidia</code>) 
              for CUDA-accelerated Whisper and NLLB inference without touching application logic.
            </p>
          </div>
        </div>
      </div>

      {/* Storage and Mount Points */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-sm space-y-6">
        <div className="flex items-center gap-3 pb-4 border-b border-slate-100">
          <div className="p-2 rounded-lg bg-emerald-50 text-emerald-600">
            <HardDrive className="w-5 h-5" />
          </div>
          <div>
            <h3 className="text-sm font-semibold text-slate-800">Storage & Volumes</h3>
            <p className="text-xs text-slate-500">Persistent storage mounts and media caching</p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 text-xs font-mono">
          <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
            <span className="text-slate-500 font-sans block text-[11px] mb-1">Uploads Path</span>
            <span className="text-slate-800 font-semibold">/app/data/uploads</span>
          </div>
          <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
            <span className="text-slate-500 font-sans block text-[11px] mb-1">Outputs Path</span>
            <span className="text-slate-800 font-semibold">/app/data/outputs</span>
          </div>
          <div className="p-3 rounded-lg bg-slate-50 border border-slate-200">
            <span className="text-slate-500 font-sans block text-[11px] mb-1">AI Model Cache</span>
            <span className="text-slate-800 font-semibold">/root/.cache</span>
          </div>
        </div>
      </div>

      {/* Docker Dev Environment Tips */}
      <div className="bg-slate-900 rounded-xl p-6 text-white text-xs space-y-4">
        <div className="flex items-center gap-2 text-slate-300 font-semibold text-sm">
          <Terminal className="w-4 h-4 text-indigo-400" />
          <span>Quick Control Commands</span>
        </div>
        <div className="space-y-2 font-mono text-slate-300">
          <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
            docker compose logs -f backend
          </div>
          <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
            docker compose exec backend pytest
          </div>
          <div className="bg-slate-950 p-2.5 rounded border border-slate-800">
            docker compose down
          </div>
        </div>
      </div>
    </div>
  );
};
