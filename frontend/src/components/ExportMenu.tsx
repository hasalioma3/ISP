import { useState } from 'react';
import { Download, FileSpreadsheet, FileText, Loader2 } from 'lucide-react';
import { toast } from 'react-hot-toast';
import api from '../services/api';
import { downloadBlob } from '../utils/downloadBlob';
import {
    DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from './ui/dropdown-menu';
import { cn } from '@/lib/utils';

type Format = 'csv' | 'xlsx' | 'pdf';

interface ExportMenuProps {
    /** API path of the report, e.g. '/analytics/income/' (the backend adds ?export=csv|pdf support). */
    path: string;
    params?: Record<string, string | number | undefined | null>;
    /** File name without extension. */
    filename: string;
    label?: string;
    className?: string;
    disabled?: boolean;
}

/**
 * "Export ▾" button offering CSV, Excel (.xlsx) or PDF for any report endpoint that goes
 * through apps.analytics.exports on the backend. The file is built server
 * side, so the PDF looks the same wherever it's exported from.
 */
export default function ExportMenu({ path, params, filename, label = 'Export', className, disabled }: ExportMenuProps) {
    const [busy, setBusy] = useState<Format | null>(null);

    const download = async (format: Format) => {
        setBusy(format);
        try {
            const clean = Object.fromEntries(Object.entries(params || {}).filter(([, v]) => v !== undefined && v !== null && v !== ''));
            const res = await api.get(path, { params: { ...clean, export: format }, responseType: 'blob' });
            downloadBlob(res.data, `${filename}.${format}`);
        } catch (err: any) {
            // Errors come back as a Blob too; pull the JSON message out of it.
            let message = 'Export failed';
            try {
                const text = await err.response?.data?.text?.();
                message = JSON.parse(text).error || message;
            } catch { /* keep the generic message */ }
            toast.error(message);
        } finally {
            setBusy(null);
        }
    };

    return (
        <DropdownMenu>
            <DropdownMenuTrigger asChild>
                <button
                    type="button"
                    disabled={disabled || !!busy}
                    className={cn(
                        'inline-flex h-10 items-center gap-2 rounded-full border border-input bg-card px-4 text-[13.5px] font-semibold text-foreground hover:bg-accent disabled:opacity-60',
                        className,
                    )}
                >
                    {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Download className="h-4 w-4" strokeWidth={1.8} />}
                    {label}
                </button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-48">
                <DropdownMenuItem onClick={() => download('xlsx')}>
                    <FileSpreadsheet className="h-4 w-4" /> Excel (.xlsx)
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => download('csv')}>
                    <FileSpreadsheet className="h-4 w-4" /> CSV
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => download('pdf')}>
                    <FileText className="h-4 w-4" /> PDF
                </DropdownMenuItem>
            </DropdownMenuContent>
        </DropdownMenu>
    );
}
