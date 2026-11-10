import { configureStore, combineReducers } from '@reduxjs/toolkit';
import authReducer from '../features/auth/authSlice';
import marketEventReducer from '../features/marketEvents/marketEventSlice';
import prospectReducer from '../features/prospects/prospectSlice';
import lqPipelineReducer from '../features/lqPipeline/lqPipelineSlice';
import userReducer from '../features/users/userSlice';
import outreachReducer from '../features/outreach/outreachSlice';
import inboxReducer from '../features/inbox/inboxSlice';
import managerReducer from '../features/manager/managerSlice';
import whatsappReducer from '../features/whatsapp/whatsappSlice';
import { clearUserCache } from '../services/cache/cacheService';
import { clearUserInboxCache } from '../services/cache/inboxCacheService';

const appReducer = combineReducers({
  auth: authReducer,
  prospects: prospectReducer,
  marketEvents: marketEventReducer,
  lqPipeline: lqPipelineReducer,
  users: userReducer,
  outreach: outreachReducer,
  inbox: inboxReducer,
  manager: managerReducer,
  whatsapp: whatsappReducer,
});

const rootReducer = (state, action) => {
  if (action.type === 'auth/logout') {
    // Clear the current user's private IndexedDB caches before wiping Redux state.
    // We use the userId stored in state.auth.user before it's cleared.
    const userId = state?.auth?.user?.id;
    if (userId) {
      // Fire-and-forget: IndexedDB operations are async; we don't block the
      // synchronous Redux dispatch, but the data is purged in the background.
      clearUserCache(userId);
      clearUserInboxCache(userId);
    }
    // Reset all Redux state slices to their initial values
    state = undefined;
  }
  return appReducer(state, action);
};

const loadState = () => {
  try {
    const serializedState = sessionStorage.getItem('reduxState');
    if (serializedState === null) {
      return undefined;
    }
    return JSON.parse(serializedState);
  } catch (err) {
    return undefined;
  }
};

const saveState = (state) => {
  try {
    const serializedState = JSON.stringify(state);
    sessionStorage.setItem('reduxState', serializedState);
  } catch (err) {
    // Ignore write errors
  }
};

export const store = configureStore({
  reducer: rootReducer,
  preloadedState: loadState(),
});

store.subscribe(() => {
  saveState(store.getState());
});
