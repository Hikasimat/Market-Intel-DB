export function extractErrorMessage(action, fallback = 'Unable to connect to the server. Please try again.') {
  const payload = action?.payload;
  if (typeof payload === 'string' && payload.trim()) {
    if (payload === 'Network Error' || payload.toLowerCase().includes('timeout')) {
      return 'Temporary connection issue with the server. Please try again.';
    }
    return payload;
  }
  if (payload && typeof payload === 'object') {
    const candidate = payload.detail || payload.error || payload.message;
    if (typeof candidate === 'string' && candidate.trim()) {
      return candidate;
    }
  }
  const errMsg = action?.error?.message;
  if (typeof errMsg === 'string' && errMsg.trim() && errMsg !== 'Rejected') {
    if (errMsg === 'Network Error' || errMsg.toLowerCase().includes('timeout')) {
      return 'Temporary connection issue with the server. Please try again.';
    }
    return errMsg;
  }
  return fallback;
}
