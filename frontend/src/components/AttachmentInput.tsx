import { Paperclip, Camera } from 'lucide-react';

interface AttachmentInputProps {
    label?: string;
    file: File | null;
    onFileChange: (file: File | null) => void;
    existingUrl?: string | null;
}

// Two explicit actions rather than one plain file input: "Take Photo" sets
// accept="image/*" + capture="environment", which makes mobile browsers
// (iOS Safari, Android Chrome) open the camera directly instead of a
// generic file/photo-library chooser -- "Choose File" stays a normal
// picker for an existing photo or PDF. capture is simply ignored on
// desktop, where both buttons just open a regular file browser.
export default function AttachmentInput({ label = 'Attachment (optional)', file, onFileChange, existingUrl }: AttachmentInputProps) {
    return (
        <div>
            <label className="block text-sm font-medium text-foreground/80 mb-1">{label}</label>
            {existingUrl && !file && (
                <a href={existingUrl} target="_blank" rel="noreferrer" className="flex items-center gap-1 text-xs text-primary hover:underline mb-1">
                    <Paperclip className="h-3 w-3" /> Current attachment
                </a>
            )}
            <div className="grid grid-cols-2 gap-2">
                <label className="flex items-center justify-center gap-2 border rounded-lg px-3 py-2 text-sm text-foreground/80 cursor-pointer hover:bg-secondary">
                    <Camera className="h-4 w-4" /> Take Photo
                    <input
                        type="file"
                        accept="image/*"
                        capture="environment"
                        className="hidden"
                        onChange={(e) => onFileChange(e.target.files?.[0] || null)}
                    />
                </label>
                <label className="flex items-center justify-center gap-2 border rounded-lg px-3 py-2 text-sm text-foreground/80 cursor-pointer hover:bg-secondary">
                    <Paperclip className="h-4 w-4" /> Choose File
                    <input
                        type="file"
                        accept=".pdf,.jpg,.jpeg,.png,.heic"
                        className="hidden"
                        onChange={(e) => onFileChange(e.target.files?.[0] || null)}
                    />
                </label>
            </div>
            {file && <p className="text-xs text-green-600 mt-1">Selected: {file.name}</p>}
            {existingUrl && <p className="text-xs text-muted-foreground mt-1">Choosing a new file replaces the current attachment.</p>}
        </div>
    );
}
