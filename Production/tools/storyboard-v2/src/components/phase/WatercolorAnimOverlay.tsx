/**
 * Live animated watercolor overlay — canvas chromakey of wc_v13 rub MP4.
 * Magenta matte is keyed in JS (matches ffmpeg chromakey=0xFF00FF:0.25:0.0).
 * video.loop keeps rub motion alive for the full cue window while WaveSurfer plays.
 */
import { useEffect, useRef } from 'preact/hooks';
import { applyMagentaChromakey } from './watercolorChromakey';

export interface WatercolorAnimOverlayProps {
  src: string;
  elapsedMs: number;
  isWavePlaying: boolean;
  opacity: number;
}

export function WatercolorAnimOverlay({
  src,
  elapsedMs,
  isWavePlaying,
  opacity,
}: WatercolorAnimOverlayProps) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const rafRef = useRef(0);

  const drawKeyedFrame = () => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas || video.readyState < 2 || !video.videoWidth) return;
    const w = video.videoWidth;
    const h = video.videoHeight;
    if (canvas.width !== w || canvas.height !== h) {
      canvas.width = w;
      canvas.height = h;
    }
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    ctx.drawImage(video, 0, 0, w, h);
    const img = ctx.getImageData(0, 0, w, h);
    applyMagentaChromakey(img);
    ctx.putImageData(img, 0, 0);
  };

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.muted = true;
    video.loop = true;
    video.playsInline = true;
    video.preload = 'auto';
    const onLoaded = () => drawKeyedFrame();
    video.addEventListener('loadeddata', onLoaded);
    return () => video.removeEventListener('loadeddata', onLoaded);
  }, [src]);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;

    cancelAnimationFrame(rafRef.current);

    if (isWavePlaying) {
      const loop = () => {
        drawKeyedFrame();
        rafRef.current = requestAnimationFrame(loop);
      };
      video.muted = true;
      void video.play().catch(() => {
        requestAnimationFrame(() => {
          video.muted = true;
          void video.play().catch(() => {});
        });
      });
      rafRef.current = requestAnimationFrame(loop);
      return () => {
        cancelAnimationFrame(rafRef.current);
        video.pause();
      };
    }

    video.pause();
    if (video.duration && Number.isFinite(video.duration)) {
      const t = Math.max(0, (elapsedMs / 1000) % video.duration);
      if (Math.abs(video.currentTime - t) > 0.05) {
        video.currentTime = t;
      }
    }
    drawKeyedFrame();
    return undefined;
  }, [isWavePlaying, src]);

  // Scrub frame while paused (waveform seek).
  useEffect(() => {
    if (isWavePlaying) return;
    const video = videoRef.current;
    if (!video || !video.duration || !Number.isFinite(video.duration)) return;
    const t = Math.max(0, (elapsedMs / 1000) % video.duration);
    if (Math.abs(video.currentTime - t) > 0.05) {
      video.currentTime = t;
    }
    drawKeyedFrame();
  }, [elapsedMs, isWavePlaying]);

  return (
    <>
      <video ref={videoRef} src={src} style={{ display: 'none' }} aria-hidden="true" />
      <canvas
        ref={canvasRef}
        class="mn-lipsync-watercolor-overlay"
        style={{ opacity }}
        aria-hidden="true"
      />
    </>
  );
}
