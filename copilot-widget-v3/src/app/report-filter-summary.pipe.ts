import { Pipe, PipeTransform } from '@angular/core';
import { summarizeReportFilters } from './report-filter-display';

@Pipe({ name: 'reportFilterSummary', pure: true })
export class ReportFilterSummaryPipe implements PipeTransform {
  transform(value: string | null | undefined): { label: string; value: string }[] {
    return summarizeReportFilters(value);
  }
}
