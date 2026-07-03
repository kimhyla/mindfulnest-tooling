/**
 * FF-042 STITCH_DRY_AUTHORITY_CLIENT_MIX_V1 — SFX layered on dry <video>.
 * Speech bytes come from the dry MP4; ambient bed uses StitchSlotAmbientBedAudio.
 */

import { resolveServerMediaUrl } from '../utils/stitchSlotVideo';
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

const DRIFT_RESYNC_MS = 80;

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

export class StitchSlotAudioMixEngine {
  private ctx: AudioContext | null = null;

  private sfxSources: AudioBufferSourceNode[] = [];

  private video: HTMLVideoElement | null = null;

  private slotInput: StitchClientMixSlotInput | null = null;

  private sfxBufferCache = new Map<string, AudioBuffer>();

  private playEpoch = 0;

  private bound = false;

  private onPlay = () => {
    void this.handlePlay();
  };

  private onPause = () => {
    this.stopSfx();
  };

  private onSeeked = () => {
    void this.resyncFromVideo();
  };

  private onTimeUpdate = () => {
    if (!this.video || this.video.paused) return;
    const driftMs = Math.abs(this.video.currentTime - this.lastScheduledVideoT) * 1000;
    if (driftMs > DRIFT_RESYNC_MS) {
      void this.resyncFromVideo();
    }
  };

  private lastScheduledVideoT = 0;

  get marker(): string {
    return STITCH_DRY_AUTHORITY_CLIENT_MIX_V1;
  }

  async attach(
    video: HTMLVideoElement,
    slot: StitchClientMixSlotInput,
    _jobCtx: StitchClientMixJobContext,
  ): Promise<void> {
    this.detachLayers();
    this.video = video;
    this.slotInput = slot;
    const chain = speechChainForVideo(video);
    this.ctx = chain.ctx;
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
    if (this.ctx?.state === 'running') {
      void this.ctx.suspend();
    }
  }

  private bindVideoEvents(): void {
    if (!this.video || this.bound) return;
    this.video.addEventListener('play', this.onPlay);
    this.video.addEventListener('pause', this.onPause);
    this.video.addEventListener('seeked', this.onSeeked);
    this.video.addEventListener('timeupdate', this.onTimeUpdate);
    this.bound = true;
  }

  private unbindVideoEvents(): void {
    if (!this.video || !this.bound) return;
    this.video.removeEventListener('play', this.onPlay);
    this.video.removeEventListener('pause', this.onPause);
    this.video.removeEventListener('seeked', this.onSeeked);
    this.video.removeEventListener('timeupdate', this.onTimeUpdate);
    this.bound = false;
  }

  private async handlePlay(): Promise<void> {
    if (!this.ctx || !this.video) return;
    if (this.ctx.state === 'suspended') {
      await this.ctx.resume();
    }
    this.playEpoch += 1;
    await this.resyncFromVideo();
  }

  private async resyncFromVideo(): Promise<void> {
    if (!this.ctx || !this.video || this.video.paused) return;
    this.stopSfx();
    this.lastScheduledVideoT = this.video.currentTime;
    await this.scheduleSfxFromCurrentTime();
  }

  private async scheduleSfxFromCurrentTime(): Promise<void> {
    if (!this.ctx || !this.video || !this.slotInput) return;
    const cues = this.slotInput.sfx_cues ?? [];
    const videoT = this.video.currentTime;
    const epoch = this.playEpoch;
    for (const cue of cues) {
      const offsetS = (cue.offset_ms ?? 0) / 1000;
      const delayS = offsetS - videoT;
      if (delayS < -0.05) continue;
      const srcPath = (cue.source_path ?? '').trim();
      if (!srcPath) continue;
      const buffer = await this.loadSfxBuffer(srcPath);
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
    const url = resolveServerMediaUrl(`/files?path=${encodeURIComponent(sourcePath)}`);
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
