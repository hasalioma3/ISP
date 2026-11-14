import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { ChevronDown, Eye, Plus, RotateCcw, Save, Trash2 } from 'lucide-react';
import { notificationAPI } from '../../services/api';
import { getErrorMessage } from '../../utils/getErrorMessage';

const SECTION_CARD = 'bg-card border rounded-lg p-4 sm:p-5';

interface SystemTemplate {
    key: string;
    name: string;
    body: string;
    default_body: string;
    is_custom: boolean;
    placeholders: Record<string, string>;
}

interface PromoTemplate {
    id: number;
    name: string;
    body: string;
}

export const TEMPLATES_KEY = ['notification-templates'];

export function useMessageTemplates() {
    return useQuery({
        queryKey: TEMPLATES_KEY,
        queryFn: async () => (await notificationAPI.getTemplates()).data as {
            system: SystemTemplate[];
            promo: PromoTemplate[];
            promo_placeholders: Record<string, string>;
        },
    });
}

/** Textarea + clickable placeholder chips (inserted at the cursor) + sample preview. */
function TemplateEditor({ value, onChange, placeholders }: {
    value: string;
    onChange: (v: string) => void;
    placeholders: Record<string, string>;
}) {
    const ref = useRef<HTMLTextAreaElement>(null);
    const [preview, setPreview] = useState<{ preview: string; length: number; sms_parts: number } | null>(null);

    const insert = (name: string) => {
        const el = ref.current;
        const token = `{${name}}`;
        if (!el) { onChange(value + token); return; }
        const start = el.selectionStart ?? value.length;
        const end = el.selectionEnd ?? value.length;
        onChange(value.slice(0, start) + token + value.slice(end));
        requestAnimationFrame(() => {
            el.focus();
            el.setSelectionRange(start + token.length, start + token.length);
        });
    };

    const showPreview = async () => {
        try {
            setPreview((await notificationAPI.previewTemplate(value)).data);
        } catch (err: any) {
            toast.error(getErrorMessage(err, 'Could not preview'));
        }
    };

    return (
        <div className="space-y-2">
            <textarea
                ref={ref}
                rows={3}
                className="w-full border rounded-lg px-3 py-2 text-sm"
                value={value}
                onChange={(e) => { onChange(e.target.value); setPreview(null); }}
            />
            <div className="flex flex-wrap items-center gap-1.5">
                <span className="text-xs text-muted-foreground mr-1">Insert:</span>
                {Object.entries(placeholders).map(([name, help]) => (
                    <button
                        key={name}
                        type="button"
                        title={help}
                        onClick={() => insert(name)}
                        className="rounded-full bg-chip px-2.5 py-0.5 font-mono text-[11.5px] text-muted-foreground hover:text-foreground"
                    >
                        {`{${name}}`}
                    </button>
                ))}
                <button type="button" onClick={showPreview} className="ml-auto inline-flex items-center gap-1 text-xs font-semibold text-primary">
                    <Eye className="h-3.5 w-3.5" /> Preview
                </button>
            </div>
            {preview && (
                <div className="rounded-lg bg-secondary px-3 py-2 text-sm">
                    <p className="text-foreground">{preview.preview}</p>
                    <p className="mt-1 text-xs text-muted-foreground">
                        {preview.length} characters · {preview.sms_parts} SMS{preview.sms_parts === 1 ? '' : ' parts'} (sample values)
                    </p>
                </div>
            )}
        </div>
    );
}

function SystemTemplateRow({ template }: { template: SystemTemplate }) {
    const queryClient = useQueryClient();
    const [open, setOpen] = useState(false);
    const [body, setBody] = useState(template.body);
    useEffect(() => setBody(template.body), [template.body]);

    const save = useMutation({
        mutationFn: () => notificationAPI.saveSystemTemplate(template.key, body),
        onSuccess: () => { toast.success(`${template.name} saved`); queryClient.invalidateQueries({ queryKey: TEMPLATES_KEY }); },
        onError: (err: any) => toast.error(getErrorMessage(err, 'Could not save')),
    });
    const reset = useMutation({
        mutationFn: () => notificationAPI.resetSystemTemplate(template.key),
        onSuccess: () => { toast.success('Back to the default wording'); queryClient.invalidateQueries({ queryKey: TEMPLATES_KEY }); },
    });

    return (
        <div className="border-t first:border-t-0 py-3">
            <button type="button" onClick={() => setOpen((v) => !v)} className="flex w-full items-center justify-between gap-3 text-left">
                <span>
                    <span className="block text-sm font-semibold text-foreground">{template.name}</span>
                    <span className="block truncate text-xs text-muted-foreground max-w-[520px]">{template.body}</span>
                </span>
                <span className="flex shrink-0 items-center gap-2">
                    {template.is_custom && <span className="rounded-full bg-ok-bg px-2 py-0.5 text-[11px] font-semibold text-ok">Customised</span>}
                    <ChevronDown className={`h-4 w-4 transition-transform ${open ? 'rotate-180' : ''}`} />
                </span>
            </button>
            {open && (
                <div className="mt-3 space-y-2">
                    <TemplateEditor value={body} onChange={setBody} placeholders={template.placeholders} />
                    <div className="flex gap-2">
                        <button
                            type="button"
                            disabled={save.isPending || !body.trim() || body === template.body}
                            onClick={() => save.mutate()}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium disabled:opacity-50"
                        >
                            <Save className="h-4 w-4" /> Save
                        </button>
                        {template.is_custom && (
                            <button
                                type="button"
                                onClick={() => window.confirm('Go back to the default wording?') && reset.mutate()}
                                className="inline-flex items-center gap-1.5 px-3 py-1.5 border rounded-lg text-sm font-medium"
                            >
                                <RotateCcw className="h-4 w-4" /> Reset to default
                            </button>
                        )}
                    </div>
                </div>
            )}
        </div>
    );
}

