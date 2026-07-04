/**
 * FF-042 STITCH_DRY_AUTHORITY_CLIENT_MIX_V1 — SFX layered on dry <video>.
 * Speech bytes come from the dry MP4; ambient bed uses StitchSlotAmbientBedAudio.
 */

import { resolveStitchSfxFetchUrl } from '../utils/stitchSlotVideo';
import { stitchSfxCuesToSchedule } from '../utils/stitchSfxCueSchedule';
import {
  stitchClientPreviewAudit,
  videoPlaybackSnapshot,
} from '../utils/stitchClientPreviewAudit';
import { STITCH_DRY_AUTHORITY_CLIENT_MIX_V1 } from '../utils/stitchSlotMuxAudioSig';

export interface StitchClientMixSfxCue {
  id?: string;
  offset_ms?: number;
  duration_ms?: number;
  volume?: number;
  fadein_ms?: number;
  fadeout_ms?: number;
  source_path?: string;
}

export interface StitchClientMixSlotInput {
  ambient_bed?: string;
  ambient_bed_path?: string;
  ambient_volume?: number;
  video_dur_ms?: number;
  sfx_cues?: StitchClientMixSfxCue[];
}

export interface StitchClientMixJobContext {
  jobName: string;
  slotKey: string;
}

/** One MediaElementSource per pooled <video> — browser forbids a second createMediaElementSource. */
type VideoSpeechChain = {
  ctx: AudioContext;
  speechNode: MediaElementAudioSourceNode;
  speechGain: GainNode;
};

const videoSpeechChains = new WeakMap<HTMLVideoElement, VideoSpeechChain>();

const activeMixEngines = new Set<StitchSlotAudioMixEngine>();

/** Stop every client preview SFX mix — used by Stop audio / tab change. */
export function stopAllStitchClientMix(): void {
  for (const engine of activeMixEngines) {
    engine.emergencyStop();
  }
}

function speechChainForVideo(video: HTMLVideoElement): VideoSpeechChain {
  const existing = videoSpeechChains.get(video);
  if (existing) return existing;
  const ctx = new AudioContext();
  const speechNode = ctx.createMediaElementSource(video);
  const speechGain = ctx.createGain();
  speechGain.gain.value = 1;
  speechNode.connect(speechGain);
  speechGain.connect(ctx.destination);
  const chain = { ctx, speechNode, speechGain };
  videoSpeechChains.set(video, chain);
  return chain;
}

/** Synchronous user-gesture hook — resume speech AudioContext before video.play(). */
export function resumeVideoSpeechContext(video: HTMLVideoElement | null | undefined): void {
  if (!video) return;
  const chain = videoSpeechChains.get(video);
  if (chain?.ctx.state === 'suspended') {
    void chain.ctx.resume();
  }
}

/** Ensure pooled composer video has a speech chain before first play (four-files client mix). */
export function primeVideoSpeechChain(video: HTMLVideoElement | null | undefined): void {
  if (!video) return;
  speechChainForVideo(video);
}

function speechContextState(video: HTMLVideoElement): string | undefined {
  return videoSpeechChains.get(video)?.ctx.state;
}

