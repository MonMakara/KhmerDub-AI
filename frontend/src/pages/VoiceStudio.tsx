import React, { useState, useEffect, useCallback, useRef } from 'react';
import {
  Mic2,
  Volume2,
  Plus,
  Play,
  Pause,
  Trash2,
  Edit2,
  ShieldCheck,
  AlertTriangle,
  RefreshCw,
  FileAudio,
  Upload,
  Clock,
  X,
  CheckCircle2,
} from 'lucide-react';
import { api } from '../services/api';
import {
  VoiceStudioData,
  VoiceProfile,
  VoiceOption,
  CreateVoiceProfilePayload,
  UpdateVoiceProfilePayload,
} from '../types';
import { formatCambodiaDateTime } from '../utils/date';

export const VoiceStudio: React.FC = () => {
  const [data, setData] = useState<VoiceStudioData | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Playback state for system voices
  const [previewingVoice, setPreviewingVoice] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState<boolean>(false);
  const systemAudioRef = useRef<HTMLAudioElement | null>(null);

  // Playback state for custom reference audio
  const [playingProfileId, setPlayingProfileId] = useState<string | null>(null);
  const customAudioRef = useRef<HTMLAudioElement | null>(null);

  // Modals
  const [isCreateModalOpen, setIsCreateModalOpen] = useState<boolean>(false);
  const [editingProfile, setEditingProfile] = useState<VoiceProfile | null>(null);
  const [deletingProfile, setDeletingProfile] = useState<VoiceProfile | null>(null);
  const [viewingConsentProfile, setViewingConsentProfile] = useState<VoiceProfile | null>(null);

  // Create form state
  const [formName, setFormName] = useState<string>('');
  const [formDesc, setFormDesc] = useState<string>('');
  const [formGender, setFormGender] = useState<string>('neutral');
  const [formSpeaker, setFormSpeaker] = useState<string>('');
  const [formAuthorizer, setFormAuthorizer] = useState<string>('');
  const [formConsent, setFormConsent] = useState<boolean>(false);
  const [formTranscript, setFormTranscript] = useState<string>('');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [createSubmitting, setCreateSubmitting] = useState<boolean>(false);
  const [createError, setCreateError] = useState<string | null>(null);

  // Edit form state
  const [editName, setEditName] = useState<string>('');
  const [editDesc, setEditDesc] = useState<string>('');
  const [editGender, setEditGender] = useState<string>('neutral');
  const [editTranscript, setEditTranscript] = useState<string>('');
  const [editSubmitting, setEditSubmitting] = useState<boolean>(false);
  const [editError, setEditError] = useState<string | null>(null);

  // Delete state
  const [deleteSubmitting, setDeleteSubmitting] = useState<boolean>(false);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await api.getVoiceStudio();
      setData(res);
    } catch (err: any) {
      console.error('Failed to load Voice Studio data:', err);
      setError(err.message || 'Failed to connect to Voice Studio.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Clean up audio players on unmount
  useEffect(() => {
    return () => {
      if (systemAudioRef.current) {
        systemAudioRef.current.pause();
      }
      if (customAudioRef.current) {
        customAudioRef.current.pause();
      }
    };
  }, []);

  // Handle system voice preview
  const handlePreviewSystemVoice = async (voice: VoiceOption) => {
    const key = `${voice.provider}:${voice.voice}`;
    if (previewingVoice === key && systemAudioRef.current && !systemAudioRef.current.paused) {
      systemAudioRef.current.pause();
      setPreviewingVoice(null);
      return;
    }

    try {
      setPreviewLoading(true);
      setPreviewingVoice(key);

      // Stop any custom audio playing
      if (customAudioRef.current) {
        customAudioRef.current.pause();
        setPlayingProfileId(null);
      }

      const blob = await api.previewVoice(
        voice.provider,
        voice.voice,
        'សួស្តីអ្នកទាំងអស់គ្នា។ សូមស្វាគមន៍មកកាន់ KhmerDub AI។'
      );
      const url = URL.createObjectURL(blob);

      if (systemAudioRef.current) {
        systemAudioRef.current.src = url;
        systemAudioRef.current.play();
      }
    } catch (err: any) {
      console.error('Failed to preview voice:', err);
      setPreviewingVoice(null);
    } finally {
      setPreviewLoading(false);
    }
  };

  // Handle custom profile reference audio playback
  const handleTogglePlayCustom = (profile: VoiceProfile) => {
    if (playingProfileId === profile.id && customAudioRef.current && !customAudioRef.current.paused) {
      customAudioRef.current.pause();
      setPlayingProfileId(null);
      return;
    }

    // Stop any system audio playing
    if (systemAudioRef.current) {
      systemAudioRef.current.pause();
      setPreviewingVoice(null);
    }

    const audioUrl = api.getVoiceProfileAudioUrl(profile.id);
    setPlayingProfileId(profile.id);

    if (customAudioRef.current) {
      customAudioRef.current.src = audioUrl;
      customAudioRef.current.play().catch((err) => {
        console.error('Audio playback error:', err);
        setPlayingProfileId(null);
      });
    }
  };

  // Handle create voice profile
  const handleOpenCreateModal = () => {
    setFormName('');
    setFormDesc('');
    setFormGender('neutral');
    setFormSpeaker('');
    setFormAuthorizer('');
    setFormConsent(false);
    setFormTranscript('');
    setSelectedFile(null);
    setCreateError(null);
    setIsCreateModalOpen(true);
  };

  const handleCreateSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedFile) {
      setCreateError('Please select a reference audio file (.wav, .mp3, .m4a, .flac).');
      return;
    }
    if (!formConsent) {
      setCreateError('You must check the consent confirmation before registering a voice.');
      return;
    }

    try {
      setCreateSubmitting(true);
      setCreateError(null);

      const payload: CreateVoiceProfilePayload = {
        name: formName.trim(),
        description: formDesc.trim() || undefined,
        gender: formGender,
        speaker_name: formSpeaker.trim(),
        authorized_by: formAuthorizer.trim(),
        consent_confirmed: formConsent,
        reference_transcript: formTranscript.trim() || undefined,
        file: selectedFile,
      };

      await api.createVoiceProfile(payload);
      setIsCreateModalOpen(false);
      await fetchData();
    } catch (err: any) {
      console.error('Failed to create voice profile:', err);
      setCreateError(err.message || 'Failed to create voice profile.');
    } finally {
      setCreateSubmitting(false);
    }
  };

  // Handle edit voice profile
  const handleOpenEditModal = (profile: VoiceProfile) => {
    setEditingProfile(profile);
    setEditName(profile.name);
    setEditDesc(profile.description || '');
    setEditGender(profile.gender || 'neutral');
    setEditTranscript(profile.reference_transcript || '');
    setEditError(null);
  };

  const handleEditSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!editingProfile) return;
    if (!editName.trim()) {
      setEditError('Voice profile name cannot be empty.');
      return;
    }

    try {
      setEditSubmitting(true);
      setEditError(null);

      const payload: UpdateVoiceProfilePayload = {
        name: editName.trim(),
        description: editDesc.trim() || undefined,
        gender: editGender,
        reference_transcript: editTranscript.trim() || undefined,
      };

      await api.updateVoiceProfile(editingProfile.id, payload);
      setEditingProfile(null);
      await fetchData();
    } catch (err: any) {
      console.error('Failed to update voice profile:', err);
      setEditError(err.message || 'Failed to update voice profile.');
    } finally {
      setEditSubmitting(false);
    }
  };

  // Handle delete profile
  const handleDeleteConfirm = async () => {
    if (!deletingProfile) return;
    try {
      setDeleteSubmitting(true);
      await api.deleteVoiceProfile(deletingProfile.id);
      setDeletingProfile(null);
      await fetchData();
    } catch (err: any) {
      console.error('Failed to delete voice profile:', err);
      alert(err.message || 'Failed to delete voice profile.');
    } finally {
      setDeleteSubmitting(false);
    }
  };

  const engineStatus = data?.cloning_engine_status || 'Checking...';
  const isEngineOnline = engineStatus.toLowerCase().includes('online');

  return (
    <div className="space-y-8 max-w-7xl mx-auto pb-12">
      {/* Hidden audio elements for playback */}
      <audio
        ref={systemAudioRef}
        onEnded={() => setPreviewingVoice(null)}
        onError={() => setPreviewingVoice(null)}
      />
      <audio
        ref={customAudioRef}
        onEnded={() => setPlayingProfileId(null)}
        onError={() => setPlayingProfileId(null)}
      />

      {/* Page Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-slate-200 pb-5">
        <div>
          <div className="flex flex-wrap items-center gap-2.5 sm:gap-3">
            <div className="p-2.5 rounded-xl bg-indigo-600 text-white shadow-md shadow-indigo-600/20">
              <Mic2 className="w-6 h-6" />
            </div>
            <div>
              <h1 className="text-2xl font-bold text-slate-900 tracking-tight">Voice Studio</h1>
              <p className="text-sm text-slate-500">
                Manage system Khmer voices and authorized custom voice profiles
              </p>
            </div>
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2.5 sm:gap-3">
          <button
            onClick={fetchData}
            disabled={loading}
            className="px-3.5 py-2 text-sm font-medium text-slate-600 hover:text-slate-900 bg-white hover:bg-slate-50 border border-slate-200 rounded-lg shadow-sm transition-colors flex items-center gap-2"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin text-indigo-600' : ''}`} />
            <span>Refresh</span>
          </button>
          <button
            onClick={handleOpenCreateModal}
            className="px-4 py-2 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg shadow-sm shadow-indigo-600/30 transition-colors flex items-center gap-2"
          >
            <Plus className="w-4 h-4" />
            <span>Register Voice Profile</span>
          </button>
        </div>
      </div>

      {/* Offline Alert when Voice Cloning Engine is Unavailable */}
      {!isEngineOnline && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-3.5 text-xs text-amber-800 flex items-center gap-2.5">
          <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0" />
          <p className="flex-1">
            Voice cloning engine is currently offline. Standard system voices remain fully available. Reconnect the service to use custom voice profiles.
          </p>
        </div>
      )}

      {/* Global Error Banner */}
      {error && (
        <div className="bg-rose-50 border border-rose-200 rounded-xl p-4 text-sm text-rose-700 flex items-center justify-between">
          <span>{error}</span>
          <button
            onClick={fetchData}
            className="font-semibold underline hover:text-rose-900 ml-4"
          >
            Retry
          </button>
        </div>
      )}

      {/* Section 1: System Voices */}
      <section className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
              <Volume2 className="w-5 h-5 text-indigo-600" />
              <span>Standard System Voices</span>
            </h2>
            <p className="text-xs text-slate-500">
              Production-ready Khmer speech synthesis providers available for all dubbing projects
            </p>
          </div>
          <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
            {data?.system_voices?.length || 0} Voices Available
          </span>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {data?.system_voices?.map((voice) => {
            const isPlaying = previewingVoice === `${voice.provider}:${voice.voice}`;
            return (
              <div
                key={`${voice.provider}:${voice.voice}`}
                className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm hover:shadow-md transition-shadow flex flex-col justify-between"
              >
                <div className="space-y-2.5">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-semibold px-2 py-0.5 rounded bg-indigo-50 text-indigo-700 border border-indigo-100 uppercase tracking-wide">
                      {voice.provider === 'gtts' ? 'Google Translate' : 'Microsoft Edge'}
                    </span>
                    <span
                      className={`text-xs px-2 py-0.5 rounded font-medium ${
                        voice.gender === 'female'
                          ? 'bg-pink-50 text-pink-700 border border-pink-100'
                          : voice.gender === 'male'
                          ? 'bg-blue-50 text-blue-700 border border-blue-100'
                          : 'bg-slate-100 text-slate-700 border border-slate-200'
                      }`}
                    >
                      {voice.gender.toUpperCase()}
                    </span>
                  </div>

                  <div>
                    <h3 className="font-bold text-slate-900 text-base">{voice.label}</h3>
                    <p className="text-xs text-slate-500 mt-1 leading-relaxed">
                      {voice.description}
                    </p>
                  </div>
                </div>

                <div className="mt-5 pt-4 border-t border-slate-100 flex items-center justify-between">
                  <span className="text-xs text-slate-400 font-mono">
                    {voice.sample_rate ? `${voice.sample_rate / 1000} kHz` : '24 kHz'}
                  </span>

                  <button
                    onClick={() => handlePreviewSystemVoice(voice)}
                    disabled={previewLoading && previewingVoice === `${voice.provider}:${voice.voice}`}
                    className={`px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-1.5 transition-colors ${
                      isPlaying
                        ? 'bg-indigo-600 text-white'
                        : 'bg-slate-100 hover:bg-slate-200 text-slate-700'
                    }`}
                  >
                    {isPlaying ? (
                      <>
                        <Pause className="w-3.5 h-3.5" />
                        <span>Stop</span>
                      </>
                    ) : (
                      <>
                        <Play className="w-3.5 h-3.5" />
                        <span>Preview Voice</span>
                      </>
                    )}
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Section 2: Custom Voice Profiles */}
      <section className="space-y-4 pt-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-slate-900 flex items-center gap-2">
              <Mic2 className="w-5 h-5 text-indigo-600" />
              <span>Custom Voice Profiles</span>
            </h2>
            <p className="text-xs text-slate-500">
              Authorized speaker reference recordings stored for Khmer voice cloning
            </p>
          </div>
          <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-slate-100 text-slate-600 border border-slate-200">
            {data?.custom_profiles?.length || 0} Registered
          </span>
        </div>

        {data?.custom_profiles && data.custom_profiles.length === 0 ? (
          <div className="bg-white rounded-2xl border border-dashed border-slate-300 p-8 text-center space-y-4">
            <div className="w-14 h-14 rounded-2xl bg-indigo-50 text-indigo-600 flex items-center justify-center mx-auto">
              <FileAudio className="w-7 h-7" />
            </div>
            <div className="max-w-md mx-auto space-y-1.5">
              <h3 className="font-bold text-slate-900 text-base">No Custom Voice Profiles Yet</h3>
              <p className="text-xs text-slate-500 leading-relaxed">
                Register an authorized speaker by uploading a 5–30 second clean Khmer speech recording.
                All reference audio is normalized to 48 kHz studio quality and secured with digital
                consent audit records.
              </p>
            </div>
            <button
              onClick={handleOpenCreateModal}
              className="px-4 py-2 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg shadow-sm transition-colors inline-flex items-center gap-2"
            >
              <Plus className="w-4 h-4" />
              <span>Register First Voice</span>
            </button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
            {data?.custom_profiles?.map((profile) => {
              const isPlaying = playingProfileId === profile.id;
              return (
                <div
                  key={profile.id}
                  className="bg-white rounded-xl border border-slate-200 p-5 shadow-sm hover:shadow-md transition-shadow flex flex-col justify-between"
                >
                  <div className="space-y-3">
                    {/* Top Row: Gender & Status */}
                    <div className="flex items-center justify-between">
                      <span
                        className={`text-xs px-2 py-0.5 rounded font-medium ${
                          profile.gender === 'female'
                            ? 'bg-pink-50 text-pink-700 border border-pink-100'
                            : profile.gender === 'male'
                            ? 'bg-blue-50 text-blue-700 border border-blue-100'
                            : 'bg-slate-100 text-slate-700 border border-slate-200'
                        }`}
                      >
                        {profile.gender.toUpperCase()}
                      </span>

                      <span
                        className={`text-[11px] font-medium px-2 py-0.5 rounded border flex items-center gap-1 ${
                          isEngineOnline
                            ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                            : 'bg-amber-50 text-amber-700 border-amber-200/60'
                        }`}
                      >
                        {isEngineOnline ? (
                          <>
                            <CheckCircle2 className="w-3 h-3 text-emerald-600" />
                            <span>Ready to Clone</span>
                          </>
                        ) : (
                          <>
                            <Clock className="w-3 h-3 text-amber-600" />
                            <span>Worker Offline</span>
                          </>
                        )}
                      </span>
                    </div>

                    {/* Title & Description */}
                    <div>
                      <h3 className="font-bold text-slate-900 text-base flex items-center justify-between">
                        <span className="truncate">{profile.name}</span>
                      </h3>
                      {profile.description && (
                        <p className="text-xs text-slate-500 mt-1 line-clamp-2">
                          {profile.description}
                        </p>
                      )}
                    </div>

                    {/* Audio Metadata Pill Bar */}
                    <div className="flex flex-wrap items-center gap-2 text-xs">
                      <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-600 font-mono text-[11px]">
                        ⏱ {profile.reference_audio_duration ? `${profile.reference_audio_duration.toFixed(1)}s` : 'N/A'}
                      </span>
                      <span className="px-2 py-0.5 rounded bg-slate-100 text-slate-600 font-mono text-[11px]">
                        48 kHz Mono
                      </span>
                      <button
                        onClick={() => setViewingConsentProfile(profile)}
                        className="px-2 py-0.5 rounded bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border border-emerald-200 font-medium text-[11px] flex items-center gap-1 transition-colors"
                        title="View legal authorization details"
                      >
                        <ShieldCheck className="w-3 h-3 text-emerald-600" />
                        <span>Consent Verified</span>
                      </button>
                    </div>

                    {/* Reference Transcript preview if present */}
                    {profile.reference_transcript && (
                      <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-100 text-xs text-slate-600 italic">
                        "{profile.reference_transcript}"
                      </div>
                    )}
                  </div>

                  {/* Bottom Controls: Playback & Actions */}
                  <div className="mt-5 pt-4 border-t border-slate-100 flex items-center justify-between gap-2">
                    <button
                      onClick={() => handleTogglePlayCustom(profile)}
                      className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors ${
                        isPlaying
                          ? 'bg-indigo-600 text-white'
                          : 'bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200'
                      }`}
                    >
                      {isPlaying ? (
                        <>
                          <Pause className="w-3.5 h-3.5" />
                          <span>Pause Audio</span>
                        </>
                      ) : (
                        <>
                          <Play className="w-3.5 h-3.5" />
                          <span>Listen Reference</span>
                        </>
                      )}
                    </button>

                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handleOpenEditModal(profile)}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100 transition-colors"
                        title="Edit Profile"
                      >
                        <Edit2 className="w-4 h-4" />
                      </button>
                      <button
                        onClick={() => setDeletingProfile(profile)}
                        className="p-1.5 rounded-lg text-slate-400 hover:text-rose-600 hover:bg-rose-50 transition-colors"
                        title="Delete Profile"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </section>

      {/* ===================== MODAL: CREATE VOICE PROFILE ===================== */}
      {isCreateModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-xl border border-slate-200 w-full max-w-xl overflow-hidden max-h-[90vh] flex flex-col">
            <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-lg bg-indigo-50 text-indigo-600">
                  <Mic2 className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-slate-900 text-base">Register Custom Voice Profile</h3>
                  <p className="text-xs text-slate-500">
                    Upload authorized speaker audio normalized to 48 kHz
                  </p>
                </div>
              </div>
              <button
                onClick={() => setIsCreateModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleCreateSubmit} className="p-6 space-y-4 overflow-y-auto flex-1">
              {createError && (
                <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-700">
                  {createError}
                </div>
              )}

              {/* Profile Name & Gender */}
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                <div className="sm:col-span-2 space-y-1">
                  <label className="text-xs font-semibold text-slate-700">
                    Profile Name <span className="text-rose-500">*</span>
                  </label>
                  <input
                    type="text"
                    required
                    value={formName}
                    onChange={(e) => setFormName(e.target.value)}
                    placeholder="e.g. Sokha Reference Voice"
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                  />
                </div>

                <div className="space-y-1">
                  <label className="text-xs font-semibold text-slate-700">Gender</label>
                  <select
                    value={formGender}
                    onChange={(e) => setFormGender(e.target.value)}
                    className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                  >
                    <option value="neutral">Neutral</option>
                    <option value="male">Male</option>
                    <option value="female">Female</option>
                  </select>
                </div>
              </div>

              {/* Description */}
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-700">Description (Optional)</label>
                <input
                  type="text"
                  value={formDesc}
                  onChange={(e) => setFormDesc(e.target.value)}
                  placeholder="e.g. Natural Cambodian male speaker, news broadcast cadence"
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                />
              </div>

              {/* Reference Audio File */}
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-700">
                  Reference Audio Recording <span className="text-rose-500">*</span>
                </label>
                <div className="border-2 border-dashed border-slate-200 rounded-xl p-4 text-center hover:border-indigo-400 transition-colors bg-slate-50/50">
                  <input
                    type="file"
                    id="referenceAudioUpload"
                    accept=".wav,.mp3,.m4a,.flac,.aac,.ogg"
                    required
                    onChange={(e) => {
                      if (e.target.files && e.target.files[0]) {
                        setSelectedFile(e.target.files[0]);
                      }
                    }}
                    className="hidden"
                  />
                  <label
                    htmlFor="referenceAudioUpload"
                    className="cursor-pointer flex flex-col items-center justify-center gap-2"
                  >
                    <div className="p-2 rounded-full bg-white shadow-sm border border-slate-200 text-indigo-600">
                      <Upload className="w-5 h-5" />
                    </div>
                    {selectedFile ? (
                      <div>
                        <p className="text-xs font-semibold text-slate-900">{selectedFile.name}</p>
                        <p className="text-[11px] text-slate-500">
                          {(selectedFile.size / (1024 * 1024)).toFixed(2)} MB • Click to replace
                        </p>
                      </div>
                    ) : (
                      <div>
                        <p className="text-xs font-semibold text-slate-700">
                          Choose WAV, MP3, M4A, or FLAC audio file
                        </p>
                        <p className="text-[11px] text-slate-400">
                          Recommended: 5 to 30 seconds of clear speech (Minimum 3s)
                        </p>
                      </div>
                    )}
                  </label>
                </div>
              </div>

              {/* Reference Transcript (Optional) */}
              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-700">
                  Reference Audio Transcript (Optional, Khmer)
                </label>
                <textarea
                  rows={2}
                  value={formTranscript}
                  onChange={(e) => setFormTranscript(e.target.value)}
                  placeholder="Exact Khmer text spoken in the recording (improves continuation voice cloning)"
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500 font-sans"
                />
              </div>

              {/* Legal Authorization & Consent Box */}
              <div className="bg-indigo-50/60 border border-indigo-100 rounded-xl p-4 space-y-3">
                <div className="flex items-center gap-2 text-indigo-950 font-bold text-xs">
                  <ShieldCheck className="w-4 h-4 text-indigo-600" />
                  <span>Mandatory Speaker Authorization & Legal Consent</span>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div className="space-y-1">
                    <label className="text-[11px] font-semibold text-slate-700">
                      Speaker Full Name <span className="text-rose-500">*</span>
                    </label>
                    <input
                      type="text"
                      required
                      value={formSpeaker}
                      onChange={(e) => setFormSpeaker(e.target.value)}
                      placeholder="e.g. Sokha Chan"
                      className="w-full px-2.5 py-1.5 text-xs bg-white border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                    />
                  </div>

                  <div className="space-y-1">
                    <label className="text-[11px] font-semibold text-slate-700">
                      Authorized By (Grantor) <span className="text-rose-500">*</span>
                    </label>
                    <input
                      type="text"
                      required
                      value={formAuthorizer}
                      onChange={(e) => setFormAuthorizer(e.target.value)}
                      placeholder="e.g. Mark / KhmerDub Admin"
                      className="w-full px-2.5 py-1.5 text-xs bg-white border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                    />
                  </div>
                </div>

                <label className="flex items-start gap-2.5 pt-1 cursor-pointer">
                  <input
                    type="checkbox"
                    required
                    checked={formConsent}
                    onChange={(e) => setFormConsent(e.target.checked)}
                    className="mt-0.5 rounded border-slate-300 text-indigo-600 focus:ring-indigo-500"
                  />
                  <span className="text-[11px] text-slate-700 leading-snug">
                    I confirm that I have obtained explicit authorization from the speaker to record
                    and condition AI voice synthesis on this reference audio for English-to-Khmer dubbing.
                  </span>
                </label>
              </div>

              {/* Modal Buttons */}
              <div className="pt-2 flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setIsCreateModalOpen(false)}
                  disabled={createSubmitting}
                  className="px-4 py-2 text-sm text-slate-600 hover:text-slate-800 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={createSubmitting}
                  className="px-4 py-2 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg shadow-sm transition-colors flex items-center gap-2"
                >
                  {createSubmitting ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      <span>Validating & Converting...</span>
                    </>
                  ) : (
                    <span>Register Voice Profile</span>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ===================== MODAL: EDIT VOICE PROFILE ===================== */}
      {editingProfile && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-xl border border-slate-200 w-full max-w-lg overflow-hidden flex flex-col">
            <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
              <h3 className="font-bold text-slate-900 text-base">Edit Voice Profile</h3>
              <button
                onClick={() => setEditingProfile(null)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleEditSubmit} className="p-6 space-y-4">
              {editError && (
                <div className="p-3 rounded-lg bg-rose-50 border border-rose-200 text-xs text-rose-700">
                  {editError}
                </div>
              )}

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-700">Profile Name</label>
                <input
                  type="text"
                  required
                  value={editName}
                  onChange={(e) => setEditName(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-700">Gender</label>
                <select
                  value={editGender}
                  onChange={(e) => setEditGender(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                >
                  <option value="neutral">Neutral</option>
                  <option value="male">Male</option>
                  <option value="female">Female</option>
                </select>
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-700">Description</label>
                <input
                  type="text"
                  value={editDesc}
                  onChange={(e) => setEditDesc(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                />
              </div>

              <div className="space-y-1">
                <label className="text-xs font-semibold text-slate-700">Reference Transcript</label>
                <textarea
                  rows={2}
                  value={editTranscript}
                  onChange={(e) => setEditTranscript(e.target.value)}
                  className="w-full px-3 py-2 text-sm border border-slate-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500/20 focus:border-indigo-500"
                />
              </div>

              <div className="pt-2 flex items-center justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setEditingProfile(null)}
                  disabled={editSubmitting}
                  className="px-4 py-2 text-sm text-slate-600 hover:text-slate-800 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={editSubmitting}
                  className="px-4 py-2 text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 rounded-lg shadow-sm transition-colors"
                >
                  {editSubmitting ? 'Saving...' : 'Save Changes'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ===================== MODAL: DELETE CONFIRMATION ===================== */}
      {deletingProfile && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-xl border border-slate-200 w-full max-w-md p-6 space-y-4">
            <div className="flex items-center gap-3 text-rose-600">
              <div className="p-2.5 rounded-full bg-rose-50">
                <Trash2 className="w-6 h-6" />
              </div>
              <h3 className="font-bold text-slate-900 text-lg">Delete Voice Profile?</h3>
            </div>

            <p className="text-sm text-slate-600 leading-relaxed">
              Are you sure you want to delete <span className="font-semibold text-slate-900">"{deletingProfile.name}"</span>?
              Its normalized reference audio recording and consent record will be permanently purged.
            </p>

            <div className="pt-3 flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => setDeletingProfile(null)}
                disabled={deleteSubmitting}
                className="px-4 py-2 text-sm text-slate-600 hover:text-slate-800 bg-slate-100 hover:bg-slate-200 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDeleteConfirm}
                disabled={deleteSubmitting}
                className="px-4 py-2 text-sm font-semibold text-white bg-rose-600 hover:bg-rose-700 rounded-lg shadow-sm transition-colors flex items-center gap-2"
              >
                {deleteSubmitting ? 'Deleting...' : 'Confirm Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ===================== MODAL: VIEW CONSENT DETAILS ===================== */}
      {viewingConsentProfile && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-xl border border-slate-200 w-full max-w-lg p-6 space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 pb-3">
              <div className="flex items-center gap-2 text-emerald-700 font-bold text-base">
                <ShieldCheck className="w-5 h-5 text-emerald-600" />
                <span>Legal Authorization & Consent Audit</span>
              </div>
              <button
                onClick={() => setViewingConsentProfile(null)}
                className="text-slate-400 hover:text-slate-600 p-1"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="space-y-3 text-xs">
              <div className="grid grid-cols-2 gap-2 p-3 rounded-lg bg-slate-50 border border-slate-100">
                <div>
                  <span className="text-slate-400 block font-medium">Speaker Name</span>
                  <span className="font-semibold text-slate-900 text-sm">
                    {viewingConsentProfile.consent.speaker_name}
                  </span>
                </div>
                <div>
                  <span className="text-slate-400 block font-medium">Authorized By</span>
                  <span className="font-semibold text-slate-900 text-sm">
                    {viewingConsentProfile.consent.authorized_by}
                  </span>
                </div>
                <div className="col-span-2 pt-2 border-t border-slate-200/60">
                  <span className="text-slate-400 block font-medium">Granted At</span>
                  <span className="font-mono text-slate-700">
                    {formatCambodiaDateTime(viewingConsentProfile.consent.granted_at)}
                  </span>
                </div>
              </div>

              <div>
                <span className="text-slate-500 font-semibold block mb-1">Consent Statement:</span>
                <p className="p-3 rounded-lg bg-slate-50 border border-slate-100 text-slate-700 leading-relaxed italic">
                  "{viewingConsentProfile.consent.consent_statement}"
                </p>
              </div>

              <div>
                <span className="text-slate-500 font-semibold block mb-1">Cryptographic Signature Hash (SHA-256):</span>
                <div className="p-2 rounded bg-slate-900 text-emerald-400 font-mono text-[10px] break-all select-all">
                  {viewingConsentProfile.consent.signature_hash}
                </div>
              </div>
            </div>

            <div className="pt-2 flex justify-end">
              <button
                onClick={() => setViewingConsentProfile(null)}
                className="px-4 py-2 text-xs font-semibold text-slate-700 bg-slate-100 hover:bg-slate-200 rounded-lg"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
