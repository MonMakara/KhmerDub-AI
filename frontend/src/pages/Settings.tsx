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
} from 'lucide-react';
import { HealthResponse, TranslationProviderInfo } from '../types';
import { api } from '../services/api';

interface SettingsProps {
  health: HealthResponse | null;
}

export const Settings: React.FC<SettingsProps> = ({ health }) => {
  const [providers, setProviders] = useState<TranslationProviderInfo[]>([]);
  const [loadingProviders, setLoadingProviders] = useState<boolean>(true);
  const [apiKeyInput, setApiKeyInput] = useState<string>('');
  const [showApiKey, setShowApiKey] = useState<boolean>(false);
  const [selectedModel, setSelectedModel] = useState<string>('gemini-2.5-flash');
  const [testingConnection, setTestingConnection] = useState<boolean>(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [savingKey, setSavingKey] = useState<boolean>(false);
  const [statusMessage, setStatusMessage] = useState<{ text: string; isError: boolean } | null>(null);

  const fetchProviders = async () => {
    try {
      setLoadingProviders(true);
      const res = await api.getTranslationProviders();
      setProviders(res.providers);
      const gemini = res.providers.find((p) => p.id === 'gemini');
      if (gemini?.default_model) {
        setSelectedModel(gemini.default_model);
      }
    } catch (err: any) {
      console.error('Failed to load translation providers', err);
    } finally {
      setLoadingProviders(false);
    }
  };

  useEffect(() => {
    fetchProviders();
  }, []);

  const handleTestConnection = async () => {
    setTestingConnection(true);
    setTestResult(null);
    setStatusMessage(null);
    try {
      const res = await api.testTranslationConnection({
        provider: 'gemini',
        api_key: apiKeyInput.trim() || undefined,
        model: selectedModel,
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
    if (!apiKeyInput.trim()) {
      setStatusMessage({ text: 'Please enter a Gemini API key first.', isError: true });
      return;
    }
    setSavingKey(true);
    setStatusMessage(null);
    try {
      const res = await api.saveTranslationCredentials('gemini', apiKeyInput.trim());
      setStatusMessage({ text: res.message || 'API key saved securely.', isError: false });
      setApiKeyInput('');
      await fetchProviders();
    } catch (err: any) {
      setStatusMessage({ text: err.message || 'Failed to save API key.', isError: true });
    } finally {
      setSavingKey(false);
    }
  };

  const handleDeleteKey = async () => {
    if (!confirm('Are you sure you want to remove the saved Gemini API key?')) {
      return;
    }
    setStatusMessage(null);
    try {
      const res = await api.deleteTranslationCredentials('gemini');
      setStatusMessage({ text: res.message || 'API key removed.', isError: false });
      setApiKeyInput('');
      setTestResult(null);
      await fetchProviders();
    } catch (err: any) {
      setStatusMessage({ text: err.message || 'Failed to delete API key.', isError: true });
    }
  };

  const geminiProvider = providers.find((p) => p.id === 'gemini');
  const nllbProvider = providers.find((p) => p.id === 'nllb');

  return (
    <div className="space-y-6 max-w-5xl mx-auto">
      <div>
        <h2 className="text-xl font-bold text-slate-900">System Configuration</h2>
        <p className="text-xs text-slate-500 mt-1">
          Review environment parameters, AI translation providers, hardware allocation, and storage mount points.
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
              <h3 className="text-sm font-semibold text-slate-800">AI Translation Providers</h3>
              <p className="text-xs text-slate-500">
                Configure Meta NLLB-200 (local offline) and Google Gemini (cloud API)
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

        {/* Local vs Cloud Providers Overview */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* NLLB Provider Card */}
          <div className="p-4 rounded-xl border border-slate-200 bg-slate-50/50 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-slate-800 text-sm">{nllbProvider?.name || 'Meta NLLB-200'}</span>
                <span className="text-[10px] bg-emerald-100 text-emerald-800 font-medium px-2 py-0.5 rounded-full">
                  Free & Local
                </span>
              </div>
              <span className="text-xs font-medium text-emerald-600 flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" /> Ready
              </span>
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              {nllbProvider?.description || 'Offline neural translation running locally inside Docker. No API key or internet connection required.'}
            </p>
            <div className="text-[11px] text-slate-500 bg-white p-2.5 rounded-lg border border-slate-200">
              <span className="font-medium text-slate-700">Capabilities: </span>
              Batch translation, offline privacy, zero API cost.
            </div>
          </div>

          {/* Google Gemini Card */}
          <div className="p-4 rounded-xl border border-indigo-200 bg-indigo-50/30 space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="font-semibold text-slate-800 text-sm">{geminiProvider?.name || 'Google Gemini'}</span>
                <span className="text-[10px] bg-indigo-100 text-indigo-800 font-medium px-2 py-0.5 rounded-full flex items-center gap-1">
                  <Sparkles className="w-2.5 h-2.5 text-indigo-600" /> AI LLM
                </span>
              </div>
              {geminiProvider?.is_configured ? (
                <span className="text-xs font-medium text-emerald-600 flex items-center gap-1">
                  <CheckCircle2 className="w-3.5 h-3.5" /> Configured
                </span>
              ) : (
                <span className="text-xs font-medium text-amber-600 flex items-center gap-1">
                  <AlertCircle className="w-3.5 h-3.5" /> Key Required
                </span>
              )}
            </div>
            <p className="text-xs text-slate-600 leading-relaxed">
              {geminiProvider?.description || 'Advanced LLM reasoning for high-accuracy spoken Khmer phrasing, style customization, and speech duration fitting.'}
            </p>
            <div className="text-[11px] text-slate-500 bg-white p-2.5 rounded-lg border border-slate-200">
              <span className="font-medium text-slate-700">Capabilities: </span>
              Natural phrasing, 5 translation styles, 1-click alternative suggestions.
            </div>
          </div>
        </div>

        {/* Gemini API Key Management Form */}
        <div className="p-5 rounded-xl border border-slate-200 bg-slate-50 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-slate-800 font-semibold text-xs">
              <Key className="w-4 h-4 text-indigo-600" />
              <span>Google Gemini API Key Management</span>
            </div>
            {geminiProvider?.masked_key && (
              <span className="text-xs font-mono bg-white px-2.5 py-1 rounded-md border border-slate-200 text-slate-700">
                Active Key: <strong className="text-slate-900">{geminiProvider.masked_key}</strong>
              </span>
            )}
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            <div className="md:col-span-2 space-y-1">
              <label className="text-[11px] font-medium text-slate-600">Gemini API Key</label>
              <div className="relative">
                <input
                  type={showApiKey ? 'text' : 'password'}
                  placeholder={
                    geminiProvider?.is_configured
                      ? 'Enter new API key to replace existing...'
                      : 'AIzaSy...'
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

            <div className="space-y-1">
              <label className="text-[11px] font-medium text-slate-600">Model</label>
              <select
                value={selectedModel}
                onChange={(e) => setSelectedModel(e.target.value)}
                className="w-full text-xs px-3 py-2 bg-white border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500"
              >
                {(geminiProvider?.available_models || ['gemini-2.5-flash', 'gemini-1.5-flash', 'gemini-1.5-pro']).map((m) => (
                  <option key={m} value={m}>
                    {m} {m === 'gemini-2.5-flash' ? '(Recommended)' : ''}
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* Action Buttons */}
          <div className="flex flex-wrap items-center gap-2 pt-1">
            <button
              onClick={handleSaveKey}
              disabled={savingKey || !apiKeyInput.trim()}
              className="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 disabled:bg-slate-300 text-white text-xs font-medium rounded-lg shadow-sm transition flex items-center gap-1.5"
            >
              <ShieldCheck className="w-3.5 h-3.5" />
              {savingKey ? 'Saving...' : 'Save API Key'}
            </button>

            <button
              onClick={handleTestConnection}
              disabled={testingConnection || (!geminiProvider?.is_configured && !apiKeyInput.trim())}
              className="px-3.5 py-1.5 bg-white border border-slate-300 hover:bg-slate-100 disabled:opacity-50 text-slate-700 text-xs font-medium rounded-lg transition flex items-center gap-1.5"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${testingConnection ? 'animate-spin' : ''}`} />
              {testingConnection ? 'Testing...' : 'Test Connection'}
            </button>

            {geminiProvider?.is_configured && (
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
              Your API key is encrypted using Fernet (AES-128-CBC with SHA-256 HMAC) and stored securely at <code className="font-mono bg-slate-100 px-1 py-0.5 rounded text-slate-800">/app/data/.secrets/credentials.enc</code> with restricted file permissions.
              It is never committed to Git, logged, or returned in plain text to the browser.
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
