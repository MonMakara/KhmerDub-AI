import React, { useState } from 'react';
import {
  Sparkles,
  Layers,
  X,
  Check,
  RefreshCw,
  AlertCircle,
  Clock,
  ShieldCheck,
} from 'lucide-react';
import {
  TranslationSegment,
  AIImproveResponse,
  AlternativeOption,
  TranslationProviderInfo,
} from '../../types';
import { api } from '../../services/api';

interface AIImproveModalProps {
  segment: TranslationSegment;
  projectId: string;
  onClose: () => void;
  onApply: (khmerText: string, style?: string, explanation?: string) => Promise<void>;
  targetDuration?: number | null;
  activeProviderId?: string;
  providers: TranslationProviderInfo[];
  initialMode?: 'improve' | 'alternatives';
}

export const AIImproveModal: React.FC<AIImproveModalProps> = ({
  segment,
  projectId,
  onClose,
  onApply,
  targetDuration,
  activeProviderId = 'gemini',
  providers,
  initialMode = 'improve',
}) => {
  const [mode, setMode] = useState<'improve' | 'alternatives'>(initialMode);
  const [selectedStyle, setSelectedStyle] = useState<string>('natural');
  const [customPrompt, setCustomPrompt] = useState<string>('');

  // States for Improve
  const [improving, setImproving] = useState<boolean>(false);
  const [improveResult, setImproveResult] = useState<AIImproveResponse | null>(null);

  // States for Alternatives
  const [loadingAlts, setLoadingAlts] = useState<boolean>(false);
  const [alternatives, setAlternatives] = useState<AlternativeOption[]>([]);

  // Applying state
  const [applying, setApplying] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const activeProvider = providers.find((p) => p.id === activeProviderId) || {
    id: activeProviderId,
    name: activeProviderId.toUpperCase(),
    type: 'cloud_llm',
    description: '',
    requires_api_key: false,
    is_configured: true,
    masked_key: null,
    supports_styles: true,
    supports_alternatives: true,
    available_models: [],
  };

  const handleImprove = async () => {
    try {
      setImproving(true);
      setError(null);
      const res = await api.aiImproveSegment(projectId, segment.id, {
        style: selectedStyle,
        target_duration: targetDuration || undefined,
        custom_prompt: customPrompt.trim() || undefined,
      });
      setImproveResult(res);
    } catch (err: any) {
      setError(err.message || 'AI improvement failed');
    } finally {
      setImproving(false);
    }
  };

  const handleGenerateAlternatives = async () => {
    try {
      setLoadingAlts(true);
      setError(null);
      const res = await api.getTranslationAlternatives(projectId, segment.id);
      setAlternatives(res.alternatives);
    } catch (err: any) {
      setError(err.message || 'Failed to generate alternatives');
    } finally {
      setLoadingAlts(false);
    }
  };

  const handleApplyText = async (text: string, style?: string, exp?: string) => {
    try {
      setApplying(true);
      await onApply(text, style, exp);
      onClose();
    } catch (err: any) {
      setError(err.message || 'Failed to apply translation');
    } finally {
      setApplying(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl border border-slate-200 shadow-2xl w-full max-w-2xl max-h-[90vh] flex flex-col overflow-hidden animate-scaleIn">
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-indigo-50 text-indigo-600">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-bold text-slate-900">
                  AI Translation Assistant
                </h3>
                <span className="text-[10px] font-mono bg-indigo-100 text-indigo-800 font-semibold px-2 py-0.5 rounded-full">
                  Segment #{segment.segment_order}
                </span>
              </div>
              <p className="text-xs text-slate-500">
                Powered by {activeProvider.name} with Khmer glossary & timing adaptation
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Source Text Context Banner */}
        <div className="px-6 py-3 bg-slate-100/70 border-b border-slate-200 text-xs space-y-1">
          <div className="flex items-center justify-between text-slate-500 text-[11px]">
            <span className="font-semibold uppercase tracking-wider">English Source</span>
            {targetDuration && (
              <span className="font-mono text-indigo-700 font-medium flex items-center gap-1">
                <Clock className="w-3 h-3" /> Target Window: ~{targetDuration.toFixed(2)}s
              </span>
            )}
          </div>
          <p className="text-slate-800 font-medium">{segment.english_text || 'No English text available'}</p>
          <div className="pt-1 text-[11px] text-slate-500 flex items-center gap-1.5">
            <span className="font-medium text-slate-600">Current Khmer:</span>
            <span className="font-khmer text-slate-800 font-medium">{segment.khmer_text}</span>
          </div>
        </div>

        {/* Tab Switcher: Improve vs Alternatives */}
        <div className="px-6 pt-3 flex items-center gap-2 border-b border-slate-100">
          <button
            onClick={() => setMode('improve')}
            className={`pb-2.5 text-xs font-semibold flex items-center gap-1.5 border-b-2 transition ${
              mode === 'improve'
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
            <span>AI Refine & Improve</span>
          </button>

          <button
            onClick={() => {
              setMode('alternatives');
              if (alternatives.length === 0) {
                handleGenerateAlternatives();
              }
            }}
            className={`pb-2.5 text-xs font-semibold flex items-center gap-1.5 border-b-2 transition ${
              mode === 'alternatives'
                ? 'border-indigo-600 text-indigo-600'
                : 'border-transparent text-slate-500 hover:text-slate-800'
            }`}
          >
            <Layers className="w-3.5 h-3.5" />
            <span>3-Style Alternatives</span>
          </button>
        </div>

        {/* Modal Scrollable Body */}
        <div className="p-6 overflow-y-auto space-y-5 flex-1">
          {error && (
            <div className="p-3.5 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0 text-rose-600" />
              <span>{error}</span>
            </div>
          )}

          {/* Mode 1: AI Improve */}
          {mode === 'improve' && (
            <div className="space-y-4">
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                {/* Style */}
                <div className="space-y-1">
                  <label className="font-semibold text-slate-700">Dubbing Style</label>
                  <select
                    value={selectedStyle}
                    onChange={(e) => setSelectedStyle(e.target.value)}
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 font-medium"
                  >
                    <option value="natural">Natural Spoken (Default)</option>
                    <option value="short">Short for Video Dubbing</option>
                    <option value="simple">Simple & Clear Words</option>
                    <option value="formal">Formal / Professional</option>
                    <option value="standard">Standard Translation</option>
                  </select>
                </div>

                {/* Duration Hint */}
                <div className="space-y-1">
                  <label className="font-semibold text-slate-700">Duration Constraint</label>
                  <div className="px-3 py-2 bg-slate-50 border border-slate-200 rounded-lg text-slate-600 font-mono flex items-center justify-between">
                    <span>Available window:</span>
                    <strong className="text-slate-900">{targetDuration ? `${targetDuration.toFixed(2)}s` : 'Flexible'}</strong>
                  </div>
                </div>
              </div>

              {/* Unconfigured Provider Notice */}
              {activeProvider.requires_api_key && !activeProvider.is_configured && (
                <div className="p-3.5 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-xs flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 text-amber-600 shrink-0" />
                  <span>
                    <strong>{activeProvider.name}</strong> requires an API key to generate improvements. Please configure it in Settings or switch to an active provider.
                  </span>
                </div>
              )}

              {/* Custom Prompt Input */}
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-700 flex items-center justify-between">
                  <span>Custom Instruction (Optional)</span>
                  <span className="text-[11px] font-normal text-slate-400">e.g. "make more concise", "use friendly tone"</span>
                </label>
                <input
                  type="text"
                  value={customPrompt}
                  onChange={(e) => setCustomPrompt(e.target.value)}
                  placeholder="e.g. Shorten by 3 words to prevent tempo increase..."
                  disabled={activeProvider.requires_api_key && !activeProvider.is_configured}
                  className="w-full text-xs px-3.5 py-2 bg-slate-50 border border-slate-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 disabled:opacity-60"
                />
              </div>

              {/* Trigger Improve Button */}
              <button
                onClick={handleImprove}
                disabled={improving || (activeProvider.requires_api_key && !activeProvider.is_configured)}
                className="w-full py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs font-semibold shadow-sm transition flex items-center justify-center gap-2"
              >
                <Sparkles className={`w-4 h-4 ${improving ? 'animate-spin' : ''}`} />
                <span>{improving ? 'Refining Translation with AI...' : 'Generate AI Improvement'}</span>
              </button>

              {/* Result Preview Card */}
              {improveResult && (
                <div className="p-4 rounded-xl border border-indigo-200 bg-indigo-50/40 space-y-3 animate-fadeIn">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-bold text-indigo-900 flex items-center gap-1.5">
                      <Check className="w-4 h-4 text-emerald-600" />
                      Suggested Khmer Translation
                    </span>
                    <span className="text-[10px] bg-indigo-100 text-indigo-800 font-medium px-2 py-0.5 rounded-full capitalize">
                      {improveResult.style} mode
                    </span>
                  </div>

                  <p className="font-khmer text-base text-slate-900 font-semibold leading-relaxed bg-white p-3 rounded-lg border border-indigo-100">
                    {improveResult.improved_khmer_text}
                  </p>

                  <div className="text-[11px] text-slate-600 bg-white/70 p-2.5 rounded-lg border border-indigo-100/60 space-y-0.5">
                    <span className="font-semibold text-slate-700 block">AI Reasoning:</span>
                    <p>{improveResult.explanation}</p>
                  </div>

                  <div className="pt-1 flex items-center justify-between">
                    <span className="text-[11px] text-slate-400">
                      Model: {improveResult.model}
                    </span>
                    <button
                      onClick={() =>
                        handleApplyText(
                          improveResult.improved_khmer_text,
                          improveResult.style,
                          improveResult.explanation
                        )
                      }
                      disabled={applying}
                      className="px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold transition flex items-center gap-1.5 shadow-sm"
                    >
                      <Check className="w-3.5 h-3.5" />
                      <span>{applying ? 'Applying...' : 'Apply Translation'}</span>
                    </button>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Mode 2: 3-Style Alternatives */}
          {mode === 'alternatives' && (
            <div className="space-y-4">
              <div className="flex items-center justify-between">
                <span className="text-xs text-slate-500">
                  Compare 3 distinct translation styles side by side:
                </span>
                <button
                  onClick={handleGenerateAlternatives}
                  disabled={loadingAlts}
                  className="px-3 py-1 rounded-lg border border-slate-300 text-slate-700 text-xs font-medium hover:bg-slate-50 transition flex items-center gap-1.5"
                >
                  <RefreshCw className={`w-3 h-3 ${loadingAlts ? 'animate-spin' : ''}`} />
                  <span>Regenerate</span>
                </button>
              </div>

              {loadingAlts ? (
                <div className="p-12 text-center space-y-2">
                  <RefreshCw className="w-6 h-6 text-indigo-600 animate-spin mx-auto" />
                  <p className="text-xs text-slate-500">Generating Natural, Simple, and Short translation alternatives...</p>
                </div>
              ) : alternatives.length === 0 ? (
                <div className="p-8 text-center bg-slate-50 rounded-xl border border-dashed border-slate-200">
                  <p className="text-xs text-slate-500">No alternatives loaded yet.</p>
                </div>
              ) : (
                <div className="space-y-3">
                  {alternatives.map((alt) => (
                    <div
                      key={alt.style}
                      className="p-3.5 rounded-xl border border-slate-200 bg-white hover:border-indigo-300 transition-all space-y-2"
                    >
                      <div className="flex items-center justify-between">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-xs text-slate-800">{alt.label}</span>
                          <span className="text-[10px] bg-slate-100 text-slate-600 px-1.5 py-0.5 rounded capitalize">
                            {alt.style}
                          </span>
                        </div>
                        <button
                          onClick={() => handleApplyText(alt.khmer_text, alt.style, alt.explanation || undefined)}
                          disabled={applying}
                          className="px-3 py-1 bg-indigo-50 hover:bg-indigo-600 text-indigo-700 hover:text-white rounded-md text-xs font-semibold transition flex items-center gap-1"
                        >
                          <Check className="w-3 h-3" />
                          <span>Apply</span>
                        </button>
                      </div>

                      <p className="font-khmer text-sm text-slate-900 font-semibold leading-relaxed">
                        {alt.khmer_text}
                      </p>

                      {alt.explanation && (
                        <p className="text-[11px] text-slate-500 leading-snug">
                          {alt.explanation}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="px-6 py-3 bg-slate-50 border-t border-slate-100 flex items-center justify-between text-[11px] text-slate-400">
          <span className="flex items-center gap-1">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
            Applying preserves manual correction flag and invalidates outdated audio.
          </span>
          <button
            onClick={onClose}
            className="px-3 py-1 rounded text-slate-500 hover:text-slate-800 text-xs font-medium"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
