import { clsx } from 'clsx'

interface SkeletonProps {
  className?: string
  width?: string | number
  height?: string | number
  rounded?: 'none' | 'sm' | 'md' | 'lg' | 'full'
}

export function Skeleton({ className, width, height, rounded = 'md' }: SkeletonProps) {
  const roundedClass = {
    none: '',
    sm: 'rounded-sm',
    md: 'rounded-md',
    lg: 'rounded-lg',
    full: 'rounded-full',
  }

  return (
    <div
      className={clsx(
        'animate-pulse bg-gray-200 dark:bg-gray-700',
        roundedClass[rounded],
        className
      )}
      style={{ width, height }}
    />
  )
}

// Pre-built skeleton components for common patterns
export function SkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div className={clsx('space-y-2', className)}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton
          key={i}
          height={16}
          className={i === lines - 1 ? 'w-3/4' : 'w-full'}
        />
      ))}
    </div>
  )
}

export function SkeletonCard({ className }: { className?: string }) {
  return (
    <div className={clsx('p-4 bg-white dark:bg-gray-800 rounded-xl shadow-sm', className)}>
      <div className="flex items-center gap-3 mb-4">
        <Skeleton width={40} height={40} rounded="full" />
        <div className="flex-1 space-y-2">
          <Skeleton height={16} className="w-1/3" />
          <Skeleton height={12} className="w-1/2" />
        </div>
      </div>
      <SkeletonText lines={2} />
    </div>
  )
}

export function SkeletonTable({ rows = 5, cols = 4 }: { rows?: number; cols?: number }) {
  return (
    <div className="bg-white dark:bg-gray-800 rounded-xl shadow-sm overflow-hidden">
      {/* Header */}
      <div className="border-b border-gray-200 dark:border-gray-700 p-4">
        <div className="flex gap-4">
          {Array.from({ length: cols }).map((_, i) => (
            <Skeleton key={i} height={16} className="flex-1" />
          ))}
        </div>
      </div>
      {/* Rows */}
      {Array.from({ length: rows }).map((_, rowIndex) => (
        <div
          key={rowIndex}
          className="border-b border-gray-100 dark:border-gray-700/50 p-4 last:border-0"
        >
          <div className="flex gap-4">
            {Array.from({ length: cols }).map((_, colIndex) => (
              <Skeleton key={colIndex} height={14} className="flex-1" />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

export function SkeletonStatCard() {
  return (
    <div className="p-6 bg-white dark:bg-gray-800 rounded-xl shadow-sm">
      <div className="flex items-start justify-between mb-4">
        <Skeleton width={40} height={40} rounded="lg" />
        <Skeleton width={60} height={20} rounded="full" />
      </div>
      <Skeleton height={32} className="w-1/2 mb-2" />
      <Skeleton height={14} className="w-3/4" />
    </div>
  )
}

export function SkeletonChart({ height = 300 }: { height?: number }) {
  return (
    <div className="p-4 bg-white dark:bg-gray-800 rounded-xl shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <Skeleton height={20} className="w-1/4" />
        <div className="flex gap-2">
          <Skeleton width={60} height={28} rounded="md" />
          <Skeleton width={60} height={28} rounded="md" />
        </div>
      </div>
      <Skeleton height={height} rounded="lg" />
    </div>
  )
}

export function SkeletonWorkerCard() {
  return (
    <div className="p-4 bg-white dark:bg-gray-800 rounded-xl shadow-sm">
      <div className="flex items-center gap-3 mb-4">
        <Skeleton width={48} height={48} rounded="lg" />
        <div className="flex-1 space-y-2">
          <Skeleton height={18} className="w-1/3" />
          <Skeleton height={14} className="w-1/2" />
        </div>
        <Skeleton width={80} height={28} rounded="full" />
      </div>
      <div className="space-y-3">
        <div className="flex justify-between">
          <Skeleton height={12} className="w-1/4" />
          <Skeleton height={12} className="w-1/4" />
        </div>
        <Skeleton height={8} rounded="full" />
        <div className="flex justify-between">
          <Skeleton height={12} className="w-1/4" />
          <Skeleton height={12} className="w-1/4" />
        </div>
        <Skeleton height={8} rounded="full" />
      </div>
    </div>
  )
}

export function SkeletonJobRow() {
  return (
    <div className="p-4 bg-white dark:bg-gray-800 rounded-lg border border-gray-200 dark:border-gray-700">
      <div className="flex items-center gap-4">
        <Skeleton width={36} height={36} rounded="lg" />
        <div className="flex-1 space-y-2">
          <Skeleton height={16} className="w-1/3" />
          <Skeleton height={12} className="w-1/2" />
        </div>
        <Skeleton width={80} height={24} rounded="full" />
        <Skeleton width={32} height={32} rounded="md" />
      </div>
    </div>
  )
}

// Loading wrapper component
interface LoadingStateProps {
  isLoading: boolean
  skeleton: React.ReactNode
  children: React.ReactNode
}

export function LoadingState({ isLoading, skeleton, children }: LoadingStateProps) {
  if (isLoading) {
    return <>{skeleton}</>
  }
  return <>{children}</>
}

export default Skeleton
