/** Category O — toast when session GET fails while local busy latch is set. */
export function shouldToastBgSessionRefreshFailure(
  hadBusyLatch: boolean,
  fetchOk: boolean,
  hasData: boolean,
): boolean {
  return hadBusyLatch && (!fetchOk || !hasData);
}
