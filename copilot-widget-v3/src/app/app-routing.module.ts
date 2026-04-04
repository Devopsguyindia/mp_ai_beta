import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';
import { LoginComponent } from './login.component';
import { DashboardComponent } from './dashboard.component';
import { ModuleInsightsPanelComponent } from './module-insights-panel.component';
import { AuthGuard } from './auth.guard';

const routes: Routes = [
  { path: '', redirectTo: '/login', pathMatch: 'full' },
  { path: 'login', component: LoginComponent },
  { path: 'dashboard', component: DashboardComponent, canActivate: [AuthGuard] },
  {
    path: 'module-insights/:erpModule',
    component: ModuleInsightsPanelComponent,
    canActivate: [AuthGuard]
  },
  { path: '**', redirectTo: '/login' }
];

@NgModule({
  imports: [
    RouterModule.forRoot(routes, {
      // Hash URLs (e.g. /#/login) so S3/CloudFront refresh always serves index.html.
      useHash: true,
    }),
  ],
  exports: [RouterModule],
})
export class AppRoutingModule { }
