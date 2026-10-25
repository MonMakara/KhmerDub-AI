import React, { useRef, useState, useMemo, forwardRef, useImperativeHandle } from 'react';
import {
  Play,
  Pause,
  Volume2,
  VolumeX,
  Maximize2,
  Minimize2,
  RotateCcw,
  Film,
  Subtitles,
} from 'lucide-react';
import { VideoInfo, SubtitleSegment, SubtitleStylePreferences } from '../../types';

export interface VideoPlayerRef {
  seekTo: (timeInSeconds: number) => void;
  play: () => void;
  pause: () => void;
}

interface PersistentVideoPlayerProps {
  projectId: string;
  video: VideoInfo | null;
  activeSegmentOrder?: number | null;
  onTimeUpdate?: (currentTime: number) => void;
  onPlayStateChange?: (isPlaying: boolean) => void;
  subtitles?: SubtitleSegment[];
  subtitleLanguage?: 'off' | 'km' | 'en';
  onSubtitleLanguageChange?: (lang: 'off' | 'km' | 'en') => void;
  subtitleStyles?: SubtitleStylePreferences;
}

export const PersistentVideoPlayer = forwardRef<VideoPlayerRef, PersistentVideoPlayerProps>(
  (
    {
      projectId,
      video,
      activeSegmentOrder,
      onTimeUpdate,
      onPlayStateChange,
      subtitles = [],
      subtitleLanguage = 'off',
      onSubtitleLanguageChange,
      subtitleStyles,
    },
    ref
  ) => {
    const videoRef = useRef<HTMLVideoElement>(null);
    const [isPlaying, setIsPlaying] = useState<boolean>(false);
    const [currentTime, setCurrentTime] = useState<number>(0);
    const [duration, setDuration] = useState<number>(video?.duration_seconds || 0);
    const [volume, setVolume] = useState<number>(1);
    const [isMuted, setIsMuted] = useState<boolean>(false);
    const [playbackRate, setPlaybackRate] = useState<number>(1);
    const [isCollapsed, setIsCollapsed] = useState<boolean>(false);

    useImperativeHandle(ref, () => ({
      seekTo: (timeInSeconds: number) => {
        if (videoRef.current) {
          videoRef.current.currentTime = Math.max(0, timeInSeconds);
          videoRef.current.play().catch(() => {});
          setIsPlaying(true);
          onPlayStateChange?.(true);
        }
      },
      play: () => {
        videoRef.current?.play().catch(() => {});
        setIsPlaying(true);
        onPlayStateChange?.(true);
      },
      pause: () => {
        videoRef.current?.pause();
        setIsPlaying(false);
        onPlayStateChange?.(false);
      },
    }));

    const videoSrc = `/api/projects/${projectId}/video`;

    // Active subtitle calculation
    const activeSubtitle = useMemo(() => {
      if (!subtitles || subtitleLanguage === 'off') return null;
      return subtitles.find(
        (s) => currentTime >= s.start_time && currentTime <= s.end_time
      );
    }, [subtitles, subtitleLanguage, currentTime]);

    const handleTimeUpdate = () => {
      if (videoRef.current) {
        const t = videoRef.current.currentTime;
        setCurrentTime(t);
        if (onTimeUpdate) {
          onTimeUpdate(t);
        }
      }
    };

    const handleLoadedMetadata = () => {
      if (videoRef.current) {
        setDuration(videoRef.current.duration || video?.duration_seconds || 0);
      }
    };

    const togglePlay = () => {
      if (!videoRef.current) return;
      if (isPlaying) {
        videoRef.current.pause();
        setIsPlaying(false);
        onPlayStateChange?.(false);
      } else {
        videoRef.current.play().catch(() => {});
        setIsPlaying(true);
        onPlayStateChange?.(true);
      }
    };

    const handleSeek = (e: React.ChangeEvent<HTMLInputElement>) => {
      const targetTime = parseFloat(e.target.value);
      if (videoRef.current) {
        videoRef.current.currentTime = targetTime;
        setCurrentTime(targetTime);
      }
    };

    const toggleMute = () => {
      if (!videoRef.current) return;
      const newMuted = !isMuted;
      videoRef.current.muted = newMuted;
      setIsMuted(newMuted);
    };

    const handleVolumeChange = (e: React.ChangeEvent<HTMLInputElement>) => {
      const v = parseFloat(e.target.value);
      setVolume(v);
      if (videoRef.current) {
        videoRef.current.volume = v;
        videoRef.current.muted = v === 0;
        setIsMuted(v === 0);
      }
    };

    const changePlaybackRate = (rate: number) => {
      setPlaybackRate(rate);
      if (videoRef.current) {
        videoRef.current.playbackRate = rate;
      }
    };

    const formatTime = (seconds: number) => {
      const mins = Math.floor(seconds / 60);
      const secs = Math.floor(seconds % 60);
      const ms = Math.floor((seconds % 1) * 10);
      return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}.${ms}`;
    };

    if (!video) {
      return (
        <div className="bg-slate-900 rounded-2xl p-6 text-center text-slate-400 border border-slate-800 space-y-3">
          <Film className="w-10 h-10 text-slate-600 mx-auto" />
          <p className="text-xs">No video uploaded yet. Please upload an MP4 in the Media tab.</p>
        </div>
      );
    }

    return (
      <div className="bg-slate-950 rounded-2xl border border-slate-800 shadow-xl overflow-hidden text-white transition-all">
        {/* Video Header bar */}
        <div className="px-4 py-2.5 bg-slate-900 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2 min-w-0">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-xs font-semibold text-slate-200 truncate">{video.filename}</span>
            {activeSegmentOrder && (
              <span className="text-[10px] bg-indigo-500/20 text-indigo-300 font-mono px-1.5 py-0.5 rounded border border-indigo-500/30">
                Segment #{activeSegmentOrder}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2 shrink-0">
            <span className="text-[11px] font-mono text-slate-400">
              {formatTime(currentTime)} / {formatTime(duration)}
            </span>
            <button
              onClick={() => setIsCollapsed(!isCollapsed)}
              className="p-1 rounded text-slate-400 hover:text-white hover:bg-slate-800 transition"
              title={isCollapsed ? 'Expand Preview' : 'Collapse Preview'}
            >
              {isCollapsed ? <Maximize2 className="w-3.5 h-3.5" /> : <Minimize2 className="w-3.5 h-3.5" />}
            </button>
          </div>
        </div>

        {/* Video Canvas */}
        {!isCollapsed && (
          <div className="relative aspect-video max-h-[360px] bg-black flex items-center justify-center group mx-auto">
            <video
              ref={videoRef}
              src={videoSrc}
              className="w-full h-full object-contain"
              onTimeUpdate={handleTimeUpdate}
              onLoadedMetadata={handleLoadedMetadata}
              onPlay={() => {
                setIsPlaying(true);
                onPlayStateChange?.(true);
              }}
              onPause={() => {
                setIsPlaying(false);
                onPlayStateChange?.(false);
              }}
              onClick={togglePlay}
            />

            {/* Big Center Play Overlay (when paused) */}
            {!isPlaying && (
              <button
                onClick={togglePlay}
                className="absolute inset-0 m-auto w-14 h-14 rounded-full bg-indigo-600/90 text-white flex items-center justify-center shadow-lg hover:scale-105 transition transform"
              >
                <Play className="w-6 h-6 ml-0.5" />
              </button>
            )}

            {/* Subtitle Caption Overlay */}
            {activeSubtitle && (
              <div
                data-testid="video-subtitle-overlay"
                className={`absolute left-4 right-4 text-center pointer-events-none transition-all z-20 flex justify-center ${
                  subtitleStyles?.position === 'top'
                    ? 'top-4'
                    : subtitleStyles?.position === 'middle'
                    ? 'top-1/2 -translate-y-1/2'
                    : ''
                }`}
                style={
                  subtitleStyles?.position === 'top' || subtitleStyles?.position === 'middle'
                    ? {}
                    : { bottom: `${subtitleStyles?.bottomMargin ?? 12}px` }
                }
              >
                <div
                  className={`px-4 py-1.5 rounded-lg max-w-[88%] inline-block leading-relaxed select-none transition-all ${
                    activeSubtitle.language === 'km' ? 'font-khmer font-medium' : 'font-sans'
                  } ${
                    subtitleStyles?.preset === 'cinema'
                      ? 'drop-shadow-[0_2px_4px_rgba(0,0,0,0.95)]'
                      : 'shadow-lg'
                  }`}
                  style={{
                    backgroundColor:
                      subtitleStyles?.preset === 'cinema'
                        ? 'transparent'
                        : subtitleStyles?.bgOpacity === 0
                        ? 'transparent'
                        : `rgba(0, 0, 0, ${subtitleStyles?.bgOpacity ?? 0.75})`,
                    color:
                      subtitleStyles?.preset === 'cinema'
                        ? '#facc15'
                        : subtitleStyles?.textColor === 'yellow'
                        ? '#facc15'
                        : subtitleStyles?.textColor === 'cyan'
                        ? '#38bdf8'
                        : subtitleStyles?.textColor === 'green'
                        ? '#4ade80'
                        : '#ffffff',
                    textShadow:
                      subtitleStyles?.preset === 'cinema' || subtitleStyles?.shadow
                        ? '2px 2px 4px rgba(0,0,0,0.95), -1px -1px 2px rgba(0,0,0,0.85), 0 0 6px rgba(0,0,0,0.9)'
                        : 'none',
                    fontSize:
                      subtitleStyles?.fontSize === 'sm'
                        ? '0.875rem'
                        : subtitleStyles?.fontSize === 'lg'
                        ? '1.125rem'
                        : subtitleStyles?.fontSize === 'xl'
                        ? '1.25rem'
                        : '1rem',
                  }}
                >
                  {activeSubtitle.text.split('\n').map((line, i) => (
                    <React.Fragment key={i}>
                      {line}
                      {i < activeSubtitle.text.split('\n').length - 1 && <br />}
                    </React.Fragment>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Custom Transport Controls Bar */}
        <div className="px-4 py-3 bg-slate-900/90 space-y-2 border-t border-slate-800/80">
          {/* Seeker Slider */}
          <div className="flex items-center gap-2">
            <input
              type="range"
              min={0}
              max={duration || 100}
              step={0.05}
              value={currentTime}
              onChange={handleSeek}
              className="w-full h-1.5 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-indigo-500 focus:outline-none"
            />
          </div>

          {/* Action buttons row */}
          <div className="flex items-center justify-between text-xs">
            <div className="flex items-center gap-2">
              <button
                onClick={togglePlay}
                className="p-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white transition shadow-sm"
                title={isPlaying ? 'Pause (Space)' : 'Play (Space)'}
              >
                {isPlaying ? <Pause className="w-4 h-4" /> : <Play className="w-4 h-4 ml-0.5" />}
              </button>

              <button
                onClick={() => {
                  if (videoRef.current) {
                    videoRef.current.currentTime = 0;
                  }
                }}
                className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
                title="Restart"
              >
                <RotateCcw className="w-4 h-4" />
              </button>

              {/* Volume */}
              <div className="flex items-center gap-1.5 ml-1">
                <button
                  onClick={toggleMute}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition"
                >
                  {isMuted || volume === 0 ? (
                    <VolumeX className="w-4 h-4 text-rose-400" />
                  ) : (
                    <Volume2 className="w-4 h-4" />
                  )}
                </button>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={isMuted ? 0 : volume}
                  onChange={handleVolumeChange}
                  className="w-16 h-1 bg-slate-800 rounded-lg appearance-none cursor-pointer accent-indigo-500"
                />
              </div>
            </div>

            {/* Right: Speed & Subtitles selection */}
            <div className="flex items-center gap-2">
              {/* Closed Captions (CC) Toggle */}
              {onSubtitleLanguageChange && (
                <button
                  data-testid="video-subtitle-toggle"
                  onClick={() => {
                    const next =
                      subtitleLanguage === 'off'
                        ? 'km'
                        : subtitleLanguage === 'km'
                        ? 'en'
                        : 'off';
                    onSubtitleLanguageChange(next);
                  }}
                  className={`flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-semibold transition border ${
                    subtitleLanguage !== 'off'
                      ? 'bg-indigo-600 text-white border-indigo-500 shadow-xs'
                      : 'bg-slate-800 text-slate-400 border-slate-700 hover:text-white'
                  }`}
                  title={`Captions: ${subtitleLanguage.toUpperCase()}. Click to toggle (Off -> KM -> EN).`}
                >
                  <Subtitles className="w-3.5 h-3.5" />
                  <span>{subtitleLanguage === 'off' ? 'CC Off' : `CC ${subtitleLanguage.toUpperCase()}`}</span>
                </button>
              )}

              {/* Speed selection */}
              <div className="flex items-center gap-1">
              {[0.75, 1, 1.25, 1.5].map((rate) => (
                <button
                  key={rate}
                  onClick={() => changePlaybackRate(rate)}
                  className={`px-1.5 py-0.5 rounded text-[11px] font-mono transition ${
                    playbackRate === rate
                      ? 'bg-indigo-600 text-white font-semibold'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {rate}x
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
);
