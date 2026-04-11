import { Injectable } from '@angular/core';
import { CanActivate, Router, UrlTree } from '@angular/router';
import { environment } from '../../environments/environment';

/**
 * When showcase is disabled in environment, users are sent to the dashboard.
 * V3 and module-insights routes are unchanged.
 */
@Injectable({ providedIn: 'root' })
export class ShowcaseFeatureGuard implements CanActivate {
  constructor(private router: Router) {}

  canActivate(): boolean | UrlTree {
    if (environment.showcaseEnabled) {
      return true;
    }
    return this.router.parseUrl('/dashboard');
  }
}
