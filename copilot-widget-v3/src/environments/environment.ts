// This file can be replaced during build by using the `fileReplacements` array.
// `ng build` replaces `environment.ts` with `environment.prod.ts`.
// The list of file replacements can be found in `angular.json`.

export const environment = {
  production: false,
  copilotApiBaseUrl: 'http://localhost:8001',
  v3AskEnabled: true,
  reportSuggestionsEnabled: true,
  /** When false, /showcase/* routes redirect to dashboard; V3 and insights unchanged. */
  showcaseEnabled: true,
  /**
   * ERP page origin(s) that may embed the widget iframe (Path B). Must match the browser
   * address bar of the parent window exactly (scheme + host + port). Not the iframe/CloudFront URL.
   */
  parentOriginsAllowlist: [
    'http://localhost:4200',
    'http://127.0.0.1:4200',
    'http://localhost:4300',
    'http://127.0.0.1:4300'
  ] as string[]
};

/*
 * For easier debugging in development mode, you can import the following file
 * to ignore zone related error stack frames such as `zone.run`, `zoneDelegate.invokeTask`.
 *
 * This import should be commented out in production mode because it will have a negative impact
 * on performance if an error is thrown.
 */
// import 'zone.js/plugins/zone-error';  // Included with Angular CLI.