/** Native controls + keyboard play must resume speech AudioContext inside user-gesture stack. */
export function wireComposerVideoPlayGuard(
  video: HTMLVideoElement,
  ctx: { jobName?: string; slotKey?: string },
): () => void {
  const onGesture = () => {
    resumeVideoSpeechContext(video);
  };
  const onPlay = () => {
    resumeVideoSpeechContext(video);
    stitchClientPreviewAudit('VIDEO_PLAY', {
      job_name: ctx.jobName,
      slot_key: ctx.slotKey,
      speech_ctx_state: speechContextState(video),
      ...videoPlaybackSnapshot(video),
    });
  };
  const onPlaying = () => {
    stitchClientPreviewAudit('VIDEO_PLAYING', {
      job_name: ctx.jobName,
      slot_key: ctx.slotKey,
      speech_ctx_state: speechContextState(video),
      ...videoPlaybackSnapshot(video),
    });
  };
  const onPause = () => {
    stitchClientPreviewAudit('VIDEO_PAUSE', {
      job_name: ctx.jobName,
      slot_key: ctx.slotKey,
      ...videoPlaybackSnapshot(video),
    });
  };
  const onError = () => {
    stitchClientPreviewAudit('VIDEO_ERROR', {
      job_name: ctx.jobName,
      slot_key: ctx.slotKey,
      ...videoPlaybackSnapshot(video),
    });
  };
  const onWaiting = () => {
    stitchClientPreviewAudit('VIDEO_WAITING', {
      job_name: ctx.jobName,
      slot_key: ctx.slotKey,
      ...videoPlaybackSnapshot(video),
    });
  };
  video.addEventListener('click', onGesture, { capture: true });
  video.addEventListener('keydown', onGesture, { capture: true });
  video.addEventListener('play', onPlay);
  video.addEventListener('playing', onPlaying);
  video.addEventListener('pause', onPause);
  video.addEventListener('error', onError);
  video.addEventListener('waiting', onWaiting);
  return () => {
    video.removeEventListener('click', onGesture, { capture: true });
    video.removeEventListener('keydown', onGesture, { capture: true });
    video.removeEventListener('play', onPlay);
    video.removeEventListener('playing', onPlaying);
    video.removeEventListener('pause', onPause);
    video.removeEventListener('error', onError);
    video.removeEventListener('waiting', onWaiting);
  };
}

export class StitchSlotAudioMixEngine {
  private ctx: AudioContext | null = null;

  private sfxSources: AudioBufferSourceNode[] = [];

  private video: HTMLVideoElement | null = null;

  private slotInput: StitchClientMixSlotInput | null = null;

  private sfxBufferCache = new Map<string, AudioBuffer>();

  private playEpoch = 0;

  private bound = false;

  private playGuardUnwire: (() => void) | null = null;

  private jobCtx: StitchClientMixJobContext | null = null;

  private onPlay = () => {
    void this.handlePlay();
  };

  private onPause = () => {
    this.stopSfx();
  };

  private onSeeked = () => {
    void this.resyncFromVideo();
  };

  get marker(): string {
    return STITCH_DRY_AUTHORITY_CLIENT_MIX_V1;
  }

  async attach(
    video: HTMLVideoElement,
    slot: StitchClientMixSlotInput,
    jobCtx: StitchClientMixJobContext,
  ): Promise<void> {
    this.detachLayers();
    this.video = video;
    this.slotInput = slot;
    this.jobCtx = jobCtx;
    this.playGuardUnwire?.();
    this.playGuardUnwire = wireComposerVideoPlayGuard(video, {
      jobName: jobCtx.jobName,
      slotKey: jobCtx.slotKey,
    });
    const chain = speechChainForVideo(video);
    this.ctx = chain.ctx;
    stitchClientPreviewAudit('CLIENT_MIX_ATTACH', {
      job_name: jobCtx.jobName,
      slot_key: jobCtx.slotKey,
      speech_ctx_state: chain.ctx.state,
      sfx_cue_count: (slot.sfx_cues ?? []).length,
      ambient_bed: slot.ambient_bed,
      ...videoPlaybackSnapshot(video),
    });
    if (this.ctx.state === 'suspended') {
      await this.ctx.resume();
    }
    this.bindVideoEvents();
    activeMixEngines.add(this);
    if (!video.paused) {
      await this.handlePlay();
    }
  }

  async rebuildGeometry(slot: StitchClientMixSlotInput): Promise<void> {
    if (!this.video || !this.ctx) return;
    this.slotInput = slot;
    this.stopSfx();
    if (!this.video.paused) {
      await this.resyncFromVideo();
    }
  }

  /** Stop SFX layers only — keep pooled video speech chain alive. */
  detachLayers(): void {
    this.unbindVideoEvents();
    this.stopSfx();
  }

