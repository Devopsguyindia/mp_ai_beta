import { NgModule } from '@angular/core';
import { BrowserModule } from '@angular/platform-browser';
import { FormsModule } from '@angular/forms';
import { HttpClientModule } from '@angular/common/http';

import { AppRoutingModule } from './app-routing.module';
import { AppComponent } from './app.component';
import { LoginComponent } from './login.component';
import { DashboardComponent } from './dashboard.component';
import { ModuleInsightsPanelComponent } from './module-insights-panel.component';
import { ShowcasePanelComponent } from './showcase/showcase-panel.component';
import { ReportFilterSummaryPipe } from './report-filter-summary.pipe';

@NgModule({
  declarations: [
    AppComponent,
    LoginComponent,
    DashboardComponent,
    ModuleInsightsPanelComponent,
    ShowcasePanelComponent,
    ReportFilterSummaryPipe
  ],
  imports: [
    BrowserModule,
    FormsModule,
    HttpClientModule,
    AppRoutingModule
  ],
  providers: [],
  bootstrap: [AppComponent]
})
export class AppModule { }
