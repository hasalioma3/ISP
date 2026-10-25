import type { LucideIcon } from "lucide-react"

import { cn } from "@/lib/utils"
import { Card } from "@/components/ui/card"

interface StatCardProps {
  label: string
  value: React.ReactNode
  icon?: LucideIcon
  trend?: { value: string; positive: boolean }
  className?: string
}

export function StatCard({ label, value, icon: Icon, trend, className }: StatCardProps) {
  return (
    <Card className={cn("p-4", className)}>
      <div className="flex items-center justify-between mb-2">
        <p className="text-xs font-medium text-muted-foreground uppercase tracking-wide truncate">{label}</p>
        {Icon && <Icon className="h-4 w-4 text-primary shrink-0" />}
      </div>
      <p className="text-2xl font-bold text-foreground">{value}</p>
      {trend && (
        <p className={cn("text-xs font-semibold mt-1", trend.positive ? "text-green-600" : "text-red-600")}>
          {trend.positive ? "↑" : "↓"} {trend.value}
        </p>
      )}
    </Card>
  )
}