  detach(): void {
    activeMixEngines.delete(this);
    this.playGuardUnwire?.();
    this.playGuardUnwire = null;
    this.jobCtx = null;
    this.detachLayers();
    this.video = null;
    this.slotInput = null;
    this.ctx = null;
  }

  /** Stop SFX + pause slot video without tearing down the speech chain. */
  emergencyStop(): void {
    this.stopSfx();
    if (this.video) {
      this.video.pause();
      try {
        this.video.currentTime = 0;
      } catch {
        /* ignore seek on unloaded media */
      }
    }
  }

  private bindVideoEvents(): void {
    if (!this.video || this.bound) return;
    this.video.addEventListener('play', this.onPlay);
    this.video.addEventListener('pause', this.onPause);
    this.video.addEventListener('seeked', this.onSeeked);
    this.bound = true;
  }

  private unbindVideoEvents(): void {
    if (!this.video || !this.bound) return;
    this.video.removeEventListener('play', this.onPlay);
    this.video.removeEventListener('pause', this.onPause);
    this.video.removeEventListener('seeked', this.onSeeked);
    this.bound = false;
  }

  private async handlePlay(): Promise<void> {
    if (!this.ctx || !this.video) return;
    if (this.ctx.state === 'suspended') {
      await this.ctx.resume();
    }
    this.playEpoch += 1;
    await this.resyncFromVideo();
    stitchClientPreviewAudit('SFX_RESYNC', {
      job_name: this.jobCtx?.jobName,
      slot_key: this.jobCtx?.slotKey,
      speech_ctx_state: this.ctx.state,
      sfx_scheduled: this.sfxSources.length,
      ...videoPlaybackSnapshot(this.video),
    });
  }

  private async resyncFromVideo(): Promise<void> {
    if (!this.ctx || !this.video || this.video.paused) return;
    this.stopSfx();
    await this.scheduleSfxFromCurrentTime();
  }

  private async scheduleSfxFromCurrentTime(): Promise<void> {
    if (!this.ctx || !this.video || !this.slotInput) return;
    const videoT = this.video.currentTime;
    const epoch = this.playEpoch;
    const toSchedule = stitchSfxCuesToSchedule(this.slotInput.sfx_cues ?? [], videoT);
    for (const { cue, delayS } of toSchedule) {
      const srcPath = (cue.source_path ?? '').trim();
      let buffer: AudioBuffer;
      try {
        buffer = await this.loadSfxBuffer(srcPath);
      } catch (err) {
        console.warn('[StitchSlotAudioMixEngine] SFX load failed:', srcPath, err);
        continue;
      }
      if (!this.ctx || epoch !== this.playEpoch || this.video.paused) return;
      const source = this.ctx.createBufferSource();
      source.buffer = buffer;
      const gain = this.ctx.createGain();
      gain.gain.value = cue.volume ?? 0.45;
      source.connect(gain);
      gain.connect(this.ctx.destination);
      const playMs = cue.duration_ms ?? Math.round(buffer.duration * 1000);
      const playS = Math.min(buffer.duration, playMs / 1000);
      const when = this.ctx.currentTime + Math.max(0, delayS);
      source.start(when, 0, playS);
      this.sfxSources.push(source);
    }
  }

  private async loadSfxBuffer(sourcePath: string): Promise<AudioBuffer> {
    const cached = this.sfxBufferCache.get(sourcePath);
    if (cached) return cached;
    const url = resolveStitchSfxFetchUrl(sourcePath);
    const res = await fetch(url);
    if (!res.ok) throw new Error(`SFX fetch failed: ${sourcePath}`);
    const buf = await res.arrayBuffer();
    if (!this.ctx) throw new Error('AudioContext missing');
    const decoded = await this.ctx.decodeAudioData(buf.slice(0));
    this.sfxBufferCache.set(sourcePath, decoded);
    return decoded;
  }

  private stopSfx(): void {
    for (const src of this.sfxSources) {
      try {
        src.stop();
      } catch {
        /* already stopped */
      }
      src.disconnect();
    }
    this.sfxSources = [];
  }
}
