// SPA is served over HTTPS (CloudFront). The API URL must use https:// as well — browsers
// block http:// calls from https:// pages (mixed content), before CORS even runs.
// After TLS on the API (Nginx + Let's Encrypt or ALB + ACM), set this to that https URL.
export const environment = {
  production: true,
  copilotApiBaseUrl: 'https://copilot-api.mpstest.net',
  v3AskEnabled: true,
  reportSuggestionsEnabled: true,
  /**
   * ERP SPA origin(s) that embed the iframe — must match `event.origin` from the parent page
   * (not the CloudFront widget URL). Add/remove hosts to match your deployment.
   */
  parentOriginsAllowlist: [
    'https://app.masterpiecemanager.com',
    'https://mpstest.masterpiecemanager.com',
    'http://localhost:4300',
    'http://localhost:4200',
    'http://127.0.0.1:4200',
    'http://127.0.0.1:4300',
    'http://127.0.0.1',
    'http://localhost',
  ] as string[]
};
