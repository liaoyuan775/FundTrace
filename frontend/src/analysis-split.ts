const COLLAPSED_TRANSACTION_HEIGHT = 74;
const ANALYSIS_SPLITTER_HEIGHT = 8;

export function maximumGraphHeight(
  layoutHeight: number,
  minimumGraphHeight: number,
) {
  return Math.max(
    minimumGraphHeight,
    layoutHeight - COLLAPSED_TRANSACTION_HEIGHT - ANALYSIS_SPLITTER_HEIGHT,
  );
}

export function resizeAnalysisSplit(
  startHeight: number,
  pointerDelta: number,
  minimum: number,
  maximum = Number.POSITIVE_INFINITY,
) {
  return Math.min(maximum, Math.max(minimum, startHeight + pointerDelta));
}
