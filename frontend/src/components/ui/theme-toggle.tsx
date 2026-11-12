import { Moon, Sun } from 'lucide-react';
import { useThemeStore } from '../../store/themeStore';
import { cn } from '@/lib/utils';

export function ThemeToggle({ className }: { className?: string }) {
    const theme = useThemeStore((s) => s.theme);
    const toggleTheme = useThemeStore((s) => s.toggleTheme);
    const label = theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode';

    return (
        <button
            onClick={toggleTheme}
            title={label}
            aria-label={label}
            className={cn('rounded-lg p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground', className)}
        >
            {theme === 'dark' ? <Sun className="h-5 w-5" strokeWidth={1.8} /> : <Moon className="h-5 w-5" strokeWidth={1.8} />}
        </button>
    );
}
