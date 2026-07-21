export function resizeAnalysisSplit(
  startHeight: number,
  pointerDelta: number,
  minimum: number,
  maximum = Number.POSITIVE_INFINITY,
) {
  return Math.min(maximum, Math.max(minimum, startHeight + pointerDelta));
}
