import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { ChevronRight, Home as HomeIcon } from 'lucide-react';
import { cn } from '@/lib/utils';
import useBreadcrumbStore from '@/stores/breadcrumb-store';

interface BreadcrumbsProps extends React.HTMLAttributes<HTMLElement> {}

export function Breadcrumbs({ className, ...props }: BreadcrumbsProps) {
  const { staticSegments, dynamicTitle } = useBreadcrumbStore();
  const location = useLocation();

  // Hide breadcrumbs entirely when on home page
  if (location.pathname === '/') {
    return null;
  }

  return (
    <div className={cn('flex items-center justify-between mb-4', className)}>
      <nav
        aria-label="breadcrumb"
        className="text-sm text-muted-foreground"
        {...props}
      >
        <ol className="list-none p-0 inline-flex items-center space-x-1">
        {/* Home Icon Link */}
        <li>
          <Link to="/" className="flex items-center hover:text-primary">
            <HomeIcon className="h-4 w-4 mr-1.5" />
          </Link>
        </li>

        {/* Static Segments */}
        {staticSegments.map((segment, index) => (
          <React.Fragment key={segment.path || index}>
            <li className="flex items-center">
              <ChevronRight className="h-4 w-4" />
            </li>
            <li className={cn(segment.path ? "hover:text-primary" : "font-medium text-foreground")}>
              {segment.path ? (
                <Link to={segment.path}>{segment.label}</Link>
              ) : (
                <span>{segment.label}</span>
              )}
            </li>
          </React.Fragment>
        ))}

        {/* Dynamic Title (Last Segment) - only if static segments exist AND dynamic title is present OR if no static segments but dynamic title is present */}
        {(staticSegments.length > 0 && dynamicTitle) || (staticSegments.length === 0 && dynamicTitle) ? (
          <>
            <li className="flex items-center">
              <ChevronRight className="h-4 w-4" />
            </li>
            <li className="font-medium text-foreground">
              <span>{dynamicTitle}</span>
            </li>
          </>
        ) : null}
      </ol>
    </nav>
    </div>
  );
} 