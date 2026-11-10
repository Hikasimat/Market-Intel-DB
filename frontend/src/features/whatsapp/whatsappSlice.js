import { createSlice } from '@reduxjs/toolkit';

/**
 * whatsappSlice
 *
 * Manages unread count, active session, and real-time calling notifications for WhatsApp,
 * ensuring session stability and cross-page incoming call alerts.
 */
const whatsappSlice = createSlice({
  name: 'whatsapp',
  initialState: {
    unreadCount: 0,
    incomingCall: null,
    isCallingPaired: false,
    activeSession: null,
  },
  reducers: {
    setWhatsappUnreadCount(state, action) {
      state.unreadCount = typeof action.payload === 'number' ? action.payload : 0;
    },
    setIncomingCall(state, action) {
      state.incomingCall = action.payload || null;
    },
    setIsCallingPaired(state, action) {
      state.isCallingPaired = Boolean(action.payload);
    },
    setActiveSession(state, action) {
      state.activeSession = action.payload || null;
    },
  },
});

export const {
  setWhatsappUnreadCount,
  setIncomingCall,
  setIsCallingPaired,
  setActiveSession,
} = whatsappSlice.actions;
export default whatsappSlice.reducer;

