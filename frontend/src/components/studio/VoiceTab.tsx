import React, { useState, useEffect, useMemo } from 'react';
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
  X,
  AudioLines,
  Users,
  Edit2,
  Check,
} from 'lucide-react';
import {
  GeneratedAudio,
  TranslationSegment,
  TimingConflict,
  VoiceOption,
  CloneCandidate,
  ProjectSpeaker,
} from '../../types';
import { api } from '../../services/api';

interface VoiceTabProps {
  projectId?: string;
  projectTitle?: string;
  voices: VoiceOption[];
  selectedVoice: { provider: string; voice: string };
  generatedAudios: GeneratedAudio[];
  translationSegments: TranslationSegment[];
  timingConflicts: TimingConflict[];
  isGeneratingSpeech: boolean;
  onSelectVoice: (provider: string, voice: string) => Promise<void>;
  onSaveSegmentVoices: (ids: string[], provider: string | null, voice: string | null) => Promise<void>;
  onRefreshVoices: () => Promise<void>;
  onPreviewVoice: (provider: string, voice: string) => Promise<void>;
  onGenerateAllSpeech: () => Promise<void>;
  onRegenerateSegmentAudio: (segmentId: string) => Promise<void>;
  onOpenAIImprove: (segment: TranslationSegment) => void;
  onSeekVideo: (timestamp: number) => void;
  activeSegmentId?: string | null;
  selectedSegmentId?: string | null;
  ttsError?: string | null;
  previewAudioUrl?: string | null;
  previewingVoice?: string | null;
  onSpeakerVoiceChanged?: () => Promise<void>;
}

