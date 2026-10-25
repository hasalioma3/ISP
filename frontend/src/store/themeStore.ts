import { create } from 'zustand';
import { persist } from 'zustand/middleware';

type Theme = 'light' | 'dark';

interface ThemeState {
    theme: Theme;
    toggleTheme: () => void;
}

function applyTheme(theme: Theme) {
    document.documentElement.classList.toggle('dark', theme === 'dark');
}

export const useThemeStore = create<ThemeState>()(
    persist(
        (set, get) => ({
            // Falls back to the OS preference the very first time (no stored
            // choice yet) rather than always defaulting to light.
            theme: window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light',
            toggleTheme: () => {
                const next = get().theme === 'dark' ? 'light' : 'dark';
                applyTheme(next);
                set({ theme: next });
            },
        }),
        {
            name: 'theme-storage',
            onRehydrateStorage: () => (state) => {
                // Runs after the persisted value (if any) loads -- applies it
                // immediately so the `dark` class is set before first paint
                // of anything that depends on it.
                if (state) applyTheme(state.theme);
            },
        }
    )
);

// No persisted value yet on a first-ever visit: apply the OS-preference
// default computed above, since onRehydrateStorage only fires when there
// was something to rehydrate.
applyTheme(useThemeStore.getState().theme);