function PromoTemplateRow({ template, placeholders }: { template: PromoTemplate; placeholders: Record<string, string> }) {
    const queryClient = useQueryClient();
    const [open, setOpen] = useState(false);
    const [name, setName] = useState(template.name);
    const [body, setBody] = useState(template.body);

    const save = useMutation({
        mutationFn: () => notificationAPI.updatePromoTemplate(template.id, { name, body }),
        onSuccess: () => { toast.success('Template saved'); queryClient.invalidateQueries({ queryKey: TEMPLATES_KEY }); },
        onError: (err: any) => toast.error(getErrorMessage(err, 'Could not save')),
    });
    const remove = useMutation({
        mutationFn: () => notificationAPI.deletePromoTemplate(template.id),
        onSuccess: () => queryClient.invalidateQueries({ queryKey: TEMPLATES_KEY }),
    });

    return (
        <div className="border-t first:border-t-0 py-3">
            <button type="button" onClick={() => setOpen((v) => !v)} className="flex w-full items-center justify-between gap-3 text-left">
                <span>
                    <span className="block text-sm font-semibold text-foreground">{template.name}</span>
                    <span className="block truncate text-xs text-muted-foreground max-w-[520px]">{template.body}</span>
                </span>
                <ChevronDown className={`h-4 w-4 shrink-0 transition-transform ${open ? 'rotate-180' : ''}`} />
            </button>
            {open && (
                <div className="mt-3 space-y-2">
                    <input className="w-full border rounded-lg px-3 py-2 text-sm" value={name} onChange={(e) => setName(e.target.value)} />
                    <TemplateEditor value={body} onChange={setBody} placeholders={placeholders} />
                    <div className="flex gap-2">
                        <button type="button" disabled={save.isPending} onClick={() => save.mutate()}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium disabled:opacity-50">
                            <Save className="h-4 w-4" /> Save
                        </button>
                        <button type="button" onClick={() => window.confirm(`Delete "${template.name}"?`) && remove.mutate()}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 border rounded-lg text-sm font-medium text-red-600">
                            <Trash2 className="h-4 w-4" /> Delete
                        </button>
                    </div>
                </div>
            )}
        </div>
    );
}

/**
 * Settings -> Notifications -> Message templates: edit the wording of the
 * automatic messages, and keep promotional texts (e.g. a voucher offer)
 * that the broadcast form can start from.
 */
export default function MessageTemplatesSection() {
    const queryClient = useQueryClient();
    const { data, isLoading } = useMessageTemplates();
    const [newName, setNewName] = useState('');
    const [newBody, setNewBody] = useState('');
    const [adding, setAdding] = useState(false);

    const create = useMutation({
        mutationFn: () => notificationAPI.createPromoTemplate({ name: newName, body: newBody }),
        onSuccess: () => {
            toast.success('Template added');
            setNewName(''); setNewBody(''); setAdding(false);
            queryClient.invalidateQueries({ queryKey: TEMPLATES_KEY });
        },
        onError: (err: any) => toast.error(getErrorMessage(err, 'Could not add template')),
    });

    return (
        <div className={SECTION_CARD}>
            <h3 className="text-lg font-bold mb-1">Message templates</h3>
            <p className="text-sm text-muted-foreground mb-3">
                Change the wording of automatic messages. Words in {'{curly braces}'} are filled in for each customer;
                click one to insert it.
            </p>
            {isLoading ? <p className="text-sm text-muted-foreground">Loading…</p> : (
                <>
                    <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground mt-2">Automatic messages</p>
                    <div>{data?.system.map((t) => <SystemTemplateRow key={t.key} template={t} />)}</div>

                    <div className="mt-5 flex items-center justify-between">
                        <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">Promotional templates</p>
                        {!adding && (
                            <button type="button" onClick={() => setAdding(true)} className="inline-flex items-center gap-1 text-sm font-semibold text-primary">
                                <Plus className="h-4 w-4" /> New template
                            </button>
                        )}
                    </div>
                    {adding && (
                        <div className="mt-2 space-y-2 rounded-lg border p-3">
                            <input className="w-full border rounded-lg px-3 py-2 text-sm" placeholder="Template name, e.g. Weekend voucher offer"
                                value={newName} onChange={(e) => setNewName(e.target.value)} />
                            <TemplateEditor value={newBody} onChange={setNewBody} placeholders={data?.promo_placeholders || {}} />
                            <div className="flex gap-2">
                                <button type="button" disabled={!newName.trim() || !newBody.trim() || create.isPending} onClick={() => create.mutate()}
                                    className="px-3 py-1.5 bg-primary text-primary-foreground rounded-lg text-sm font-medium disabled:opacity-50">
                                    Add template
                                </button>
                                <button type="button" onClick={() => setAdding(false)} className="px-3 py-1.5 border rounded-lg text-sm font-medium">Cancel</button>
                            </div>
                        </div>
                    )}
                    {data?.promo.length ? (
                        <div>{data.promo.map((t) => <PromoTemplateRow key={t.id} template={t} placeholders={data.promo_placeholders} />)}</div>
                    ) : !adding && (
                        <p className="mt-2 text-sm text-muted-foreground">No promotional templates yet. Add one to reuse it in Promo Broadcast.</p>
                    )}
                </>
            )}
        </div>
    );
}
