import React, { useState, useRef } from 'react';
import {
  UploadCloud,
  FileVideo,
  FileAudio,
  CheckCircle2,
  RefreshCw,
  AlertCircle,
} from 'lucide-react';
import { ProjectDetail, VideoInfo } from '../../types';

interface MediaTabProps {
  project: ProjectDetail;
  video: VideoInfo | null;
  onUploadFile: (file: File) => Promise<void>;
  onExtractAudio: () => Promise<void>;
  isUploading: boolean;
  isExtracting: boolean;
  uploadProgress: number;
}

export const MediaTab: React.FC<MediaTabProps> = ({
  project,
  video,
  onUploadFile,
  onExtractAudio,
  isUploading,
  isExtracting,
  uploadProgress,
}) => {
  const [dragActive, setDragActive] = useState<boolean>(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [localError, setLocalError] = useState<string | null>(null);

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === 'dragenter' || e.type === 'dragover') {
      setDragActive(true);
    } else if (e.type === 'dragleave') {
      setDragActive(false);
    }
  };

  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      validateAndUpload(e.dataTransfer.files[0]);
    }
  };

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      validateAndUpload(e.target.files[0]);
    }
  };

  const validateAndUpload = async (file: File) => {
    setLocalError(null);
    if (!file.name.toLowerCase().endsWith('.mp4') && !file.name.toLowerCase().endsWith('.mov')) {
      setLocalError('Invalid file format. Please upload an MP4 or MOV video file.');
      return;
    }
    const maxBytes = 500 * 1024 * 1024;
    if (file.size > maxBytes) {
      setLocalError(`File too large (${(file.size / (1024 * 1024)).toFixed(1)} MB). Max limit is 500 MB.`);
      return;
    }
    try {
      await onUploadFile(file);
    } catch (err: any) {
      setLocalError(err.message || 'Upload failed');
    }
  };

  const formatFileSize = (bytes?: number | null) => {
    if (!bytes) return '0 MB';
    const mb = bytes / (1024 * 1024);
    return `${mb.toFixed(2)} MB`;
  };

  const formatDuration = (secs?: number | null) => {
    if (!secs) return '0:00';
    const m = Math.floor(secs / 60);
    const s = Math.floor(secs % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  return (
    <div className="space-y-6">
      {/* Upload Zone */}
      <div className="bg-white rounded-2xl border border-slate-200 p-6 shadow-sm space-y-4">
        <div className="flex items-center justify-between pb-3 border-b border-slate-100">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-blue-50 text-blue-600">
              <UploadCloud className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-900">Source Video Media</h3>
              <p className="text-xs text-slate-500">Upload English MP4 video for audio extraction and dubbing</p>
            </div>
          </div>

          {video && (
            <button
              onClick={() => fileInputRef.current?.click()}
              disabled={isUploading || isExtracting}
              className="text-xs font-semibold text-indigo-600 hover:text-indigo-700 px-3 py-1.5 rounded-lg border border-slate-200 hover:bg-slate-50 transition"
            >
              Replace Video
            </button>
          )}
        </div>

        {/* Drag and Drop Container */}
        <div
          onDragEnter={handleDrag}
          onDragLeave={handleDrag}
          onDragOver={handleDrag}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
          className={`border-2 border-dashed rounded-2xl p-8 text-center cursor-pointer transition-all ${
            dragActive
              ? 'border-indigo-500 bg-indigo-50/50 scale-[1.01]'
              : 'border-slate-200 hover:border-indigo-400 hover:bg-slate-50/60'
          }`}
        >
          <input
            ref={fileInputRef}
            type="file"
            accept="video/mp4,video/quicktime"
            onChange={handleInputChange}
            className="hidden"
          />

          <div className="flex flex-col items-center justify-center space-y-2.5">
            <div className="w-12 h-12 rounded-2xl bg-indigo-50 text-indigo-600 flex items-center justify-center shadow-xs">
              <UploadCloud className="w-6 h-6" />
            </div>
            <div>
              <span className="font-semibold text-sm text-slate-800">
                Click to upload or drag & drop video
              </span>
              <p className="text-xs text-slate-400 mt-0.5">MP4 or MOV container (H.264/AAC), max 500 MB</p>
            </div>
          </div>
        </div>

        {/* Upload Progress */}
        {isUploading && (
          <div className="space-y-1.5 p-3 rounded-xl bg-indigo-50/60 border border-indigo-100 animate-fadeIn">
            <div className="flex justify-between text-xs text-indigo-700 font-semibold">
              <span className="flex items-center gap-1.5">
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
                Uploading video file to persistent storage...
              </span>
              <span>{uploadProgress}%</span>
            </div>
            <div className="w-full bg-indigo-200/50 h-2 rounded-full overflow-hidden">
              <div
                className="bg-indigo-600 h-full rounded-full transition-all duration-200"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
          </div>
        )}

        {localError && (
          <div className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-rose-700 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>{localError}</span>
          </div>
        )}
      </div>

      {/* Video Metadata & Extracted Audio Details */}
      {video && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
          {/* Video Metadata Card */}
          <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <span className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
                <FileVideo className="w-4 h-4 text-blue-600" />
                Container Specifications
              </span>
              <span className="text-[10px] font-semibold bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded-full">
                Verified FFprobe
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200">
                <span className="text-[11px] text-slate-400 block">Resolution</span>
                <span className="font-semibold text-slate-800">
                  {video.width && video.height ? `${video.width} × ${video.height}` : 'Standard HD'}
                </span>
              </div>

              <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200">
                <span className="text-[11px] text-slate-400 block">Duration</span>
                <span className="font-semibold text-slate-800 font-mono">
                  {formatDuration(video.duration_seconds)} ({video.duration_seconds?.toFixed(1)}s)
                </span>
              </div>

              <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200">
                <span className="text-[11px] text-slate-400 block">File Size</span>
                <span className="font-semibold text-slate-800">
                  {formatFileSize(video.file_size_bytes)}
                </span>
              </div>

              <div className="p-2.5 rounded-lg bg-slate-50 border border-slate-200">
                <span className="text-[11px] text-slate-400 block">Codecs</span>
                <span className="font-semibold text-slate-800 uppercase text-[11px]">
                  {video.video_codec || 'h264'} / {video.audio_codec || 'aac'}
                </span>
              </div>
            </div>
          </div>

          {/* Audio Extraction Card */}
          <div className="bg-white rounded-2xl border border-slate-200 p-5 shadow-sm space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100">
              <span className="text-xs font-bold text-slate-800 flex items-center gap-1.5">
                <FileAudio className="w-4 h-4 text-emerald-600" />
                Extracted PCM WAV Audio
              </span>
              {project.status !== 'uploaded' && project.status !== 'created' ? (
                <span className="text-[10px] font-semibold bg-emerald-100 text-emerald-800 px-2 py-0.5 rounded-full flex items-center gap-1">
                  <CheckCircle2 className="w-3 h-3" /> Ready (16kHz Mono)
                </span>
              ) : (
                <span className="text-[10px] font-semibold bg-amber-100 text-amber-800 px-2 py-0.5 rounded-full">
                  Pending Extraction
                </span>
              )}
            </div>

            <p className="text-xs text-slate-500">
              FFmpeg extracts clean 16,000 Hz 16-bit mono PCM audio from the video container for optimal Whisper transcription.
            </p>

            <div className="pt-2 flex items-center justify-between">
              <audio
                controls
                src={`/api/projects/${project.id}/audio`}
                className="w-full max-w-sm h-8"
              />

              <button
                onClick={onExtractAudio}
                disabled={isExtracting}
                className="ml-3 px-3.5 py-1.5 rounded-lg bg-slate-100 hover:bg-slate-200 text-slate-700 text-xs font-semibold transition shrink-0 flex items-center gap-1.5"
                title="Force re-extract audio"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isExtracting ? 'animate-spin' : ''}`} />
                <span>{isExtracting ? 'Extracting...' : 'Re-extract'}</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
