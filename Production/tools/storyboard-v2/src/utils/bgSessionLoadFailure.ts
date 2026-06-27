import { isTransientSessionFetchError } from './sessionFetchRetry.ts';

/** Toast policy for ensureBgSession — suppress restart blips when cached beats remain. */
export function shouldToastBgSessionLoadFailure(opts: {
  message: string;
  hadCachedBeats: boolean;
  retriesExhausted: boolean;
}): boolean {
  if (!opts.retriesExhausted) return false;
  if (isTransientSessionFetchError(opts.message) && opts.hadCachedBeats) {
    return false;
  }
  return true;
}
