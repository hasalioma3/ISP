import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import toast from 'react-hot-toast';
import { Gift, Sparkles } from 'lucide-react';
import { loyaltyAPI } from '../services/api';
import { errText } from '../utils/errText';
import { Panel, PanelHeader } from './savanna';

/** The customer's points balance with a redeem button (customer dashboard). Hidden when the programme doesn't apply to them. */
export default function LoyaltyCard() {
    const qc = useQueryClient();
    const [points, setPoints] = useState('');
    const { data } = useQuery({ queryKey: ['my-loyalty'], queryFn: async () => (await loyaltyAPI.mine()).data });
    const redeem = useMutation({
        mutationFn: (n: number) => loyaltyAPI.redeemMine(n),
        onSuccess: (r) => {
            toast.success(`Done! KES ${r.data.entry.kes_value} added to your account balance.`);
            setPoints('');
            qc.invalidateQueries({ queryKey: ['my-loyalty'] });
            qc.invalidateQueries({ queryKey: ['profile'] });
        },
        onError: (e) => toast.error(errText(e)),
    });
    if (!data?.enabled) return null;
    const n = Number(points);
    const canRedeem = data.can_self_redeem && data.points >= data.min_redeem_points;

    return (
        <Panel>
            <PanelHeader
                leading={<span className="grid h-9 w-9 place-items-center rounded-full bg-sunset/15 text-sunset"><Gift className="h-4 w-4" /></span>}
                title="Loyalty points"
                subtitle={`Earn 1 point for every KES ${Number(data.kes_per_point).toLocaleString()} you pay`}
            />
            <div className="flex items-end justify-between gap-3">
                <div>
                    <p className="num text-[32px] font-extrabold leading-none">{data.points.toLocaleString()}</p>
                    <p className="mt-1 text-[13px] text-muted-foreground">worth KES {Number(data.value_kes).toLocaleString()}</p>
                </div>
            </div>
            {data.can_self_redeem && (
                canRedeem ? (
                    <div className="mt-4 flex gap-2">
                        <input type="number" min={data.min_redeem_points} max={data.points} placeholder={`${data.min_redeem_points}–${data.points}`}
                            className="h-10 w-full rounded-full border border-input bg-card px-4 text-[14px]" value={points} onChange={(e) => setPoints(e.target.value)} />
                        <button disabled={redeem.isPending || !(n >= data.min_redeem_points && n <= data.points)} onClick={() => redeem.mutate(n)}
                            className="inline-flex h-10 shrink-0 items-center gap-1.5 rounded-full bg-sunset px-4 text-[14px] font-semibold text-white disabled:opacity-50">
                            <Sparkles className="h-4 w-4" /> Redeem
                        </button>
                    </div>
                ) : (
                    <p className="mt-3 text-[12.5px] text-muted-foreground">You can redeem from {data.min_redeem_points} points. Redeemed points go to your account balance for your next renewal.</p>
                )
            )}
            {data.entries?.length > 0 && (
                <ul className="mt-4 space-y-1 border-t border-border-soft pt-3 text-[12.5px]">
                    {data.entries.slice(0, 3).map((e: any) => (
                        <li key={e.id} className="flex justify-between gap-2">
                            <span className="truncate text-muted-foreground">{e.description}</span>
                            <span className={e.points < 0 ? 'text-bad' : 'text-ok'}>{e.points > 0 ? '+' : ''}{e.points}</span>
                        </li>
                    ))}
                </ul>
            )}
        </Panel>
    );
}
