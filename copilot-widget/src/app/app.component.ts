import { Component } from '@angular/core';
import { CopilotApiService, ChatResponse } from './copilot-api.service';

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss']
})
export class AppComponent {
  idcompany = 1;
  question = 'Show sales count and revenue for last 30 days';
  debug = true;

  loading = false;
  error: any = null;
  response: ChatResponse | null = null;

  constructor(private api: CopilotApiService) {}

  run(): void {
    this.loading = true;
    this.error = null;
    this.response = null;

    this.api
      .chat({
        idcompany: Number(this.idcompany),
        question: this.question,
        debug: this.debug,
      })
      .subscribe({
        next: (res) => {
          this.response = res;
          this.loading = false;
        },
        error: (err) => {
          this.error = err;
          this.loading = false;
        },
      });
  }
}
