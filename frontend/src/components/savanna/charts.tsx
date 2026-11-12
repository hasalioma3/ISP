import { useId } from 'react';
import {
    Area,
    AreaChart,
    Bar,
    BarChart,
    CartesianGrid,
    Cell,
    Pie,
    PieChart,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from 'recharts';

// Recharts wrappers styled with the Savanna tokens (admin and self-care only;
// the captive portal must not pull Recharts in). Colours are CSS variables
// so dark mode follows automatically. No vertical gridlines, no axis lines,
// and the latest point/bar is highlighted.

const AXIS_TICK = { fontSize: 12, fill: 'var(--sv-faint)' };

const tooltipStyle = {
    contentStyle: {
        background: 'var(--sv-surface)',
        border: '1px solid var(--sv-border)',
        borderRadius: 12,
        boxShadow: 'var(--sv-shadow)',
        fontSize: 12.5,
        color: 'var(--sv-text)',
    },
    labelStyle: { color: 'var(--sv-muted)', marginBottom: 2 },
    cursor: { stroke: 'var(--sv-border-strong)', strokeWidth: 1 },
};

interface SeriesProps<T> {
    data: T[];
    xKey: keyof T & string;
    yKey: keyof T & string;
    height?: number;
    formatX?: (value: any) => string;
    formatY?: (value: number) => string;
    formatTooltip?: (value: number) => string;
    name?: string;
}

export function AreaTrend<T extends Record<string, any>>({
    data, xKey, yKey, height = 300, formatX, formatY, formatTooltip, name,
}: SeriesProps<T>) {
    const gradientId = useId().replace(/:/g, '');
    const last = data.length - 1;
    return (
        <ResponsiveContainer width="100%" height={height}>
            <AreaChart data={data} margin={{ top: 12, right: 8, left: 0, bottom: 0 }}>
                <defs>
                    <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="var(--sv-ok)" stopOpacity={0.28} />
                        <stop offset="100%" stopColor="var(--sv-ok)" stopOpacity={0.02} />
                    </linearGradient>
                </defs>
                <CartesianGrid vertical={false} strokeDasharray="4 6" stroke="var(--sv-border)" />
                <XAxis dataKey={xKey} tick={AXIS_TICK} tickLine={false} axisLine={false} tickFormatter={formatX} minTickGap={40} />
                <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} tickFormatter={formatY} width={48} />
                <Tooltip
                    {...tooltipStyle}
                    labelFormatter={(l) => (formatX ? formatX(l) : String(l))}
                    formatter={(v) => [formatTooltip ? formatTooltip(Number(v)) : String(v), name ?? yKey]}
                />
                <Area
                    type="monotone"
                    dataKey={yKey}
                    name={name}
                    stroke="var(--sv-primary)"
                    strokeWidth={2.5}
                    fill={`url(#${gradientId})`}
                    dot={(props: any) =>
                        props.index === last ? (
                            <circle key="last" cx={props.cx} cy={props.cy} r={5} fill="var(--sv-primary)" stroke="var(--sv-surface)" strokeWidth={3} />
                        ) : <g key={props.index} />
                    }
                    activeDot={{ r: 5, fill: 'var(--sv-primary)', stroke: 'var(--sv-surface)', strokeWidth: 3 }}
                    isAnimationActive={false}
                />
            </AreaChart>
        </ResponsiveContainer>
    );
}

export function BarTrend<T extends Record<string, any>>({
    data, xKey, yKey, height = 240, formatX, formatY, formatTooltip, name, onBarClick, selected, showYAxis,
}: SeriesProps<T> & {
    /** Makes bars clickable (drill-down); receives the clicked row. */
    onBarClick?: (row: T) => void;
    /** xKey value of the bar to highlight instead of the latest one. */
    selected?: string | null;
    showYAxis?: boolean;
}) {
    const last = data.length - 1;
    const highlight = (row: T, i: number) => (selected != null ? row[xKey] === selected : i === last);
    return (
        <ResponsiveContainer width="100%" height={height}>
            <BarChart data={data} margin={{ top: 8, right: 0, left: 0, bottom: 0 }}>
                {showYAxis && <CartesianGrid vertical={false} strokeDasharray="4 6" stroke="var(--sv-border)" />}
                <XAxis dataKey={xKey} tick={AXIS_TICK} tickLine={false} axisLine={false} tickFormatter={formatX} interval={data.length > 16 ? 'preserveStartEnd' : 0} minTickGap={12} />
                <YAxis hide={!showYAxis} tick={AXIS_TICK} tickLine={false} axisLine={false} tickFormatter={formatY} width={48} />
                <Tooltip
                    {...tooltipStyle}
                    cursor={{ fill: 'var(--sv-chip)' }}
                    labelFormatter={(l) => (formatX ? formatX(l) : String(l))}
                    formatter={(v) => [formatTooltip ? formatTooltip(Number(v)) : String(v), name ?? yKey]}
                />
                <Bar
                    dataKey={yKey}
                    name={name}
                    radius={[6, 6, 0, 0]}
                    isAnimationActive={false}
                    cursor={onBarClick ? 'pointer' : undefined}
                    onClick={onBarClick ? (entry: any) => onBarClick((entry?.payload ?? entry) as T) : undefined}
                >
                    {data.map((row, i) => (
                        <Cell key={i} fill={highlight(row, i) ? 'var(--sv-accent)' : 'var(--sv-chart-fill)'} />
                    ))}
                </Bar>
            </BarChart>
        </ResponsiveContainer>
    );
}

/** Forest, leaf, sunset, gold, then muted tones for the long tail. */
export const DONUT_COLORS = ['#0B4D33', '#3BB54A', '#F2772E', '#F4C542', '#8FB9A0', '#C9B99A', '#5E6B62'];

export interface DonutSlice {
    name: string;
    value: number;
    [key: string]: unknown;  // Recharts' ChartDataInput shape
}

export function Donut({ data, centerValue, centerLabel, size = 236 }: {
    data: DonutSlice[];
    centerValue: React.ReactNode;
    centerLabel: string;
    size?: number;
}) {
    const hasData = data.some((d) => d.value > 0);
    return (
        <div className="relative mx-auto" style={{ width: size, height: size }}>
            <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                    <Pie
                        data={hasData ? data : [{ name: 'none', value: 1 }]}
                        dataKey="value"
                        innerRadius="68%"
                        outerRadius="100%"
                        startAngle={90}
                        endAngle={-270}
                        paddingAngle={hasData ? 1 : 0}
                        stroke="var(--sv-surface)"
                        strokeWidth={3}
                        isAnimationActive={false}
                    >
                        {hasData
                            ? data.map((_, i) => <Cell key={i} fill={DONUT_COLORS[i % DONUT_COLORS.length]} />)
                            : <Cell fill="var(--sv-chip)" />}
                    </Pie>
                </PieChart>
            </ResponsiveContainer>
            <div className="pointer-events-none absolute inset-0 grid place-items-center text-center">
                <div>
                    <p className="num text-[30px] font-extrabold leading-none text-foreground">{centerValue}</p>
                    <p className="mt-1 text-[13px] text-muted-foreground">{centerLabel}</p>
                </div>
            </div>
        </div>
    );
}