export const VoiceTab: React.FC<VoiceTabProps> = ({
  projectId,
  projectTitle,
  voices,
  selectedVoice,
  generatedAudios,
  translationSegments,
  timingConflicts,
  isGeneratingSpeech,
  onSelectVoice,
  onSaveSegmentVoices,
  onRefreshVoices,
  onPreviewVoice,
  onGenerateAllSpeech,
  onRegenerateSegmentAudio,
  onOpenAIImprove,
  onSeekVideo,
  activeSegmentId,
  selectedSegmentId,
  ttsError,
  previewAudioUrl,
  previewingVoice,
  onSpeakerVoiceChanged,
}) => {
  const [regeneratingId, setRegeneratingId] = useState<string | null>(null);
  const [selectedUnits, setSelectedUnits] = useState<Set<string>>(new Set());
  const [savingVoice, setSavingVoice] = useState(false);
  const [voiceError, setVoiceError] = useState<string | null>(null);
  const [bulkVoice, setBulkVoice] = useState('inherit');

  // Clone Voice from Video State
  const [showCloneModal, setShowCloneModal] = useState(false);
  const [isLoadingCandidates, setIsLoadingCandidates] = useState(false);
  const [candidates, setCandidates] = useState<CloneCandidate[]>([]);
  const [selectedCandidateId, setSelectedCandidateId] = useState<string | null>(null);
  const [customVoiceName, setCustomVoiceName] = useState('');
  const [consentConfirmed, setConsentConfirmed] = useState(true);
  const [storeInVoiceStudio, setStoreInVoiceStudio] = useState(true);
  const [isCloning, setIsCloning] = useState(false);
  const [cloneError, setCloneError] = useState<string | null>(null);
  const [cloneSuccess, setCloneSuccess] = useState<string | null>(null);

  // Multi-Speaker Diarization State
  const [speakers, setSpeakers] = useState<ProjectSpeaker[]>([]);
  const [isDiarizing, setIsDiarizing] = useState(false);
  const [saveMultiToStudio, setSaveMultiToStudio] = useState(false);
  const [isCloningSpeakers, setIsCloningSpeakers] = useState(false);
  const [diarizeError, setDiarizeError] = useState<string | null>(null);
  const [diarizeSuccess, setDiarizeSuccess] = useState<string | null>(null);
  const [minSpeakers, setMinSpeakers] = useState<number>(1);
  const [maxSpeakers, setMaxSpeakers] = useState<number>(4);
  const [editingSpeakerLabel, setEditingSpeakerLabel] = useState<string | null>(null);
  const [editingSpeakerName, setEditingSpeakerName] = useState<string>('');
  const [isSavingSpeaker, setIsSavingSpeaker] = useState(false);
  const [isAutoCloningAll, setIsAutoCloningAll] = useState(false);

  const fetchSpeakers = async () => {
    if (!projectId) return;
    try {
      const data = await api.getProjectSpeakers(projectId);
      setSpeakers(data);
    } catch (e: any) {
      console.warn('Could not load speakers:', e);
    }
  };

  useEffect(() => {
    fetchSpeakers();
  }, [projectId]);

  const handleRunDiarization = async () => {
    if (!projectId) return;
    setIsDiarizing(true);
    setDiarizeError(null);
    setDiarizeSuccess(null);
    try {
      const res = await api.runProjectDiarization(projectId, minSpeakers, maxSpeakers);
      setSpeakers(res.speakers);
      setDiarizeSuccess(
        `Successfully detected ${res.speakers_detected} character(s) across ${res.assigned_segments_count} segments!`
      );
      if (onSpeakerVoiceChanged) {
        await onSpeakerVoiceChanged();
      } else {
        await onRefreshVoices();
      }
      setTimeout(() => setDiarizeSuccess(null), 5000);
    } catch (err: any) {
      setDiarizeError(err.message || 'Diarization failed');
    } finally {
      setIsDiarizing(false);
    }
  };

  const handleSaveSpeakerVoice = async (
    speakerLabel: string,
    voiceKeyStr: string
  ) => {
    if (!projectId) return;
    setIsSavingSpeaker(true);
    setDiarizeError(null);
    try {
      const [provider, voiceId] = JSON.parse(voiceKeyStr);
      const updated = await api.updateProjectSpeaker(projectId, speakerLabel, {
        assigned_voice_provider: provider,
        assigned_voice_id: voiceId,
      });
      setSpeakers((prev) =>
        prev.map((s) => (s.speaker_label === speakerLabel ? updated : s))
      );
      setDiarizeSuccess(`Voice updated for ${updated.display_name}!`);
      if (onSpeakerVoiceChanged) {
        await onSpeakerVoiceChanged();
      } else {
        await onRefreshVoices();
      }
      setTimeout(() => setDiarizeSuccess(null), 4000);
    } catch (err: any) {
      setDiarizeError(err.message || 'Failed to update speaker voice');
    } finally {
      setIsSavingSpeaker(false);
    }
  };

  const handleSaveSpeakerName = async (speakerLabel: string) => {
    if (!projectId || !editingSpeakerName.trim()) {
      setEditingSpeakerLabel(null);
      return;
    }
    setIsSavingSpeaker(true);
    try {
      const updated = await api.updateProjectSpeaker(projectId, speakerLabel, {
        display_name: editingSpeakerName.trim(),
      });
      setSpeakers((prev) =>
        prev.map((s) => (s.speaker_label === speakerLabel ? updated : s))
      );
      setEditingSpeakerLabel(null);
    } catch (err: any) {
      setDiarizeError(err.message || 'Failed to rename speaker');
    } finally {
      setIsSavingSpeaker(false);
    }
  };

  const speakerNameMap = useMemo(() => {
    const map: Record<string, string> = {};
    for (const s of speakers) {
      map[s.speaker_label] = s.display_name;
    }
    return map;
  }, [speakers]);

  const getSpeakerTheme = (color: string) => {
    switch (color?.toLowerCase()) {
      case 'emerald':
        return {
          bg: 'bg-emerald-50',
          border: 'border-emerald-200',
          text: 'text-emerald-700',
          badgeBg: 'bg-emerald-500',
          avatarBg: 'bg-emerald-100 text-emerald-800 border-emerald-300',
        };
      case 'amber':
        return {
          bg: 'bg-amber-50',
          border: 'border-amber-200',
          text: 'text-amber-700',
          badgeBg: 'bg-amber-500',
          avatarBg: 'bg-amber-100 text-amber-800 border-amber-300',
        };
      case 'rose':
        return {
          bg: 'bg-rose-50',
          border: 'border-rose-200',
          text: 'text-rose-700',
          badgeBg: 'bg-rose-500',
          avatarBg: 'bg-rose-100 text-rose-800 border-rose-300',
        };
      case 'cyan':
        return {
          bg: 'bg-cyan-50',
          border: 'border-cyan-200',
          text: 'text-cyan-700',
          badgeBg: 'bg-cyan-500',
          avatarBg: 'bg-cyan-100 text-cyan-800 border-cyan-300',
        };
      case 'purple':
        return {
          bg: 'bg-purple-50',
          border: 'border-purple-200',
          text: 'text-purple-700',
          badgeBg: 'bg-purple-500',
          avatarBg: 'bg-purple-100 text-purple-800 border-purple-300',
        };
      case 'teal':
        return {
          bg: 'bg-teal-50',
          border: 'border-teal-200',
          text: 'text-teal-700',
          badgeBg: 'bg-teal-500',
          avatarBg: 'bg-teal-100 text-teal-800 border-teal-300',
        };
      case 'orange':
        return {
          bg: 'bg-orange-50',
          border: 'border-orange-200',
          text: 'text-orange-700',
          badgeBg: 'bg-orange-500',
          avatarBg: 'bg-orange-100 text-orange-800 border-orange-300',
        };
      case 'indigo':
      default:
        return {
          bg: 'bg-indigo-50',
          border: 'border-indigo-200',
          text: 'text-indigo-700',
          badgeBg: 'bg-indigo-500',
          avatarBg: 'bg-indigo-100 text-indigo-800 border-indigo-300',
        };
    }
  };

  const handleOpenCloneModal = async () => {
    if (!projectId) return;
    setShowCloneModal(true);
    setIsLoadingCandidates(true);
    setCloneError(null);
    setCloneSuccess(null);
    setCustomVoiceName(`${projectTitle || 'Video'} Speaker`);
    try {
      const data = await api.getCloneCandidates(projectId);
      setCandidates(data.candidates);
      setSelectedCandidateId(data.recommended_candidate_id || (data.candidates[0]?.candidate_id ?? null));
    } catch (err: any) {
      setCloneError(err.message || 'Failed to analyze video transcript for speech clips.');
    } finally {
      setIsLoadingCandidates(false);
    }
  };

  const handleExecuteClone = async () => {
    if (!projectId || !selectedCandidateId) return;
    const cand = candidates.find((c) => c.candidate_id === selectedCandidateId);
    if (!cand) return;

    setIsCloning(true);
    setCloneError(null);
    try {
      const profile = await api.cloneVoiceFromVideo(projectId, {
        start_time: cand.start_time,
        end_time: cand.end_time,
        voice_name: customVoiceName.trim(),
        set_as_project_voice: true,
        store_in_voice_studio: storeInVoiceStudio,
      });

      await onRefreshVoices();
      await onSelectVoice('voxcpm', profile.id);
      const storeMsg = storeInVoiceStudio ? 'and added to Voice Studio' : '(project-only, not stored in Voice Studio)';
      setCloneSuccess(`Cloned voice "${profile.name}" successfully created ${storeMsg} and set as active project voice!`);
      setTimeout(() => {
        setShowCloneModal(false);
        setCloneSuccess(null);
      }, 2500);
    } catch (err: any) {
      setCloneError(err.message || 'Failed to clone voice from video.');
    } finally {
      setIsCloning(false);
    }
  };

  const handleCloneSpeakers = async (targetSpeakerLabel?: string) => {
    if (!projectId) return;
    setIsCloningSpeakers(true);
    setDiarizeError(null);
    setDiarizeSuccess(null);
    try {
      const res = await api.cloneSpeakerVoices(projectId, {
        speaker_label: targetSpeakerLabel || null,
        store_in_voice_studio: saveMultiToStudio,
      });
      await fetchSpeakers();
      const storageNote = saveMultiToStudio ? 'and saved to Voice Studio' : '(project-only, not stored in Voice Studio)';
      setDiarizeSuccess(`Successfully cloned ${res.created_profiles_count} character voice(s) ${storageNote}!`);
      if (onSpeakerVoiceChanged) {
        await onSpeakerVoiceChanged();
      } else {
        await onRefreshVoices();
      }
      setTimeout(() => setDiarizeSuccess(null), 5000);
    } catch (err: any) {
      setDiarizeError(err.message || 'Failed to clone character voices');
    } finally {
      setIsCloningSpeakers(false);
    }
  };

  const handleAutoDetectAndClone = async () => {
    if (!projectId) return;
    setIsAutoCloningAll(true);
    setDiarizeError(null);
    setDiarizeSuccess(null);
    try {
      const res = await api.autoDetectAndCloneSpeakers(projectId, {
        min_speakers: minSpeakers,
        max_speakers: maxSpeakers,
        store_in_voice_studio: saveMultiToStudio,
      });
      setSpeakers(res.speakers);
      setDiarizeSuccess(res.message);
      if (onSpeakerVoiceChanged) {
        await onSpeakerVoiceChanged();
      } else {
        await onRefreshVoices();
      }
      setTimeout(() => setDiarizeSuccess(null), 6000);
    } catch (err: any) {
      setDiarizeError(err.message || 'Auto-detect and voice cloning failed');
    } finally {
      setIsAutoCloningAll(false);
    }
  };
  const voiceKey = (provider: string, voice: string) => JSON.stringify([provider, voice]);
  const saveVoices = async (ids: string[], key: string) => {
    setSavingVoice(true); setVoiceError(null);
    try {
      const pair: [string | null, string | null] = key === 'inherit' ? [null, null] : JSON.parse(key);
      await onSaveSegmentVoices(ids, pair[0], pair[1]);
    } catch (error) {
      setVoiceError(error instanceof Error ? error.message : 'Could not save voice selection.');
    } finally { setSavingVoice(false); }
  };

  // Audio map by translation_segment_id
  const audioMap = new Map<string, GeneratedAudio>();
  generatedAudios.forEach((a) => {
    if (a.translation_segment_id) audioMap.set(a.translation_segment_id, a);
  });

  // Conflict map by segment_order
  const conflictMap = new Map<number, TimingConflict>();
  timingConflicts.forEach((c) => conflictMap.set(c.segment_order, c));

  // Scroll matching segment into view when selected from timeline
  React.useEffect(() => {
    if (!selectedSegmentId) return;
    const el =
      document.getElementById(`voice-seg-${selectedSegmentId}`) ||
      document.getElementById(`voice-seg-trans-${selectedSegmentId}`);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [selectedSegmentId]);

  const handleRegenerate = async (segmentId: string) => {
    try {
      setRegeneratingId(segmentId);
      await onRegenerateSegmentAudio(segmentId);
    } catch (err: any) {
      setVoiceError(`Error generating audio: ${err.message}`);
    } finally {
      setRegeneratingId(null);
    }
  };

  const availableVoices = voices.filter((v) => v.language?.split('-')[0] === 'km');
  const effective = (seg: TranslationSegment) => ({
    provider: seg.effective_tts_provider || seg.voice_override_provider || selectedVoice.provider,
    voice: seg.effective_tts_voice || seg.voice_override_id || selectedVoice.voice,
  });
  const voiceLabel = (provider: string, voice: string) =>
    availableVoices.find((v) => v.provider === provider && v.voice === voice)?.label || `${provider}: ${voice}`;
  const selectedOption = (seg: TranslationSegment) => {
    const pair = effective(seg);
    return availableVoices.find((v) => v.provider === pair.provider && v.voice === pair.voice);
  };
  const hasUnavailable = translationSegments.some((seg) => !selectedOption(seg) || selectedOption(seg)?.is_available === false);

  const totalSegments = translationSegments.length;
  const currentCount = translationSegments.filter((seg) => {
    const audio = audioMap.get(seg.id);
    return audio && !audio.is_outdated && !seg.is_outdated;
  }).length;
  const outdatedCount = translationSegments.filter((seg) => {
    const audio = audioMap.get(seg.id);
    return audio && (audio.is_outdated || seg.is_outdated);
  }).length;
  const missingCount = translationSegments.filter((seg) => {
    const audio = audioMap.get(seg.id);
    return !audio;
  }).length;

  return (
    <div className="space-y-6">
      {/* Voice Selection Cards */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-100">
          <div>
            <div className="flex items-center gap-2">
              <Mic2 className="w-5 h-5 text-indigo-600" />
              <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wide">
                Project Default Voice
              </h3>
            </div>
            <p className="text-xs text-slate-500">
              Units inherit this voice unless you select an individual override below.
            </p>
          </div>

          <div className="flex items-center gap-2.5">
            {projectId && (
              <button
                type="button"
                onClick={handleOpenCloneModal}
                disabled={isGeneratingSpeech}
                className="px-3.5 py-2 rounded-xl bg-purple-50 hover:bg-purple-100 border border-purple-200 text-purple-700 text-xs font-semibold shadow-xs transition flex items-center gap-1.5 shrink-0"
              >
                <Sparkles className="w-4 h-4 text-purple-600" />
                <span>Clone Voice from Video</span>
              </button>
            )}

            <button
              onClick={onGenerateAllSpeech}
              disabled={translationSegments.length === 0 || isGeneratingSpeech || savingVoice || hasUnavailable}
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
                  <span>
                    {timingConflicts.length > 0 && outdatedCount === 0 && missingCount === 0
                      ? `Fit Speech Timing (${timingConflicts.length})`
                      : outdatedCount > 0 || missingCount > 0
                      ? `Generate Speech (${currentCount}/${totalSegments} Current)`
                      : `All Speech Current (${totalSegments})`}
                  </span>
                </>
              )}
            </button>
          </div>
        </div>

        {/* Voice Option Cards Grid */}
        <p className="text-xs text-slate-500">Speech generation checks timing automatically and can rephrase machine translations for the selected voice. Manually edited text is preserved. Any remaining timing conflict needs review; speech is never cut to fit.</p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {availableVoices.map((voice) => {
            const isSelected =
              selectedVoice.provider === voice.provider && selectedVoice.voice === voice.voice;
            const isPreviewing = previewingVoice === `${voice.provider}-${voice.voice}`;
            const isUnavailable = voice.is_available === false;

            return (
              <div
                key={`${voice.provider}-${voice.voice}`}
                onClick={() => {
                  if (isUnavailable) {
                    alert('The custom voice service is currently offline. Please check System Status in Settings or select an available standard voice.');
                    return;
                  }
                  onSelectVoice(voice.provider, voice.voice);
                }}
                className={`p-4 rounded-xl border-2 transition-all cursor-pointer flex flex-col justify-between space-y-3 ${
                  isSelected
                    ? 'border-indigo-600 bg-indigo-50/40 shadow-sm'
                    : isUnavailable
                    ? 'border-slate-200 bg-slate-50/70 opacity-75 hover:border-slate-300'
                    : 'border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50/50'
                }`}
              >
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-sm text-slate-900">{voice.label}</span>
                    <div className="flex items-center gap-1.5">
                      {voice.is_custom && (
                        <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-amber-100 text-amber-800 flex items-center gap-0.5">
                          <Sparkles className="w-2.5 h-2.5" />
                          Clone
                        </span>
                      )}
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
                  </div>

                  <p className="text-[11px] text-slate-500 leading-relaxed">
                    {voice.description}
                  </p>

                  <div className="flex items-center justify-between pt-1">
                    <span className="text-[10px] font-mono text-slate-400 block uppercase">
                      Provider: {voice.provider}
                    </span>
                    {isUnavailable && (
                      <span className="text-[10px] font-semibold text-rose-600 flex items-center gap-1">
                        <AlertCircle className="w-3 h-3" />
                        {voice.availability_reason || 'Unavailable'}
                      </span>
                    )}
                  </div>
                </div>

                <div className="pt-2 border-t border-slate-100 flex items-center justify-between">
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation();
                      if (isUnavailable) {
                        alert('Custom voice service is offline. Cannot preview custom voice.');
                        return;
                      }
                      onPreviewVoice(voice.provider, voice.voice);
                    }}
                    disabled={isPreviewing || isUnavailable}
                    className="px-2.5 py-1 rounded-md bg-white border border-slate-200 hover:bg-slate-100 disabled:opacity-50 text-slate-700 text-xs font-medium flex items-center gap-1 transition"
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

      {/* Character Voice Casting (Multi-Speaker Diarization) Card */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4">
        <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 pb-3 border-b border-slate-100">
          <div>
            <div className="flex items-center gap-2">
              <Users className="w-5 h-5 text-indigo-600" />
              <h3 className="text-sm font-bold text-slate-900 uppercase tracking-wide">
                Character Voice Casting
              </h3>
              {speakers.length > 0 && (
                <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-indigo-100 text-indigo-800">
                  {speakers.length} Characters
                </span>
              )}
            </div>
            <p className="text-xs text-slate-500">
              Automatically identify distinct speakers, vocal pitch, and cast character voices in bulk.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <div className="flex items-center gap-1.5 text-xs text-slate-600 bg-slate-50 border border-slate-200 rounded-xl px-2.5 py-1.5">
              <span>Speakers:</span>
              <select
                aria-label="Min speakers"
                value={minSpeakers}
                onChange={(e) => setMinSpeakers(Number(e.target.value))}
                className="bg-transparent font-semibold text-slate-800 outline-hidden"
              >
                <option value={1}>Min: 1</option>
                <option value={2}>Min: 2</option>
                <option value={3}>Min: 3</option>
              </select>
              <span className="text-slate-300">|</span>
              <select
                aria-label="Max speakers"
                value={maxSpeakers}
                onChange={(e) => setMaxSpeakers(Number(e.target.value))}
                className="bg-transparent font-semibold text-slate-800 outline-hidden"
              >
                <option value={2}>Max: 2</option>
                <option value={4}>Max: 4</option>
                <option value={6}>Max: 6</option>
                <option value={8}>Max: 8</option>
              </select>
            </div>

            {/* 1-Click Auto-Detect & Clone All Characters */}
            <button
              type="button"
              onClick={handleAutoDetectAndClone}
              disabled={isAutoCloningAll || isDiarizing || isCloningSpeakers || translationSegments.length === 0}
              className="px-4 py-2 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-700 hover:to-indigo-700 disabled:opacity-50 text-white text-xs font-bold shadow-xs transition flex items-center gap-1.5 shrink-0"
              title="1-Click: Detect all speakers in this video, extract reference voices, and clone each character with VoxCPM to speak Khmer"
            >
              {isAutoCloningAll ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Cloning All Voices...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  <span>{speakers.length > 0 ? 'Re-Detect & Clone Voices' : 'Auto-Detect & Clone Voices'}</span>
                </>
              )}
            </button>

            <button
              type="button"
              onClick={handleRunDiarization}
              disabled={isDiarizing || isAutoCloningAll || translationSegments.length === 0}
              className="px-3 py-2 rounded-xl bg-slate-100 hover:bg-slate-200 disabled:opacity-50 text-slate-700 text-xs font-semibold transition flex items-center gap-1.5 shrink-0"
              title="Only detect and cluster speaking characters without cloning voices"
            >
              {isDiarizing ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                  <span>Analyzing...</span>
                </>
              ) : (
                <>
                  <Users className="w-3.5 h-3.5 text-slate-500" />
                  <span>Detect Only</span>
                </>
              )}
            </button>

            {speakers.length > 0 && (
              <div className="flex items-center gap-2 pl-1 border-l border-slate-200">
                <label
                  className="flex items-center gap-1.5 text-xs text-slate-700 bg-slate-50 border border-slate-200 rounded-xl px-2.5 py-1.5 cursor-pointer hover:bg-slate-100 transition"
                  title="When checked, cloned character voices will also be saved in your global Voice Studio library. Uncheck to keep project voices private."
                >
                  <input
                    type="checkbox"
                    checked={saveMultiToStudio}
                    onChange={(e) => setSaveMultiToStudio(e.target.checked)}
                    className="rounded text-purple-600 focus:ring-purple-500"
                  />
                  <span>Save to Voice Studio</span>
                </label>

                <button
                  type="button"
                  onClick={() => handleCloneSpeakers()}
                  disabled={isCloningSpeakers || isDiarizing || isAutoCloningAll}
                  className="px-3.5 py-2 rounded-xl bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white text-xs font-semibold shadow-xs transition flex items-center gap-1.5 shrink-0"
                  title="Auto-clone voices for all detected characters from their speech in this video"
                >
                  {isCloningSpeakers ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      <span>Cloning Characters...</span>
                    </>
                  ) : (
                    <>
                      <Sparkles className="w-4 h-4" />
                      <span>Auto-Clone All Characters</span>
                    </>
                  )}
                </button>
              </div>
            )}
          </div>
        </div>

        {/* Diarization Notifications */}
        {diarizeError && (
          <div className="p-3 bg-rose-50 border border-rose-200 rounded-xl text-rose-800 text-xs flex items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-rose-600 shrink-0" />
              <span>{diarizeError}</span>
            </div>
            <button onClick={() => setDiarizeError(null)} className="text-rose-500 hover:text-rose-700">
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {diarizeSuccess && (
          <div className="p-3 bg-emerald-50 border border-emerald-200 rounded-xl text-emerald-800 text-xs flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span>{diarizeSuccess}</span>
          </div>
        )}

        {/* Speaker Cards or Empty State */}
        {speakers.length === 0 ? (
          <div className="p-8 rounded-xl border border-dashed border-purple-200 bg-gradient-to-b from-purple-50/40 to-slate-50/50 text-center space-y-3">
            <div className="w-12 h-12 rounded-full bg-purple-100 border border-purple-200 text-purple-700 flex items-center justify-center mx-auto shadow-xs">
              <Sparkles className="w-6 h-6" />
            </div>
            <div className="space-y-1">
              <p className="text-sm font-bold text-slate-900">Multi-Speaker Voice Cloning</p>
              <p className="text-xs text-slate-600 max-w-md mx-auto">
                If your video features multiple actors or hosts, KhmerDub AI can automatically detect each speaker, extract their reference speech, and clone their voices so each character speaks Khmer with their original vocal style.
              </p>
            </div>
            <div className="pt-2">
              <button
                type="button"
                onClick={handleAutoDetectAndClone}
                disabled={isAutoCloningAll || isDiarizing || translationSegments.length === 0}
                className="px-5 py-2.5 rounded-xl bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-700 hover:to-indigo-700 disabled:opacity-50 text-white text-xs font-bold shadow-md transition inline-flex items-center gap-2"
              >
                {isAutoCloningAll ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    <span>Detecting Speakers & Cloning Reference Voices...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4" />
                    <span>Auto-Detect & Clone All Voices from Video</span>
                  </>
                )}
              </button>
            </div>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5 pt-1">
            {speakers.map((spk) => {
              const theme = getSpeakerTheme(spk.color);
              const isEditingThis = editingSpeakerLabel === spk.speaker_label;
              const currentVoiceKey = JSON.stringify([spk.assigned_voice_provider, spk.assigned_voice_id]);

              return (
                <div
                  key={spk.speaker_label}
                  className={`p-4 rounded-xl border ${theme.border} ${theme.bg} shadow-2xs space-y-3 transition`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2.5">
                      <div
                        className={`w-9 h-9 rounded-full flex items-center justify-center text-xs font-bold border ${theme.avatarBg}`}
                      >
                        {spk.speaker_label.replace('SPEAKER_', 'S')}
                      </div>

                      <div>
                        {isEditingThis ? (
                          <div className="flex items-center gap-1">
                            <input
                              type="text"
                              value={editingSpeakerName}
                              onChange={(e) => setEditingSpeakerName(e.target.value)}
                              onKeyDown={(e) => {
                                if (e.key === 'Enter') handleSaveSpeakerName(spk.speaker_label);
                                if (e.key === 'Escape') setEditingSpeakerLabel(null);
                              }}
                              className="text-xs font-bold px-2 py-0.5 rounded border border-slate-300 bg-white"
                              autoFocus
                            />
                            <button
                              type="button"
                              onClick={() => handleSaveSpeakerName(spk.speaker_label)}
                              className="p-1 text-emerald-600 hover:bg-emerald-100 rounded"
                            >
                              <Check className="w-3.5 h-3.5" />
                            </button>
                          </div>
                        ) : (
                          <div className="flex items-center gap-1.5 group">
                            <span className="text-xs font-bold text-slate-900">{spk.display_name}</span>
                            <button
                              type="button"
                              onClick={() => {
                                setEditingSpeakerLabel(spk.speaker_label);
                                setEditingSpeakerName(spk.display_name);
                              }}
                              className="opacity-0 group-hover:opacity-100 p-0.5 text-slate-400 hover:text-slate-700 transition"
                              title="Rename character"
                            >
                              <Edit2 className="w-3 h-3" />
                            </button>
                          </div>
                        )}
                        <div className="flex items-center gap-1.5">
                          <span className="text-[10px] font-mono text-slate-400">{spk.speaker_label}</span>
                          {spk.assigned_voice_provider === 'voxcpm' && (
                            <span className="inline-flex items-center gap-1 text-[10px] font-bold text-purple-700 bg-purple-100/90 border border-purple-200 px-1.5 py-0.2 rounded-md">
                              <Sparkles className="w-2.5 h-2.5 text-purple-600" />
                              <span>Cloned Voice</span>
                            </span>
                          )}
                        </div>
                      </div>
                    </div>

                    {/* Biometrics & Stats */}
                    <div className="text-right space-y-0.5">
                      <div className="flex items-center justify-end gap-1">
                        {spk.detected_gender === 'female' ? (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-rose-100 text-rose-800">
                            ♀ Female {spk.average_pitch_hz ? `(${Math.round(spk.average_pitch_hz)}Hz)` : ''}
                          </span>
                        ) : spk.detected_gender === 'male' ? (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-blue-100 text-blue-800">
                            ♂ Male {spk.average_pitch_hz ? `(${Math.round(spk.average_pitch_hz)}Hz)` : ''}
                          </span>
                        ) : (
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-semibold bg-slate-100 text-slate-700">
                            Voice {spk.average_pitch_hz ? `(${Math.round(spk.average_pitch_hz)}Hz)` : ''}
                          </span>
                        )}
                      </div>
                      <span className="text-[10px] text-slate-500 block">
                        {spk.segment_count} clips • {spk.total_duration}s
                      </span>
                    </div>
                  </div>

                  {/* Character Voice Dropdown */}
                  <div className="pt-2 border-t border-slate-200/60 flex items-center gap-2">
                    <span className="text-[11px] font-semibold text-slate-700 shrink-0">Cast Voice:</span>
                    <select
                      aria-label={`Voice for ${spk.display_name}`}
                      value={currentVoiceKey}
                      onChange={(e) => handleSaveSpeakerVoice(spk.speaker_label, e.target.value)}
                      disabled={isSavingSpeaker}
                      className="grow text-xs rounded-lg border border-slate-200 bg-white p-1.5 shadow-2xs font-medium text-slate-800 focus:border-indigo-500 outline-hidden"
                    >
                      {availableVoices.map((v) => {
                        const optKey = voiceKey(v.provider, v.voice);
                        return (
                          <option key={optKey} value={optKey} disabled={v.is_available === false}>
                            {v.label} ({v.gender}) {v.is_available === false ? '— Offline' : ''}
                          </option>
                        );
                      })}
                    </select>

                    <button
                      type="button"
                      onClick={() => {
                        if (spk.assigned_voice_provider && spk.assigned_voice_id) {
                          onPreviewVoice(spk.assigned_voice_provider, spk.assigned_voice_id);
                        }
                      }}
                      className="p-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-600 transition shrink-0"
                      title="Preview this character's voice"
                    >
                      <Volume2 className="w-3.5 h-3.5" />
                    </button>

                    <button
                      type="button"
                      onClick={() => handleCloneSpeakers(spk.speaker_label)}
                      disabled={isCloningSpeakers}
                      className="px-2 py-1.5 rounded-lg border border-purple-200 bg-purple-50 hover:bg-purple-100 text-purple-700 transition shrink-0 flex items-center gap-1 text-[11px] font-semibold"
                      title={`Extract audio and clone voice for ${spk.display_name}`}
                    >
                      <Sparkles className="w-3.5 h-3.5 text-purple-600" />
                      <span className="hidden sm:inline">Clone Voice</span>
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      <div className="bg-white border border-slate-200 rounded-xl p-4 space-y-3">
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <label className="flex items-center gap-2">
            <input type="checkbox" aria-label="Select all dubbing units"
              checked={translationSegments.length > 0 && selectedUnits.size === translationSegments.length}
              onChange={(e) => setSelectedUnits(new Set(e.target.checked ? translationSegments.map((s) => s.id) : []))} />
            {selectedUnits.size} selected
          </label>
          <select aria-label="Bulk segment voice" value={bulkVoice} onChange={(e) => setBulkVoice(e.target.value)} className="border rounded-lg p-2">
            <option value="inherit">Reset to project default</option>
            {availableVoices.map((v) => <option key={voiceKey(v.provider, v.voice)} value={voiceKey(v.provider, v.voice)} disabled={v.is_available === false}>
              {v.label}{v.is_available === false ? ` — ${v.availability_reason || 'Unavailable'}` : ''}
            </option>)}
          </select>
          <button disabled={!selectedUnits.size || savingVoice} onClick={() => saveVoices([...selectedUnits], bulkVoice)} className="px-3 py-2 rounded-lg bg-indigo-600 text-white disabled:opacity-50">Apply to selected</button>
          <button onClick={onRefreshVoices} className="text-indigo-700 underline">Refresh voices</button>
          <span role="status">{savingVoice ? 'Saving voice selection…' : 'Voice selections saved automatically'}</span>
        </div>
        {hasUnavailable && <p className="text-xs text-amber-800">A selected voice is unavailable. Refresh availability or choose another voice before generating that unit.</p>}
        {voiceError && <p role="alert" className="text-xs text-rose-700">{voiceError}</p>}
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
        <div className="flex flex-wrap items-center justify-between text-xs text-slate-500 px-1 gap-2">
          <div className="flex items-center gap-2">
            <span>
              Speech Status:{' '}
              <strong className="text-emerald-700 font-bold">{currentCount} Current</strong>
            </span>
            {outdatedCount > 0 && (
              <span className="text-amber-800 font-bold bg-amber-50 px-2 py-0.5 rounded border border-amber-200">
                {outdatedCount} Outdated
              </span>
            )}
            {missingCount > 0 && (
              <span className="text-slate-600 font-bold bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
                {missingCount} Missing
              </span>
            )}
          </div>
          {timingConflicts.length > 0 && outdatedCount === 0 && (
            <span className="text-amber-700 font-semibold flex items-center gap-1 bg-amber-50 px-2.5 py-0.5 rounded-full border border-amber-200">
              <AlertTriangle className="w-3.5 h-3.5 text-amber-600" />
              {timingConflicts.length} timing conflict(s) detected
            </span>
          )}
          {outdatedCount > 0 && (
            <span className="text-amber-700 text-[11px] font-medium flex items-center gap-1">
              <AlertCircle className="w-3.5 h-3.5 text-amber-600" />
              Click 'Generate Speech' to refresh outdated audio
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
            const isOutdated = Boolean(audio?.is_outdated || seg.is_outdated);
            const isMissing = !audio;
            const option = selectedOption(seg);
            const unavailable = !option || option.is_available === false;
            const pair = effective(seg);
            const selectionKey = seg.voice_override_id ? voiceKey(pair.provider, pair.voice) : 'inherit';
            const isActive =
              activeSegmentId &&
              (activeSegmentId === seg.id || activeSegmentId === seg.transcript_segment_id);
            const isSelected =
              Boolean(selectedSegmentId) &&
              (selectedSegmentId === seg.id || selectedSegmentId === seg.transcript_segment_id);

            return (
              <div
                key={seg.id}
                id={`voice-seg-${seg.transcript_segment_id || seg.id}`}
                className={`p-4 rounded-xl border transition-all ${
                  isSelected
                    ? 'ring-2 ring-indigo-500 bg-indigo-50/70 border-indigo-400 shadow-md'
                    : isActive
                    ? 'ring-1 ring-indigo-400 bg-indigo-50/30 border-indigo-300'
                    : isOutdated
                    ? 'bg-amber-50/30 border-amber-200'
                    : conflict && !isOutdated
                    ? 'bg-amber-50/40 border-amber-300'
                    : audio
                    ? 'bg-white border-slate-200'
                    : 'bg-slate-50/60 border-slate-200'
                }`}
              >
                {/* Segment Header */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2 border-b border-slate-100 text-xs">
                  <div className="flex flex-wrap items-center gap-2">
                    <input type="checkbox" aria-label={`Select segment ${seg.segment_order}`} checked={selectedUnits.has(seg.id)} onChange={(e) => {
                      const next = new Set(selectedUnits); if (e.target.checked) next.add(seg.id); else next.delete(seg.id); setSelectedUnits(next);
                    }} />
                    <span className="font-mono font-bold text-indigo-700 bg-indigo-50 px-2 py-0.5 rounded border border-indigo-200">
                      #{seg.segment_order}
                    </span>

                    {seg.speaker_label && (
                      <span className="px-2 py-0.5 rounded text-[10px] font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200 flex items-center gap-1">
                        <Users className="w-3 h-3 text-indigo-500" />
                        <span>{speakerNameMap[seg.speaker_label] || seg.speaker_label}</span>
                      </span>
                    )}

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

                    {seg.style && seg.style !== 'natural' && (
                      <span className="text-[10px] bg-purple-50 text-purple-800 border border-purple-200 px-2 py-0.5 rounded-full font-semibold">
                        🎭 {seg.style}
                      </span>
                    )}

                    {isOutdated && (
                      <span className="text-[10px] bg-amber-100 text-amber-900 border border-amber-300 px-2 py-0.5 rounded-full font-bold">
                        Audio Outdated (Regeneration Required)
                      </span>
                    )}

                    {!isOutdated && !isMissing && conflict && (
                      <span className="text-[10px] bg-amber-100 text-amber-900 border border-amber-300 px-2 py-0.5 rounded-full font-bold flex items-center gap-1 animate-pulse">
                        <AlertTriangle className="w-3 h-3 text-amber-600" />
                        {conflict.required_tempo <= 1 ? 'Delayed by earlier speech' : 'Exceeds by'} +{conflict.overflow_seconds.toFixed(2)}s
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-1.5 self-end sm:self-auto">
                    {!isOutdated && !isMissing && conflict && (
                      <button
                        onClick={() => conflict.required_tempo <= 1 ? onGenerateAllSpeech() : onOpenAIImprove(seg)}
                        disabled={isGeneratingSpeech}
                        className="px-2.5 py-1 rounded bg-amber-600 hover:bg-amber-700 text-white text-xs font-semibold flex items-center gap-1 shadow-sm transition"
                        title={conflict.required_tempo <= 1 ? 'Repair earlier timing conflicts without shortening this naturally fitting sentence' : 'Review a shorter translation to fit the speech window'}
                      >
                        <Sparkles className="w-3 h-3" />
                        <span>{conflict.required_tempo <= 1 ? 'Fit Speech Timing' : 'Shorten with AI'}</span>
                      </button>
                    )}

                    <button
                      onClick={() => handleRegenerate(seg.id)}
                      disabled={isRegenerating || isGeneratingSpeech || savingVoice || unavailable}
                      className="px-2.5 py-1 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold flex items-center gap-1 transition"
                      title="Regenerate speech audio for this segment"
                    >
                      <RotateCcw className={`w-3 h-3 ${isRegenerating ? 'animate-spin' : ''}`} />
                      <span>{isRegenerating ? 'Generating...' : audio ? 'Regenerate' : 'Generate'}</span>
                    </button>
                  </div>
                </div>

                <div className="pt-3 space-y-2 text-xs">
                  <label className="flex flex-wrap items-center gap-2">
                    Voice for segment #{seg.segment_order}
                    <select aria-label={`Voice for segment ${seg.segment_order}`} value={selectionKey} disabled={savingVoice}
                      onChange={(e) => saveVoices([seg.id], e.target.value)} className="border border-slate-300 rounded-lg p-2 bg-white max-w-full">
                      <option value="inherit">Inherit project default — {voiceLabel(selectedVoice.provider, selectedVoice.voice)}</option>
                      {!option && seg.voice_override_id && <option value={selectionKey} disabled>{pair.provider}: {pair.voice} — unavailable</option>}
                      {availableVoices.map((v) => <option key={voiceKey(v.provider, v.voice)} value={voiceKey(v.provider, v.voice)} disabled={v.is_available === false}>
                        {v.label}{v.is_available === false ? ` — ${v.availability_reason || 'Unavailable'}` : ''}
                      </option>)}
                    </select>
                  </label>
                  <p className={unavailable ? 'text-amber-800' : 'text-slate-600'}>
                    Selected: {voiceLabel(pair.provider, pair.voice)} · {unavailable ? option?.availability_reason || 'Unavailable or consent missing' : 'Available'}
                  </p>
                  {audio && <p className="text-slate-500">Recorded with: {voiceLabel(audio.provider, audio.voice)} · {isOutdated ? 'Outdated — regenerate to use selected voice' : 'Current audio'}</p>}
                  {seg.tts_error && <p role="alert" className="text-rose-700">Generation failed: {seg.tts_error}</p>}
                </div>
                {/* Segment Body: Khmer text + Audio Player */}
                <div className="pt-2.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <p className="font-khmer text-sm text-slate-900 font-semibold leading-relaxed flex-1">
                    {seg.khmer_text}
                  </p>

                  {audio ? (
                    <audio
                      controls
                      preload="metadata"
                      src={`${audio.audio_url || `/api/projects/${audio.project_id}/tts/${seg.id}/audio`}?t=${audio.updated_at ? new Date(audio.updated_at).getTime() : ''}`}
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

        {/* Custom Voice Profiles Banner */}
        <div className="mt-2 flex items-center justify-between text-xs text-slate-600 bg-slate-50 rounded-xl p-3 border border-slate-200">
          <div className="flex items-center gap-2">
            <Mic2 className="w-4 h-4 text-indigo-600 shrink-0" />
            <span>
              Looking for custom voice cloning? Manage authorized voice recordings and custom voice profiles in the{' '}
              <a
                href="#voices"
                className="font-semibold text-indigo-600 hover:text-indigo-800 underline"
              >
                Voice Studio
              </a>
              .
            </span>
          </div>
        </div>
      </div>

      {/* Clone Voice from Video Modal */}
      {showCloneModal && (
        <div className="fixed inset-0 z-50 bg-slate-900/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-2xl w-full p-6 shadow-2xl space-y-5 max-h-[90vh] overflow-y-auto border border-slate-100">
            <div className="flex items-start justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-xl bg-purple-100 text-purple-700">
                  <Sparkles className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-bold text-slate-900">Clone Voice from This Video</h3>
                  <p className="text-xs text-slate-500">
                    Extract clean speech directly from the video to condition a custom VoxCPM Khmer voice.
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setShowCloneModal(false)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {cloneError && (
              <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-center gap-2">
                <AlertCircle className="w-4 h-4 shrink-0" />
                <span>{cloneError}</span>
              </div>
            )}

            {cloneSuccess && (
              <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs flex items-center gap-2">
                <CheckCircle2 className="w-4 h-4 shrink-0" />
                <span>{cloneSuccess}</span>
              </div>
            )}

            {isLoadingCandidates ? (
              <div className="py-12 flex flex-col items-center justify-center gap-3 text-slate-500">
                <RefreshCw className="w-6 h-6 animate-spin text-purple-600" />
                <p className="text-sm font-medium">Scanning transcript for optimal reference speech clips...</p>
              </div>
            ) : candidates.length === 0 ? (
              <div className="py-8 text-center space-y-2">
                <AudioLines className="w-10 h-10 text-slate-300 mx-auto" />
                <p className="text-sm font-medium text-slate-700">No suitable speech clips found</p>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  Ensure the video has been transcribed with speech segments of at least 3 seconds before cloning.
                </p>
              </div>
            ) : (
              <div className="space-y-4">
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="text-xs font-bold text-slate-700 uppercase tracking-wide">
                      Select Speech Reference Clip
                    </label>
                    <span className="text-[11px] text-slate-400">
                      Ranked by clarity, speech rate & duration (4–7s optimal)
                    </span>
                  </div>

                  <div className="space-y-2.5 max-h-64 overflow-y-auto pr-1">
                    {candidates.map((c, idx) => {
                      const isSelected = selectedCandidateId === c.candidate_id;
                      return (
                        <div
                          key={c.candidate_id}
                          onClick={() => setSelectedCandidateId(c.candidate_id)}
                          className={`p-3.5 rounded-xl border-2 transition cursor-pointer space-y-2 ${
                            isSelected
                              ? 'border-purple-600 bg-purple-50/50'
                              : 'border-slate-200 bg-white hover:border-slate-300'
                          }`}
                        >
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <input
                                type="radio"
                                name="clone_candidate"
                                checked={isSelected}
                                onChange={() => setSelectedCandidateId(c.candidate_id)}
                                className="text-purple-600 focus:ring-purple-500"
                              />
                              <span className="text-xs font-bold text-slate-800">
                                Clip #{idx + 1} ({c.start_time.toFixed(1)}s – {c.end_time.toFixed(1)}s)
                              </span>
                              <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-slate-100 text-slate-600">
                                {c.duration.toFixed(1)}s
                              </span>
                            </div>

                            <span className="text-[10px] font-semibold px-2 py-0.5 rounded-full bg-purple-100 text-purple-700">
                              Score: {Math.round(c.score)}%
                            </span>
                          </div>

                          <p className="text-xs text-slate-600 italic line-clamp-2">
                            "{c.text}"
                          </p>

                          {projectId && (
                            <div className="pt-1">
                              <audio
                                controls
                                preload="none"
                                className="w-full h-8"
                                src={api.getPreviewCandidateUrl(projectId, c.start_time, c.end_time)}
                              />
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                </div>

                <div className="space-y-3 pt-2 border-t border-slate-100">
                  <div>
                    <label className="block text-xs font-bold text-slate-700 uppercase tracking-wide mb-1">
                      Cloned Voice Name
                    </label>
                    <input
                      type="text"
                      value={customVoiceName}
                      onChange={(e) => setCustomVoiceName(e.target.value)}
                      placeholder="e.g. Documentary Host Voice"
                      className="w-full px-3 py-2 rounded-xl border border-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-purple-500"
                    />
                  </div>

                  <label className="flex items-start gap-2.5 cursor-pointer text-xs text-slate-700 select-none p-2.5 rounded-xl border border-slate-200 bg-slate-50/70">
                    <input
                      type="checkbox"
                      checked={storeInVoiceStudio}
                      onChange={(e) => setStoreInVoiceStudio(e.target.checked)}
                      className="mt-0.5 rounded text-purple-600 focus:ring-purple-500"
                    />
                    <div>
                      <span className="font-semibold block">Store reference in Voice Studio library</span>
                      <span className="text-[11px] text-slate-500">
                        {storeInVoiceStudio
                          ? 'Voice will be saved in your Voice Studio for use across other projects.'
                          : 'Project only: Voice will dub this video without cluttering your permanent Voice Studio library.'}
                      </span>
                    </div>
                  </label>

                  <label className="flex items-start gap-2.5 cursor-pointer text-xs text-slate-600 select-none">
                    <input
                      type="checkbox"
                      checked={consentConfirmed}
                      onChange={(e) => setConsentConfirmed(e.target.checked)}
                      className="mt-0.5 rounded text-purple-600 focus:ring-purple-500"
                    />
                    <span>
                      I authorize extracting this audio sample from the uploaded video for voice cloning and synthesis in KhmerDub AI.
                    </span>
                  </label>
                </div>
              </div>
            )}

            <div className="pt-3 border-t border-slate-100 flex items-center justify-end gap-2.5">
              <button
                type="button"
                onClick={() => setShowCloneModal(false)}
                disabled={isCloning}
                className="px-4 py-2 rounded-xl border border-slate-200 text-slate-700 text-xs font-semibold hover:bg-slate-50 transition"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleExecuteClone}
                disabled={
                  isCloning ||
                  isLoadingCandidates ||
                  candidates.length === 0 ||
                  !selectedCandidateId ||
                  !consentConfirmed ||
                  !customVoiceName.trim()
                }
                className="px-5 py-2 rounded-xl bg-purple-600 hover:bg-purple-700 disabled:opacity-50 text-white text-xs font-semibold shadow-sm transition flex items-center gap-2"
              >
                {isCloning ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    <span>Extracting & Cloning Voice...</span>
                  </>
                ) : (
                  <>
                    <Sparkles className="w-4 h-4" />
                    <span>Clone & Set as Project Voice</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
