import React, { useState } from 'react';
import {
  Mic2,
  Volume2,
  RotateCcw,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Clock,
  Sparkles,
  AlertCircle,
} from 'lucide-react';
import {
  GeneratedAudio,
  TranslationSegment,
  TimingConflict,
  VoiceOption,
} from '../../types';

interface VoiceTabProps {
  voices: VoiceOption[];
  selectedVoice: { provider: string; voice: string };
  generatedAudios: GeneratedAudio[];
  translationSegments: TranslationSegment[];
  timingConflicts: TimingConflict[];
  isGeneratingSpeech: boolean;
  onSelectVoice: (provider: string, voice: string) => Promise<void>;
  onPreviewVoice: (provider: string, voice: string) => Promise<void>;
  onGenerateAllSpeech: () => Promise<void>;
  onRegenerateSegmentAudio: (segmentId: string) => Promise<void>;
  onOpenAIImprove: (segment: TranslationSegment) => void;
  onSeekVideo: (timestamp: number) => void;
  activeSegmentId?: string | null;
  ttsError?: string | null;
  previewAudioUrl?: string | null;
  previewingVoice?: string | null;
}

export const VoiceTab: React.FC<VoiceTabProps> = ({
  voices,
  selectedVoice,
  generatedAudios,
  translationSegments,
  timingConflicts,
  isGeneratingSpeech,
  onSelectVoice,
  onPreviewVoice,
  onGenerateAllSpeech,
  onRegenerateSegmentAudio,
  onOpenAIImprove,
  onSeekVideo,
  activeSegmentId,
  ttsError,
  previewAudioUrl,
  previewingVoice,
}) => {
  const [regeneratingId, setRegeneratingId] = useState<string | null>(null);

  // Audio map by translation_segment_id
  const audioMap = new Map<string, GeneratedAudio>();
  generatedAudios.forEach((a) => {
    if (a.translation_segment_id) audioMap.set(a.translation_segment_id, a);
  });

  // Conflict map by segment_order
  const conflictMap = new Map<number, TimingConflict>();
  timingConflicts.forEach((c) => conflictMap.set(c.segment_order, c));

  const handleRegenerate = async (segmentId: string) => {
    try {
      setRegeneratingId(segmentId);
      await onRegenerateSegmentAudio(segmentId);
    } catch (err: any) {
      alert(`Error regenerating audio: ${err.message}`);
    } finally {
      setRegeneratingId(null);
    }
  };

  const defaultVoices: VoiceOption[] = [
    {
      voice: 'default',
      label: 'Google Khmer',
      provider: 'gtts',
      gender: 'neutral',
      description: 'Standard natural Google Khmer Text-to-Speech synthesis.',
    },
    {
      voice: 'km-KH-PisethNeural',
      label: 'Microsoft Piseth',
      provider: 'edge',
      gender: 'male',
      description: 'Microsoft Neural male Cambodian voice with clear intonation.',
    },
    {
      voice: 'km-KH-SreymomNeural',
      label: 'Microsoft Sreymom',
      provider: 'edge',
      gender: 'female',
      description: 'Microsoft Neural female Cambodian voice with expressive cadence.',
    },
  ];

  const availableVoices = voices.length > 0 ? voices : defaultVoices;

  const totalGenerated = generatedAudios.filter((a) => !a.is_outdated).length;
  const totalSegments = translationSegments.length;

  return (
    <div className="space-y-6">
      {/* Voice Selection Cards */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
          <div>
            <div className="flex items-center gap-2">
              <Mic2 className="w-5 h-5 text-indigo-600" />
              <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wide">
                Khmer Voice Selection
              </h3>
            </div>
            <p className="text-xs text-slate-500">
              Select the voice model for speech synthesis. Preview sample speech before generating.
            </p>
          </div>

          <button
            onClick={onGenerateAllSpeech}
            disabled={translationSegments.length === 0 || isGeneratingSpeech}
            className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-xs font-semibold shadow-sm transition flex items-center gap-2 shrink-0"
          >
            {isGeneratingSpeech ? (
              <>
                <RefreshCw className="w-4 h-4 animate-spin" />
                <span>Generating Khmer Speech...</span>
              </>
            ) : (
              <>
                <Volume2 className="w-4 h-4" />
                <span>Generate Speech ({totalGenerated}/{totalSegments})</span>
              </>
            )}
          </button>
        </div>

        {/* Voice Option Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {availableVoices.map((voice) => {
            const isSelected =
              selectedVoice.provider === voice.provider && selectedVoice.voice === voice.voice;
            const isPreviewing = previewingVoice === `${voice.provider}-${voice.voice}`;

            return (
              <div
                key={`${voice.provider}-${voice.voice}`}
                onClick={() => onSelectVoice(voice.provider, voice.voice)}
                className={`p-4 rounded-xl border-2 transition-all cursor-pointer flex flex-col justify-between space-y-3 ${
                  isSelected
                    ? 'border-indigo-600 bg-indigo-50/40 shadow-sm'
                    : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50/50'
                }`}
              >
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-sm text-slate-900">{voice.label}</span>
                    <span
                      className={`text-[10px] font-semibold px-2 py-0.5 rounded-full capitalize ${
                        voice.gender === 'female'
                          ? 'bg-purple-100 text-purple-700'
                          : voice.gender === 'male'
                          ? 'bg-blue-100 text-blue-700'
                          : 'bg-emerald-100 text-emerald-700'
                      }`}
                    >
                      {voice.gender}
                    </span>
                  </div>

                  <p className="text-[11px] text-slate-500 leading-relaxed">
                    {voice.description}
                  </p>

                  <span className="text-[10px] font-mono text-slate-400 block uppercase">
                    Provider: {voice.provider}
                  </span>
                </div>

                <div className="pt-2 border-t border-slate-100 flex items-center justify-between">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      onPreviewVoice(voice.provider, voice.voice);
                    }}
                    disabled={isPreviewing}
                    className="px-2.5 py-1 rounded-md bg-white border border-slate-200 hover:bg-slate-100 text-slate-700 text-xs font-medium flex items-center gap-1 transition"
                  >
                    <Volume2 className={`w-3.5 h-3.5 ${isPreviewing ? 'animate-bounce text-indigo-600' : ''}`} />
                    <span>{isPreviewing ? 'Playing...' : 'Preview Voice'}</span>
                  </button>

                  {isSelected && (
                    <span className="text-xs font-semibold text-indigo-600 flex items-center gap-1">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      Active
                    </span>
                  )}
                </div>
              </div>
            );
          })}
        </div>

        {/* Global Voice Preview Audio Player */}
        {previewAudioUrl && (
          <div className="p-3 bg-indigo-50 rounded-xl border border-indigo-200 flex items-center justify-between gap-3 text-xs animate-fadeIn">
            <span className="font-semibold text-indigo-900 flex items-center gap-1.5">
              <Volume2 className="w-4 h-4 text-indigo-600" />
              Sample Voice Audio:
            </span>
            <audio controls autoPlay src={previewAudioUrl} className="h-7 w-64" />
          </div>
        )}
      </div>

      {/* Error Banner */}
      {ttsError && (
        <div className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-rose-800 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
            <span>{ttsError}</span>
          </div>
          <button
            onClick={onGenerateAllSpeech}
            className="px-3 py-1 rounded bg-rose-600 text-white font-semibold text-xs"
          >
            Retry
          </button>
        </div>
      )}

      {/* Generated Speech Segments List with Timing Warnings */}
      <div className="space-y-3">
        <div className="flex items-center justify-between text-xs text-slate-500 px-1">
          <span>
            Speech Segments: <strong className="text-slate-800 font-semibold">{totalGenerated} / {totalSegments}</strong> Generated
          </span>
          {timingConflicts.length > 0 && (
            <span className="text-amber-700 font-semibold flex items-center gap-1 bg-amber-50 px-2.5 py-0.5 rounded-full border border-amber-200">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
              {timingConflicts.length} timing conflict(s) detected
            </span>
          )}
        </div>

        <div className="space-y-3">
          {translationSegments.map((seg) => {
            const audio = audioMap.get(seg.id);
            const conflict = conflictMap.get(seg.segment_order);
            const availableDuration = (seg.end_time || 0) - (seg.start_time || 0);
            const speechDuration = audio?.duration_seconds || 0;
            const isRegenerating = regeneratingId === seg.id;
            const isActive =
              activeSegmentId &&
              (activeSegmentId === seg.id || activeSegmentId === seg.transcript_segment_id);

            return (
              <div
                key={seg.id}
                className={`p-4 rounded-xl border transition-all ${
                  isActive
                    ? 'ring-2 ring-indigo-500 bg-indigo-50/30 border-indigo-300'
                    : conflict
                    ? 'bg-amber-50/40 border-amber-300'
                    : audio
                    ? 'bg-white border-slate-200'
                    : 'bg-slate-50/60 border-slate-200'
                }`}
              >
                {/* Segment Header */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2 border-b border-slate-100 text-xs">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono font-bold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-200">
                      #{seg.segment_order}
                    </span>

                    <button
                      onClick={() => onSeekVideo(seg.start_time || 0)}
                      className="font-mono text-slate-600 hover:text-indigo-600 flex items-center gap-1"
                    >
                      <Clock className="w-3 h-3 text-slate-400" />
                      Window: {availableDuration.toFixed(2)}s
                    </button>

                    {audio && (
                      <span className="font-mono text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
                        Speech: {speechDuration.toFixed(2)}s
                      </span>
                    )}

                    {audio?.is_outdated && (
                      <span className="text-[10px] bg-amber-100 text-amber-900 border border-amber-300 px-2 py-0.5 rounded-full font-bold">
                        Audio Outdated (Text Edited)
                      </span>
                    )}

                    {conflict && (
                      <span className="text-[10px] bg-amber-100 text-amber-900 border border-amber-300 px-2 py-0.5 rounded-full font-bold flex items-center gap-1 animate-pulse">
                        <AlertTriangle className="w-3 h-3 text-amber-600" />
                        Exceeds by +{conflict.overflow_seconds.toFixed(2)}s
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-1.5 self-end sm:self-auto">
                    {conflict && (
                      <button
                        onClick={() => onOpenAIImprove(seg)}
                        className="px-2.5 py-1 rounded bg-amber-600 hover:bg-amber-700 text-white text-xs font-semibold flex items-center gap-1 shadow-sm transition"
                        title="Shorten translation text with AI to fit speech window"
                      >
                        <Sparkles className="w-3 h-3" />
                        <span>Shorten with AI</span>
                      </button>
                    )}

                    <button
                      onClick={() => handleRegenerate(seg.id)}
                      disabled={isRegenerating || isGeneratingSpeech}
                      className="px-2.5 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold flex items-center gap-1 transition"
                      title="Regenerate speech audio for this segment"
                    >
                      <RotateCcw className={`w-3 h-3 ${isRegenerating ? 'animate-spin' : ''}`} />
                      <span>{isRegenerating ? 'Generating...' : 'Regenerate'}</span>
                    </button>
                  </div>
                </div>

                {/* Segment Body: Khmer text + Audio Player */}
                <div className="pt-2.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <p className="font-khmer text-sm text-slate-900 font-semibold leading-relaxed flex-1">
                    {seg.khmer_text}
                  </p>

                  {audio ? (
                    <audio
                      controls
                      src={`/api/tts/stream/${audio.id}`}
                      className="w-full sm:w-64 h-8 shrink-0"
                    />
                  ) : (
                    <span className="text-xs text-slate-400 italic">No audio generated yet</span>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
};
