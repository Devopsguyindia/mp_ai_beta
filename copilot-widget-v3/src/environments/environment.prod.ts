// SPA is served over HTTPS (CloudFront). The API URL must use https:// as well — browsers
// block http:// calls from https:// pages (mixed content), before CORS even runs.
// After TLS on the API (Nginx + Let's Encrypt or ALB + ACM), set this to that https URL.
export const environment = {
  production: true,
  copilotApiBaseUrl: 'https://copilot-api.mpstest.net:8001',
  v3AskEnabled: true,
  reportSuggestionsEnabled: true
};
