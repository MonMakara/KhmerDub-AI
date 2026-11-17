import React, { useState, useEffect, useMemo, useRef } from 'react';
import {
  FileText,
  Upload,
  Clipboard,
  History,
  CheckCircle2,
  AlertCircle,
  Copy,
  Check,
  Download,
  Archive,
  ArrowRight,
  Radio,
  Languages,
  Mic2,
  Sliders,
  Sparkles,
  RefreshCw,
  AlignLeft,
  Clock,
  BookOpen,
  Volume2,
} from 'lucide-react';
import { api } from '../../services/api';
import { ToolkitTask } from '../../types';

interface TranscriptToTextProps {
  tasks: ToolkitTask[];
  initialTask?: ToolkitTask | null;
  onTaskCreated: (task: ToolkitTask) => void;
  onSendToTTS?: (text: string) => void;
  onSendToTranslation?: (text: string) => void;
  onSendToTranscriptToAudio?: (taskId: string) => void;
  onNavigateToTool?: (toolId: string) => void;
}

export const TranscriptToText: React.FC<TranscriptToTextProps> = ({
  tasks,
  initialTask,
  onTaskCreated,
  onSendToTTS,
  onSendToTranslation,
  onSendToTranscriptToAudio,
  onNavigateToTool,
}) => {
  // Input Selection State
  const [inputTab, setInputTab] = useState<'file' | 'paste' | 'task'>('file');
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [pastedContent, setPastedContent] = useState<string>('');
  const [sourceTaskId, setSourceTaskId] = useState<string>('');

  // Processing & Formatting Options
  const [paragraphMode, setParagraphMode] = useState<'smart_paragraphs' | 'continuous' | 'line_by_line' | 'timestamped'>('smart_paragraphs');
  const [speakerHandling, setSpeakerHandling] = useState<'strip' | 'keep'>('strip');
  const [pauseThreshold, setPauseThreshold] = useState<number>(1.5);
  const [deduplicatePhrases, setDeduplicatePhrases] = useState<boolean>(true);
  const [stripTags, setStripTags] = useState<boolean>(true);
  const [targetFormat, setTargetFormat] = useState<'txt' | 'md' | 'json'>('txt');
  const [documentTitle, setDocumentTitle] = useState<string>('Extracted Transcript');

  // Execution & Output State
  const [isProcessing, setIsProcessing] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [currentTask, setCurrentTask] = useState<ToolkitTask | null>(
    initialTask?.tool_type === 'transcript_to_text' ? initialTask : null
  );
  const [copied, setCopied] = useState<boolean>(false);
  const [activePreviewTab, setActivePreviewTab] = useState<'formatted' | 'raw' | 'json'>('formatted');

  const fileInputRef = useRef<HTMLInputElement>(null);

  // Sync initial task if provided
  useEffect(() => {
    if (initialTask && initialTask.tool_type === 'transcript_to_text') {
      setCurrentTask(initialTask);
    }
  }, [initialTask]);

  // Candidates for source tasks (completed transcription or translation tasks)
  const candidateTasks = useMemo(() => {
    return tasks.filter(
      (t) =>
        t.status === 'completed' &&
        [
          'video_to_transcript',
          'audio_to_transcript',
          'video_to_text',
          'audio_to_text',
          'transcript_translation',
          'subtitle_conversion',
        ].includes(t.tool_type)
    );
  }, [tasks]);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setSelectedFile(file);
      setError(null);
      // Auto-set title from filename stem
      const stem = file.name.replace(/\.[^/.]+$/, '');
      if (!documentTitle || documentTitle === 'Extracted Transcript') {
        setDocumentTitle(stem);
      }
    }
  };

  const handleExtract = async () => {
    setError(null);
    setSuccessMessage(null);
    setIsProcessing(true);

    try {
      let task: ToolkitTask;

      if (inputTab === 'file') {
        if (!selectedFile) {
          throw new Error('Please select a subtitle or transcript file to extract.');
        }
        task = await api.uploadTranscriptToText(selectedFile, {
          paragraph_mode: paragraphMode,
          speaker_handling: speakerHandling,
          pause_threshold_seconds: pauseThreshold,
          deduplicate_phrases: deduplicatePhrases,
          strip_tags: stripTags,
          target_format: targetFormat,
          title: documentTitle.trim() || undefined,
        });
      } else if (inputTab === 'paste') {
        if (!pastedContent.trim()) {
          throw new Error('Please paste subtitle cues or transcript text.');
        }
        task = await api.convertTranscriptToText({
          content: pastedContent.trim(),
          filename: 'pasted_transcript.srt',
          paragraph_mode: paragraphMode,
          speaker_handling: speakerHandling,
          pause_threshold_seconds: pauseThreshold,
          deduplicate_phrases: deduplicatePhrases,
          strip_tags: stripTags,
          target_format: targetFormat,
          title: documentTitle.trim() || undefined,
        });
      } else {
        // Source task
        if (!sourceTaskId) {
          throw new Error('Please select a completed transcription task from the list.');
        }
        const picked = candidateTasks.find((t) => t.id === sourceTaskId);
        task = await api.convertTranscriptToText({
          source_task_id: sourceTaskId,
          filename: picked?.source_filename || 'source_transcript.srt',
          paragraph_mode: paragraphMode,
          speaker_handling: speakerHandling,
          pause_threshold_seconds: pauseThreshold,
          deduplicate_phrases: deduplicatePhrases,
          strip_tags: stripTags,
          target_format: targetFormat,
          title: documentTitle.trim() || (picked?.source_filename ? picked.source_filename.replace(/\.[^/.]+$/, '') : undefined),
        });
      }

      setCurrentTask(task);
      onTaskCreated(task);
      setSuccessMessage('Transcript converted to text successfully!');
    } catch (err: any) {
      console.error('Transcript to text extraction failed:', err);
      setError(err.message || 'Failed to extract text from transcript.');
    } finally {
      setIsProcessing(false);
    }
  };

  const handleCopyText = () => {
    if (!currentTask?.full_text) return;
    navigator.clipboard.writeText(currentTask.full_text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2200);
  };

  const metadata = currentTask?.output_media_metadata || {};
  const wordCount = metadata.word_count || 0;
  const charCount = metadata.character_count || (currentTask?.full_text ? currentTask.full_text.length : 0);
  const paragraphCount = metadata.paragraph_count || (currentTask?.segments ? currentTask.segments.length : 0);
  const cueCount = metadata.cue_count || 0;
  const readingTime = metadata.reading_time_minutes || (wordCount > 0 ? (wordCount / 200).toFixed(1) : '0.0');
  const speakingTime = metadata.speaking_time_minutes || (wordCount > 0 ? (wordCount / 130).toFixed(1) : '0.0');
  const detectedLang = metadata.detected_language || 'en';

  const getLanguageBadge = (lang: string) => {
    if (lang === 'km') {
      return { label: 'Khmer (ខ្មែរ)', color: 'bg-emerald-50 text-emerald-700 border-emerald-200' };
    }
    if (lang === 'bilingual') {
      return { label: 'Bilingual (EN + KM)', color: 'bg-indigo-50 text-indigo-700 border-indigo-200' };
    }
    return { label: 'English', color: 'bg-blue-50 text-blue-700 border-blue-200' };
  };

  const langBadge = getLanguageBadge(detectedLang);

  return (
    <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
      {/* LEFT COLUMN: Input & Configuration (5 cols) */}
      <div className="lg:col-span-5 space-y-6">
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
          {/* Header */}
          <div className="px-5 py-4 border-b border-slate-200 bg-slate-50/50 flex items-center justify-between">
            <div className="flex items-center space-x-2.5">
              <div className="p-2 bg-indigo-50 text-indigo-600 rounded-lg">
                <FileText className="w-5 h-5" />
              </div>
              <div>
                <h3 className="font-semibold text-slate-800 text-sm">Transcript to Text</h3>
                <p className="text-xs text-slate-500">Extract clean narrative paragraphs from subtitles</p>
              </div>
            </div>
          </div>

          <div className="p-5 space-y-5">
            {/* Source Selection Tabs */}
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
                Source Input
              </label>
              <div className="grid grid-cols-3 gap-1 bg-slate-100 p-1 rounded-lg text-xs font-medium text-slate-600">
                <button
                  type="button"
                  onClick={() => setInputTab('file')}
                  className={`flex items-center justify-center py-2 rounded-md transition ${
                    inputTab === 'file' ? 'bg-white text-indigo-600 shadow-sm font-semibold' : 'hover:text-slate-800'
                  }`}
                >
                  <Upload className="w-3.5 h-3.5 mr-1.5" />
                  File Upload
                </button>
                <button
                  type="button"
                  onClick={() => setInputTab('paste')}
                  className={`flex items-center justify-center py-2 rounded-md transition ${
                    inputTab === 'paste' ? 'bg-white text-indigo-600 shadow-sm font-semibold' : 'hover:text-slate-800'
                  }`}
                >
                  <Clipboard className="w-3.5 h-3.5 mr-1.5" />
                  Paste Cues
                </button>
                <button
                  type="button"
                  onClick={() => setInputTab('task')}
                  className={`flex items-center justify-center py-2 rounded-md transition ${
                    inputTab === 'task' ? 'bg-white text-indigo-600 shadow-sm font-semibold' : 'hover:text-slate-800'
                  }`}
                >
                  <History className="w-3.5 h-3.5 mr-1.5" />
                  From Task
                </button>
              </div>
            </div>

            {/* Input Tab Contents */}
            {inputTab === 'file' && (
              <div
                onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-slate-300 hover:border-indigo-400 rounded-xl p-6 text-center cursor-pointer transition bg-slate-50/50 hover:bg-indigo-50/20"
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".srt,.vtt,.json,.sbv,.ass,.sub"
                  onChange={handleFileSelect}
                  className="hidden"
                />
                <div className="w-12 h-12 mx-auto bg-indigo-50 rounded-full flex items-center justify-center text-indigo-600 mb-3">
                  <Upload className="w-6 h-6" />
                </div>
                {selectedFile ? (
                  <div>
                    <p className="font-semibold text-slate-800 text-sm">{selectedFile.name}</p>
                    <p className="text-xs text-slate-500 mt-1">{(selectedFile.size / 1024).toFixed(1)} KB • Ready to extract</p>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setSelectedFile(null);
                      }}
                      className="text-xs text-red-500 hover:text-red-700 mt-2 font-medium"
                    >
                      Remove file
                    </button>
                  </div>
                ) : (
                  <div>
                    <p className="text-sm font-medium text-slate-700">Click to upload subtitle file</p>
                    <p className="text-xs text-slate-400 mt-1">Supports SRT, WebVTT, JSON, SBV, and ASS formats</p>
                  </div>
                )}
              </div>
            )}

            {inputTab === 'paste' && (
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <span className="text-xs text-slate-500">Paste raw SRT, WebVTT, or cues text</span>
                  {pastedContent && (
                    <button
                      type="button"
                      onClick={() => setPastedContent('')}
                      className="text-xs text-slate-400 hover:text-slate-600"
                    >
                      Clear
                    </button>
                  )}
                </div>
                <textarea
                  value={pastedContent}
                  onChange={(e) => setPastedContent(e.target.value)}
                  placeholder={`1\n00:00:01,000 --> 00:00:03,000\n[Speaker 1]: Welcome to KhmerDub AI...\n\n2\n00:00:03,500 --> 00:00:05,000\nThis is a sample subtitle cue.`}
                  rows={6}
                  className="w-full text-xs font-mono p-3 border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none resize-y"
                />
              </div>
            )}

            {inputTab === 'task' && (
              <div>
                <label className="block text-xs text-slate-500 mb-1.5">
                  Select Completed Transcription Task
                </label>
                {candidateTasks.length === 0 ? (
                  <p className="text-xs text-slate-400 italic p-3 bg-slate-50 rounded-lg border border-slate-200">
                    No completed transcription tasks found in history yet.
                  </p>
                ) : (
                  <select
                    value={sourceTaskId}
                    onChange={(e) => setSourceTaskId(e.target.value)}
                    className="w-full text-xs p-2.5 bg-white border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none"
                  >
                    <option value="">-- Choose a transcription task --</option>
                    {candidateTasks.map((t) => (
                      <option key={t.id} value={t.id}>
                        {t.source_filename} ({t.tool_type.replace(/_/g, ' ')})
                      </option>
                    ))}
                  </select>
                )}
              </div>
            )}

            <hr className="border-slate-100" />

            {/* Formatting Mode */}
            <div>
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 mb-2">
                Paragraph Structure
              </label>
              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setParagraphMode('smart_paragraphs')}
                  className={`p-3 rounded-lg border text-left transition ${
                    paragraphMode === 'smart_paragraphs'
                      ? 'border-indigo-500 bg-indigo-50/50 text-indigo-900 shadow-xs'
                      : 'border-slate-200 hover:border-slate-300 text-slate-700'
                  }`}
                >
                  <div className="flex items-center space-x-1.5 font-semibold text-xs mb-1">
                    <Sparkles className="w-3.5 h-3.5 text-indigo-600" />
                    <span>Smart Paragraphs</span>
                  </div>
                  <p className="text-[11px] text-slate-500 leading-tight">
                    Groups cues by pauses and punctuation into natural paragraphs
                  </p>
                </button>

                <button
                  type="button"
                  onClick={() => setParagraphMode('continuous')}
                  className={`p-3 rounded-lg border text-left transition ${
                    paragraphMode === 'continuous'
                      ? 'border-indigo-500 bg-indigo-50/50 text-indigo-900 shadow-xs'
                      : 'border-slate-200 hover:border-slate-300 text-slate-700'
                  }`}
                >
                  <div className="flex items-center space-x-1.5 font-semibold text-xs mb-1">
                    <AlignLeft className="w-3.5 h-3.5 text-indigo-600" />
                    <span>Continuous Flow</span>
                  </div>
                  <p className="text-[11px] text-slate-500 leading-tight">
                    Merges all cues into one smooth unbroken block
                  </p>
                </button>

                <button
                  type="button"
                  onClick={() => setParagraphMode('line_by_line')}
                  className={`p-3 rounded-lg border text-left transition ${
                    paragraphMode === 'line_by_line'
                      ? 'border-indigo-500 bg-indigo-50/50 text-indigo-900 shadow-xs'
                      : 'border-slate-200 hover:border-slate-300 text-slate-700'
                  }`}
                >
                  <div className="flex items-center space-x-1.5 font-semibold text-xs mb-1">
                    <FileText className="w-3.5 h-3.5 text-indigo-600" />
                    <span>Line by Line</span>
                  </div>
                  <p className="text-[11px] text-slate-500 leading-tight">
                    One clean sentence or cue per line without timecodes
                  </p>
                </button>

                <button
                  type="button"
                  onClick={() => setParagraphMode('timestamped')}
                  className={`p-3 rounded-lg border text-left transition ${
                    paragraphMode === 'timestamped'
                      ? 'border-indigo-500 bg-indigo-50/50 text-indigo-900 shadow-xs'
                      : 'border-slate-200 hover:border-slate-300 text-slate-700'
                  }`}
                >
                  <div className="flex items-center space-x-1.5 font-semibold text-xs mb-1">
                    <Clock className="w-3.5 h-3.5 text-indigo-600" />
                    <span>Timestamped</span>
                  </div>
                  <p className="text-[11px] text-slate-500 leading-tight">
                    Prepends readable [HH:MM:SS] timecodes per cue
                  </p>
                </button>
              </div>
            </div>

            {/* Smart Pause Slider */}
            {paragraphMode === 'smart_paragraphs' && (
              <div className="p-3 bg-slate-50 rounded-lg border border-slate-200/80 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-slate-700 flex items-center">
                    <Sliders className="w-3.5 h-3.5 mr-1.5 text-slate-500" />
                    Silence Pause Threshold
                  </span>
                  <span className="text-xs font-bold text-indigo-600">{pauseThreshold.toFixed(1)}s</span>
                </div>
                <input
                  type="range"
                  min="0.5"
                  max="4.0"
                  step="0.1"
                  value={pauseThreshold}
                  onChange={(e) => setPauseThreshold(parseFloat(e.target.value))}
                  className="w-full accent-indigo-600 h-1.5 bg-slate-200 rounded-lg cursor-pointer"
                />
                <p className="text-[11px] text-slate-400">
                  Gaps between cues longer than {pauseThreshold.toFixed(1)}s trigger a new paragraph.
                </p>
              </div>
            )}

            {/* Speaker & Cleaning Options */}
            <div className="space-y-2">
              <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500">
                Text Polish & Cleaning
              </label>

              <div className="flex items-center justify-between p-2.5 rounded-lg border border-slate-200 bg-slate-50/30 text-xs">
                <span className="text-slate-700 font-medium">Speaker Labels</span>
                <div className="flex items-center space-x-1 bg-white border border-slate-200 p-0.5 rounded-md">
                  <button
                    type="button"
                    onClick={() => setSpeakerHandling('strip')}
                    className={`px-2.5 py-1 rounded text-xs transition ${
                      speakerHandling === 'strip' ? 'bg-indigo-600 text-white font-medium' : 'text-slate-600 hover:text-slate-800'
                    }`}
                  >
                    Strip
                  </button>
                  <button
                    type="button"
                    onClick={() => setSpeakerHandling('keep')}
                    className={`px-2.5 py-1 rounded text-xs transition ${
                      speakerHandling === 'keep' ? 'bg-indigo-600 text-white font-medium' : 'text-slate-600 hover:text-slate-800'
                    }`}
                  >
                    Keep
                  </button>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-2 pt-1 text-xs">
                <label className="flex items-center space-x-2 p-2 rounded-lg border border-slate-200 bg-slate-50/30 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={stripTags}
                    onChange={(e) => setStripTags(e.target.checked)}
                    className="rounded text-indigo-600 focus:ring-indigo-500 w-3.5 h-3.5"
                  />
                  <span className="text-slate-700">Strip HTML / ASS tags</span>
                </label>

                <label className="flex items-center space-x-2 p-2 rounded-lg border border-slate-200 bg-slate-50/30 cursor-pointer">
                  <input
                    type="checkbox"
                    checked={deduplicatePhrases}
                    onChange={(e) => setDeduplicatePhrases(e.target.checked)}
                    className="rounded text-indigo-600 focus:ring-indigo-500 w-3.5 h-3.5"
                  />
                  <span className="text-slate-700">Deduplicate repeat words</span>
                </label>
              </div>
            </div>

            {/* Target Output Format & Title */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1">
                  Primary Format
                </label>
                <select
                  value={targetFormat}
                  onChange={(e) => setTargetFormat(e.target.value as any)}
                  className="w-full text-xs p-2.5 bg-white border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none"
                >
                  <option value="txt">Plain Text (.txt)</option>
                  <option value="md">Markdown (.md)</option>
                  <option value="json">Structured JSON (.json)</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-600 mb-1">
                  Document Title
                </label>
                <input
                  type="text"
                  value={documentTitle}
                  onChange={(e) => setDocumentTitle(e.target.value)}
                  placeholder="Extracted Transcript"
                  className="w-full text-xs p-2.5 bg-white border border-slate-200 rounded-lg focus:ring-2 focus:ring-indigo-500 outline-none"
                />
              </div>
            </div>

            {error && (
              <div className="p-3 bg-red-50 text-red-700 border border-red-200 rounded-lg text-xs flex items-start space-x-2">
                <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                <span>{error}</span>
              </div>
            )}

            {successMessage && (
              <div className="p-3 bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-lg text-xs flex items-center space-x-2">
                <CheckCircle2 className="w-4 h-4 shrink-0" />
                <span>{successMessage}</span>
              </div>
            )}

            {/* Action Button */}
            <button
              type="button"
              onClick={handleExtract}
              disabled={isProcessing}
              className="w-full py-3 bg-indigo-600 hover:bg-indigo-700 text-white rounded-xl font-medium text-xs flex items-center justify-center space-x-2 shadow-sm transition disabled:opacity-50"
            >
              {isProcessing ? (
                <>
                  <RefreshCw className="w-4 h-4 animate-spin" />
                  <span>Processing Transcript...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  <span>Extract & Format Text</span>
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* RIGHT COLUMN: Output Viewer & Connected Actions (7 cols) */}
      <div className="lg:col-span-7 space-y-6">
        <div className="bg-white rounded-xl shadow-sm border border-slate-200 flex flex-col h-full min-h-[580px]">
          {/* Header with Stats & Actions */}
          <div className="px-5 py-4 border-b border-slate-200 bg-slate-50/50 flex flex-wrap items-center justify-between gap-3">
            <div>
              <h3 className="font-semibold text-slate-800 text-sm">Extracted Text Output</h3>
              <p className="text-xs text-slate-500">
                {currentTask ? currentTask.output_filename || 'Formatted Text Document' : 'No transcript processed yet'}
              </p>
            </div>

            {currentTask && (
              <div className="flex items-center space-x-2">
                <button
                  type="button"
                  onClick={handleCopyText}
                  className="px-3 py-1.5 rounded-lg border border-slate-200 bg-white hover:bg-slate-50 text-slate-700 text-xs font-medium flex items-center space-x-1.5 transition shadow-2xs"
                >
                  {copied ? <Check className="w-3.5 h-3.5 text-emerald-600" /> : <Copy className="w-3.5 h-3.5 text-slate-500" />}
                  <span>{copied ? 'Copied!' : 'Copy Text'}</span>
                </button>

                <div className="relative group">
                  <a
                    href={api.getToolkitExportUrl(currentTask.id, targetFormat)}
                    download
                    className="px-3 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-medium flex items-center space-x-1.5 transition shadow-2xs"
                  >
                    <Download className="w-3.5 h-3.5" />
                    <span>Download .{targetFormat}</span>
                  </a>
                </div>
              </div>
            )}
          </div>

          {/* Stats Bar */}
          {currentTask && (
            <div className="px-5 py-3 border-b border-slate-200 bg-white grid grid-cols-2 sm:grid-cols-5 gap-3 text-center">
              <div className="p-2 rounded-lg bg-slate-50 border border-slate-100">
                <span className="block text-[10px] uppercase font-bold text-slate-400">Word Count</span>
                <span className="text-base font-bold text-slate-800">{wordCount.toLocaleString()}</span>
                <span className={`inline-block mt-0.5 text-[9px] px-1.5 py-0.2 rounded border font-medium ${langBadge.color}`}>
                  {langBadge.label}
                </span>
              </div>

              <div className="p-2 rounded-lg bg-slate-50 border border-slate-100">
                <span className="block text-[10px] uppercase font-bold text-slate-400">Characters</span>
                <span className="text-base font-bold text-slate-800">{charCount.toLocaleString()}</span>
              </div>

              <div className="p-2 rounded-lg bg-slate-50 border border-slate-100">
                <span className="block text-[10px] uppercase font-bold text-slate-400">Paragraphs</span>
                <span className="text-base font-bold text-slate-800">{paragraphCount}</span>
                <span className="block text-[10px] text-slate-400 mt-0.5">from {cueCount} cues</span>
              </div>

              <div className="p-2 rounded-lg bg-slate-50 border border-slate-100">
                <span className="block text-[10px] uppercase font-bold text-slate-400 flex items-center justify-center">
                  <BookOpen className="w-3 h-3 mr-1 text-slate-400" /> Reading
                </span>
                <span className="text-base font-bold text-slate-800">~{readingTime}</span>
                <span className="block text-[10px] text-slate-400 mt-0.5">minutes</span>
              </div>

              <div className="p-2 rounded-lg bg-slate-50 border border-slate-100">
                <span className="block text-[10px] uppercase font-bold text-slate-400 flex items-center justify-center">
                  <Volume2 className="w-3 h-3 mr-1 text-slate-400" /> Speaking
                </span>
                <span className="text-base font-bold text-slate-800">~{speakingTime}</span>
                <span className="block text-[10px] text-slate-400 mt-0.5">minutes</span>
              </div>
            </div>
          )}

          {/* Viewer Tabs */}
          {currentTask && (
            <div className="px-5 pt-3 border-b border-slate-100 flex items-center justify-between text-xs">
              <div className="flex space-x-4">
                <button
                  type="button"
                  onClick={() => setActivePreviewTab('formatted')}
                  className={`pb-2 border-b-2 font-medium transition ${
                    activePreviewTab === 'formatted'
                      ? 'border-indigo-600 text-indigo-600'
                      : 'border-transparent text-slate-500 hover:text-slate-800'
                  }`}
                >
                  Formatted Document
                </button>
                <button
                  type="button"
                  onClick={() => setActivePreviewTab('raw')}
                  className={`pb-2 border-b-2 font-medium transition ${
                    activePreviewTab === 'raw'
                      ? 'border-indigo-600 text-indigo-600'
                      : 'border-transparent text-slate-500 hover:text-slate-800'
                  }`}
                >
                  Plain Text View
                </button>
                <button
                  type="button"
                  onClick={() => setActivePreviewTab('json')}
                  className={`pb-2 border-b-2 font-medium transition ${
                    activePreviewTab === 'json'
                      ? 'border-indigo-600 text-indigo-600'
                      : 'border-transparent text-slate-500 hover:text-slate-800'
                  }`}
                >
                  JSON Structure
                </button>
              </div>

              {/* Multi-format quick downloads */}
              <div className="flex items-center space-x-1 text-[11px] pb-1">
                <span className="text-slate-400 mr-1">Download:</span>
                <a
                  href={api.getToolkitExportUrl(currentTask.id, 'txt')}
                  download
                  className="px-1.5 py-0.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 font-mono"
                >
                  .txt
                </a>
                <a
                  href={api.getToolkitExportUrl(currentTask.id, 'md')}
                  download
                  className="px-1.5 py-0.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 font-mono"
                >
                  .md
                </a>
                <a
                  href={api.getToolkitExportUrl(currentTask.id, 'json')}
                  download
                  className="px-1.5 py-0.5 rounded bg-slate-100 hover:bg-slate-200 text-slate-700 font-mono"
                >
                  .json
                </a>
                <a
                  href={api.getTaskBundleUrl(currentTask.id)}
                  download
                  title="Download consolidated ZIP bundle"
                  className="px-1.5 py-0.5 rounded bg-indigo-50 hover:bg-indigo-100 text-indigo-700 flex items-center font-mono"
                >
                  <Archive className="w-3 h-3 mr-0.5" /> .zip
                </a>
              </div>
            </div>
          )}

          {/* Viewer Content Area */}
          <div className="p-5 flex-1 overflow-y-auto max-h-[520px]">
            {!currentTask ? (
              <div className="h-full flex flex-col items-center justify-center text-center p-8 text-slate-400">
                <div className="w-14 h-14 bg-slate-100 rounded-full flex items-center justify-center text-slate-400 mb-3">
                  <FileText className="w-7 h-7" />
                </div>
                <h4 className="font-semibold text-slate-700 text-sm">No Extracted Text Yet</h4>
                <p className="text-xs text-slate-400 max-w-sm mt-1">
                  Upload a subtitle file (.srt, .vtt, .json) or paste cues on the left and click "Extract & Format Text" to generate clean paragraphs.
                </p>
              </div>
            ) : activePreviewTab === 'formatted' ? (
              <div className="space-y-4">
                {currentTask.segments && currentTask.segments.length > 0 ? (
                  currentTask.segments.map((seg, idx) => (
                    <div
                      key={seg.id || idx}
                      className="p-3.5 rounded-lg border border-slate-100 bg-slate-50/50 hover:bg-slate-50 transition leading-relaxed text-sm text-slate-800"
                    >
                      <div className="flex items-center justify-between text-[11px] text-slate-400 mb-1.5 font-mono">
                        <span>Paragraph #{seg.segment_order || idx + 1}</span>
                        {seg.start_time !== undefined && seg.start_time !== null && (
                          <span className="bg-slate-200/60 px-1.5 py-0.5 rounded text-[10px]">
                            {Math.floor(seg.start_time / 60)}:{(seg.start_time % 60).toFixed(0).padStart(2, '0')} - {Math.floor(seg.end_time / 60)}:{(seg.end_time % 60).toFixed(0).padStart(2, '0')}
                          </span>
                        )}
                      </div>
                      <p className="whitespace-pre-wrap">{seg.text || seg.raw_text}</p>
                    </div>
                  ))
                ) : (
                  <div className="whitespace-pre-wrap text-sm text-slate-800 leading-relaxed font-sans p-2">
                    {currentTask.full_text}
                  </div>
                )}
              </div>
            ) : activePreviewTab === 'raw' ? (
              <textarea
                readOnly
                value={currentTask.full_text || ''}
                rows={18}
                className="w-full text-xs font-mono p-3 bg-slate-50 border border-slate-200 rounded-lg outline-none resize-none leading-relaxed text-slate-800"
              />
            ) : (
              <pre className="text-[11px] font-mono p-3 bg-slate-900 text-emerald-400 rounded-lg overflow-x-auto leading-relaxed max-h-[460px]">
                {JSON.stringify(
                  {
                    title: metadata.title || 'Extracted Transcript',
                    stats: metadata,
                    full_text: currentTask.full_text,
                    paragraphs: currentTask.segments?.map((s) => ({
                      index: s.segment_order,
                      start_time: s.start_time,
                      end_time: s.end_time,
                      text: s.text || s.raw_text,
                    })),
                  },
                  null,
                  2
                )}
              </pre>
            )}
          </div>

          {/* Bottom Bar: Connected Workflows Handoffs */}
          {currentTask && (
            <div className="px-5 py-3 border-t border-slate-200 bg-slate-50/70 flex flex-wrap items-center justify-between gap-2">
              <span className="text-xs font-semibold text-slate-600 flex items-center">
                <ArrowRight className="w-3.5 h-3.5 mr-1 text-slate-400" />
                Send Extracted Text To:
              </span>

              <div className="flex flex-wrap items-center gap-2">
                <button
                  type="button"
                  onClick={() => {
                    if (onSendToTTS && currentTask.full_text) {
                      onSendToTTS(currentTask.full_text);
                    } else if (onNavigateToTool) {
                      onNavigateToTool('text_to_speech');
                    }
                  }}
                  className="px-3 py-1.5 bg-white hover:bg-slate-100 text-indigo-700 border border-indigo-200 rounded-lg text-xs font-medium flex items-center space-x-1.5 transition shadow-2xs"
                >
                  <Mic2 className="w-3.5 h-3.5 text-indigo-600" />
                  <span>Text to Speech Studio</span>
                </button>

                <button
                  type="button"
                  onClick={() => {
                    if (onSendToTranslation && currentTask.full_text) {
                      onSendToTranslation(currentTask.full_text);
                    } else if (onNavigateToTool) {
                      onNavigateToTool('text_translation');
                    }
                  }}
                  className="px-3 py-1.5 bg-white hover:bg-slate-100 text-purple-700 border border-purple-200 rounded-lg text-xs font-medium flex items-center space-x-1.5 transition shadow-2xs"
                >
                  <Languages className="w-3.5 h-3.5 text-purple-600" />
                  <span>Translation Studio</span>
                </button>

                {onSendToTranscriptToAudio && (
                  <button
                    type="button"
                    onClick={() => {
                      if (currentTask.source_task_id) {
                        onSendToTranscriptToAudio(currentTask.source_task_id);
                      } else if (onNavigateToTool) {
                        onNavigateToTool('transcript_to_audio');
                      }
                    }}
                    className="px-3 py-1.5 bg-white hover:bg-slate-100 text-teal-700 border border-teal-200 rounded-lg text-xs font-medium flex items-center space-x-1.5 transition shadow-2xs"
                  >
                    <Radio className="w-3.5 h-3.5 text-teal-600" />
                    <span>Transcript to Audio</span>
                  </button>
                )}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
