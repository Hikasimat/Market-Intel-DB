import { createSlice } from '@reduxjs/toolkit';

/**
 * whatsappSlice
 *
 * Manages unread count and notification state for WhatsApp,
 * mirroring inboxSlice for email notifications.
 */
const whatsappSlice = createSlice({
  name: 'whatsapp',
  initialState: {
    unreadCount: 0,
  },
  reducers: {
    setWhatsappUnreadCount(state, action) {
      state.unreadCount = typeof action.payload === 'number' ? action.payload : 0;
    },
  },
});

export const { setWhatsappUnreadCount } = whatsappSlice.actions;
export default whatsappSlice.reducer;
